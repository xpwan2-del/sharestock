from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from loguru import logger

from trading.signal_generator import SignalGenerator
from utils.event_bus import Event, get_event_bus
from utils.redis_manager import get_redis_manager


class MLFeedbackLoop:
    def __init__(self, confidence_threshold: float = 0.6):
        self.confidence_threshold = confidence_threshold
        self.event_bus = get_event_bus()
        self.redis = get_redis_manager()
        self.signal_generator = SignalGenerator()
        self.event_bus.subscribe("MODEL_PREDICTION_READY", self.on_prediction_ready)
        self.event_bus.subscribe("MODEL_BATCH_PREDICTION_READY", self.on_batch_prediction_ready)

    def on_prediction_ready(self, event: Event):
        payload = event.payload or {}
        code = payload.get("code") or payload.get("stock_code")
        if not code:
            return
        up_probability = float(payload.get("up_probability", 0) or 0)
        prediction = payload.get("prediction", "neutral")
        if prediction != "bullish" or up_probability < self.confidence_threshold:
            return
        signal = self._build_compound_signal(code, up_probability, payload)
        self._publish_compound_signal(signal)

    def on_batch_prediction_ready(self, event: Event):
        codes = event.payload.get("codes", []) if event.payload else []
        logger.info(f"模型批量预测完成，进入复合信号候选池: {len(codes)} 只")

    def _build_compound_signal(self, code: str, up_probability: float, payload: Dict[str, Any]) -> Dict[str, Any]:
        confidence = min(1.0, up_probability * 0.72 + 0.18)
        signal = {
            "code": code,
            "signal_type": "ml_compound_buy",
            "confidence": round(float(confidence), 4),
            "ml_up_probability": round(float(up_probability), 4),
            "source_prediction": payload.get("prediction", "bullish"),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reason": "模型上涨概率达到阈值，进入复合信号池",
        }
        return signal

    def _publish_compound_signal(self, signal: Dict[str, Any]):
        self.event_bus.publish("COMPOUND_SIGNAL_GENERATED", signal, source="MLFeedbackLoop")
        if getattr(self.redis, "client", None):
            self.redis.hset_dict(f"quant:signal:compound:{signal['code']}", signal, ex=86400)
        logger.info(f"复合信号生成: {signal['code']} confidence={signal['confidence']}")


def start_ml_feedback_loop(confidence_threshold: float = 0.6) -> MLFeedbackLoop:
    return MLFeedbackLoop(confidence_threshold=confidence_threshold)
