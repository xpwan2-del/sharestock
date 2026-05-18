from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from analysis.smart_money_strategies import generate_custom_strategy_signals, generate_smart_money_signals
from data.market_data import MarketDataCollector
from data.watchlist_store import WatchlistStore


def _signal_name(signal_type: str) -> str:
    return {
        "BUY": "买入提示",
        "SELL": "卖出提示",
        "TAKE_PROFIT": "止盈提醒",
        "STOP_LOSS": "止损提醒",
    }.get(signal_type, signal_type or "信号提醒")


@dataclass
class TradeSignal:
    date: pd.Timestamp
    signal_type: str
    strategy_id: str
    strategy_name: str
    strength: int
    price: float
    reason: str
    risk: str


class TradeSignalEngine:
    def __init__(self, custom_strategies: Optional[List[Dict]] = None):
        self.market = MarketDataCollector()
        self.custom_strategies = custom_strategies if custom_strategies is not None else self._load_custom_strategies()

    def analyze_stock(
        self,
        code: str,
        name: str = "",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        holding_periods: Optional[List[int]] = None,
    ) -> Dict:
        holding_periods = holding_periods or [3, 5, 10, 20]
        end_dt = pd.to_datetime(end_date) if end_date else pd.Timestamp.today()
        start_dt = pd.to_datetime(start_date) if start_date else end_dt - timedelta(days=900)
        df = self.market.get_daily_kline(
            code,
            start_dt.strftime("%Y%m%d"),
            end_dt.strftime("%Y%m%d"),
            adjust="qfq",
        )
        df = self._prepare_frame(df)
        if df.empty or len(df) < 80:
            return {
                "code": code,
                "name": name,
                "has_data": False,
                "message": "历史K线不足，暂时无法计算买卖点和胜率",
            }

        signals = self.generate_signals(df)
        evaluated = self.evaluate_signals(df, signals, holding_periods)
        latest = evaluated.iloc[-1].to_dict() if not evaluated.empty else None
        latest_buy = self._latest_by_type(evaluated, "BUY")
        latest_sell = self._latest_by_type(evaluated, "SELL")
        performance = self.summarize_performance(evaluated, holding_periods)
        current = df.iloc[-1]

        return {
            "code": code,
            "name": name,
            "has_data": True,
            "current_price": float(current["close"]),
            "trade_date": current["date"],
            "latest_signal": latest,
            "latest_buy": latest_buy,
            "latest_sell": latest_sell,
            "signal_score": self.score_result(current, latest, performance),
            "action_suggestion": self.suggest_action(current, latest, performance),
            "risk_level": self.estimate_risk(current, latest),
            "signals": evaluated,
            "performance": performance,
            "data": df,
        }

    def scan_market(self, quotes: pd.DataFrame, limit: int = 80, min_strength: int = 3) -> pd.DataFrame:
        if quotes is None or quotes.empty:
            return pd.DataFrame()
        universe = quotes.copy()
        if "amount" in universe.columns:
            universe = universe.sort_values("amount", ascending=False)
        elif "pct_chg" in universe.columns:
            universe = universe.sort_values("pct_chg", ascending=False)
        rows = []
        for _, row in universe.head(limit).iterrows():
            code = str(row.get("code", "")).zfill(6)
            if not code or code == "000000":
                continue
            name = str(row.get("name", ""))
            try:
                result = self.analyze_stock(code, name=name)
                signal = result.get("latest_signal")
                perf = result.get("performance", {})
                if not signal or signal.get("strength", 0) < min_strength:
                    continue
                if signal.get("signal_type") not in ("BUY", "SELL", "TAKE_PROFIT", "STOP_LOSS"):
                    continue
                stat10 = perf.get(signal.get("strategy_id", ""), {}).get(10, {})
                score = result.get("signal_score", 0)
                rows.append({
                    "code": code,
                    "name": name,
                    "signal_type": signal.get("signal_type"),
                    "strategy_name": signal.get("strategy_name"),
                    "strength": signal.get("strength"),
                    "score": score,
                    "risk_level": result.get("risk_level"),
                    "suggestion": result.get("action_suggestion"),
                    "price": signal.get("price"),
                    "date": signal.get("date"),
                    "reason": signal.get("reason"),
                    "win_rate_10d": stat10.get("win_rate"),
                    "avg_return_10d": stat10.get("avg_return"),
                    "sample_count_10d": stat10.get("sample_count"),
                    "current_pct_chg": row.get("pct_chg"),
                })
            except Exception:
                continue
        return pd.DataFrame(rows).sort_values(["score", "strength", "win_rate_10d"], ascending=False) if rows else pd.DataFrame()

    def score_result(self, current: pd.Series, latest: Optional[Dict], performance: Dict) -> float:
        if not latest:
            return 0.0
        strength_score = float(latest.get("strength", 1)) * 14
        trend_score = 10 if current.get("close", 0) > current.get("ma20", np.inf) else -6
        volume_score = min(max(float(current.get("volume_ratio", 1) or 1) - 1, 0) * 12, 12)
        stat = performance.get(latest.get("strategy_id", ""), {}).get(10, {})
        win_rate = stat.get("win_rate")
        win_score = (float(win_rate) - 0.5) * 50 if win_rate is not None and pd.notna(win_rate) else 0
        risk_penalty = 10 if latest.get("signal_type") in ("STOP_LOSS", "SELL") else 0
        score = strength_score + trend_score + volume_score + win_score - risk_penalty
        return round(float(max(0, min(100, score))), 1)

    def suggest_action(self, current: pd.Series, latest: Optional[Dict], performance: Dict) -> str:
        if not latest:
            return "暂无明确买卖点，保持观察"
        signal_type = latest.get("signal_type")
        stat = performance.get(latest.get("strategy_id", ""), {}).get(10, {})
        sample_count = int(stat.get("sample_count") or 0)
        win_rate = stat.get("win_rate")
        if signal_type == "BUY":
            if sample_count >= 10 and win_rate is not None and win_rate >= 0.55:
                return "出现买入信号且历史胜率偏高，可加入重点观察并等待成交确认"
            return "出现买入信号，但样本或胜率一般，建议小仓观察"
        if signal_type == "SELL":
            return "出现卖出信号，若已持仓建议降低仓位或设置保护止损"
        if signal_type == "STOP_LOSS":
            return "出现止损风险，优先控制回撤，避免亏损扩大"
        if signal_type == "TAKE_PROFIT":
            return "出现止盈提醒，可考虑分批锁定利润"
        return "信号偏观察性质，等待更强确认"

    def estimate_risk(self, current: pd.Series, latest: Optional[Dict]) -> str:
        if latest and latest.get("signal_type") == "STOP_LOSS":
            return "高"
        if current.get("close", 0) < current.get("ma20", np.inf):
            return "中高"
        if current.get("volatility_20d", 0) > 0.04:
            return "中"
        return "低"

    def build_watchlist_snapshot(self, watchlist: pd.DataFrame) -> pd.DataFrame:
        if watchlist is None or watchlist.empty:
            return pd.DataFrame()
        rows = []
        for _, item in watchlist.iterrows():
            code = str(item.get("code", "")).zfill(6)
            name = str(item.get("name", ""))
            try:
                result = self.analyze_stock(code, name=name)
                latest = result.get("latest_signal") or {}
                stat = result.get("performance", {}).get(latest.get("strategy_id", ""), {}).get(10, {})
                rows.append({
                    "code": code,
                    "name": name,
                    "group_name": item.get("group_name", "默认"),
                    "current_price": result.get("current_price"),
                    "trade_date": result.get("trade_date"),
                    "signal_type": latest.get("signal_type", "WATCH"),
                    "strategy_name": latest.get("strategy_name", "暂无强信号"),
                    "strength": latest.get("strength", 0),
                    "score": result.get("signal_score", 0),
                    "risk_level": result.get("risk_level", "未知"),
                    "suggestion": result.get("action_suggestion", "暂无明确买卖点，保持观察"),
                    "reason": latest.get("reason", "暂无明确触发原因"),
                    "win_rate_10d": stat.get("win_rate"),
                    "avg_return_10d": stat.get("avg_return"),
                    "sample_count_10d": stat.get("sample_count"),
                })
            except Exception as exc:
                rows.append({
                    "code": code,
                    "name": name,
                    "group_name": item.get("group_name", "默认"),
                    "signal_type": "ERROR",
                    "strategy_name": "分析失败",
                    "strength": 0,
                    "score": 0,
                    "risk_level": "未知",
                    "suggestion": "该股票本次分析失败，稍后重试",
                    "reason": str(exc)[:120],
                })
        return pd.DataFrame(rows).sort_values(["score", "strength"], ascending=False) if rows else pd.DataFrame()

    def build_alerts_from_snapshot(self, snapshot: pd.DataFrame) -> List[Dict]:
        alerts = []
        if snapshot is None or snapshot.empty:
            return alerts
        for _, row in snapshot.iterrows():
            signal_type = row.get("signal_type")
            strength = int(row.get("strength") or 0)
            risk = row.get("risk_level")
            if signal_type in ("BUY", "SELL", "STOP_LOSS", "TAKE_PROFIT") and (strength >= 4 or risk in ("高", "中高")):
                severity = "high" if signal_type in ("STOP_LOSS", "SELL") or risk == "高" else "medium"
                title = f"{row.get('name') or row.get('code')} {_signal_name(signal_type)}"
                alerts.append({
                    "code": row.get("code"),
                    "name": row.get("name"),
                    "alert_type": signal_type,
                    "severity": severity,
                    "title": title,
                    "content": f"{row.get('strategy_name')}｜强度{strength}/5｜{row.get('suggestion')}｜原因：{row.get('reason')}",
                    "signal_date": row.get("trade_date"),
                    "fingerprint": f"{row.get('code')}:{signal_type}:{row.get('trade_date')}",
                })
        return alerts

    def _prepare_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        data = df.copy()
        if "date" not in data.columns:
            data = data.reset_index().rename(columns={"index": "date"})
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")
        data = data.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
        data = self.market.calculate_technical_indicators(data)
        if "pct_chg" not in data.columns:
            data["pct_chg"] = data["close"].pct_change() * 100
        data["ma20_slope"] = data["ma20"].diff(5) / data["ma20"].shift(5)
        data["breakout_20"] = data["close"] > data["high"].rolling(20).max().shift(1)
        data["breakdown_20"] = data["close"] < data["low"].rolling(20).min().shift(1)
        return data.replace([np.inf, -np.inf], np.nan)

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for i in range(60, len(df)):
            prev = df.iloc[i - 1]
            cur = df.iloc[i]
            if self._is_buy_ma_cross(prev, cur):
                rows.append(self._build_signal(cur, "BUY", "ma_cross_v1", "均线金叉", self._strength_ma(cur), "MA5上穿MA20，趋势转强，成交量同步放大", "跌破MA20或出现死叉应控制风险"))
            if self._is_sell_ma_cross(prev, cur):
                rows.append(self._build_signal(cur, "SELL", "ma_cross_v1", "均线死叉", 4, "MA5下穿MA20，短线趋势转弱", "若已经持仓，需关注止损或减仓"))
            if self._is_buy_macd(prev, cur):
                rows.append(self._build_signal(cur, "BUY", "macd_cross_v1", "MACD金叉", self._strength_macd(cur), "DIF上穿DEA，MACD柱体改善", "震荡行情中MACD容易反复钝化"))
            if self._is_sell_macd(prev, cur):
                rows.append(self._build_signal(cur, "SELL", "macd_cross_v1", "MACD死叉", 3, "DIF下穿DEA，动能转弱", "若仍在强趋势中，可结合均线确认"))
            if self._is_buy_rsi(prev, cur):
                rows.append(self._build_signal(cur, "BUY", "rsi_rebound_v1", "RSI超卖反弹", self._strength_rsi(cur), "RSI从超卖区重新上穿30，短线修复信号", "弱势下跌趋势中反弹可能失败"))
            if self._is_sell_rsi(prev, cur):
                rows.append(self._build_signal(cur, "SELL", "rsi_rebound_v1", "RSI高位回落", 3, "RSI高位回落，短线过热降温", "强趋势股票可能高位持续钝化"))
            if self._is_breakout(cur):
                rows.append(self._build_signal(cur, "BUY", "breakout_v1", "放量突破", self._strength_breakout(cur), "收盘突破20日高点并放量，趋势突破信号", "假突破后跌回平台需及时控制风险"))
            if self._is_stop_loss(cur):
                rows.append(self._build_signal(cur, "STOP_LOSS", "risk_control_v1", "风控止损", 5, "跌破20日低点或明显破位", "风险信号优先级高，应避免扩大亏损"))
            if self._is_take_profit(cur):
                rows.append(self._build_signal(cur, "TAKE_PROFIT", "risk_control_v1", "止盈提醒", 4, "短期涨幅较大且RSI过热，注意止盈保护", "强趋势中可分批止盈而非一次清仓"))
        technical = pd.DataFrame([s.__dict__ for s in rows]) if rows else pd.DataFrame()
        smart_money = generate_smart_money_signals(df)
        custom = generate_custom_strategy_signals(df, self.custom_strategies)
        frames = [item for item in [technical, smart_money, custom] if item is not None and not item.empty]
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True).sort_values(["date", "strength"], ascending=[True, True]).reset_index(drop=True)

    def _load_custom_strategies(self) -> List[Dict]:
        try:
            strategies = WatchlistStore().list_custom_strategies(enabled_only=True)
            return strategies.to_dict("records") if not strategies.empty else []
        except Exception:
            return []

    def evaluate_signals(self, df: pd.DataFrame, signals: pd.DataFrame, holding_periods: List[int]) -> pd.DataFrame:
        if signals.empty:
            return signals
        data = df.reset_index(drop=True)
        date_to_idx = {pd.Timestamp(row["date"]): idx for idx, row in data.iterrows()}
        result = signals.copy()
        for days in holding_periods:
            returns = []
            max_drawdowns = []
            for _, sig in result.iterrows():
                idx = date_to_idx.get(pd.Timestamp(sig["date"]))
                if idx is None or idx + days >= len(data):
                    returns.append(np.nan)
                    max_drawdowns.append(np.nan)
                    continue
                entry = float(sig["price"])
                window = data.iloc[idx + 1: idx + days + 1]
                exit_price = float(window.iloc[-1]["close"])
                if sig["signal_type"] in ("SELL", "STOP_LOSS"):
                    ret = (entry / exit_price) - 1
                    adverse = (window["high"].max() / entry) - 1
                else:
                    ret = (exit_price / entry) - 1
                    adverse = (window["low"].min() / entry) - 1
                returns.append(ret)
                max_drawdowns.append(adverse)
            result[f"return_{days}d"] = returns
            result[f"max_drawdown_{days}d"] = max_drawdowns
            result[f"win_{days}d"] = result[f"return_{days}d"] > 0
        return result

    def summarize_performance(self, signals: pd.DataFrame, holding_periods: List[int]) -> Dict:
        if signals.empty:
            return {}
        summary = {}
        for strategy_id, group in signals.groupby("strategy_id"):
            summary[strategy_id] = {}
            for days in holding_periods:
                ret = group[f"return_{days}d"].dropna()
                if ret.empty:
                    continue
                wins = ret > 0
                losses = ret[ret <= 0]
                gains = ret[ret > 0]
                summary[strategy_id][days] = {
                    "sample_count": int(len(ret)),
                    "win_rate": float(wins.mean()),
                    "avg_return": float(ret.mean()),
                    "median_return": float(ret.median()),
                    "max_return": float(ret.max()),
                    "max_loss": float(ret.min()),
                    "profit_loss_ratio": float(gains.mean() / abs(losses.mean())) if not gains.empty and not losses.empty and losses.mean() != 0 else np.nan,
                }
        return summary

    def _build_signal(self, row: pd.Series, signal_type: str, strategy_id: str, strategy_name: str, strength: int, reason: str, risk: str) -> TradeSignal:
        return TradeSignal(
            date=pd.Timestamp(row["date"]),
            signal_type=signal_type,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            strength=int(max(1, min(5, strength))),
            price=float(row["close"]),
            reason=reason,
            risk=risk,
        )

    def _latest_by_type(self, signals: pd.DataFrame, signal_type: str) -> Optional[Dict]:
        if signals.empty:
            return None
        matched = signals[signals["signal_type"] == signal_type]
        return matched.iloc[-1].to_dict() if not matched.empty else None

    def _is_buy_ma_cross(self, prev: pd.Series, cur: pd.Series) -> bool:
        return prev["ma5"] <= prev["ma20"] and cur["ma5"] > cur["ma20"] and cur.get("volume_ratio", 0) >= 1.05

    def _is_sell_ma_cross(self, prev: pd.Series, cur: pd.Series) -> bool:
        return prev["ma5"] >= prev["ma20"] and cur["ma5"] < cur["ma20"]

    def _is_buy_macd(self, prev: pd.Series, cur: pd.Series) -> bool:
        return prev["macd"] <= prev["macd_signal"] and cur["macd"] > cur["macd_signal"] and cur["macd_hist"] > prev["macd_hist"]

    def _is_sell_macd(self, prev: pd.Series, cur: pd.Series) -> bool:
        return prev["macd"] >= prev["macd_signal"] and cur["macd"] < cur["macd_signal"]

    def _is_buy_rsi(self, prev: pd.Series, cur: pd.Series) -> bool:
        return prev["rsi14"] < 30 and cur["rsi14"] >= 30

    def _is_sell_rsi(self, prev: pd.Series, cur: pd.Series) -> bool:
        return prev["rsi14"] > 70 and cur["rsi14"] <= 70

    def _is_breakout(self, cur: pd.Series) -> bool:
        return bool(cur.get("breakout_20", False)) and cur.get("volume_ratio", 0) >= 1.2 and cur.get("pct_chg", 0) > 1

    def _is_stop_loss(self, cur: pd.Series) -> bool:
        return bool(cur.get("breakdown_20", False)) or (cur["close"] < cur["ma20"] and cur.get("pct_chg", 0) < -4)

    def _is_take_profit(self, cur: pd.Series) -> bool:
        return cur.get("ret_20d", 0) > 0.18 and cur.get("rsi14", 0) > 72

    def _strength_ma(self, cur: pd.Series) -> int:
        score = 3
        if cur.get("volume_ratio", 0) >= 1.5:
            score += 1
        if cur.get("ma20_slope", 0) > 0:
            score += 1
        return score

    def _strength_macd(self, cur: pd.Series) -> int:
        score = 3
        if cur.get("macd_hist", 0) > 0:
            score += 1
        if cur.get("close", 0) > cur.get("ma20", np.inf):
            score += 1
        return score

    def _strength_rsi(self, cur: pd.Series) -> int:
        score = 3
        if cur.get("volume_ratio", 0) >= 1.2:
            score += 1
        if cur.get("close", 0) > cur.get("ma5", np.inf):
            score += 1
        return score

    def _strength_breakout(self, cur: pd.Series) -> int:
        score = 3
        if cur.get("volume_ratio", 0) >= 1.8:
            score += 1
        if cur.get("pct_chg", 0) >= 5:
            score += 1
        return score
