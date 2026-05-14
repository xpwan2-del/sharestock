from typing import List, Dict
from loguru import logger

from sentiment.news_sentiment import NewsSentimentAnalyzer
from data.announcement import AnnouncementCollector


class AnnouncementNLPAnalyzer:
    def __init__(self):
        self.news_analyzer = NewsSentimentAnalyzer()
        self.announcement_collector = AnnouncementCollector()

    def analyze_announcement(self, title: str, content: str = "") -> Dict:
        impact = self.announcement_collector.check_announcement_impact(title, content)
        sentiment = self.news_analyzer.analyze_text(content, title) if content else {"sentiment": "neutral", "score": 0}
        combined_score = impact["score"] * 0.6 + sentiment["score"] * 5 * 0.4
        combined_level = (
            "strong_bullish" if combined_score >= 2.5 else
            "bullish" if combined_score >= 0.5 else
            "neutral" if combined_score > -0.5 else
            "bearish" if combined_score > -2.5 else
            "strong_bearish"
        )
        return {
            "title": title,
            "impact_level": impact["level"],
            "impact_category": impact["category"],
            "impact_keywords": impact["keywords_matched"],
            "sentiment": sentiment.get("sentiment", "neutral"),
            "combined_score": round(combined_score, 2),
            "combined_level": combined_level,
        }

    def analyze_batch(
        self, announcements: List[Dict]
    ) -> List[Dict]:
        results = []
        for ann in announcements:
            result = self.analyze_announcement(
                ann.get("title", ""),
                ann.get("content", ""),
            )
            result["stock_code"] = ann.get("stock_code", "")
            result["pub_date"] = ann.get("pub_date", "")
            result["source"] = ann.get("source", "")
            results.append(result)
        significant = [r for r in results if r["combined_level"] not in ("neutral",)]
        logger.info(f"公告分析: {len(results)} 条, 重要 {len(significant)} 条")
        return results