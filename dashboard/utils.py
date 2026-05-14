"""
仪表盘工具模块 - 提供数据加载、缓存、格式化等通用功能
"""
import sys
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATA_DIR
from utils.cache import disk_cache
from utils.redis_manager import get_redis_manager


# ---------- 数据加载器单例 ----------

@disk_cache(ttl_hours=0.033)
def _load_market_breadth() -> Dict:
    """加载市场宽度数据（带缓存）"""
    from data.market_data import MarketDataCollector
    mc = MarketDataCollector()
    return mc.get_market_breadth()


@disk_cache(ttl_hours=0.033)
def _load_realtime_quotes() -> pd.DataFrame:
    """加载实时行情数据（直接走统一数据网关，避免Redis KEYS全量扫描）"""
    from data.market_data import MarketDataCollector
    mc = MarketDataCollector()
    return mc.get_realtime_quotes()


@disk_cache(ttl_hours=0.016)
def _load_limit_up_pool() -> pd.DataFrame:
    """加载涨停池（带缓存）"""
    from data.market_data import MarketDataCollector
    mc = MarketDataCollector()
    return mc.get_limit_up_pool()


@disk_cache(ttl_hours=0.25)
def _load_concept_board() -> pd.DataFrame:
    """加载概念板块行情（带缓存）"""
    from data.market_data import MarketDataCollector
    mc = MarketDataCollector()
    return mc.get_concept_board()


@disk_cache(ttl_hours=0.25)
def _load_industry_board() -> pd.DataFrame:
    """加载行业板块行情（带缓存）"""
    from data.market_data import MarketDataCollector
    mc = MarketDataCollector()
    return mc.get_industry_board()


@disk_cache(ttl_hours=0.016)
def _load_market_indices() -> Dict:
    """加载核心指数数据（腾讯快速接口，避免AKShare指数接口卡死）"""
    indices = {
        "上证指数": "sh000001",
        "深证成指": "sz399001",
        "创业板指": "sz399006",
        "科创50": "sh000688",
        "北证50": "bj899050",
    }
    url = "http://qt.gtimg.cn/q=" + ",".join(indices.values())
    result = {}
    try:
        resp = requests.get(
            url,
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com/"},
        )
        resp.raise_for_status()
        code_to_name = {code: name for name, code in indices.items()}
        for item in resp.text.strip().split(";"):
            if not item or "=" not in item:
                continue
            left, right = item.split("=", 1)
            code = left.split("_", 1)[-1].replace("v_", "").strip().strip('"')
            raw = right.strip().strip('"')
            parts = raw.split("~")
            if len(parts) < 38 or code not in code_to_name:
                continue
            name = code_to_name[code]
            result[name] = {
                "code": code,
                "name": parts[1] or name,
                "price": pd.to_numeric(parts[3], errors="coerce"),
                "change": pd.to_numeric(parts[31], errors="coerce") if len(parts) > 31 else 0,
                "pct_chg": pd.to_numeric(parts[32], errors="coerce") if len(parts) > 32 else 0,
                "volume": pd.to_numeric(parts[6], errors="coerce") if len(parts) > 6 else 0,
                "amount": pd.to_numeric(parts[37], errors="coerce") if len(parts) > 37 else 0,
                "time": parts[30] if len(parts) > 30 else "",
                "source": "tencent",
            }
    except BaseException as e:
        if isinstance(e, KeyboardInterrupt):
            raise
        return {}
    return result


@disk_cache(ttl_hours=2)
def _load_dragon_tiger(date: Optional[str] = None) -> pd.DataFrame:
    """加载龙虎榜数据（带缓存）"""
    from data.dragon_tiger import DragonTigerCollector
    dt = DragonTigerCollector()
    return dt.get_daily_dragon_tiger(date)


@disk_cache(ttl_hours=2)
def _load_north_bound() -> Dict:
    """加载北向资金数据（带缓存）"""
    from data.fund_flow import FundFlowCollector
    ff = FundFlowCollector()
    return ff.get_north_bound_daily()


# ---------- 会话级缓存 ----------

class SessionCache:
    """Streamlit 会话级缓存，避免同一会话重复拉取数据"""

    def __init__(self):
        self._data: Dict[str, Any] = {}

    def get(self, key: str, loader_fn, *args, **kwargs):
        cache_key = f"{key}_{str(args)}_{str(kwargs)}"
        if cache_key not in self._data:
            self._data[cache_key] = loader_fn(*args, **kwargs)
        return self._data[cache_key]

    def set(self, key: str, value: Any, *args, **kwargs):
        cache_key = f"{key}_{str(args)}_{str(kwargs)}"
        self._data[cache_key] = value

    def has(self, key: str, *args, **kwargs) -> bool:
        cache_key = f"{key}_{str(args)}_{str(kwargs)}"
        return cache_key in self._data

    def clear(self):
        self._data.clear()


# ---------- 格式化辅助函数 ----------

def format_amount(amount: float) -> str:
    """格式化金额显示"""
    if amount is None or pd.isna(amount):
        return "-"
    abs_amt = abs(amount)
    if abs_amt >= 1e12:
        return f"{amount / 1e12:.2f}万亿"
    elif abs_amt >= 1e8:
        return f"{amount / 1e8:.2f}亿"
    elif abs_amt >= 1e4:
        return f"{amount / 1e4:.2f}万"
    return f"{amount:.2f}"


def format_pct(value: float, with_sign: bool = True) -> str:
    """格式化百分比显示"""
    if value is None or pd.isna(value):
        return "-"
    if with_sign:
        return f"{value:+.2f}%"
    return f"{value:.2f}%"


def color_pct(val: float) -> str:
    """根据涨跌返回颜色"""
    if val is None or pd.isna(val):
        return "gray"
    if val > 0:
        return "red"
    elif val < 0:
        return "green"
    return "gray"


def color_sentiment(score: float) -> str:
    """根据情绪分数返回颜色"""
    if score >= 80:
        return "#FF4444"  # 极度亢奋 - 红色
    elif score >= 65:
        return "#FF8C00"  # 偏乐观 - 橙色
    elif score >= 45:
        return "#888888"  # 中性 - 灰色
    elif score >= 30:
        return "#4169E1"  # 偏悲观 - 蓝色
    else:
        return "#228B22"  # 极度恐慌 - 深绿


def style_pct_dataframe(df: pd.DataFrame, pct_columns: List[str]) -> Any:
    """给 DataFrame 添加条件样式（用于 st.dataframe）"""
    styles = []
    for col in pct_columns:
        if col in df.columns:

            def _color_map(val):
                if isinstance(val, (int, float)) and not pd.isna(val):
                    color = "red" if val > 0 else ("green" if val < 0 else "gray")
                    return f"color: {color}"
                return ""

            styles.append({col: _color_map})
    return styles


def get_today_str() -> str:
    """返回今天的日期字符串"""
    return datetime.now().strftime("%Y%m%d")


def get_recent_dates(days: int = 30) -> List[str]:
    """返回最近 N 天的日期列表"""
    today = datetime.now()
    return [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]


# ---------- 数据合并辅助 ----------

def safe_merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_on: str,
    right_on: str,
    how: str = "inner",
) -> pd.DataFrame:
    """安全的 DataFrame 合并"""
    if left.empty or right.empty:
        return pd.DataFrame()
    return left.merge(right, left_on=left_on, right_on=right_on, how=how)


def extract_col(df: pd.DataFrame, possible_names: List[str], default: Any = None) -> Any:
    """尝试从多个可能的列名中提取数据"""
    for name in possible_names:
        if name in df.columns:
            return df[name]
    return default