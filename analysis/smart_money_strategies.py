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
        "description": "识别低位首板或准涨停启动，强调涨幅、成交量和短线转强，适合题材启动初期观察。",
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
    {
        "strategy_id": "mainline_low_position_v1",
        "name": "低位主线共振",
        "style": "机构+游资合力",
        "description": "当前短线更重视低位、主线、放量启动和非过热结构，避免纯高位打板。",
        "risk": "需要后续板块持续确认，孤立个股冲高容易回落。",
    },
    {
        "strategy_id": "trend_core_holding_v1",
        "name": "趋势中军抱团",
        "style": "机构趋势/大资金抱团",
        "description": "识别稳步沿均线上行、波动可控、趋势强于短线情绪的中军股。",
        "risk": "趋势股不能用打板节奏处理，跌破中期均线或量价背离要降级。",
    },
    {
        "strategy_id": "sector_rotation_breakout_v1",
        "name": "行业轮动突破",
        "style": "机构行业轮动",
        "description": "识别横盘后首次放量突破且中期涨幅不过热的行业轮动型买点。",
        "risk": "轮动行情持续性不稳定，突破后缩量回落需观察。",
    },
    {
        "strategy_id": "quant_lhasa_risk_v1",
        "name": "量化/散户拥挤风险",
        "style": "风险过滤",
        "description": "识别高位巨量、长上影、冲高回落等疑似量化做T或散户拥挤后的兑现风险。",
        "risk": "风险信号优先级高，不适合继续追涨。",
    },
    {
        "strategy_id": "high_position_distribution_v1",
        "name": "高位派发风险",
        "style": "卖点/降仓",
        "description": "识别高位大涨后放量滞涨、长上影或跌破短期均线的派发风险。",
        "risk": "高位风险通常来得很快，先保护利润再判断是否修复。",
    },
    {
        "strategy_id": "emotion_retreat_defense_v1",
        "name": "情绪退潮防守",
        "style": "短线防守",
        "description": "识别连续强势后转弱、跌破均线、动量衰减的短线退潮信号。",
        "risk": "退潮期减少接力和打板，优先控制回撤。",
    },
    {
        "strategy_id": "emotion_repair_confirm_v1",
        "name": "情绪修复确认",
        "style": "短线情绪修复",
        "description": "识别连续调整后重新放量收强、收盘位置较高的修复确认信号，适合冰点后观察。",
        "risk": "修复行情容易一日游，若次日不能延续强承接，应降低短线预期。",
    },
    {
        "strategy_id": "quant_momentum_open_v1",
        "name": "量化动量早强",
        "style": "量化动量/强势确认",
        "description": "用日线代理早盘强势确认，识别跳空、放量、收盘强且短期不过热的动量信号。",
        "risk": "量化动量信号衰减快，冲高回落或量能失控时不能追涨。",
    },
    {
        "strategy_id": "hot_money_one_day_risk_v1",
        "name": "游资一日游风险",
        "style": "游资兑现风险",
        "description": "识别首板或强势日后次日缩量/放量走弱、低收盘位置等一日游风险。",
        "risk": "此类风险信号出现时，不宜继续按接力逻辑处理。",
    },
    {
        "strategy_id": "institution_hot_money_combo_v1",
        "name": "机构游资合力",
        "style": "机构+游资共振",
        "description": "识别中期趋势良好、低位不高、突然放量强攻的机构趋势和短线资金合力信号。",
        "risk": "合力信号需要次日承接确认，若高开低走说明合力失败。",
    },
    {
        "strategy_id": "box_breakout_pullback_v1",
        "name": "箱体突破回踩",
        "style": "趋势突破回踩",
        "description": "识别突破平台后回踩不破、缩量企稳的二次买点，偏右侧确认。",
        "risk": "若回踩跌回箱体内部，突破逻辑失败。",
    },
    {
        "strategy_id": "swing_trend_band_v1",
        "name": "主线趋势波段",
        "style": "趋势波段",
        "description": "识别中期多头、回撤可控、量能健康的趋势波段持有/加仓信号。",
        "risk": "趋势波段不适合追加速，跌破20日或60日均线要降级。",
    },
    {
        "strategy_id": "mean_reversion_oversold_v1",
        "name": "超跌均值回归",
        "style": "量化反转",
        "description": "识别连续下跌、RSI低位、偏离均线过大的超跌反弹机会。",
        "risk": "弱势股超跌后可能继续阴跌，只适合小仓试错并严格止损。",
    },
    {
        "strategy_id": "top_divergence_exit_v1",
        "name": "顶部背离减仓",
        "style": "趋势卖点/风控",
        "description": "识别创新高或高位大涨后量价、RSI、MACD动能背离的减仓信号。",
        "risk": "顶部背离不一定马上下跌，但应降低追涨和满仓风险。",
    },
    {
        "strategy_id": "trend_breakdown_exit_v1",
        "name": "趋势破位离场",
        "style": "趋势止损/风控",
        "description": "识别放量跌破关键均线或平台支撑的趋势离场信号。",
        "risk": "趋势破位后先保护本金，等待重新站回关键均线再评估。",
    },
]


