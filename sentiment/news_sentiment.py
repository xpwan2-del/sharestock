import re
import jieba
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from loguru import logger
from snownlp import SnowNLP

from config.settings import DATA_DIR
from utils.cache import disk_cache
from sentiment.market_sentiment import BULLISH_WORDS, BEARISH_WORDS, STOP_WORDS

NEWS_DIR = DATA_DIR / "news"
NEWS_DIR.mkdir(exist_ok=True)


class NewsSentimentAnalyzer:
    def tokenize_chinese(self, text: str) -> List[str]:
        if not text:
            return []
        words = jieba.lcut(text)
        return [w for w in words if w.strip() and w not in STOP_WORDS]

    def analyze_snownlp(self, text: str) -> float:
        try:
            s = SnowNLP(text)
            return s.sentiments
        except Exception:
            return 0.5

    def keyword_sentiment_score(self, words: List[str]) -> float:
        if not words:
            return 0.0
        bull_count = sum(BULLISH_WORDS.get(w, 0) for w in words)
        bear_count = sum(BEARISH_WORDS.get(w, 0) for w in words)
        total_weight = sum(
            abs(BULLISH_WORDS.get(w, 0)) + abs(BEARISH_WORDS.get(w, 0))
            for w in words
        )
        if total_weight == 0:
            return 0.0
        return (bull_count + bear_count) / total_weight

    def analyze_text(
        self, text: str, title: str = ""
    ) -> Dict[str, any]:
        if not text and not title:
            return {"score": 0, "sentiment": "neutral", "confidence": 0}
        full_text = f"{title} {text}"
        words = self.tokenize_chinese(full_text)
        keyword_score = self.keyword_sentiment_score(words)
        snownlp_score = self.analyze_snownlp(full_text[:500])
        raw_score = keyword_score * 0.6 + (snownlp_score - 0.5) * 2 * 0.4
        score = max(-1.0, min(1.0, raw_score))
        confidence = 0.5 + abs(score)
        if score > 0.3:
            sentiment = "positive"
        elif score > 0.1:
            sentiment = "slightly_positive"
        elif score > -0.1:
            sentiment = "neutral"
        elif score > -0.3:
            sentiment = "slightly_negative"
        else:
            sentiment = "negative"
        key_bullish = [w for w in words if w in BULLISH_WORDS]
        key_bearish = [w for w in words if w in BEARISH_WORDS]
        return {
            "score": round(score, 4),
            "sentiment": sentiment,
            "confidence": round(confidence, 4),
            "snownlp_score": round(snownlp_score, 4),
            "keyword_score": round(keyword_score, 4),
            "key_bullish_words": key_bullish[:10],
            "key_bearish_words": key_bearish[:10],
        }

    def analyze_news_batch(
        self, articles: List[Dict[str, str]]
    ) -> pd.DataFrame:
        results = []
        for art in articles:
            title = art.get("title", "")
            content = art.get("content", "")
            if not title and not content:
                continue
            analysis = self.analyze_text(content, title)
            results.append({
                "title": title[:100],
                "source": art.get("source", ""),
                "sentiment": analysis["sentiment"],
                "score": analysis["score"],
                "confidence": analysis["confidence"],
                "key_bullish": ",".join(analysis["key_bullish_words"]),
                "key_bearish": ",".join(analysis["key_bearish_words"]),
            })
        df = pd.DataFrame(results)
        if not df.empty:
            positive_count = (df["sentiment"].str.contains("positive")).sum()
            negative_count = (df["sentiment"].str.contains("negative")).sum()
            logger.info(
                f"新闻批量分析: {len(df)} 篇, "
                f"正面{positive_count}, 负面{negative_count}, "
                f"平均分{df['score'].mean():.3f}"
            )
        return df

    def get_stock_news_sentiment(self, stock_name: str, stock_code: str) -> Dict:
        """利用 AKShare 获取个股新闻并分析情绪"""
        import akshare as ak
        results = []
        try:
            df = ak.stock_news_em(symbol=stock_code)
            if df is not None and not df.empty:
                recent = df.head(20)
                for _, row in recent.iterrows():
                    title = str(row.get("标题", "") or row.get("title", ""))
                    content = str(row.get("内容", "") or row.get("content", ""))
                    analysis = self.analyze_text(content, title)
                    results.append({
                        "title": title[:80],
                        "sentiment": analysis["sentiment"],
                        "score": analysis["score"],
                    })
        except Exception as e:
            logger.warning(f"获取 {stock_code} 新闻失败: {e}")
        if not results:
            return {"stock": stock_name, "avg_score": 0, "sentiment": "neutral", "count": 0}
        scores = [r["score"] for r in results]
        avg_score = np.mean(scores)
        sentiment = (
            "positive" if avg_score > 0.2 else
            "negative" if avg_score < -0.2 else
            "neutral"
        )
        return {
            "stock": stock_name,
            "code": stock_code,
            "avg_score": round(float(avg_score), 4),
            "sentiment": sentiment,
            "positive_count": sum(1 for r in results if r["sentiment"] in ("positive", "slightly_positive")),
            "negative_count": sum(1 for r in results if r["sentiment"] in ("negative", "slightly_negative")),
            "count": len(results),
            "details": results[:5],
        }