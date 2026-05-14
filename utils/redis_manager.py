from __future__ import annotations

import json
from typing import Any, Dict, Optional

import redis
from loguru import logger

from config.settings import DATABASE_CONFIG


class RedisManager:
    _instance: Optional[RedisManager] = None

    def __init__(self, **kwargs):
        if not hasattr(self, "_pool"):
            try:
                self._pool = redis.BlockingConnectionPool.from_url(
                    DATABASE_CONFIG["redis"]["uri"],
                    max_connections=DATABASE_CONFIG["redis"]["max_connections"],
                    decode_responses=True,
                    **kwargs,
                )
                self.client = redis.Redis(connection_pool=self._pool)
                self.client.ping()
                logger.info("Redis 连接成功")
            except redis.exceptions.ConnectionError as e:
                logger.error(f"Redis 连接失败: {e}")
                self._pool = None
                self.client = None

    def hset_dict(self, key: str, data: Dict[str, Any], ex: int = 60) -> bool:
        if not self.client:
            return False
        try:
            mapping = {
                str(k): json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                for k, v in data.items()
            }
            self.client.hset(key, mapping=mapping)
            if ex:
                self.client.expire(key, ex)
            return True
        except Exception as e:
            logger.warning(f"Redis HSET 失败 key={key}: {e}")
            return False

    def hgetall_dict(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        try:
            raw = self.client.hgetall(key)
            data = {}
            for k, v in raw.items():
                try:
                    data[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    data[k] = v
            return data
        except Exception as e:
            logger.warning(f"Redis HGETALL 失败 key={key}: {e}")
            return None

    def publish(self, channel: str, message: Dict[str, Any]) -> int:
        if not self.client:
            return 0
        try:
            return self.client.publish(channel, json.dumps(message, default=str))
        except Exception as e:
            logger.warning(f"Redis PUBLISH 失败 channel={channel}: {e}")
            return 0

    def get_subscriber(self, channel: str):
        if not self.client:
            return None
        pubsub = self.client.pubsub()
        pubsub.subscribe(channel)
        return pubsub


def get_redis_manager() -> RedisManager:
    global _REDIS_MANAGER
    try:
        return _REDIS_MANAGER
    except NameError:
        _REDIS_MANAGER = RedisManager()
        return _REDIS_MANAGER
