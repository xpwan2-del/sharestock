from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class SmartMoneySignal:
    date: pd.Timestamp
    signal_type: str
    strategy_id: str
    strategy_name: str
    strength: int
    price: float
    reason: str
    risk: str


BUILTIN_STRATEGY_PROFILES = [
    {
        "strategy_id": "youzi_first_board_v1",
        "name": "游资首板启动",
        "style": "小游资/题材试错",
        "description": "识别首板或准涨停启动，强调涨幅、成交量和短线转强，适合题材启动初期观察。",
        "risk": "首板次日分化大，不能盲目高开追涨；若低开弱承接应放弃。",
    },
    {
        "strategy_id": "youzi_relay_v1",
        "name": "游资接力/打板",
        "style": "大游资/连板接力",
        "description": "识别强势涨停、放量突破、均线多头的短线接力信号，偏高风险高波动。",
        "risk": "退潮期接力风险极高，炸板、天地板和大幅低开都需要严格风控。",
    },
    {
        "strategy_id": "weak_to_strong_v1",
        "name": "弱转强反包",
        "style": "游资分歧转一致",
        "description": "昨日分歧或回落后，今日高开上攻并重新放量站上短线均线，属于情绪修复信号。",
        "risk": "弱转强失败通常回撤较快，不能跌回关键均线或前日低点。",
    },
    {
        "strategy_id": "leader_first_yin_v1",
        "name": "龙头首阴低吸",
        "style": "龙头分歧低吸",
        "description": "短期大涨后的首次明显阴线，若仍在强趋势上方，给出低吸观察而非追涨信号。",
        "risk": "只适合真正强势龙头，普通高位股首阴可能是退潮开始。",
    },
    {
        "strategy_id": "institution_trend_v1",
        "name": "机构趋势突破",
        "style": "机构/中军趋势",
        "description": "识别站上中期均线、20日均线斜率向上、温和放量的趋势型买点。",
        "risk": "机构趋势更看重持续性，短线爆发力通常弱于游资题材股。",
    },
    {
        "strategy_id": "institution_pullback_v1",
        "name": "机构缩量回踩",
        "style": "机构趋势低吸",
        "description": "上升趋势中缩量回踩20日均线附近并企稳，偏向中线低吸观察。",
        "risk": "若放量跌破20日均线，说明趋势可能失效。",
    },
]


CUSTOM_FIELD_LABELS = {
    "pct_chg": "涨跌幅%",
    "volume_ratio": "量比",
    "rsi14": "RSI14",
    "close_vs_ma5": "收盘价/MA5-1",
    "close_vs_ma20": "收盘价/MA20-1",
    "ma20_slope": "MA20斜率",
    "ret_20d": "20日涨幅",
    "volatility_20d": "20日波动率",
    "turnover_proxy": "成交额代理",
}


OPERATORS = {
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    "==": lambda left, right: left == right,
}


def get_builtin_strategy_profiles() -> List[Dict]:
    return BUILTIN_STRATEGY_PROFILES.copy()


