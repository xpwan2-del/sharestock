import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data_cache"
DATA_DIR.mkdir(exist_ok=True)

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

DATABASE_CONFIG = {
    # ClickHouse - 时序数据（日K线、分钟线、实时快照、模型特征/预测、警报）
    "clickhouse": {
        "host": os.getenv("CLICKHOUSE_HOST", "localhost"),
        "port": int(os.getenv("CLICKHOUSE_PORT", "9000")),
        "http_port": int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123")),
        "user": os.getenv("CLICKHOUSE_USER", "default"),
        "password": os.getenv("CLICKHOUSE_PASSWORD", ""),
        "database": "quant_ts",
    },
    # PostgreSQL - 元数据/业务数据（股票基础信息、产业链、公告、龙虎榜、情绪、信号）
    "postgresql": {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "user": os.getenv("PG_USER", "quant_user"),
        "password": os.getenv("PG_PASSWORD", ""),
        "database": "quant_meta",
    },
    # Redis - 缓存（实时行情、监控列表、模型标准化参数）
    "redis": {
        "uri": os.getenv("REDIS_URI", "redis://localhost:6379"),
        "max_connections": int(os.getenv("REDIS_MAX_CONN", "50")),
    },
}

MARKET_CONFIG = {
    "commission_rate": 0.0003,
    "stamp_tax_rate": 0.001,
    "slippage_rate": 0.001,
    "min_commission": 5.0,
    "enable_limit_up_down": True,
}

ANNOUNCEMENT_SOURCES = {
    "cninfo": "https://www.cninfo.com.cn",
    "eastmoney": "https://data.eastmoney.com",
    "sse": "https://www.sse.com.cn",
    "szse": "https://www.szse.cn",
}

SENTIMENT_SOURCES = {
    "eastmoney_news": "https://np-listapi.eastmoney.com",
    "xueqiu": "https://xueqiu.com",
    "weibo": "https://s.weibo.com",
}

LEADER_THRESHOLDS = {
    "turnover_rate_min": 0.05,
    "market_cap_min": 5e9,
    "volume_ratio_min": 1.5,
    "consecutive_limit_up_min": 2,
    "sector_contribution_min": 0.15,
}

INDUSTRY_CHAIN_CONFIG = {
    "use_io_table": True,
    "update_frequency_days": 7,
}

TREND_REVERSAL_CONFIG = {
    "ma_short": 5,
    "ma_mid": 20,
    "ma_long": 60,
    "volume_breakout_ratio": 1.5,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "macd_divergence_lookback": 60,
}

ML_CONFIG = {
    "default_model": "lightgbm",
    "cv_folds": 5,
    "feature_lookback_days": 120,
    "prediction_horizon_days": 5,
    "retrain_frequency_days": 7,
    "online_learning_batch_size": 32,
    "enable_daily_training": True,
    "daily_train_batch_size": 20,
}

REALTIME_CONFIG = {
    "watch_list": [],
    "scan_interval_seconds": 3,
    "alert_threshold_pct": 3.0,
    "volume_alert_ratio": 2.0,
}

DAILY_RUN_TIME = "18:00"

# ============================================================
# 数据源分层配置 (核心!)
# ============================================================
# 级别说明:
#   realtime - 实时/毫秒级延迟，可做盘中交易决策
#   delayed  - 延迟 3-15 分钟，可参考不可交易
#   eod      - 盘后数据，仅能做盘后分析/学习
#   unpaid   - 免费接口，可靠性低但够用于回测

DATA_SOURCE_TIER = {
    # 盘后分析模式：全部用免费/盘后数据
    "eod": {
        "market_data": "akshare_free",       # AKShare 免费日K
        "realtime_quote": "akshare_free",    # AKShare (有延迟/不稳定)
        "north_bound": "akshare_free",       # 北向资金 延迟15分+
        "dragon_tiger": "akshare_free",      # 龙虎榜 盘后
        "announcement": "cninfo_free",       # 巨潮资讯 盘后
        "fund_flow": "akshare_free",         # 资金流向 延迟/盘后
    },
    # 实时模式：需要付费/Tushare Pro
    "realtime": {
        "market_data": "tushare_pro",        # Tushare Pro (需积分)
        "realtime_quote": "broker_xtp",      # 券商XTP接口 (需开户)
        "north_bound": "tushare_pro",        # Tushare更及时
        "dragon_tiger": "tushare_pro",       # Tushare盘后
        "announcement": "tushare_pro",       # Tushare公告
        "fund_flow": "tushare_pro",          # Tushare资金流
    },
}

# 各数据源的延迟说明 (用于日志/报告标注)
DATA_LATENCY = {
    "akshare_free": {
        "daily_kline": {"latency": "盘后 18:00", "reliable": True},
        "realtime_quote": {"latency": "3-5秒/易断连", "reliable": False},
        "limit_up_pool": {"latency": "盘中 1-3分钟", "reliable": True},
        "dragon_tiger": {"latency": "盘后 17:00", "reliable": True},
        "north_bound": {"latency": "盘中 15分钟", "reliable": True},
        "margin": {"latency": "盘后/T+1", "reliable": True},
        "announcement": {"latency": "盘后 实时", "reliable": True},
    },
    "tushare_pro": {
        "daily_kline": {"latency": "盘后 15:30", "reliable": True},
        "realtime_quote": {"latency": "3秒(Level1)", "reliable": True},
        "dragon_tiger": {"latency": "盘后 17:00", "reliable": True},
        "north_bound": {"latency": "盘中 延迟", "reliable": True},
    },
    "broker_xtp": {
        "realtime_quote": {"latency": "毫秒级 Level2", "reliable": True},
    },
}

# 当前激活的数据层级 (默认: eod盘后模式)
ACTIVE_DATA_TIER = os.getenv("DATA_TIER", "eod")