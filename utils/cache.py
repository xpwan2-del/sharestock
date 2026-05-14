from base64 import b64decode, b64encode
import hashlib
import json
import pickle
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

from config.settings import DATA_DIR

try:
    from utils.redis_manager import get_redis_manager
except Exception:
    get_redis_manager = None

CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def cache_key(*args, **kwargs):
    raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


import pandas as pd


def _is_cacheable(result: Any) -> bool:
    if result is None:
        return False
    if isinstance(result, pd.DataFrame):
        return not result.empty
    if isinstance(result, (list, tuple, set, dict)):
        return len(result) > 0
    return True


def disk_cache(ttl_hours: int = 24):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}_{cache_key(*args, **kwargs)}"
            cache_file = CACHE_DIR / f"{key}.pkl"
            if cache_file.exists():
                age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
                if age < timedelta(hours=ttl_hours):
                    with open(cache_file, "rb") as f:
                        cached = pickle.load(f)
                    if _is_cacheable(cached):
                        return cached
                    try:
                        cache_file.unlink()
                    except Exception:
                        pass
            result = func(*args, **kwargs)
            if _is_cacheable(result):
                with open(cache_file, "wb") as f:
                    pickle.dump(result, f)
            return result
        return wrapper
    return decorator


def redis_cache(key_prefix: str, ttl_seconds: int = 60):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if get_redis_manager is None:
                return func(*args, **kwargs)
            redis_mgr = get_redis_manager()
            if not getattr(redis_mgr, "client", None):
                return func(*args, **kwargs)
            key = f"{key_prefix}:{func.__name__}:{cache_key(*args, **kwargs)}"
            try:
                cached = redis_mgr.client.get(key)
                if cached:
                    return pickle.loads(b64decode(cached.encode("utf-8")))
            except Exception:
                pass
            result = func(*args, **kwargs)
            try:
                redis_mgr.client.setex(key, ttl_seconds, b64encode(pickle.dumps(result)).decode("utf-8"))
            except Exception:
                pass
            return result
        return wrapper
    return decorator

