-- ============================================================
-- PostgreSQL DDL: 股票基础信息表
-- 数据来源: CompanyInfoCollector + MarketDataCollector.get_a_share_list()
-- ============================================================

CREATE TABLE IF NOT EXISTS quant.stock_basic
(
    stock_code       VARCHAR(6)     PRIMARY KEY  COMMENT '股票代码，如 000001',
    stock_name       VARCHAR(50)    NOT NULL     COMMENT '股票简称',
    full_name        VARCHAR(200)                COMMENT '公司全称',
    market           CHAR(2)        NOT NULL     COMMENT '交易所: SH/SZ/BJ',
    listing_date     DATE                        COMMENT '上市日期',
    total_shares     BIGINT                      COMMENT '总股本',
    float_shares     BIGINT                      COMMENT '流通股本',
    industry_sw      VARCHAR(100)                COMMENT '申万一级行业',
    industry_sw_detail VARCHAR(200)              COMMENT '申万行业细分',
    company_profile  TEXT                        COMMENT '公司概况（来自 cninfo）',
    website          VARCHAR(500)                COMMENT '官网',
    is_active        BOOLEAN        DEFAULT TRUE COMMENT '是否正常交易（非退市）',

    created_at       TIMESTAMPTZ    DEFAULT now(),
    updated_at       TIMESTAMPTZ    DEFAULT now()
);

COMMENT ON TABLE quant.stock_basic IS 'A股股票基础信息';

-- 按名称模糊搜索（pg_trgm）
CREATE INDEX idx_stock_basic_name_trgm ON quant.stock_basic USING GIN (stock_name gin_trgm_ops);
CREATE INDEX idx_stock_basic_market ON quant.stock_basic (market) WHERE is_active;
CREATE INDEX idx_stock_basic_industry ON quant.stock_basic (industry_sw);