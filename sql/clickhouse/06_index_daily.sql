-- ============================================================
-- ClickHouse DDL: 指数行情表
-- 上证指数、深证成指、创业板指等主要指数日线
-- ============================================================

CREATE TABLE IF NOT EXISTS quant_ts.index_daily
(
    index_code       String           COMMENT '指数代码，如 sh000001',
    trade_date       Date             COMMENT '交易日期',

    open             Float64          COMMENT '开盘',
    high             Float64          COMMENT '最高',
    low              Float64          COMMENT '最低',
    close            Float64          COMMENT '收盘',
    volume           Float64          COMMENT '成交量',
    amount           Float64          COMMENT '成交额',

    created_at       DateTime         DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY (index_code, trade_date)
SETTINGS index_granularity = 256
COMMENT '主要指数日线行情';