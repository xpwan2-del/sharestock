-- ============================================================
-- ClickHouse DDL: 日K线行情表（核心表）
-- 数据量估算: 5000只 x 250交易日/年 = 125万行/年
-- 含技术指标，10年约 1250万行，单表可支撑
-- ============================================================

CREATE TABLE IF NOT EXISTS quant_ts.daily_kline
(
    -- 主键维度
    stock_code       FixedString(6)   COMMENT '股票代码，如 000001',
    trade_date       Date             COMMENT '交易日期',

    -- OHLCV 原始行情
    open             Float64          COMMENT '开盘价（前复权）',
    high             Float64          COMMENT '最高价',
    low              Float64          COMMENT '最低价',
    close            Float64          COMMENT '收盘价',
    volume           Float64          COMMENT '成交量（股）',
    amount           Float64          COMMENT '成交额（元）',

    -- 涨跌信息
    amplitude        Float64          COMMENT '振幅(%)',
    pct_chg          Float64          COMMENT '涨跌幅(%)',
    change           Float64          COMMENT '涨跌额',
    turnover         Float64          COMMENT '换手率(%)',

    -- 移动均线
    ma5              Nullable(Float64) COMMENT '5日均线',
    ma10             Nullable(Float64) COMMENT '10日均线',
    ma20             Nullable(Float64) COMMENT '20日均线',
    ma60             Nullable(Float64) COMMENT '60日均线',

    -- 量价指标
    ma5_volume       Nullable(Float64) COMMENT '5日均量',
    volume_ratio     Nullable(Float64) COMMENT '量比',

    -- RSI
    rsi14            Nullable(Float64) COMMENT '14日RSI',

    -- MACD
    macd             Nullable(Float64) COMMENT 'MACD DIF',
    macd_signal      Nullable(Float64) COMMENT 'MACD DEA(信号线)',
    macd_hist        Nullable(Float64) COMMENT 'MACD 柱(2*(DIF-DEA))',

    -- 布林带
    boll_mid         Nullable(Float64) COMMENT '布林带中轨(20日均线)',
    boll_upper       Nullable(Float64) COMMENT '布林带上轨',
    boll_lower       Nullable(Float64) COMMENT '布林带下轨',

    -- ATR
    atr14            Nullable(Float64) COMMENT '14日平均真实波幅',

    -- 动量/收益
    ret_1d           Nullable(Float64) COMMENT '1日收益率',
    ret_5d           Nullable(Float64) COMMENT '5日收益率',
    ret_20d          Nullable(Float64) COMMENT '20日收益率',
    volatility_20d   Nullable(Float64) COMMENT '20日年化波动率',

    -- 元数据
    adjust_type      LowCardinality(String) DEFAULT 'qfq' COMMENT '复权类型: qfq/hfq/None',
    created_at       DateTime          DEFAULT now() COMMENT '入库时间'
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY (stock_code, trade_date)
SETTINGS index_granularity = 8192
COMMENT 'A股日K线行情（含技术指标）';

-- 跳数索引：加速涨跌幅范围查询
ALTER TABLE quant_ts.daily_kline
ADD INDEX idx_pct_chg pct_chg TYPE minmax GRANULARITY 4;

-- 跳数索引：加速换手率筛选
ALTER TABLE quant_ts.daily_kline
ADD INDEX idx_turnover turnover TYPE minmax GRANULARITY 4;

-- 物化列：加速 MySQL 兼容查询（部分框架按字符串查代码）
ALTER TABLE quant_ts.daily_kline
ADD COLUMN stock_code_str String MATERIALIZED toString(stock_code);