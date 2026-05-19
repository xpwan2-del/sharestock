from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd


STYLE_STRATEGY_GROUPS = {
    "短线情绪/连板": [
        "youzi_first_board_v1",
        "youzi_relay_v1",
        "weak_to_strong_v1",
        "leader_first_yin_v1",
        "emotion_repair_confirm_v1",
        "quant_momentum_open_v1",
    ],
    "低位主线/补涨": [
        "mainline_low_position_v1",
        "sector_rotation_breakout_v1",
        "institution_hot_money_combo_v1",
        "box_breakout_pullback_v1",
        "breakout_v1",
    ],
    "机构趋势/中军": [
        "institution_trend_v1",
        "institution_pullback_v1",
        "trend_core_holding_v1",
        "swing_trend_band_v1",
        "ma_cross_v1",
        "macd_cross_v1",
    ],
    "高位风险/退潮": [
        "quant_lhasa_risk_v1",
        "hot_money_one_day_risk_v1",
        "high_position_distribution_v1",
        "emotion_retreat_defense_v1",
        "mean_reversion_oversold_v1",
        "top_divergence_exit_v1",
        "trend_breakdown_exit_v1",
        "risk_control_v1",
    ],
}

STRATEGY_STYLE_MAP = {
    strategy_id: style
    for style, strategy_ids in STYLE_STRATEGY_GROUPS.items()
    for strategy_id in strategy_ids
}


def build_market_style_report(
    df: pd.DataFrame,
    evaluated_signals: Optional[pd.DataFrame] = None,
    performance: Optional[Dict] = None,
    recent_window: int = 60,
) -> Dict:
    if df is None or df.empty:
        return _empty_report()
    recent = _enrich(df).tail(recent_window).copy()
    style_scores = _calculate_price_style_scores(recent)
    perf_scores = _calculate_performance_style_scores(evaluated_signals, performance)
    blended = {}
    for style in STYLE_STRATEGY_GROUPS:
        blended[style] = round(style_scores.get(style, 50) * 0.65 + perf_scores.get(style, 50) * 0.35, 1)
    dominant = max(blended, key=blended.get) if blended else "未知"
    regime = _regime_label(dominant, blended.get(dominant, 50), recent)
    weights = _strategy_weights(blended, performance)
    advice = _style_advice(dominant, blended, recent)
    return {
        "dominant_style": dominant,
        "regime": regime,
        "style_scores": blended,
        "price_style_scores": style_scores,
        "performance_style_scores": perf_scores,
        "strategy_weights": weights,
        "advice": advice,
        "metrics": _recent_metrics(recent),
    }


def apply_style_weights(signals: pd.DataFrame, style_report: Dict) -> pd.DataFrame:
    if signals is None or signals.empty or not style_report:
        return signals
    weights = style_report.get("strategy_weights", {}) or {}
    result = signals.copy()
    result["style_group"] = result["strategy_id"].map(lambda item: STRATEGY_STYLE_MAP.get(item, "人工/其他"))
    result["style_weight"] = result["strategy_id"].map(lambda item: float(weights.get(item, 1.0)))
    result["weighted_strength"] = (result["strength"].astype(float) * result["style_weight"]).round(2)
    result["style_note"] = result["style_group"].map(lambda item: f"当前风格：{style_report.get('dominant_style', '未知')}，本策略归属：{item}")
    return result


def style_adjusted_score(base_score: float, latest: Optional[Dict], style_report: Dict) -> float:
    if not latest or not style_report:
        return base_score
    strategy_id = latest.get("strategy_id", "")
    weight = float((style_report.get("strategy_weights") or {}).get(strategy_id, 1.0))
    style_group = STRATEGY_STYLE_MAP.get(strategy_id)
    dominant = style_report.get("dominant_style")
    adjustment = (weight - 1.0) * 22
    if style_group and dominant and style_group == dominant:
        adjustment += 4
    if latest.get("signal_type") in ("SELL", "STOP_LOSS", "TAKE_PROFIT") and dominant == "高位风险/退潮":
        adjustment += 8
    return round(float(max(0, min(100, base_score + adjustment))), 1)


