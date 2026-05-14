-- ============================================================
-- ClickHouse DDL: 市场宽度表
-- 每日全市场涨跌统计，量很小但分析价值高
-- ============================================================

CREATE TABLE IF NOT EXISTS quant_ts.market_breadth
(
    trade_date           Date             COMMENT '交易日期',

    -- 涨跌统计
    total                UInt32           COMMENT '总股票数',
    up_count             UInt32           COMMENT '上涨家数',
    down_count           UInt32           COMMENT '下跌家数',
    flat_count           UInt32           COMMENT '平盘家数',
    up_ratio             Float64          COMMENT '上涨占比(%)',

    -- 极端行情
    limit_up_count       UInt32           COMMENT '涨停家数',
    limit_down_count     UInt32           COMMENT '跌停家数',
    up_gt_5pct           UInt32           COMMENT '涨幅>5%家数',
    down_gt_5pct         UInt32           COMMENT '跌幅>5%家数',

    -- 均值统计
    avg_pct_chg          Float64          COMMENT '平均涨跌幅(%)',
    median_pct_chg       Float64          COMMENT '中位数涨跌幅(%)',

    created_at           DateTime         DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY trade_date
SETTINGS index_granularity = 256
COMMENT '每日市场宽度统计';