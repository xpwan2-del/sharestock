import re
import jieba
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from collections import Counter
from loguru import logger
from snownlp import SnowNLP

from config.settings import DATA_DIR
from utils.cache import disk_cache

SENTIMENT_DIR = DATA_DIR / "sentiment"
SENTIMENT_DIR.mkdir(exist_ok=True)

STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "及", "与", "或", "但", "被", "从", "以", "之", "而", "于", "则",
    "为", "对", "所", "能", "可", "过", "将", "把", "如", "等",
}

BULLISH_WORDS = {
    "涨停": 5, "大涨": 4, "利好": 4, "突破": 3, "龙头": 3,
    "主升浪": 5, "牛市": 4, "爆发": 4, "起飞": 3, "涨停板": 5,
    "连板": 5, "封板": 4, "翻倍": 5, "妖股": 3, "牛股": 3,
    "满仓": 3, "加仓": 2, "抄底": 2, "反弹": 2, "反转": 3,
    "增持": 3, "回购": 2, "放量": 3, "金叉": 2, "新高": 3,
    "增长": 2, "超预期": 4, "业绩暴增": 5,
}

BEARISH_WORDS = {
    "跌停": -5, "大跌": -4, "利空": -4, "破位": -3, "崩盘": -5,
    "暴跌": -5, "踩踏": -4, "炸板": -3, "天地板": -5, "核按钮": -4,
    "割肉": -3, "止损": -2, "套牢": -3, "腰斩": -5, "退市": -5,
    "减持": -3, "爆雷": -5, "亏损": -3, "ST": -4, "死叉": -2,
    "缩量": -2, "破发": -3, "踩雷": -4, "业绩暴雷": -5,
}