def describe_style_for_signal(latest: Optional[Dict], style_report: Dict) -> str:
    if not latest or not style_report:
        return "暂无风格自学习结论"
    strategy_id = latest.get("strategy_id", "")
    style_group = STRATEGY_STYLE_MAP.get(strategy_id, "人工/其他")
    weight = float((style_report.get("strategy_weights") or {}).get(strategy_id, 1.0))
    dominant = style_report.get("dominant_style", "未知")
    if weight >= 1.12:
        return f"当前市场更偏{dominant}，该信号属于{style_group}，策略权重上调至{weight:.2f}。"
    if weight <= 0.9:
        return f"当前市场更偏{dominant}，该信号属于{style_group}，策略权重下调至{weight:.2f}，建议降低预期。"
    return f"当前市场偏{dominant}，该信号属于{style_group}，策略权重保持中性。"


def _calculate_price_style_scores(recent: pd.DataFrame) -> Dict[str, float]:
    pct = recent.get("pct_chg", pd.Series(dtype="float")).dropna()
    if pct.empty:
        return {style: 50.0 for style in STYLE_STRATEGY_GROUPS}
    strong_days = float((pct >= 6).sum())
    limit_like = float((pct >= 8.5).sum())
    big_down = float((pct <= -4).sum())
    avg_pct = float(pct.mean())
    latest_ret_20d = float(recent["ret_20d"].dropna().iloc[-1]) if "ret_20d" in recent and not recent["ret_20d"].dropna().empty else 0
    latest_ret_5d = float(recent["ret_5d"].dropna().iloc[-1]) if "ret_5d" in recent and not recent["ret_5d"].dropna().empty else 0
    volatility = float(recent.get("volatility_20d", pd.Series([0.03])).dropna().tail(20).mean() or 0.03)
    volume_ratio = float(recent.get("volume_ratio", pd.Series([1])).dropna().tail(20).mean() or 1)
    slope = float(recent.get("ma20_slope", pd.Series([0])).dropna().tail(10).mean() or 0)
    close_above_ma20 = float((recent["close"] > recent["ma20"]).mean()) if {"close", "ma20"}.issubset(recent.columns) else 0.5
    upper_shadow = float(recent.get("upper_shadow_ratio", pd.Series([0])).dropna().tail(10).mean() or 0)
    close_position = float(recent.get("close_position", pd.Series([0.5])).dropna().tail(10).mean() or 0.5)
    range_20 = float(recent["high"].tail(20).max() / max(recent["low"].tail(20).min(), 0.01) - 1) if {"high", "low"}.issubset(recent.columns) else 0.25
    scores = {
        "短线情绪/连板": 42 + strong_days * 4 + limit_like * 6 + max(avg_pct, 0) * 3 + max(volume_ratio - 1, 0) * 10 - big_down * 5 - max(volatility - 0.055, 0) * 120,
        "低位主线/补涨": 48 + max(volume_ratio - 1, 0) * 12 + max(avg_pct, 0) * 4 + (1 if -0.08 <= latest_ret_20d <= 0.28 else -1) * 12 + (1 if range_20 <= 0.45 else -1) * 8,
        "机构趋势/中军": 45 + max(slope, 0) * 600 + close_above_ma20 * 22 + (1 if 0.05 <= latest_ret_20d <= 0.45 else -1) * 8 + (1 if volatility <= 0.045 else -1) * 10,
        "高位风险/退潮": 35 + big_down * 8 + max(upper_shadow - 0.02, 0) * 260 + (1 if latest_ret_20d >= 0.45 else 0) * 20 + (1 if latest_ret_5d >= 0.18 else 0) * 12 + (1 if close_position < 0.45 else 0) * 8,
    }
    return {key: round(float(max(0, min(100, value))), 1) for key, value in scores.items()}


def _calculate_performance_style_scores(evaluated_signals: Optional[pd.DataFrame], performance: Optional[Dict]) -> Dict[str, float]:
    scores = {style: 50.0 for style in STYLE_STRATEGY_GROUPS}
    if not performance:
        return scores
    for style, strategy_ids in STYLE_STRATEGY_GROUPS.items():
        values = []
        samples = []
        for strategy_id in strategy_ids:
            stat = performance.get(strategy_id, {}).get(10) or performance.get(strategy_id, {}).get(5) or {}
            sample_count = int(stat.get("sample_count") or 0)
            win_rate = stat.get("win_rate")
            avg_return = stat.get("avg_return")
            if sample_count <= 0 or win_rate is None or pd.isna(win_rate):
                continue
            score = 50 + (float(win_rate) - 0.5) * 80
            if avg_return is not None and not pd.isna(avg_return):
                score += float(avg_return) * 160
            values.append(max(0, min(100, score)))
            samples.append(min(sample_count, 30))
        if values:
            scores[style] = round(float(np.average(values, weights=samples if samples else None)), 1)
    return scores