CUSTOM_FIELD_LABELS = {
    "pct_chg": "涨跌幅%",
    "volume_ratio": "量比",
    "rsi14": "RSI14",
    "close_vs_ma5": "收盘价/MA5-1",
    "close_vs_ma10": "收盘价/MA10-1",
    "close_vs_ma20": "收盘价/MA20-1",
    "ma20_slope": "MA20斜率",
    "ret_5d": "5日涨幅",
    "ret_20d": "20日涨幅",
    "volatility_20d": "20日波动率",
    "upper_shadow_ratio": "上影线比例",
    "close_position": "收盘位置",
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


def get_builtin_strategy_name_map() -> Dict[str, str]:
    return {item["strategy_id"]: item["name"] for item in BUILTIN_STRATEGY_PROFILES}


def generate_smart_money_signals(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if df is None or df.empty or len(df) < 80:
        return pd.DataFrame()
    enriched = _enrich_frame(df)
    for i in range(60, len(enriched)):
        prev = enriched.iloc[i - 1]
        cur = enriched.iloc[i]
        recent = enriched.iloc[max(0, i - 20): i + 1]
        for detector in [
            _youzi_first_board,
            _youzi_relay,
            _weak_to_strong,
            _leader_first_yin,
            _institution_trend,
            _institution_pullback,
            _mainline_low_position,
            _trend_core_holding,
            _sector_rotation_breakout,
            _quant_lhasa_risk,
            _high_position_distribution,
            _emotion_retreat_defense,
            _emotion_repair_confirm,
            _quant_momentum_open,
            _hot_money_one_day_risk,
            _institution_hot_money_combo,
            _box_breakout_pullback,
            _swing_trend_band,
            _mean_reversion_oversold,
            _top_divergence_exit,
            _trend_breakdown_exit,
        ]:
            signal = detector(prev, cur, recent)
            if signal:
                rows.append(signal)
    return pd.DataFrame([item.__dict__ for item in rows]) if rows else pd.DataFrame()


def generate_custom_strategy_signals(df: pd.DataFrame, strategies: Optional[List[Dict]] = None) -> pd.DataFrame:
    rows = []
    if df is None or df.empty or not strategies:
        return pd.DataFrame()
    enriched = _enrich_frame(df)
    for strategy in strategies:
        if not int(strategy.get("enabled", 1)):
            continue
        conditions = _load_json(strategy.get("conditions_json"), [])
        risk_rule = _load_json(strategy.get("risk_rule_json"), {})
        if not conditions:
            continue
        for i in range(60, len(enriched)):
            cur = enriched.iloc[i]
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


def _enrich_frame(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    close = data.get("close", pd.Series(dtype="float"))
    high = data.get("high", close)
    low = data.get("low", close)
    open_price = data.get("open", close)
    if "ret_5d" not in data:
        data["ret_5d"] = close.pct_change(5)
    if "upper_shadow_ratio" not in data:
        data["upper_shadow_ratio"] = (high - data[["open", "close"]].max(axis=1)) / close.replace(0, np.nan)
    if "lower_shadow_ratio" not in data:
        data["lower_shadow_ratio"] = (data[["open", "close"]].min(axis=1) - low) / close.replace(0, np.nan)
    if "close_position" not in data:
        data["close_position"] = (close - low) / (high - low).replace(0, np.nan)
    if "intraday_range" not in data:
        data["intraday_range"] = (high - low) / close.replace(0, np.nan)
    if "gap_pct" not in data:
        data["gap_pct"] = open_price / close.shift(1).replace(0, np.nan) - 1
    if "ma60" not in data:
        data["ma60"] = close.rolling(60).mean()
    if "ma60_slope" not in data:
        data["ma60_slope"] = data["ma60"].diff(10) / data["ma60"].shift(10)
    if "volatility_10d" not in data:
        data["volatility_10d"] = close.pct_change().rolling(10).std()
    if "drawdown_20d" not in data:
        data["drawdown_20d"] = close / close.rolling(20).max() - 1
    if "volume_shrink" not in data:
        data["volume_shrink"] = data.get("volume", pd.Series(dtype="float")) / data.get("volume", pd.Series(dtype="float")).rolling(5).mean()
    return data


def _youzi_first_board(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = _num(cur, "pct_chg")
    prev_pct = _num(prev, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio")
    near_limit = pct >= 8.5
    first_surge = recent.iloc[:-1]["pct_chg"].max() < 8 if "pct_chg" in recent else True
    not_overheated = _num(cur, "ret_20d") < 0.35
    close_strong = _num(cur, "close_position", 0.7) >= 0.7
    if near_limit and first_surge and volume_ratio >= 1.4 and cur.get("close", 0) > cur.get("ma5", np.inf) and prev_pct < 6 and not_overheated and close_strong:
        strength = 4 + int(pct >= 9.5 and volume_ratio >= 2)
        return _build(cur, "BUY", "youzi_first_board_v1", "游资首板启动", strength, f"低位接近涨停启动，涨幅{pct:.1f}%，量比{volume_ratio:.1f}，近20日首次强势封板特征", "首板次日分化较大，避免极端高开追涨")
    return None


def _youzi_relay(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = _num(cur, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio")
    recent_strong_days = int((recent["pct_chg"] >= 6).sum()) if "pct_chg" in recent else 0
    trend_ok = cur.get("close", 0) > cur.get("ma5", np.inf) > cur.get("ma20", np.inf)
    overheated = _num(cur, "ret_20d") > 0.75 or _num(cur, "rsi14", 50) > 83
    if pct >= 6.5 and volume_ratio >= 1.5 and recent_strong_days >= 2 and trend_ok and not overheated:
        strength = 4 + int(pct >= 9 and volume_ratio >= 2)
        return _build(cur, "BUY", "youzi_relay_v1", "游资接力/打板", strength, f"近20日强势日{recent_strong_days}次，今日涨幅{pct:.1f}%且量比{volume_ratio:.1f}，短线资金接力特征明显", "接力策略风险高，退潮期、炸板或低开不及预期应快速控制风险")
    return None


def _weak_to_strong(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    prev_pct = _num(prev, "pct_chg")
    pct = _num(cur, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio")
    recover_prev_high = cur.get("close", 0) > prev.get("high", np.inf)
    prev_divergence = prev_pct < -2 or (prev.get("high", 0) / max(prev.get("close", 1), 0.01) - 1) > 0.04
    if prev_divergence and pct >= 3 and volume_ratio >= 1.2 and recover_prev_high and cur.get("close", 0) > cur.get("ma5", np.inf):
        strength = 4 + int(pct >= 6 and volume_ratio >= 1.8)
        return _build(cur, "BUY", "weak_to_strong_v1", "弱转强反包", strength, f"昨日分歧后今日放量转强，涨幅{pct:.1f}%并收复前高，符合弱转强/反包观察", "弱转强失败回撤快，跌回前日低点或MA5应及时降风险")
    return None


def _leader_first_yin(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = _num(cur, "pct_chg")
    ret_20d = _num(cur, "ret_20d")
    volume_ratio = _num(cur, "volume_ratio")
    prior = recent.iloc[:-1]
    strong_days = int((prior["pct_chg"] >= 5).sum()) if "pct_chg" in prior else 0
    trend_holding = cur.get("close", 0) > cur.get("ma10", cur.get("ma20", np.inf)) and cur.get("close", 0) > cur.get("ma20", np.inf)
    if ret_20d >= 0.22 and strong_days >= 2 and -6 <= pct <= -1.5 and volume_ratio <= 1.6 and trend_holding:
        return _build(cur, "BUY", "leader_first_yin_v1", "龙头首阴低吸", 3, f"20日涨幅{ret_20d:.1%}后首次明显回落但趋势未破，强势股首阴低吸观察", "普通高位股首阴可能是退潮开始，仅适合小仓观察和严格止损")
    return None


def _institution_trend(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = _num(cur, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio")
    slope = _num(cur, "ma20_slope")
    breakout = bool(cur.get("breakout_20", False))
    not_overheated = _num(cur, "rsi14", 50) < 72
    if breakout and 0.8 <= volume_ratio <= 2.5 and slope > 0 and pct > 1 and not_overheated:
        strength = 4 + int(slope > 0.03 and volume_ratio >= 1.3)
        return _build(cur, "BUY", "institution_trend_v1", "机构趋势突破", strength, f"突破20日新高，MA20斜率{slope:.2%}，量能温和放大，偏机构趋势中军特征", "趋势信号适合分批跟踪，跌回20日均线需重新评估")
    return None


def _institution_pullback(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    close = _num(cur, "close")
    ma20 = _num(cur, "ma20", np.inf)
    slope = _num(cur, "ma20_slope")
    pct = _num(cur, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio")
    distance = abs(close / ma20 - 1) if ma20 and np.isfinite(ma20) else np.inf
    prior_uptrend = _num(cur, "ret_20d") > 0.06 and slope > 0
    stabilizing = pct > -1.5 and close >= ma20 * 0.985
    if prior_uptrend and distance <= 0.035 and volume_ratio <= 1.1 and stabilizing:
        return _build(cur, "BUY", "institution_pullback_v1", "机构缩量回踩", 3, f"20日趋势向上，回踩MA20附近{distance:.1%}且缩量，偏机构趋势低吸观察", "若后续放量跌破MA20，趋势低吸逻辑失效")
    return None


def _mainline_low_position(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = _num(cur, "pct_chg")
    ret_20d = _num(cur, "ret_20d")
    volume_ratio = _num(cur, "volume_ratio")
    slope = _num(cur, "ma20_slope")
    close_position = _num(cur, "close_position", 0.5)
    base_days = int((recent.iloc[:-1]["pct_chg"].abs() < 3).sum()) if "pct_chg" in recent else 0
    if 4 <= pct <= 9.7 and 1.3 <= volume_ratio <= 3.2 and -0.08 <= ret_20d <= 0.28 and slope >= -0.01 and close_position >= 0.65 and base_days >= 8:
        strength = 4 + int(pct >= 7 and volume_ratio >= 1.8)
        return _build(cur, "BUY", "mainline_low_position_v1", "低位主线共振", strength, f"低位横盘后放量上攻，20日涨幅{ret_20d:.1%}不过热，涨幅{pct:.1f}%且收盘位置强", "需要板块持续性确认，若次日高开过大或冲高回落需谨慎")
    return None


def _trend_core_holding(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    close = _num(cur, "close")
    ma5 = _num(cur, "ma5", np.inf)
    ma20 = _num(cur, "ma20", np.inf)
    slope = _num(cur, "ma20_slope")
    ret_20d = _num(cur, "ret_20d")
    volatility = _num(cur, "volatility_20d")
    volume_ratio = _num(cur, "volume_ratio", 1)
    pct = _num(cur, "pct_chg")
    steady_days = int((recent["close"] >= recent["ma20"]).sum()) if "ma20" in recent else 0
    if close > ma5 > ma20 and slope > 0.015 and 0.08 <= ret_20d <= 0.45 and volatility <= 0.045 and 0.7 <= volume_ratio <= 1.9 and pct > -1 and steady_days >= 14:
        strength = 4 + int(ret_20d >= 0.18 and volatility <= 0.035)
        return _build(cur, "BUY", "trend_core_holding_v1", "趋势中军抱团", strength, f"价格沿MA20上行，20日涨幅{ret_20d:.1%}、波动{volatility:.1%}可控，偏机构抱团趋势", "趋势中军适合跟踪不适合追急涨，跌破MA20需降级")
    return None


def _sector_rotation_breakout(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = _num(cur, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio")
    ret_20d = _num(cur, "ret_20d")
    range_20 = (recent["high"].max() / max(recent["low"].min(), 0.01) - 1) if {"high", "low"}.issubset(recent.columns) else np.inf
    breakout = bool(cur.get("breakout_20", False))
    if breakout and 2 <= pct <= 7.5 and 1.2 <= volume_ratio <= 2.2 and ret_20d < 0.32 and range_20 <= 0.45:
        return _build(cur, "BUY", "sector_rotation_breakout_v1", "行业轮动突破", 4, f"横盘区间后放量突破，20日区间振幅{range_20:.1%}，涨幅{pct:.1f}%未过热", "轮动突破需看板块扩散，若突破后缩量回落则信号降级")
    return None


def _quant_lhasa_risk(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = _num(cur, "pct_chg")
    ret_5d = _num(cur, "ret_5d")
    volume_ratio = _num(cur, "volume_ratio")
    upper_shadow = _num(cur, "upper_shadow_ratio")
    close_position = _num(cur, "close_position", 0.5)
    intraday_range = _num(cur, "intraday_range")
    if ret_5d >= 0.18 and volume_ratio >= 2.3 and upper_shadow >= 0.035 and close_position <= 0.45 and intraday_range >= 0.07:
        return _build(cur, "SELL", "quant_lhasa_risk_v1", "量化/散户拥挤风险", 4, f"5日涨幅{ret_5d:.1%}后巨量长上影，量比{volume_ratio:.1f}，疑似拥挤交易或做T兑现", "高位拥挤风险不适合追涨，若次日不能快速反包应控制仓位")
    if pct <= -4 and volume_ratio >= 1.8 and _num(prev, "ret_5d") >= 0.15:
        return _build(cur, "SELL", "quant_lhasa_risk_v1", "量化/散户拥挤风险", 4, f"短期大涨后放量下跌{pct:.1f}%，资金兑现压力上升", "放量回落通常代表筹码松动，先降风险再观察")
    return None


def _high_position_distribution(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    ret_20d = _num(cur, "ret_20d")
    pct = _num(cur, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio")
    upper_shadow = _num(cur, "upper_shadow_ratio")
    close = _num(cur, "close")
    ma5 = _num(cur, "ma5", np.inf)
    rsi = _num(cur, "rsi14", 50)
    if ret_20d >= 0.45 and volume_ratio >= 1.5 and (upper_shadow >= 0.035 or close < ma5 or rsi >= 78) and pct < 3:
        return _build(cur, "TAKE_PROFIT", "high_position_distribution_v1", "高位派发风险", 5, f"20日涨幅{ret_20d:.1%}后放量滞涨/上影，量比{volume_ratio:.1f}，高位派发风险升高", "优先保护利润，可分批止盈或设置更紧保护止损")
    return None


def _emotion_retreat_defense(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    close = _num(cur, "close")
    ma5 = _num(cur, "ma5", np.inf)
    ma20 = _num(cur, "ma20", np.inf)
    pct = _num(cur, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio")
    recent_strong_days = int((recent.iloc[:-1]["pct_chg"] >= 5).sum()) if "pct_chg" in recent else 0
    momentum_down = _num(cur, "macd_hist") < _num(prev, "macd_hist") or _num(cur, "rsi14", 50) < _num(prev, "rsi14", 50)
    if recent_strong_days >= 2 and close < ma5 and pct <= -3 and volume_ratio >= 1.2 and momentum_down:
        strength = 4 + int(close < ma20 or pct <= -6)
        return _build(cur, "STOP_LOSS", "emotion_retreat_defense_v1", "情绪退潮防守", strength, f"连续强势后跌破MA5且放量回落{pct:.1f}%，短线情绪退潮迹象", "退潮期不做接力，优先控制回撤并等待重新转强")
    return None


def _emotion_repair_confirm(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = _num(cur, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio")
    close_position = _num(cur, "close_position", 0.5)
    prior = recent.iloc[:-1]
    down_days = int((prior["pct_chg"] <= -2.5).sum()) if "pct_chg" in prior else 0
    drawdown = _num(cur, "drawdown_20d")
    macd_repair = _num(cur, "macd_hist") > _num(prev, "macd_hist")
    if down_days >= 2 and drawdown <= -0.08 and 2.5 <= pct <= 8 and volume_ratio >= 1.15 and close_position >= 0.65 and macd_repair:
        strength = 3 + int(pct >= 5 and volume_ratio >= 1.6)
        return _build(cur, "BUY", "emotion_repair_confirm_v1", "情绪修复确认", strength, f"近20日回撤{drawdown:.1%}后放量收强，涨幅{pct:.1f}%且收盘位置较高，短线情绪修复确认", "修复行情持续性不稳定，次日弱承接或低开低走应降低仓位")
    return None



def _quant_momentum_open(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    pct = _num(cur, "pct_chg")
    gap = _num(cur, "gap_pct")
    volume_ratio = _num(cur, "volume_ratio")
    close_position = _num(cur, "close_position", 0.5)
    ret_20d = _num(cur, "ret_20d")
    intraday_range = _num(cur, "intraday_range")
    if 0.01 <= gap <= 0.055 and 3 <= pct <= 8.5 and 1.25 <= volume_ratio <= 2.8 and close_position >= 0.72 and ret_20d <= 0.38 and intraday_range <= 0.095:
        strength = 4 + int(pct >= 6 and volume_ratio >= 1.8)
        return _build(cur, "BUY", "quant_momentum_open_v1", "量化动量早强", strength, f"跳空{gap:.1%}后放量收强，涨幅{pct:.1f}%、量比{volume_ratio:.1f}，符合量化动量确认特征", "动量策略衰减快，若次日不能继续强于大盘，应避免追高扩大仓位")
    return None



def _hot_money_one_day_risk(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    prev_pct = _num(prev, "pct_chg")
    pct = _num(cur, "pct_chg")
    gap = _num(cur, "gap_pct")
    volume_ratio = _num(cur, "volume_ratio")
    close_position = _num(cur, "close_position", 0.5)
    upper_shadow = _num(cur, "upper_shadow_ratio")
    if prev_pct >= 7 and ((gap >= 0.035 and pct <= 1.5 and close_position <= 0.42) or (volume_ratio >= 1.7 and upper_shadow >= 0.035 and close_position <= 0.5)):
        return _build(cur, "SELL", "hot_money_one_day_risk_v1", "游资一日游风险", 4, f"前日强势{prev_pct:.1f}%后今日承接不足，涨幅{pct:.1f}%、收盘位置{close_position:.0%}，疑似一日游兑现", "首板次日若不能强承接，不应继续按接力处理")
    return None



def _institution_hot_money_combo(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    close = _num(cur, "close")
    ma20 = _num(cur, "ma20", np.inf)
    ma60 = _num(cur, "ma60", np.inf)
    slope20 = _num(cur, "ma20_slope")
    slope60 = _num(cur, "ma60_slope")
    pct = _num(cur, "pct_chg")
    ret_20d = _num(cur, "ret_20d")
    volume_ratio = _num(cur, "volume_ratio")
    close_position = _num(cur, "close_position", 0.5)
    trend_ok = close > ma20 > ma60 and slope20 > 0.005 and slope60 >= -0.005
    if trend_ok and 3.5 <= pct <= 9.2 and 1.4 <= volume_ratio <= 3.0 and 0.02 <= ret_20d <= 0.42 and close_position >= 0.68:
        strength = 4 + int(pct >= 6 and slope20 >= 0.02)
        return _build(cur, "BUY", "institution_hot_money_combo_v1", "机构游资合力", strength, f"中期趋势向上且短线放量强攻，20日涨幅{ret_20d:.1%}、量比{volume_ratio:.1f}，偏机构与游资合力", "合力买点需要次日承接确认，高开低走说明短线资金兑现")
    return None



def _box_breakout_pullback(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    close = _num(cur, "close")
    ma20 = _num(cur, "ma20", np.inf)
    pct = _num(cur, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio", 1)
    prior = recent.iloc[:-1]
    if prior.empty or not {"high", "low", "close"}.issubset(prior.columns):
        return None
    box_high = float(prior["high"].tail(15).max())
    box_low = float(prior["low"].tail(15).min())
    box_range = box_high / max(box_low, 0.01) - 1
    had_breakout = bool((prior["close"].tail(5) > box_high * 0.995).any())
    pullback_hold = close >= box_high * 0.97 and close >= ma20 * 0.99 and -2 <= pct <= 3.5 and volume_ratio <= 1.25
    if had_breakout and box_range <= 0.28 and pullback_hold:
        return _build(cur, "BUY", "box_breakout_pullback_v1", "箱体突破回踩", 3, f"近15日箱体振幅{box_range:.1%}，突破后回踩箱体上沿不破且量能收敛，属于二次确认买点", "若跌回箱体内部或放量破位，突破回踩逻辑失效")
    return None



def _swing_trend_band(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    close = _num(cur, "close")
    ma20 = _num(cur, "ma20", np.inf)
    ma60 = _num(cur, "ma60", np.inf)
    slope20 = _num(cur, "ma20_slope")
    ret_20d = _num(cur, "ret_20d")
    volatility = _num(cur, "volatility_20d")
    volume_ratio = _num(cur, "volume_ratio", 1)
    drawdown = _num(cur, "drawdown_20d")
    trend_days = int((recent["close"] >= recent["ma20"]).sum()) if {"close", "ma20"}.issubset(recent.columns) else 0
    if close > ma20 > ma60 and slope20 > 0.01 and 0.06 <= ret_20d <= 0.35 and volatility <= 0.04 and -0.08 <= drawdown <= -0.005 and 0.65 <= volume_ratio <= 1.45 and trend_days >= 13:
        return _build(cur, "BUY", "swing_trend_band_v1", "主线趋势波段", 4, f"中期多头趋势保持，20日涨幅{ret_20d:.1%}、回撤{drawdown:.1%}、波动{volatility:.1%}可控，适合趋势波段跟踪", "趋势波段应避免急涨追高，跌破MA20需降低仓位")
    return None



def _mean_reversion_oversold(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    close = _num(cur, "close")
    ma20 = _num(cur, "ma20", np.inf)
    rsi = _num(cur, "rsi14", 50)
    ret_5d = _num(cur, "ret_5d")
    pct = _num(cur, "pct_chg")
    lower_shadow = _num(cur, "lower_shadow_ratio")
    close_position = _num(cur, "close_position", 0.5)
    distance = close / ma20 - 1 if ma20 and np.isfinite(ma20) else 0
    if ret_5d <= -0.11 and distance <= -0.08 and rsi <= 34 and pct > -3.5 and (lower_shadow >= 0.025 or close_position >= 0.55):
        strength = 3 + int(rsi <= 28 and close_position >= 0.65)
        return _build(cur, "BUY", "mean_reversion_oversold_v1", "超跌均值回归", strength, f"5日跌幅{ret_5d:.1%}且偏离MA20 {distance:.1%}，RSI{rsi:.0f}低位并出现止跌迹象", "超跌反弹不是趋势反转，仓位要轻，跌破当日低点应止损")
    return None



def _top_divergence_exit(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    ret_20d = _num(cur, "ret_20d")
    pct = _num(cur, "pct_chg")
    rsi = _num(cur, "rsi14", 50)
    prev_rsi = _num(prev, "rsi14", 50)
    macd_hist = _num(cur, "macd_hist")
    prev_macd_hist = _num(prev, "macd_hist")
    volume_ratio = _num(cur, "volume_ratio")
    upper_shadow = _num(cur, "upper_shadow_ratio")
    new_high = cur.get("close", 0) >= recent["close"].max() * 0.995 if "close" in recent else False
    momentum_divergence = rsi < prev_rsi or macd_hist < prev_macd_hist
    if ret_20d >= 0.35 and new_high and momentum_divergence and (upper_shadow >= 0.025 or volume_ratio <= 0.85 or pct <= 1):
        return _build(cur, "TAKE_PROFIT", "top_divergence_exit_v1", "顶部背离减仓", 4, f"20日涨幅{ret_20d:.1%}后接近新高，但RSI/MACD动能回落并出现量价背离，建议降低追涨风险", "顶部背离可能钝化，但应分批保护利润，避免高位满仓")
    return None



def _trend_breakdown_exit(prev: pd.Series, cur: pd.Series, recent: pd.DataFrame) -> Optional[SmartMoneySignal]:
    close = _num(cur, "close")
    ma20 = _num(cur, "ma20", np.inf)
    ma60 = _num(cur, "ma60", np.inf)
    pct = _num(cur, "pct_chg")
    volume_ratio = _num(cur, "volume_ratio")
    breakdown = close < ma20 * 0.985 and _num(prev, "close") >= _num(prev, "ma20", np.inf) * 0.995
    deeper_break = close < ma60 * 0.99 and pct <= -2
    if (breakdown and pct <= -2.5 and volume_ratio >= 1.2) or deeper_break:
        strength = 4 + int(deeper_break or volume_ratio >= 1.8)
        return _build(cur, "STOP_LOSS", "trend_breakdown_exit_v1", "趋势破位离场", strength, f"放量下跌{pct:.1f}%并跌破关键趋势均线，趋势支撑失效风险上升", "趋势破位后先控制本金风险，重新站回MA20前不宜加仓")
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
    if field in ("close_vs_ma5", "close_vs_ma10", "close_vs_ma20"):
        ma_name = field.replace("close_vs_", "")
        ma = row.get(ma_name)
        return float(row.get("close", np.nan) / ma - 1) if ma and pd.notna(ma) else None
    if field == "turnover_proxy":
        return float(row.get("amount", row.get("volume", np.nan)) or np.nan)
    return float(row.get(field, np.nan)) if field in row else None


def _num(row: pd.Series, field: str, default: float = 0.0) -> float:
    value = row.get(field, default)
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _load_json(value, default):
    if isinstance(value, (list, dict)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default
