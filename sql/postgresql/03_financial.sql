-- ============================================================
-- PostgreSQL DDL: 股东信息与财务报表
-- 数据来源: CompanyInfoCollector
-- ============================================================

-- 十大股东
CREATE TABLE IF NOT EXISTS quant.top10_holders
(
    id               BIGSERIAL      PRIMARY KEY,
    stock_code       VARCHAR(6)     NOT NULL REFERENCES quant.stock_basic(stock_code),
    report_date      DATE           NOT NULL COMMENT '报告期',
    holder_name      VARCHAR(300)   NOT NULL COMMENT '股东名称',
    holder_type      VARCHAR(50)                COMMENT '股东类型: 机构/个人/外资',
    shares_held      BIGINT                    COMMENT '持股数量',
    ratio_pct        NUMERIC(8,4)              COMMENT '持股比例(%)',
    change_qoq       BIGINT                    COMMENT '较上期变动(股)',

    created_at       TIMESTAMPTZ    DEFAULT now(),
    UNIQUE (stock_code, report_date, holder_name)
);

COMMENT ON TABLE quant.top10_holders IS '十大股东信息';
CREATE INDEX idx_top10_stock ON quant.top10_holders (stock_code, report_date DESC);

-- 股东户数变化
CREATE TABLE IF NOT EXISTS quant.holder_number
(
    id               BIGSERIAL      PRIMARY KEY,
    stock_code       VARCHAR(6)     NOT NULL REFERENCES quant.stock_basic(stock_code),
    report_date      DATE           NOT NULL COMMENT '报告期',
    holder_count     BIGINT         NOT NULL COMMENT '股东总户数',
    avg_shares       BIGINT                    COMMENT '户均持股',

    created_at       TIMESTAMPTZ    DEFAULT now(),
    UNIQUE (stock_code, report_date)
);

COMMENT ON TABLE quant.holder_number IS '股东户数变化';
CREATE INDEX idx_holder_num_stock ON quant.holder_number (stock_code, report_date DESC);

-- 财务报表摘要（用 JSONB 存灵活字段）
CREATE TABLE IF NOT EXISTS quant.financial_summary
(
    id               BIGSERIAL      PRIMARY KEY,
    stock_code       VARCHAR(6)     NOT NULL REFERENCES quant.stock_basic(stock_code),
    report_date      DATE           NOT NULL COMMENT '报告期（如 2024-12-31）',
    report_type      VARCHAR(20)    NOT NULL COMMENT '报表类型: balance_sheet/income/cash_flow',

    -- 关键指标提取（方便直接查询）
    total_assets     NUMERIC(18,2)             COMMENT '总资产',
    net_assets       NUMERIC(18,2)             COMMENT '净资产',
    revenue          NUMERIC(18,2)             COMMENT '营业收入',
    net_profit       NUMERIC(18,2)             COMMENT '归母净利润',
    eps              NUMERIC(10,4)             COMMENT '基本每股收益',
    roe              NUMERIC(8,4)              COMMENT '净资产收益率(%)',

    -- 完整报表存 JSONB（字段名不固定，灵活性高）
    raw_data         JSONB           NOT NULL,

    created_at       TIMESTAMPTZ    DEFAULT now(),
    UNIQUE (stock_code, report_date, report_type)
);

COMMENT ON TABLE quant.financial_summary IS '财务报表摘要 + 原始JSONB';
CREATE INDEX idx_financial_stock ON quant.financial_summary (stock_code, report_date DESC);
CREATE INDEX idx_financial_raw_gin ON quant.financial_summary USING GIN (raw_data);