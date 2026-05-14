from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Iterable, Optional

from loguru import logger

from config.settings import DAILY_RUN_TIME


@lru_cache(maxsize=8)
def _get_trade_dates(start: Optional[str] = None, end: Optional[str] = None) -> set[str]:
    try:
        import akshare as ak

        df = ak.tool_trade_date_hist_sina()
        if df is None or df.empty:
            raise ValueError("empty trade calendar")
        if "trade_date" in df.columns:
            series = df["trade_date"]
        else:
            series = df.iloc[:, 0]
        trade_dates = {
            pd_date.strftime("%Y-%m-%d") if hasattr(pd_date, "strftime") else str(pd_date)[:10]
            for pd_date in series
        }
        if start or end:
            return {
                d for d in trade_dates
                if (start is None or d >= start) and (end is None or d <= end)
            }
        return trade_dates
    except Exception as e:
        logger.debug(f"交易日历加载失败，回退到工作日模式: {e}")
        return set()


def _weekday_trade_dates(start: date, end: date) -> Iterable[str]:
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            yield cur.strftime("%Y-%m-%d")
        cur += timedelta(days=1)


@lru_cache(maxsize=32)
def is_trading_day(d: Optional[date] = None) -> bool:
    if d is None:
        d = datetime.now().date()
    trade_dates = _get_trade_dates()
    day = d.strftime("%Y-%m-%d")
    if trade_dates:
        return day in trade_dates
    return d.weekday() < 5


@lru_cache(maxsize=32)
def get_latest_trading_day() -> str:
    today = datetime.now().date()
    trade_dates = _get_trade_dates()
    if trade_dates:
        for i in range(10):
            candidate = today - timedelta(days=i)
            c = candidate.strftime("%Y-%m-%d")
            if c in trade_dates:
                return candidate.strftime("%Y%m%d")
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    return today.strftime("%Y%m%d")


def get_today_formatted() -> str:
    return datetime.now().strftime("%Y%m%d")


def is_market_open() -> bool:
    now = datetime.now()
    if not is_trading_day(now.date()):
        return False
    morning_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    morning_end = now.replace(hour=11, minute=30, second=0, microsecond=0)
    afternoon_start = now.replace(hour=13, minute=0, second=0, microsecond=0)
    afternoon_end = now.replace(hour=15, minute=0, second=0, microsecond=0)
    return (morning_start <= now <= morning_end) or (afternoon_start <= now <= afternoon_end)


def get_recent_trading_days(n: int = 5) -> list:
    days = []
    d = datetime.now().date()
    trade_dates = _get_trade_dates()
    if trade_dates:
        while len(days) < n:
            day = d.strftime("%Y-%m-%d")
            if day in trade_dates:
                days.append(d.strftime("%Y%m%d"))
            d -= timedelta(days=1)
        return days
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return days


def get_next_trading_day(from_date: Optional[date] = None) -> str:
    cur = from_date or datetime.now().date()
    trade_dates = _get_trade_dates()
    if trade_dates:
        for i in range(1, 20):
            candidate = cur + timedelta(days=i)
            if candidate.strftime("%Y-%m-%d") in trade_dates:
                return candidate.strftime("%Y-%m-%d")
    candidate = cur + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.strftime("%Y-%m-%d")


def get_next_daily_run_datetime(run_time: str = DAILY_RUN_TIME, now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now()
    hour, minute = [int(x) for x in run_time.split(":", 1)]
    target_today = datetime.combine(now.date(), time(hour=hour, minute=minute))
    if is_trading_day(now.date()) and now < target_today:
        return target_today
    next_trading_day = get_next_trading_day(now.date())
    next_day = datetime.strptime(next_trading_day, "%Y-%m-%d").date()
    return datetime.combine(next_day, time(hour=hour, minute=minute))
