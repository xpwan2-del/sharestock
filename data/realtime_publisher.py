from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

from loguru import logger

from config.settings import REALTIME_CONFIG
from data.gateway import MarketDataGateway


class RealtimeDataPublisher:
    def __init__(self, watch_list: Optional[List[str]] = None, interval_seconds: Optional[int] = None):
        self.watch_list = watch_list or REALTIME_CONFIG["watch_list"]
        self.interval_seconds = interval_seconds or REALTIME_CONFIG["scan_interval_seconds"]
        self.gateway = MarketDataGateway()
        self._running = False
        self.last_publish_at = None
        self.publish_count = 0

    async def publish_once(self):
        quotes = await self.gateway.get_quotes_async(self.watch_list or None, publish=True)
        if quotes is None or quotes.empty:
            logger.warning("实时行情发布跳过: 无可用行情")
            return quotes
        self.last_publish_at = datetime.now()
        self.publish_count += 1
        logger.info(f"实时行情已发布: {len(quotes)} 条, batch={self.publish_count}")
        return quotes

    async def start(self):
        self._running = True
        logger.info(f"实时行情发布服务启动, 标的数={len(self.watch_list)}, 间隔={self.interval_seconds}s")
        while self._running:
            try:
                await self.publish_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"实时行情发布异常: {e}")
            await asyncio.sleep(self.interval_seconds)

    def stop(self):
        self._running = False
        logger.info("实时行情发布服务停止")
