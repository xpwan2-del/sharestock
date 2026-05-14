-- ============================================================
-- ClickHouse DDL: 概念板块每日行情
-- 用于产业链热度分析
-- ============================================================

CREATE TABLE IF NOT EXISTS quant_ts.concept_board_daily
(
    trade_date       Date             COMMENT '交易日期',
    board_name       String           COMMENT '板块名称',
    board_code       Nullable(String)  COMMENT '板块代码',

    pct_chg          Float64          COMMENT '涨跌幅(%)',
    up_count         Nullable(UInt16) COMMENT '上涨家数',
    down_count       Nullable(UInt16) COMMENT '下跌家数',
    leader_stock     Nullable(String)  COMMENT '领涨股',

    -- 板块强度得分
    strength_score   Nullable(Float64) COMMENT '板块强弱得分(0-100)',

    created_at       DateTime         DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY (trade_date, board_name)
SETTINGS index_granularity = 256
COMMENT '概念板块每日行情';

-- 行业板块每日行情
CREATE TABLE IF NOT EXISTS quant_ts.industry_board_daily
(
    trade_date       Date             COMMENT '交易日期',
    board_name       String           COMMENT '行业名称',
    board_code       Nullable(String)  COMMENT '行业代码',

    pct_chg          Float64          COMMENT '涨跌幅(%)',
    up_count         Nullable(UInt16) COMMENT '上涨家数',
    down_count       Nullable(UInt16) COMMENT '下跌家数',

    created_at       DateTime         DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(trade_date)
ORDER BY (trade_date, board_name)
SETTINGS index_granularity = 256
COMMENT '行业板块每日行情';