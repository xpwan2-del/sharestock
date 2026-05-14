import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import List, Dict, Optional, Callable, Set
from dataclasses import dataclass, field
from loguru import logger

from config.settings import REALTIME_CONFIG, MARKET_CONFIG, DATA_DIR
from utils.event_bus import get_event_bus
from utils.redis_manager import get_redis_manager

TRADING_DIR = DATA_DIR / "trading"
TRADING_DIR.mkdir(exist_ok=True)


@dataclass
class PriceAlert:
    code: str
    name: str
    alert_type: str
    message: str
    price: float
    pct_chg: float
    timestamp: str


class RealtimeMonitor:
    def __init__(
        self,
        watch_list: Optional[List[str]] = None,
        on_alert: Optional[Callable[[PriceAlert], None]] = None,
    ):
        self.watch_list: Set[str] = set(watch_list or REALTIME_CONFIG["watch_list"])
        self.on_alert = on_alert or self._default_alert_handler
        self.redis = get_redis_manager()
        self.event_bus = get_event_bus()
        self.scan_interval = REALTIME_CONFIG["scan_interval_seconds"]
        self.alert_pct = REALTIME_CONFIG["alert_threshold_pct"]
        self.volume_alert_ratio = REALTIME_CONFIG["volume_alert_ratio"]
        self._running = False
        self._previous_data: Dict[str, Dict] = {}
        self._alerts: List[PriceAlert] = []
        self.event_bus.subscribe("ALERT_TRIGGERED", self._on_alert_event)
        self.event_bus.subscribe("MARKET_TICK", self._on_market_tick)
        self.event_bus.subscribe("COMPOUND_SIGNAL_GENERATED", self._on_compound_signal)

    def _on_compound_signal(self, event):
        payload = event.payload or {}
        alert = PriceAlert(
            code=str(payload.get("code", "")),
            name=str(payload.get("name", "ML复合信号")),
            alert_type=str(payload.get("signal_type", "ml_compound_buy")),
            message=f"复合信号触发 置信度={payload.get('confidence', 'N/A')}",
            price=float(payload.get("price", 0) or 0),
            pct_chg=float(payload.get("pct_chg", 0) or 0),
            timestamp=datetime.now().strftime("%H:%M:%S"),
        )
        self._alerts.append(alert)
        self.on_alert(alert)
        if getattr(self.redis, "client", None):
            self.redis.publish("quant:events", event.to_dict())
        logger.info(f"复合信号事件: {payload.get('code', '')} {payload.get('confidence', '')}")

    def _on_alert_event(self, event):
        payload = event.payload or {}
        self.redis.publish("quant:events", event.to_dict())
        logger.info(f"事件通知[{event.topic}]: {payload.get('code', '')} {payload.get('message', '')}")

    def _on_market_tick(self, event):
        payload = event.payload or {}
        quotes = payload.get("quotes")
        if isinstance(quotes, pd.DataFrame) and not quotes.empty:
            self._check_alerts(quotes)

    def _store_snapshot(self, quotes: pd.DataFrame):
        if quotes is None or quotes.empty or not getattr(self.redis, "client", None):
            return
        if "code" not in quotes.columns:
            return
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        for _, row in quotes.iterrows():
            code = str(row.get("code", ""))
            if not code:
                continue
            payload = row.to_dict()
            payload["updated_at"] = ts
            self.redis.hset_dict(f"quant:snapshot:{code}", payload, ex=self.scan_interval * 4)

    def _publish_alert(self, alert: PriceAlert):
        self.event_bus.publish("ALERT_TRIGGERED", {
            "code": alert.code,
            "name": alert.name,
            "alert_type": alert.alert_type,
            "message": alert.message,
            "price": alert.price,
            "pct_chg": alert.pct_chg,
            "timestamp": alert.timestamp,
        }, source="RealtimeMonitor")

    def _default_alert_handler(self, alert: PriceAlert):
        logger.info(
            f"[{alert.alert_type.upper()}] {alert.code} {alert.name} "
            f"价格:{alert.price:.2f} 涨跌:{alert.pct_chg:+.2f}% - {alert.message}"
        )

    def add_watch(self, codes: List[str]):
        for code in codes:
            self.watch_list.add(code)
            logger.info(f"添加监控: {code}")
        logger.info(f"当前监控 {len(self.watch_list)} 只")

    def remove_watch(self, codes: List[str]):
        for code in codes:
            self.watch_list.discard(code)

    def set_hot_watch_from_leaders(self, concept_names: Optional[List[str]] = None):
        from analysis.leader_finder import LeaderFinder
        finder = LeaderFinder()
        if concept_names is None:
            concept_names = finder.scan_hot_concepts(top_n=5)
        for concept in concept_names:
            leaders = finder.identify_all_leaders(concept)
            for leader_type in ["logic_leaders", "sentiment_leaders", "capacity_leaders"]:
                df = leaders.get(leader_type, pd.DataFrame())
                if not df.empty:
                    codes = df["code"].tolist() if "code" in df.columns else (
                        df["代码"].tolist() if "代码" in df.columns else []
                    )
                    self.add_watch(codes)
                    logger.info(f"从 [{concept}] {leader_type} 添加 {len(codes)} 只监控")

    def _check_alerts(self, quotes: pd.DataFrame):
        for _, row in quotes.iterrows():
            code = row["code"]
            name = row.get("name", "")
            pct = row.get("pct_chg", 0)
            price = row.get("price", 0)
            vol_ratio = row.get("volume_ratio", 1)
            if abs(pct) >= self.alert_pct:
                alert_type = "surge" if pct > 0 else "plunge"
                alert = PriceAlert(
                    code=code, name=name, alert_type=alert_type,
                    message=f"{'大涨' if pct > 0 else '大跌'} {pct:+.2f}%",
                    price=price, pct_chg=pct,
                    timestamp=datetime.now().strftime("%H:%M:%S"),
                )
                self._alerts.append(alert)
                self.on_alert(alert)
                self._publish_alert(alert)
            if vol_ratio >= self.volume_alert_ratio and abs(pct) > 0:
                alert = PriceAlert(
                    code=code, name=name, alert_type="volume_breakout",
                    message=f"放量 x{vol_ratio:.1f}",
                    price=price, pct_chg=pct,
                    timestamp=datetime.now().strftime("%H:%M:%S"),
                )
                self._alerts.append(alert)
                self.on_alert(alert)
                self._publish_alert(alert)
            prev_data = self._previous_data.get(code, {})
            prev_pct = prev_data.get("pct_chg", 0)
            if abs(prev_pct) < 5 and abs(pct) >= 5:
                alert = PriceAlert(
                    code=code, name=name, alert_type="breakout",
                    message=f"突破 5% 阈值 ({pct:+.2f}%)",
                    price=price, pct_chg=pct,
                    timestamp=datetime.now().strftime("%H:%M:%S"),
                )
                self._alerts.append(alert)
                self.on_alert(alert)
                self._publish_alert(alert)
            self._previous_data[code] = {"pct_chg": pct, "price": price, "volume_ratio": vol_ratio}

    def scan_once(self) -> Optional[pd.DataFrame]:
        logger.info("实时监控已切换为事件驱动模式，scan_once 仅等待 MARKET_TICK 事件")
        return None

    async def _scan_loop(self):
        logger.info(f"启动事件驱动实时监控! 监控 {len(self.watch_list)} 只, 间隔 {self.scan_interval}s")
        self._running = True
        try:
            while self._running:
                await asyncio.sleep(self.scan_interval)
        except asyncio.CancelledError:
            logger.info("监控任务被取消")
        finally:
            self._running = False

    def start_background(self):
        import threading
        def run_loop():
            asyncio.run(self._scan_loop())
        logger.info("启动后台实时监控线程")
        thread = threading.Thread(target=run_loop, daemon=True, name="RealtimeMonitor")
        thread.start()
        return thread

    def stop(self):
        self._running = False
        logger.info("停止实时监控")

    def get_alerts(self, limit: int = 50) -> List[Dict]:
        return [
            {
                "code": a.code, "name": a.name,
                "type": a.alert_type, "message": a.message,
                "pct_chg": a.pct_chg, "price": a.price,
                "time": a.timestamp,
            }
            for a in self._alerts[-limit:]
        ]

    def get_market_snapshot(self) -> Dict:
        rows = []
        if getattr(self.redis, "client", None):
            for code in self.watch_list:
                row = self.redis.hgetall_dict(f"quant:snapshot:{code}")
                if row:
                    rows.append(row)
        if not rows:
            return {}
        quotes = pd.DataFrame(rows)
        if "pct_chg" not in quotes.columns:
            return {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "total": len(quotes)}
        quotes["pct_chg"] = pd.to_numeric(quotes["pct_chg"], errors="coerce").fillna(0)
        if "volume_ratio" in quotes.columns:
            quotes["volume_ratio"] = pd.to_numeric(quotes["volume_ratio"], errors="coerce").fillna(1)
        else:
            quotes["volume_ratio"] = 1
        up_count = (quotes["pct_chg"] > 0).sum()
        down_count = (quotes["pct_chg"] < 0).sum()
        avg_pct = quotes["pct_chg"].mean()
        turnover_active = (quotes["volume_ratio"] > 1.5).sum()
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total": len(quotes),
            "up": int(up_count),
            "down": int(down_count),
            "up_ratio": round(float(up_count) / len(quotes) * 100, 1),
            "avg_pct_chg": round(float(avg_pct), 2),
            "turnover_active": int(turnover_active),
        }