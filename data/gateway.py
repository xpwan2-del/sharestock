from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

import pandas as pd
from loguru import logger

from data.market_data import MarketDataCollector
from utils.event_bus import get_event_bus
from utils.redis_manager import get_redis_manager


class MarketDataGateway:
    def __init__(self):
        self.market = MarketDataCollector()
        self.redis = get_redis_manager()
        self.event_bus = get_event_bus()

    def get_quotes(self, symbols: Optional[List[str]] = None, publish: bool = True) -> pd.DataFrame:
        quotes = self.market.get_realtime_quotes(symbols)
        if quotes is None or quotes.empty:
            return pd.DataFrame()
        self.store_quotes(quotes)
        if publish:
            self.event_bus.publish(
                "MARKET_TICK",
                {"quotes": quotes, "symbols": symbols or []},
                source="MarketDataGateway",
            )
        return quotes

    async def get_quotes_async(self, symbols: Optional[List[str]] = None, publish: bool = True) -> pd.DataFrame:
        return await asyncio.to_thread(self.get_quotes, symbols, publish)

    def store_quotes(self, quotes: pd.DataFrame, ttl_seconds: int = 15) -> int:
        if quotes is None or quotes.empty or not getattr(self.redis, "client", None):
            return 0
        if "code" not in quotes.columns:
            return 0
        saved = 0
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for _, row in quotes.iterrows():
            code = str(row.get("code", ""))
            if not code:
                continue
            item_data = row.to_dict()
            item_data["_snapshot_time"] = timestamp
            if self.redis.hset_dict(f"quant:snapshot:{code}", item_data, ex=ttl_seconds):
                saved += 1
        logger.debug(f"行情快照写入 Redis: {saved}/{len(quotes)}")
        return saved

    def get_cached_quote(self, code: str) -> dict:
        data = self.redis.hgetall_dict(f"quant:snapshot:{code}")
        return data or {}
