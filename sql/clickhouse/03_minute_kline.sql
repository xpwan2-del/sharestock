-- ============================================================
-- ClickHouse DDL: 分钟K线行情表（超大规模表）
-- 数据量估算: 5000只 x 240分钟/天 x 250天 = 3亿行/年
-- 保留1年约 3亿行，ClickHouse 完全可支撑
-- ============================================================

CREATE TABLE IF NOT EXISTS quant_ts.minute_kline
(
    stock_code       FixedString(6)   COMMENT '股票代码',
    trade_time       DateTime         COMMENT '交易时间(精确到分钟)',

    open             Float64          COMMENT '开盘价',
    high             Float64          COMMENT '最高价',
    low              Float64          COMMENT '最低价',
    close            Float64          COMMENT '收盘价',
    volume           Float64          COMMENT '成交量（股）',
    amount           Float64          COMMENT '成交额（元）',

    created_at       DateTime         DEFAULT now() COMMENT '入库时间'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(toDate(trade_time))
ORDER BY (stock_code, trade_time)
TTL trade_time + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192
COMMENT 'A股分钟K线行情（保留1年，自动过期）';

-- 物化列：日期维度便于分区裁剪
ALTER TABLE quant_ts.minute_kline
ADD COLUMN trade_date Date MATERIALIZED toDate(trade_time);

-- 物化列：小时维度便于盘中分析
ALTER TABLE quant_ts.minute_kline
ADD COLUMN trade_hour UInt8 MATERIALIZED toHour(trade_time);