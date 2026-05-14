import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from loguru import logger

from config.settings import DATA_DIR
from data.market_data import MarketDataCollector
from data.dragon_tiger import DragonTigerCollector
from data.fund_flow import FundFlowCollector

ANALYSIS_DIR = DATA_DIR / "analysis"
ANALYSIS_DIR.mkdir(exist_ok=True)


class LeaderFinder:
    def __init__(self):
        self.market = MarketDataCollector()
        self.dragon_tiger = DragonTigerCollector()
        self.fund_flow = FundFlowCollector()

    def _code_column(self, df: pd.DataFrame) -> Optional[str]:
        for col in ["代码", "code", "symbol"]:
            if col in df.columns:
                return col
        return None

    def _name_column(self, df: pd.DataFrame) -> Optional[str]:
        for col in ["名称", "name", "股票名称"]:
            if col in df.columns:
                return col
        return None

    def _to_number(self, series: pd.Series, default: float = 0) -> pd.Series:
        return pd.to_numeric(series, errors="coerce").fillna(default)

    def _rank_score(self, series: pd.Series, weight: float, ascending: bool = True) -> pd.Series:
        numeric = self._to_number(series)
        if numeric.nunique(dropna=True) <= 1:
            return pd.Series(weight * 0.5, index=series.index)
        return numeric.rank(pct=True, ascending=ascending).fillna(0) * weight

    def _merge_concept_quotes(self, concept_stocks: pd.DataFrame, daily_quotes: pd.DataFrame) -> pd.DataFrame:
        concept_code = self._code_column(concept_stocks)
        quote_code = self._code_column(daily_quotes)
        if concept_code is None or quote_code is None:
            return pd.DataFrame()
        concept = concept_stocks.copy()
        quotes = daily_quotes.copy()
        concept[concept_code] = concept[concept_code].astype(str).str.zfill(6)
        quotes[quote_code] = quotes[quote_code].astype(str).str.zfill(6)
        merged = concept.merge(quotes, left_on=concept_code, right_on=quote_code, how="inner")
        if "code" not in merged.columns:
            merged["code"] = merged[quote_code]
        name_col = self._name_column(merged)
        if name_col and "name" not in merged.columns:
            merged["name"] = merged[name_col]
        return merged

    def _build_behavior_features(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        for col in ["open", "high", "low", "close", "volume", "amount", "pct_chg"]:
            if col not in result.columns:
                result[col] = 0
            result[col] = self._to_number(result[col])
        price_range = (result["high"] - result["low"]).replace(0, np.nan)
        result["close_position"] = ((result["close"] - result["low"]) / price_range).replace([np.inf, -np.inf], np.nan).fillna(0.5).clip(0, 1)
        result["intraday_return"] = ((result["close"] - result["open"]) / result["open"].replace(0, np.nan) * 100).replace([np.inf, -np.inf], np.nan).fillna(0)
        result["amplitude"] = ((result["high"] - result["low"]) / result["open"].replace(0, np.nan) * 100).replace([np.inf, -np.inf], np.nan).fillna(0)
        result["limit_like"] = (result["pct_chg"] >= 9.5).astype(float)
        result["touch_limit_like"] = (result["pct_chg"] >= 8.5).astype(float)
        result["not_broken_score"] = ((result["close_position"] >= 0.85) & (result["pct_chg"] >= 7)).astype(float)
        result["range_control_score"] = (1 - (result["amplitude"] / 20).clip(0, 1)).fillna(0)
        return result

    def _format_behavior_reason(self, row: pd.Series, hints: List[str]) -> str:
        parts = []
        try:
            pct = float(row.get("pct_chg", 0))
            if pct >= 9.5:
                parts.append("涨停封板")
            elif pct >= 8.5:
                parts.append("近涨停")
            elif pct >= 6:
                parts.append("强势拉升")
            if float(row.get("close_position", 0)) >= 0.85:
                parts.append("收盘接近最高点")
            if float(row.get("amount", 0)) > 0:
                parts.append("成交额活跃")
            if float(row.get("limit_like", 0)) > 0:
                parts.append("涨停结构强")
        except Exception:
            parts.extend(hints[:2])
        return "；".join(parts[:4]) or "；".join(hints[:2])

    def _filter_limit_up_stocks(self, limit_up_pool: pd.DataFrame, concept_stocks: pd.DataFrame) -> pd.DataFrame:
        if limit_up_pool.empty or concept_stocks.empty:
            return pd.DataFrame()
        limit_code = self._code_column(limit_up_pool)
        concept_code = self._code_column(concept_stocks)
        if limit_code is None or concept_code is None:
            return pd.DataFrame()
        limit_df = limit_up_pool.copy()
        concept_df = concept_stocks.copy()
        limit_df["code"] = limit_df[limit_code].astype(str).str.zfill(6)
        concept_df["code"] = concept_df[concept_code].astype(str).str.zfill(6)
        concept_codes = set(concept_df["code"])
        filtered = limit_df[limit_df["code"].isin(concept_codes)].copy()
        if filtered.empty:
            return pd.DataFrame()
        name_col = self._name_column(filtered)
        if name_col and "name" not in filtered.columns:
            filtered["name"] = filtered[name_col]
        return filtered

    def find_logic_leaders(
        self,
        concept_name: str,
        concept_stocks: pd.DataFrame,
        daily_quotes: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        逻辑龙头：不用接口估值字段，只看板块内交易行为强度。
        核心是板块内涨幅领先、收盘位置强、成交额/成交量领先、接近涨停且不炸。
        """
        if concept_stocks.empty or daily_quotes.empty:
            return pd.DataFrame()
        merged = self._merge_concept_quotes(concept_stocks, daily_quotes)
        if merged.empty:
            return pd.DataFrame()
        merged = self._build_behavior_features(merged)
        merged["logic_score"] = 0.0
        merged["logic_score"] += self._rank_score(merged["pct_chg"], 30)
        merged["logic_score"] += self._rank_score(merged["amount"], 20)
        merged["logic_score"] += self._rank_score(merged["volume"], 15)
        merged["logic_score"] += merged["close_position"] * 15
        merged["logic_score"] += merged["touch_limit_like"] * 10
        merged["logic_score"] += merged["not_broken_score"] * 10
        merged["leader_type"] = "逻辑龙头"
        merged["leader_reason"] = merged.apply(
            lambda row: self._format_behavior_reason(row, ["板块涨幅领先", "资金成交领先", "收盘强势", "涨停/近涨停"]),
            axis=1,
        )
        merged = merged.sort_values("logic_score", ascending=False)
        top = merged.head(min(5, len(merged)))
        logger.info(f"概念[{concept_name}] 逻辑龙头: {', '.join(top['name'].astype(str).tolist())}")
        return top

    def find_sentiment_leaders(
        self,
        limit_up_pool: pd.DataFrame,
        concept_stocks: pd.DataFrame,
        daily_quotes: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        情绪龙头：看的是涨停行为本身——连板高度、封板质量、回封韧性、封单力度。
        """
        candidates = self._filter_limit_up_stocks(limit_up_pool, concept_stocks)
        if candidates.empty:
            return pd.DataFrame()
        concept_code = self._code_column(concept_stocks)
        quote_code = self._code_column(daily_quotes)
        if concept_code and quote_code:
            codes = set(concept_stocks[concept_code].astype(str).str.zfill(6))
            quotes = daily_quotes.copy()
            quotes[quote_code] = quotes[quote_code].astype(str).str.zfill(6)
            quotes = quotes[quotes[quote_code].isin(codes)]
            if not quotes.empty:
                candidates = candidates.merge(
                    quotes, left_on="code", right_on=quote_code, how="left"
                )
        name_col = self._name_column(candidates)
        if name_col and "name" not in candidates.columns:
            candidates["name"] = candidates[name_col]
        elif "name_x" in candidates.columns:
            candidates["name"] = candidates["name_x"]
        elif "name_y" in candidates.columns:
            candidates["name"] = candidates["name_y"]
        candidates = self._build_behavior_features(candidates)
        candidates["sentiment_score"] = 0.0
        if "连板数" in candidates.columns:
            candidates["sentiment_score"] += self._rank_score(candidates["连板数"], 25)
        candidates["sentiment_score"] += self._rank_score(candidates["pct_chg"], 15, ascending=False)
        candidates["sentiment_score"] += candidates["close_position"] * 20
        candidates["sentiment_score"] += candidates["not_broken_score"] * 15
        if "封单资金" in candidates.columns:
            candidates["sentiment_score"] += self._rank_score(candidates["封单资金"], 15)
        if "换手率" in candidates.columns:
            turnover_norm = self._to_number(candidates["换手率"])
            candidates["sentiment_score"] += ((turnover_norm.between(3, 25)).astype(float)) * 10
        candidates["sentiment_score"] += self._rank_score(candidates["amount"], 10)
        candidates["leader_type"] = "情绪龙头"
        candidates["leader_reason"] = candidates.apply(
            lambda row: self._format_behavior_reason(row, ["连板/涨停高度", "封板结构强", "资金封单大", "情绪主导股"]),
            axis=1,
        )
        candidates = candidates.sort_values("sentiment_score", ascending=False)
        top = candidates.head(min(5, len(candidates)))
        logger.info(f"情绪龙头: {', '.join(top['name'].astype(str).tolist())}")
        return top

    def find_capacity_leaders(
        self,
        concept_stocks: pd.DataFrame,
        daily_quotes: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        容量龙头：大资金愿意参与的标的。
        不看 PE/PB，看成交额规模、成交额相对放大、板块内涨幅强弱、收盘强度。
        """
        merged = self._merge_concept_quotes(concept_stocks, daily_quotes)
        if merged.empty:
            return pd.DataFrame()
        merged = self._build_behavior_features(merged)
        merged["capacity_score"] = 0.0
        merged["capacity_score"] += self._rank_score(merged["amount"], 30)
        merged["capacity_score"] += self._rank_score(merged["volume"], 20)
        merged["capacity_score"] += self._rank_score(merged["pct_chg"], 20)
        merged["capacity_score"] += merged["close_position"] * 15
        merged["capacity_score"] += merged["touch_limit_like"] * 10
        merged["capacity_score"] += merged["range_control_score"] * 5
        merged["leader_type"] = "容量龙头"
        merged["leader_reason"] = merged.apply(
            lambda row: self._format_behavior_reason(row, ["成交额大", "成交量强", "板块内强势", "收盘结构好"]),
            axis=1,
        )
        merged = merged.sort_values("capacity_score", ascending=False)
        top = merged.head(min(5, len(merged)))
        logger.info(f"容量龙头: {', '.join(top['name'].astype(str).tolist())}")
        return top

    def find_trend_reversal_stocks(
        self, daily_quotes: pd.DataFrame, lookback_days: int = 60
    ) -> pd.DataFrame:
        """
        趋势逆转股票识别：
        1. 底部放量突破
        2. 均线从粘合到发散
        3. MACD 底背离
        4. 首板突破长期均线
        """
        if daily_quotes.empty:
            return pd.DataFrame()
        try:
            continuous_limit = self.market.get_continuous_limit_up()
        except Exception:
            continuous_limit = pd.DataFrame()
        candidates = daily_quotes[
            (daily_quotes["pct_chg"] > 3) &
            (daily_quotes["pct_chg"] < 9.5)
        ].copy()
        if candidates.empty:
            return pd.DataFrame()
        reversal_stocks = []
        for _, stock in candidates.iterrows():
            code = stock["code"]
            try:
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=lookback_days + 30)).strftime("%Y%m%d")
                kline = self.market.get_daily_kline(code, start_date, end_date)
                if kline.empty or len(kline) < 20:
                    continue
                kline = self.market.calculate_technical_indicators(kline)
                latest = kline.iloc[-1]
                reversal_score = 0
                signals = []
                if latest["close"] > latest["ma20"] and kline.iloc[-2]["close"] <= kline.iloc[-2]["ma20"]:
                    reversal_score += 20
                    signals.append("上穿MA20")
                if latest["close"] > latest["ma60"] and kline.iloc[-5]["close"] < kline.iloc[-5]["ma60"]:
                    reversal_score += 25
                    signals.append("突破MA60")
                vol_ratio = latest["volume"] / kline["volume"].iloc[-20:].mean()
                if vol_ratio > 1.5:
                    reversal_score += 20
                    signals.append(f"放量{vol_ratio:.1f}倍")
                if latest["rsi14"] < 40 and kline["rsi14"].iloc[-2] < 35:
                    reversal_score += 10
                    signals.append("RSI超卖反弹")
                if latest["macd_hist"] > 0 and kline["macd_hist"].iloc[-2] <= 0:
                    reversal_score += 15
                    signals.append("MACD金叉")
                recent_low = kline["close"].iloc[-20:].min()
                if latest["close"] > recent_low * 1.05:
                    reversal_score += 10
                    signals.append("脱离底部")
                if reversal_score >= 40:
                    reversal_stocks.append({
                        "code": code,
                        "name": stock.get("name", ""),
                        "reversal_score": reversal_score,
                        "signals": "|".join(signals),
                        "pct_chg": stock["pct_chg"],
                        "volume_ratio": round(vol_ratio, 1),
                        "close": latest["close"],
                        "ma20": round(latest["ma20"], 2),
                        "ma60": round(latest["ma60"], 2),
                    })
            except Exception as e:
                logger.debug(f"分析 {code} 趋势逆转时出错: {e}")
                continue
        result = pd.DataFrame(reversal_stocks).sort_values("reversal_score", ascending=False)
        if not result.empty:
            logger.info(f"发现 {len(result)} 只趋势逆转候选股")
        return result

    def identify_all_leaders(
        self, concept_name: str
    ) -> Dict[str, pd.DataFrame]:
        logger.info(f"=== 分析 [{concept_name}] 龙头 ===")
        concept_stocks = self.market.get_concept_board_components(concept_name)
        if concept_stocks.empty:
            logger.warning(f"概念 [{concept_name}] 无成分股数据")
            return {}
        daily_quotes = self.market.get_realtime_quotes()
        limit_up_pool = self.market.get_limit_up_pool()
        return {
            "logic_leaders": self.find_logic_leaders(concept_name, concept_stocks, daily_quotes),
            "sentiment_leaders": self.find_sentiment_leaders(limit_up_pool, concept_stocks, daily_quotes),
            "capacity_leaders": self.find_capacity_leaders(concept_stocks, daily_quotes),
            "reversal_candidates": self.find_trend_reversal_stocks(daily_quotes),
        }

    def scan_hot_concepts(self, top_n: int = 10) -> List[str]:
        concept_board = self.market.get_concept_board()
        if concept_board.empty:
            return []
        if "涨跌幅" in concept_board.columns:
            concept_board = concept_board.sort_values("涨跌幅", ascending=False)
        hot = concept_board.head(top_n)
        concepts = hot["板块名称"].tolist() if "板块名称" in hot.columns else []
        logger.info(f"热门概念 Top{top_n}: {concepts[:5]}...")
        return concepts

    def find_leaders(
        self, limit_pool: "pd.DataFrame", strong_pool: "pd.DataFrame"
    ) -> Dict:
        """便捷方法：从涨停池中识别三类龙头"""
        import pandas as pd
        if limit_pool is None or limit_pool.empty:
            return {"logic": [], "sentiment": [], "capacity": []}
        daily_quotes = self.market.get_realtime_quotes()
        result = {"logic": [], "sentiment": [], "capacity": []}
        try:
            sentiment_leaders = self.find_sentiment_leaders(limit_pool, limit_pool, daily_quotes)
            if sentiment_leaders is not None and not sentiment_leaders.empty:
                names = sentiment_leaders["名称"].tolist() if "名称" in sentiment_leaders.columns else []
                result["sentiment"] = names[:5]
        except Exception as e:
            logger.warning(f"情绪龙头识别失败: {e}")
        try:
            capacity_leaders = self.find_capacity_leaders(limit_pool, daily_quotes)
            if capacity_leaders is not None and not capacity_leaders.empty:
                names = capacity_leaders["name"].tolist() if "name" in capacity_leaders.columns else (
                    capacity_leaders["名称"].tolist() if "名称" in capacity_leaders.columns else []
                )
                result["capacity"] = names[:5]
        except Exception as e:
            logger.warning(f"容量龙头识别失败: {e}")
        result["logic"] = []
        return result