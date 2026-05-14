import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from loguru import logger

from config.settings import TREND_REVERSAL_CONFIG, DATA_DIR
from data.market_data import MarketDataCollector

ANALYSIS_DIR = DATA_DIR / "analysis"
ANALYSIS_DIR.mkdir(exist_ok=True)


class TrendReversalDetector:
    def __init__(self):
        self.market = MarketDataCollector()
        self.config = TREND_REVERSAL_CONFIG

    def detect_macd_divergence(self, kline: pd.DataFrame) -> Dict:
        if kline.empty or "macd" not in kline.columns:
            return {"type": "none", "strength": 0}
        lookback = self.config["macd_divergence_lookback"]
        recent = kline.tail(lookback)
        if len(recent) < 20:
            return {"type": "none", "strength": 0}
        price_low = recent["close"].nsmallest(3)
        macd_at_low = recent.loc[price_low.index, "macd"]
        price_high = recent["close"].nlargest(3)
        macd_at_high = recent.loc[price_high.index, "macd"]
        result = {"type": "none", "strength": 0}
        if len(price_low) >= 2 and len(macd_at_low) >= 2:
            if price_low.iloc[0] < price_low.iloc[1] and macd_at_low.iloc[0] > macd_at_low.iloc[1]:
                result["type"] = "bullish_divergence"
                result["strength"] = min(100, abs(macd_at_low.iloc[0] - macd_at_low.iloc[1]) / abs(macd_at_low.iloc[1]) * 50 + 50)
        if len(price_high) >= 2 and len(macd_at_high) >= 2:
            if price_high.iloc[0] > price_high.iloc[1] and macd_at_high.iloc[0] < macd_at_high.iloc[1]:
                result["type"] = "bearish_divergence"
                result["strength"] = min(100, abs(macd_at_high.iloc[0] - macd_at_high.iloc[1]) / abs(macd_at_high.iloc[1]) * 50 + 50)
        return result

    def detect_volume_breakout(self, kline: pd.DataFrame) -> Dict:
        if kline.empty or "volume" not in kline.columns:
            return {"breakout": False, "ratio": 1.0}
        recent_vol = kline["volume"].iloc[-5:]
        baseline_vol = kline["volume"].iloc[-25:-5].mean()
        if baseline_vol == 0:
            return {"breakout": False, "ratio": 1.0}
        vol_ratio = recent_vol.mean() / baseline_vol
        return {
            "breakout": vol_ratio > self.config["volume_breakout_ratio"],
            "ratio": round(float(vol_ratio), 2),
            "today_ratio": round(float(kline["volume"].iloc[-1] / baseline_vol), 2),
        }

    def detect_ma_convergence_breakout(self, kline: pd.DataFrame) -> Dict:
        if kline.empty or "ma5" not in kline.columns:
            return {"converged": False, "breaking_out": False}
        latest = kline.iloc[-1]
        mas = {
            "MA5": latest["ma5"],
            "MA10": latest["ma10"],
            "MA20": latest["ma20"],
            "MA60": latest["ma60"],
        }
        valid_mas = {k: v for k, v in mas.items() if not pd.isna(v)}
        if len(valid_mas) < 3:
            return {"converged": False, "breaking_out": False}
        values = list(valid_mas.values())
        spread = (max(values) - min(values)) / np.mean(values)
        converged = spread < 0.05
        breaking_out = False
        direction = "none"
        if converged and latest["close"] > max(values):
            breaking_out = True
            direction = "up"
        elif converged and latest["close"] < min(values):
            breaking_out = True
            direction = "down"
        return {
            "converged": converged,
            "breaking_out": breaking_out,
            "direction": direction,
            "spread": round(spread * 100, 1),
        }

    def detect_rsi_reversal(self, kline: pd.DataFrame) -> Dict:
        if kline.empty or "rsi14" not in kline.columns:
            return {"signal": "none", "value": 50}
        latest_rsi = kline["rsi14"].iloc[-1]
        prev_rsi = kline["rsi14"].iloc[-2]
        signal = "none"
        if latest_rsi < self.config["rsi_oversold"] and latest_rsi > prev_rsi:
            signal = "oversold_bounce"
        elif latest_rsi > self.config["rsi_overbought"] and latest_rsi < prev_rsi:
            signal = "overbought_pullback"
        return {
            "signal": signal,
            "value": round(float(latest_rsi), 1),
            "prev_value": round(float(prev_rsi), 1),
        }

    def detect_bottom_pattern(self, kline: pd.DataFrame) -> Dict:
        if kline.empty or len(kline) < 20:
            return {"pattern": "none", "confidence": 0}
        recent = kline.tail(10)
        closes = recent["close"].values
        lows = recent["low"].values
        patterns = []
        if len(closes) >= 3:
            if closes[-1] > closes[-2] and closes[-2] < closes[-3]:
                if closes[-1] > closes[-3] and lows[-2] < lows[-3]:
                    patterns.append({"pattern": "morning_star", "confidence": 70})
        if len(closes) >= 5:
            down_trend = all(closes[i] < closes[i - 1] for i in range(-4, -1))
            if down_trend and closes[-1] > closes[-2]:
                patterns.append({"pattern": "v_reversal", "confidence": 60})
        last_3 = closes[-3:]
        if max(last_3) - min(last_3) < np.mean(last_3) * 0.02 and closes[-1] > closes[-2]:
            patterns.append({"pattern": "double_bottom", "confidence": 50})
        if patterns:
            best = max(patterns, key=lambda x: x["confidence"])
            return best
        return {"pattern": "none", "confidence": 0}

    def comprehensive_reversal_scan(
        self, stock_code: str, stock_name: str = ""
    ) -> Dict:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y%m%d")
        kline = self.market.get_daily_kline(stock_code, start_date, end_date)
        if kline.empty or len(kline) < 60:
            return {"code": stock_code, "name": stock_name, "has_data": False}
        kline = self.market.calculate_technical_indicators(kline)
        macd_result = self.detect_macd_divergence(kline)
        volume_result = self.detect_volume_breakout(kline)
        ma_result = self.detect_ma_convergence_breakout(kline)
        rsi_result = self.detect_rsi_reversal(kline)
        pattern_result = self.detect_bottom_pattern(kline)
        reversal_score = 0
        signals = []
        if macd_result["type"] == "bullish_divergence":
            reversal_score += 30
            signals.append("MACD底背离")
        elif macd_result["type"] == "bearish_divergence":
            reversal_score -= 20
            signals.append("MACD顶背离")
        if volume_result["breakout"]:
            reversal_score += 20
            signals.append(f"放量突破(x{volume_result['ratio']})")
        if ma_result["converged"] and ma_result["breaking_out"]:
            if ma_result["direction"] == "up":
                reversal_score += 25
                signals.append(f"均线粘合向上突破(离散{ma_result['spread']}%)")
            elif ma_result["direction"] == "down":
                reversal_score -= 20
                signals.append("均线粘合向下突破")
        if rsi_result["signal"] == "oversold_bounce":
            reversal_score += 15
            signals.append(f"RSI超卖反弹({rsi_result['value']})")
        elif rsi_result["signal"] == "overbought_pullback":
            reversal_score -= 10
            signals.append(f"RSI超买回落({rsi_result['value']})")
        if pattern_result["pattern"] != "none":
            reversal_score += 15
            signals.append(f"底部形态:{pattern_result['pattern']}")
        reversal_type = (
            "strong_reversal" if reversal_score >= 60 else
            "potential_reversal" if reversal_score >= 30 else
            "no_signal" if reversal_score > -20 else
            "potential_top" if reversal_score > -40 else
            "strong_top_signal"
        )
        return {
            "code": stock_code,
            "name": stock_name,
            "has_data": True,
            "reversal_score": reversal_score,
            "reversal_type": reversal_type,
            "signals": signals,
            "macd_divergence": macd_result,
            "volume_breakout": volume_result,
            "ma_convergence": ma_result,
            "rsi_signal": rsi_result,
            "bottom_pattern": pattern_result,
            "latest_close": round(float(kline["close"].iloc[-1]), 2),
            "pct_chg_today": round(float(kline["pct_chg"].iloc[-1]), 2),
        }

    def detect_reversal(self, kline: pd.DataFrame) -> List[Dict]:
        """便捷方法：从K线DataFrame检测逆转信号"""
        results = []
        if kline is None or kline.empty or len(kline) < 60:
            return results
        kline = self.market.calculate_technical_indicators(kline)
        macd_result = self.detect_macd_divergence(kline)
        volume_result = self.detect_volume_breakout(kline)
        ma_result = self.detect_ma_convergence_breakout(kline)
        rsi_result = self.detect_rsi_reversal(kline)
        pattern_result = self.detect_bottom_pattern(kline)
        signals = []
        if macd_result.get("type") == "bullish_divergence":
            signals.append({"signal": "MACD底背离", "strength": macd_result.get("strength", 0)})
        if volume_result.get("breakout"):
            signals.append({"signal": f"放量突破", "strength": 60})
        if ma_result.get("converged") and ma_result.get("breaking_out"):
            signals.append({"signal": "均线粘合突破", "strength": 70})
        if rsi_result.get("signal") == "oversold_bounce":
            signals.append({"signal": "RSI超卖反弹", "strength": 50})
        if pattern_result.get("pattern") != "none":
            signals.append({"signal": f"底部形态:{pattern_result.get('pattern')}", "strength": 55})
        if signals:
            results.append({
                "signals": signals,
            })
        return results