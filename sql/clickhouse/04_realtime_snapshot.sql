-- ============================================================
-- ClickHouse DDL: 实时行情快照表
-- 交易时段每隔N秒采集一次全市场快照
-- 保留30天，主要用于盘中回放和事后分析
-- ============================================================

CREATE TABLE IF NOT EXISTS quant_ts.realtime_snapshot
(
    snapshot_time    DateTime         COMMENT '快照时间',
    stock_code       FixedString(6)   COMMENT '股票代码',
    stock_name       String           COMMENT '股票名称',

    -- 价格信息
    price            Float64          COMMENT '最新价',
    open             Float64          COMMENT '今开',
    high             Float64          COMMENT '最高',
    low              Float64          COMMENT '最低',
    pre_close        Float64          COMMENT '昨收',

    -- 涨跌
    pct_chg          Float64          COMMENT '涨跌幅(%)',
    change           Float64          COMMENT '涨跌额',

    -- 成交
    volume           Float64          COMMENT '成交量',
    amount           Float64          COMMENT '成交额',
    amplitude        Float64          COMMENT '振幅(%)',
    turnover         Float64          COMMENT '换手率(%)',
    volume_ratio     Float64          COMMENT '量比',

    -- 估值
    pe_ttm           Nullable(Float64) COMMENT '市盈率(TTM)',
    pb               Nullable(Float64) COMMENT '市净率',
    total_mv         Nullable(Float64) COMMENT '总市值',
    float_mv         Nullable(Float64) COMMENT '流通市值',

    -- 中长期涨跌
    pct_chg_60d      Nullable(Float64) COMMENT '60日涨跌幅(%)',
    pct_chg_ytd      Nullable(Float64) COMMENT '年初至今涨跌幅(%)',

    created_at       DateTime         DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(snapshot_time)
ORDER BY (snapshot_time, stock_code)
TTL snapshot_time + INTERVAL 30 DAY DELETE
SETTINGS index_granularity = 8192
COMMENT '全市场实时行情快照（保留30天）';