class MarketSentimentAnalyzer:
    def analyze_market_breadth(self, breadth_data: Dict) -> Dict:
        if not breadth_data:
            return {"sentiment": "unknown", "score": 50}
        up_ratio = breadth_data.get("up_ratio", 50)
        limit_up = breadth_data.get("limit_up_count", 0)
        limit_down = breadth_data.get("limit_down_count", 0)
        avg_pct = breadth_data.get("avg_pct_chg", 0)
        score = 50.0
        score += (up_ratio - 50) * 0.5
        score += min(limit_up, 200) * 0.1 - min(limit_down, 200) * 0.2
        score += avg_pct * 2
        score = max(0, min(100, score))
        if score >= 80:
            sentiment = "极度亢奋"
        elif score >= 65:
            sentiment = "乐观"
        elif score >= 45:
            sentiment = "中性"
        elif score >= 30:
            sentiment = "悲观"
        else:
            sentiment = "极度恐慌"
        return {
            "sentiment": sentiment,
            "score": round(score, 1),
            "up_ratio": up_ratio,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "avg_pct_chg": avg_pct,
        }

    def analyze_volume_sentiment(self, realtime_quotes: pd.DataFrame) -> Dict:
        if realtime_quotes.empty:
            return {}
        vol_ratio = realtime_quotes.get("volume_ratio", pd.Series(dtype=float))
        vol_ratio = vol_ratio.dropna()
        if len(vol_ratio) == 0:
            return {}
        high_vol = (vol_ratio > 2).sum()
        low_vol = (vol_ratio < 0.5).sum()
        total = len(vol_ratio)
        return {
            "high_volume_ratio": round(high_vol / total * 100, 1),
            "low_volume_ratio": round(low_vol / total * 100, 1),
            "avg_volume_ratio": round(float(vol_ratio.mean()), 2),
            "volume_active": high_vol > total * 0.15,
        }

    def analyze_northbound_sentiment(self, north_data: Dict) -> Dict:
        net_yi = north_data.get("net_flow_yi") if north_data else None
        if net_yi is None:
            return {"signal": "neutral", "net_flow_yi": 0}
        net = net_yi * 1e8
        signal = "neutral"
        if net > 5e9:
            signal = "strong_inflow"
        elif net > 1e9:
            signal = "inflow"
        elif net < -5e9:
            signal = "strong_outflow"
        elif net < -1e9:
            signal = "outflow"
        return {
            "signal": signal,
            "net_flow": net,
            "net_flow_yi": round(net / 1e8, 2),
        }

    def analyze_limit_up_quality(self, limit_up_data: pd.DataFrame) -> Dict:
        if limit_up_data is None or limit_up_data.empty:
            return {"quality": "low", "solid_count": 0}
        solid = 0
        fragile = 0
        for _, row in limit_up_data.iterrows():
            open_pct = float(row.get("open_pct", 0)) if row.get("open_pct") else 0
            if open_pct > 8:
                solid += 1
            elif open_pct < 3:
                fragile += 1
        total = len(limit_up_data)
        return {
            "total": total,
            "solid_count": solid,
            "fragile_count": fragile,
            "solid_ratio": round(solid / total * 100, 1) if total else 0,
            "quality": "high" if solid > total * 0.3 else ("medium" if solid > total * 0.15 else "low"),
        }

    def calculate_board_strength(self, board_data: pd.DataFrame) -> pd.DataFrame:
        if board_data is None or board_data.empty:
            return pd.DataFrame()
        if "涨跌幅" in board_data.columns:
            board_data = board_data.copy()
            board_data["strength_score"] = board_data["涨跌幅"].apply(
                lambda x: min(100, max(0, float(x) * 5 + 50))
            )
            board_data = board_data.sort_values("涨跌幅", ascending=False)
            logger.info(f"板块强弱分析: 最强 {board_data.iloc[0].get('板块名称', '')} "
                        f"涨{board_data.iloc[0].get('涨跌幅', 0)}%")
        return board_data

    def analyze_sentiment(
        self,
        limit_pool: "pd.DataFrame" = None,
        north_data: Dict = None,
        breadth_data: Dict = None,
    ) -> Dict:
        """便捷方法：一次性分析市场情绪"""
        import pandas as pd
        if limit_pool is None:
            limit_pool = pd.DataFrame()
        if north_data is None:
            north_data = {}
        if breadth_data is None:
            breadth_data = {}
        volume_sent = {}
        limit_quality = self.analyze_limit_up_quality(limit_pool)
        north_sent = self.analyze_northbound_sentiment(north_data)
        breadth_analysis = self.analyze_market_breadth(breadth_data)
        result = self.get_comprehensive_sentiment(
            breadth_analysis, volume_sent, north_sent, limit_quality
        )
        result["sentiment_label"] = result.get("level", "中性")
        result["composite_score"] = result.get("overall_score", 50)
        return result

    def get_comprehensive_sentiment(
        self,
        breadth: Dict,
        volume_sent: Dict,
        north_sent: Dict,
        limit_up_quality: Dict,
    ) -> Dict:
        score = 50.0
        if breadth:
            score += (breadth.get("score", 50) - 50)
        if volume_sent and volume_sent.get("volume_active"):
            score += 10
        if north_sent:
            net_flow_yi = north_sent.get("net_flow_yi", 0)
            score += min(max(net_flow_yi / 2, -15), 15)
        if limit_up_quality and limit_up_quality.get("quality") == "high":
            score += 5
        score = max(0, min(100, score))
        level = (
            "极度亢奋" if score >= 80 else
            "偏乐观" if score >= 60 else
            "中性" if score >= 40 else
            "偏悲观" if score >= 20 else
            "极度恐慌"
        )
        return {
            "overall_score": round(score, 1),
            "level": level,
            "components": {
                "breadth": breadth.get("score", 50) if breadth else 50,
                "volume_active": volume_sent.get("volume_active", False) if volume_sent else False,
                "north_signal": north_sent.get("signal", "neutral") if north_sent else "neutral",
                "limit_up_quality": limit_up_quality.get("quality", "low") if limit_up_quality else "low",
            },
        }