def _strategy_weights(style_scores: Dict[str, float], performance: Optional[Dict]) -> Dict[str, float]:
    weights = {}
    top_style = max(style_scores, key=style_scores.get) if style_scores else ""
    for style, strategy_ids in STYLE_STRATEGY_GROUPS.items():
        style_score = float(style_scores.get(style, 50))
        style_weight = 0.82 + style_score / 250
        if style == top_style:
            style_weight += 0.08
        if top_style == "高位风险/退潮" and style in ("短线情绪/连板", "低位主线/补涨"):
            style_weight -= 0.14
        for strategy_id in strategy_ids:
            perf = (performance or {}).get(strategy_id, {}).get(10, {})
            win_rate = perf.get("win_rate")
            sample_count = int(perf.get("sample_count") or 0)
            perf_adj = 0
            if sample_count >= 8 and win_rate is not None and not pd.isna(win_rate):
                perf_adj = (float(win_rate) - 0.5) * 0.28
            weights[strategy_id] = round(float(max(0.68, min(1.32, style_weight + perf_adj))), 2)
    return weights


def _style_advice(dominant: str, scores: Dict[str, float], recent: pd.DataFrame) -> str:
    if dominant == "高位风险/退潮":
        return "当前更偏风险释放或短线退潮，优先看止盈止损和防守信号，降低接力、打板和高开追涨。"
    if dominant == "机构趋势/中军":
        return "当前更偏机构趋势和中军抱团，重点关注趋势突破、缩量回踩和稳步上行，少做纯情绪追涨。"
    if dominant == "低位主线/补涨":
        return "当前更偏低位主线和补涨扩散，重点看放量启动、横盘突破和不过热的主线共振。"
    if dominant == "短线情绪/连板":
        return "当前短线情绪较强，可关注首板、弱转强和接力，但必须结合次日承接和退潮风险。"
    return "当前风格不明确，策略权重保持中性，等待更强确认。"


def _regime_label(dominant: str, score: float, recent: pd.DataFrame) -> str:
    if dominant == "高位风险/退潮" and score >= 62:
        return "退潮/高风险"
    if score >= 70:
        return f"强{dominant}"
    if score >= 58:
        return f"偏{dominant}"
    return "混沌轮动"


def _recent_metrics(recent: pd.DataFrame) -> Dict:
    pct = recent.get("pct_chg", pd.Series(dtype="float")).dropna()
    return {
        "recent_days": int(len(recent)),
        "strong_days": int((pct >= 6).sum()) if not pct.empty else 0,
        "limit_like_days": int((pct >= 8.5).sum()) if not pct.empty else 0,
        "big_down_days": int((pct <= -4).sum()) if not pct.empty else 0,
        "avg_pct_chg": round(float(pct.mean()), 2) if not pct.empty else 0,
        "latest_ret_20d": round(float(recent["ret_20d"].dropna().iloc[-1]), 4) if "ret_20d" in recent and not recent["ret_20d"].dropna().empty else None,
        "avg_volume_ratio": round(float(recent.get("volume_ratio", pd.Series([1])).dropna().tail(20).mean() or 1), 2),
    }


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    close = data.get("close", pd.Series(dtype="float"))
    high = data.get("high", close)
    low = data.get("low", close)
    open_price = data.get("open", close)
    if "ret_5d" not in data:
        data["ret_5d"] = close.pct_change(5)
    if "ret_20d" not in data:
        data["ret_20d"] = close.pct_change(20)
    if "upper_shadow_ratio" not in data:
        data["upper_shadow_ratio"] = (high - data[["open", "close"]].max(axis=1)) / close.replace(0, np.nan)
    if "close_position" not in data:
        data["close_position"] = (close - low) / (high - low).replace(0, np.nan)
    if "gap_pct" not in data:
        data["gap_pct"] = open_price / close.shift(1).replace(0, np.nan) - 1
    return data.replace([np.inf, -np.inf], np.nan)


def _empty_report() -> Dict:
    return {
        "dominant_style": "未知",
        "regime": "无数据",
        "style_scores": {},
        "price_style_scores": {},
        "performance_style_scores": {},
        "strategy_weights": {},
        "advice": "暂无足够数据识别市场风格。",
        "metrics": {},
    }
