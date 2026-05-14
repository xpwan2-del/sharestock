import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger

from config.settings import MARKET_CONFIG, DATA_DIR
from data.market_data import MarketDataCollector
from analysis.leader_finder import LeaderFinder
from analysis.trend_reversal import TrendReversalDetector
from sentiment.market_sentiment import MarketSentimentAnalyzer

TRADING_DIR = DATA_DIR / "trading"
TRADING_DIR.mkdir(exist_ok=True)


class SignalGenerator:
    def __init__(self):
        self.market = MarketDataCollector()
        self.leader_finder = LeaderFinder()
        self.reversal_detector = TrendReversalDetector()
        self.sentiment_analyzer = MarketSentimentAnalyzer()

    def generate_leader_signals(self) -> List[Dict]:
        hot_concepts = self.leader_finder.scan_hot_concepts(top_n=10)
        signals = []
        for concept in hot_concepts[:5]:
            try:
                leaders = self.leader_finder.identify_all_leaders(concept)
                if not leaders:
                    continue
                for leader_type, df in leaders.items():
                    if df is None or df.empty:
                        continue
                    codes = df["code"].tolist() if "code" in df.columns else (
                        df["代码"].tolist() if "代码" in df.columns else []
                    )
                    names = df["name"].tolist() if "name" in df.columns else (
                        df["名称"].tolist() if "名称" in df.columns else codes
                    )
                    signals.append({
                        "concept": concept,
                        "type": leader_type,
                        "stocks": list(zip(codes, names)),
                        "count": len(codes),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "signal": "leader_watch",
                    })
            except Exception as e:
                logger.warning(f"生成 [{concept}] 龙头信号失败: {e}")
        logger.info(f"龙头信号: {len(signals)} 个概念")
        return signals

    def generate_reversal_signals(
        self, stock_codes: List[str]
    ) -> List[Dict]:
        signals = []
        for code in stock_codes:
            try:
                result = self.reversal_detector.comprehensive_reversal_scan(code)
                if result.get("has_data") and result["reversal_type"] in (
                    "strong_reversal", "potential_reversal"
                ):
                    signals.append({
                        "code": code,
                        "name": result.get("name", ""),
                        "signal": "reversal_buy",
                        "strength": result["reversal_score"],
                        "type": result["reversal_type"],
                        "signals": result.get("signals", []),
                        "close": result.get("latest_close", 0),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    })
            except Exception as e:
                logger.debug(f"分析 {code} 逆转信号失败: {e}")
        signals.sort(key=lambda x: x["strength"], reverse=True)
        logger.info(f"逆转信号: {len(signals)} 只")
        return signals[:20]

    def generate_sentiment_signal(self) -> Dict:
        try:
            breadth = self.market.get_market_breadth()
            sentiment = self.sentiment_analyzer.analyze_market_breadth(breadth)
        except Exception:
            sentiment = {"sentiment": "unknown", "score": 50}
        action = "hold"
        if sentiment.get("score", 50) >= 80:
            action = "caution"
        elif sentiment.get("score", 50) >= 65:
            action = "buy"
        elif sentiment.get("score", 50) <= 20:
            action = "opportunity"
        elif sentiment.get("score", 50) <= 35:
            action = "reduce"
        return {
            "sentiment_score": sentiment.get("score", 50),
            "sentiment": sentiment.get("sentiment", ""),
            "action": action,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def generate_limit_up_signals(self) -> Dict:
        pool = self.market.get_limit_up_pool()
        continuous = self.market.get_continuous_limit_up()
        return {
            "daily_limit_up": len(pool) if pool is not None else 0,
            "continuous_limit_up": len(continuous) if continuous is not None else 0,
            "sentiment": "hot" if len(continuous) > 30 else ("warm" if len(continuous) > 10 else "cold") if continuous is not None else "unknown",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def get_top_stocks_by_turnover(self, top_n: int = 20) -> pd.DataFrame:
        quotes = self.market.get_realtime_quotes()
        if quotes.empty:
            return pd.DataFrame()
        result = quotes.nlargest(top_n, "amount") if "amount" in quotes.columns else quotes.nlargest(top_n, "volume")
        return result[["code", "name", "price", "pct_chg", "amount", "turnover"]].head(top_n) if all(c in result.columns for c in ["code", "name", "price", "pct_chg"]) else result.head(top_n)

    def generate_all_signals(self) -> List[Dict]:
        """生成所有信号的综合结果"""
        signals = []
        try:
            sentiment = self.generate_sentiment_signal()
            signals.append({"type": "sentiment", **sentiment})
        except Exception as e:
            logger.warning(f"情绪信号生成失败: {e}")
        try:
            limit = self.generate_limit_up_signals()
            signals.append({"type": "limit_up", **limit})
        except Exception as e:
            logger.warning(f"涨停信号生成失败: {e}")
        try:
            leaders = self.generate_leader_signals()
            if leaders:
                signals.extend(leaders)
        except Exception as e:
            logger.warning(f"龙头信号生成失败: {e}")
        try:
            top_stocks = self.get_top_stocks_by_turnover(10)
            if not top_stocks.empty:
                codes = top_stocks["code"].tolist()
                reversals = self.generate_reversal_signals(codes)
                if reversals:
                    signals.extend(reversals)
        except Exception as e:
            logger.warning(f"逆转信号生成失败: {e}")
        return signals