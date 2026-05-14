-- ============================================================
-- ClickHouse DDL: 涨停池 + 连续涨停
-- ============================================================

-- 每日涨停池
CREATE TABLE IF NOT EXISTS quant_ts.limit_up_pool_daily
(
    trade_date       Date             COMMENT '交易日期',
    stock_code       FixedString(6)   COMMENT '股票代码',
    stock_name       String           COMMENT '股票名称',

    -- AKShare 返回的涨停池原始字段
    pct_chg          Float64          COMMENT '涨跌幅(%)',
    latest_price     Float64          COMMENT '最新价',
    limit_up_price   Nullable(Float64) COMMENT '涨停价',

    -- 封板信息
    first_seal_time  Nullable(String)  COMMENT '首次封板时间',
    last_seal_time   Nullable(String)  COMMENT '最后封板时间',
    open_count       Nullable(UInt8)  COMMENT '炸板次数',
    seal_amount      Nullable(Float64) COMMENT '封单金额（元）',
    seal_ratio       Nullable(Float64) COMMENT '封成比（封单/成交）',

    -- 连板信息
    consecutive_days Nullable(UInt8)  COMMENT '连板天数',

    turnover         Nullable(Float64) COMMENT '换手率(%)',
    amount           Nullable(Float64) COMMENT '成交额（元）',
    float_mv         Nullable(Float64) COMMENT '流通市值',

    -- 行业/概念
    industry         Nullable(String)  COMMENT '所属行业',

    created_at       DateTime         DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY (trade_date, stock_code)
SETTINGS index_granularity = 512
COMMENT '每日涨停池';

-- 连续涨停池（独立存一份便于查询）
CREATE TABLE IF NOT EXISTS quant_ts.continuous_limit_up
(
    trade_date       Date             COMMENT '交易日期',
    stock_code       FixedString(6)   COMMENT '股票代码',
    stock_name       String           COMMENT '股票名称',

    limit_up_days    UInt8            COMMENT '连续涨停天数',
    pct_chg          Float64          COMMENT '当日涨跌幅(%)',
    turnover         Nullable(Float64) COMMENT '换手率(%)',

    created_at       DateTime         DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY (trade_date, stock_code)
SETTINGS index_granularity = 512
COMMENT '连续涨停股票';