def generate_smart_money_signals(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if df is None or df.empty or len(df) < 80:
        return pd.DataFrame()
    for i in range(60, len(df)):
        prev = df.iloc[i - 1]
        cur = df.iloc[i]
        recent = df.iloc[max(0, i - 20): i + 1]
        signal = _youzi_first_board(prev, cur, recent)
        if signal:
            rows.append(signal)
        signal = _youzi_relay(prev, cur, recent)
        if signal:
            rows.append(signal)
        signal = _weak_to_strong(prev, cur, recent)
        if signal:
            rows.append(signal)
        signal = _leader_first_yin(prev, cur, recent)
        if signal:
            rows.append(signal)
        signal = _institution_trend(prev, cur, recent)
        if signal:
            rows.append(signal)
        signal = _institution_pullback(prev, cur, recent)
        if signal:
            rows.append(signal)
    return pd.DataFrame([item.__dict__ for item in rows]) if rows else pd.DataFrame()


def generate_custom_strategy_signals(df: pd.DataFrame, strategies: Optional[List[Dict]] = None) -> pd.DataFrame:
    rows = []
    if df is None or df.empty or not strategies:
        return pd.DataFrame()
    for strategy in strategies:
        if not int(strategy.get("enabled", 1)):
            continue
        conditions = _load_json(strategy.get("conditions_json"), [])
        risk_rule = _load_json(strategy.get("risk_rule_json"), {})
        if not conditions:
            continue
        for i in range(60, len(df)):
            cur = df.iloc[i]
            matched, reason_parts = _match_conditions(cur, conditions)
            if not matched:
                continue
            signal_type = str(strategy.get("signal_type") or "BUY")
            strength = int(risk_rule.get("strength", min(5, 2 + len(reason_parts))))
            risk = risk_rule.get("risk", "人工策略信号需要结合仓位、止损和市场环境二次确认")
            rows.append(SmartMoneySignal(
                date=pd.Timestamp(cur["date"]),
                signal_type=signal_type,
                strategy_id=str(strategy.get("strategy_id")),
                strategy_name=strategy.get("name") or "人工策略",
                strength=max(1, min(5, strength)),
                price=float(cur["close"]),
                reason="；".join(reason_parts),
                risk=str(risk),
            ))
    return pd.DataFrame([item.__dict__ for item in rows]) if rows else pd.DataFrame()


def _youzi_first_board(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = float(cur.get("pct_chg", 0) or 0)
    prev_pct = float(prev.get("pct_chg", 0) or 0)
    volume_ratio = float(cur.get("volume_ratio", 0) or 0)
    near_limit = pct >= 8.5
    first_surge = recent.iloc[:-1]["pct_chg"].max() < 8 if "pct_chg" in recent else True
    if near_limit and first_surge and volume_ratio >= 1.4 and cur.get("close", 0) > cur.get("ma5", np.inf) and prev_pct < 6:
        strength = 4 + int(pct >= 9.5 and volume_ratio >= 2)
        return _build(cur, "BUY", "youzi_first_board_v1", "游资首板启动", strength, f"接近涨停启动，涨幅{pct:.1f}%，量比{volume_ratio:.1f}，近20日首次强势封板特征", "首板次日分化较大，避免极端高开追涨")
    return None


def _youzi_relay(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = float(cur.get("pct_chg", 0) or 0)
    volume_ratio = float(cur.get("volume_ratio", 0) or 0)
    recent_strong_days = int((recent["pct_chg"] >= 6).sum()) if "pct_chg" in recent else 0
    trend_ok = cur.get("close", 0) > cur.get("ma5", np.inf) > cur.get("ma20", np.inf)
    if pct >= 6.5 and volume_ratio >= 1.5 and recent_strong_days >= 2 and trend_ok:
        strength = 4 + int(pct >= 9 and volume_ratio >= 2)
        return _build(cur, "BUY", "youzi_relay_v1", "游资接力/打板", strength, f"近20日强势日{recent_strong_days}次，今日涨幅{pct:.1f}%且量比{volume_ratio:.1f}，短线资金接力特征明显", "接力策略风险高，退潮期、炸板或低开不及预期应快速控制风险")
    return None


def _weak_to_strong(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    prev_pct = float(prev.get("pct_chg", 0) or 0)
    pct = float(cur.get("pct_chg", 0) or 0)
    volume_ratio = float(cur.get("volume_ratio", 0) or 0)
    recover_prev_high = cur.get("close", 0) > prev.get("high", np.inf)
    prev_divergence = prev_pct < -2 or (prev.get("high", 0) / max(prev.get("close", 1), 0.01) - 1) > 0.04
    if prev_divergence and pct >= 3 and volume_ratio >= 1.2 and recover_prev_high and cur.get("close", 0) > cur.get("ma5", np.inf):
        strength = 4 + int(pct >= 6 and volume_ratio >= 1.8)
        return _build(cur, "BUY", "weak_to_strong_v1", "弱转强反包", strength, f"昨日分歧后今日放量转强，涨幅{pct:.1f}%并收复前高，符合弱转强/反包观察", "弱转强失败回撤快，跌回前日低点或MA5应及时降风险")
    return None


def _leader_first_yin(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = float(cur.get("pct_chg", 0) or 0)
    ret_20d = float(cur.get("ret_20d", 0) or 0)
    volume_ratio = float(cur.get("volume_ratio", 0) or 0)
    prior = recent.iloc[:-1]
    strong_days = int((prior["pct_chg"] >= 5).sum()) if "pct_chg" in prior else 0
    trend_holding = cur.get("close", 0) > cur.get("ma10", cur.get("ma20", np.inf)) and cur.get("close", 0) > cur.get("ma20", np.inf)
    if ret_20d >= 0.22 and strong_days >= 2 and -6 <= pct <= -1.5 and volume_ratio <= 1.6 and trend_holding:
        return _build(cur, "BUY", "leader_first_yin_v1", "龙头首阴低吸", 3, f"20日涨幅{ret_20d:.1%}后首次明显回落但趋势未破，强势股首阴低吸观察", "普通高位股首阴可能是退潮开始，仅适合小仓观察和严格止损")
    return None


def _institution_trend(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = float(cur.get("pct_chg", 0) or 0)
    volume_ratio = float(cur.get("volume_ratio", 0) or 0)
    slope = float(cur.get("ma20_slope", 0) or 0)
    breakout = bool(cur.get("breakout_20", False))
    not_overheated = float(cur.get("rsi14", 50) or 50) < 72
    if breakout and 0.8 <= volume_ratio <= 2.5 and slope > 0 and pct > 1 and not_overheated:
        strength = 4 + int(slope > 0.03 and volume_ratio >= 1.3)
        return _build(cur, "BUY", "institution_trend_v1", "机构趋势突破", strength, f"突破20日新高，MA20斜率{slope:.2%}，量能温和放大，偏机构趋势中军特征", "趋势信号适合分批跟踪，跌回20日均线需重新评估")
    return None


def _institution_pullback(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    close = float(cur.get("close", 0) or 0)
    ma20 = float(cur.get("ma20", np.inf) or np.inf)
    slope = float(cur.get("ma20_slope", 0) or 0)
    pct = float(cur.get("pct_chg", 0) or 0)
    volume_ratio = float(cur.get("volume_ratio", 0) or 0)
    distance = abs(close / ma20 - 1) if ma20 and np.isfinite(ma20) else np.inf
    prior_uptrend = float(cur.get("ret_20d", 0) or 0) > 0.06 and slope > 0
    stabilizing = pct > -1.5 and close >= ma20 * 0.985
    if prior_uptrend and distance <= 0.035 and volume_ratio <= 1.1 and stabilizing:
        return _build(cur, "BUY", "institution_pullback_v1", "机构缩量回踩", 3, f"20日趋势向上，回踩MA20附近{distance:.1%}且缩量，偏机构趋势低吸观察", "若后续放量跌破MA20，趋势低吸逻辑失效")
    return None


def _build(row: pd.Series, signal_type: str, strategy_id: str, strategy_name: str, strength: int, reason: str, risk: str) -> SmartMoneySignal:
    return SmartMoneySignal(
        date=pd.Timestamp(row["date"]),
        signal_type=signal_type,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        strength=int(max(1, min(5, strength))),
        price=float(row["close"]),
        reason=reason,
        risk=risk,
    )


def _match_conditions(row: pd.Series, conditions: List[Dict]) -> tuple[bool, List[str]]:
    reasons = []
    for condition in conditions:
        field = str(condition.get("field", ""))
        operator = str(condition.get("operator", ">="))
        expected = float(condition.get("value", 0) or 0)
        current = _field_value(row, field)
        matcher = OPERATORS.get(operator)
        if matcher is None or current is None or pd.isna(current) or not matcher(float(current), expected):
            return False, []
        label = CUSTOM_FIELD_LABELS.get(field, field)
        reasons.append(f"{label}{operator}{expected:g}，当前{float(current):.3g}")
    return True, reasons


def _field_value(row: pd.Series, field: str) -> Optional[float]:
    if field == "close_vs_ma5":
        ma = row.get("ma5")
        return float(row.get("close", np.nan) / ma - 1) if ma and pd.notna(ma) else None
    if field == "close_vs_ma20":
        ma = row.get("ma20")
        return float(row.get("close", np.nan) / ma - 1) if ma and pd.notna(ma) else None
    if field == "turnover_proxy":
        return float(row.get("amount", row.get("volume", np.nan)) or np.nan)
    return float(row.get(field, np.nan)) if field in row else None


def _load_json(value, default):
    if isinstance(value, (list, dict)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default
