-- ============================================================
-- ClickHouse DDL: 资金流向表
-- 北向资金 + 融资融券，日频数据
-- ============================================================

-- 北向资金每日净流向
CREATE TABLE IF NOT EXISTS quant_ts.northbound_flow_daily
(
    trade_date        Date            COMMENT '交易日期',
    net_flow          Float64         COMMENT '北向净流入（元）',
    buy_amount        Nullable(Float64) COMMENT '买入金额',
    sell_amount       Nullable(Float64) COMMENT '卖出金额',
    balance           Nullable(Float64) COMMENT '累计余额',

    created_at        DateTime        DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY trade_date
SETTINGS index_granularity = 256
COMMENT '北向资金每日净流向';

-- 融资融券
CREATE TABLE IF NOT EXISTS quant_ts.margin_trading_daily
(
    trade_date        Date            COMMENT '交易日期',
    margin_balance    Float64         COMMENT '融资余额（元）',
    margin_buy        Float64         COMMENT '融资买入额（元）',
    short_balance     Nullable(Float64) COMMENT '融券余量',

    created_at        DateTime        DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY trade_date
SETTINGS index_granularity = 256
COMMENT '融资融券每日数据';