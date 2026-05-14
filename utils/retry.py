import time
from functools import wraps
from loguru import logger


def retry_on_disconnect(max_retries: int = 3, base_delay: float = 2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    msg = str(e)
                    if "Connection" in msg or "RemoteDisconnected" in msg or "timeout" in msg.lower():
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            logger.debug(f"{func.__name__} 网络异常，{delay}s后重试({attempt+1}/{max_retries})")
                            time.sleep(delay)
                            continue
            raise last_exception
        return wrapper
    return decorator