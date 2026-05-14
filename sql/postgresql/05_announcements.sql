-- ============================================================
-- PostgreSQL DDL: 公告数据表
-- 数据来源: AnnouncementCollector (cninfo + eastmoney)
-- 使用 pg_trgm 做全文模糊搜索
-- ============================================================

CREATE TABLE IF NOT EXISTS quant.announcements
(
    id               BIGSERIAL       PRIMARY KEY,
    stock_code       VARCHAR(6)      NOT NULL REFERENCES quant.stock_basic(stock_code),
    title            VARCHAR(1000)   NOT NULL COMMENT '公告标题',
    pub_date         TIMESTAMPTZ     NOT NULL COMMENT '发布日期',
    source           VARCHAR(50)     NOT NULL COMMENT '数据源: cninfo/eastmoney/sse/szse',
    source_url       VARCHAR(2000)               COMMENT '公告原文链接',
    sec_type         VARCHAR(50)                 COMMENT '公告分类（来自 cninfo）',
    raw_content      TEXT                        COMMENT '公告全文（可选，爬取后存）',
    content_hash     VARCHAR(64)                 COMMENT '内容摘要哈希（去重）',

    created_at       TIMESTAMPTZ     DEFAULT now(),
    UNIQUE (stock_code, pub_date, source_url)
);

COMMENT ON TABLE quant.announcements IS '上市公司公告';
CREATE INDEX idx_ann_stock_date ON quant.announcements (stock_code, pub_date DESC);
CREATE INDEX idx_ann_title_trgm ON quant.announcements USING GIN (title gin_trgm_ops);
CREATE INDEX idx_ann_pub_date ON quant.announcements (pub_date DESC);

-- 公告影响力分析
CREATE TABLE IF NOT EXISTS quant.announcement_impact
(
    id               BIGSERIAL       PRIMARY KEY,
    announcement_id  BIGINT          NOT NULL REFERENCES quant.announcements(id) ON DELETE CASCADE,

    -- 影响力分析
    impact_level     VARCHAR(20)     NOT NULL COMMENT '影响级别: strong_bullish/bullish/neutral/bearish/strong_bearish',
    impact_category  VARCHAR(30)                 COMMENT '影响类别: restructuring/insider_trading/earnings/dividend/contract/regulatory',
    impact_score     INT             NOT NULL DEFAULT 0 COMMENT '影响分数(-10到+10)',
    keywords         TEXT[]                      COMMENT '匹配到的关键词数组',

    -- NLP 分析
    combined_score   NUMERIC(5,2)               COMMENT '综合得分（规则+NLP）',
    combined_level   VARCHAR(20)                COMMENT '综合级别',
    sentiment        VARCHAR(20)                COMMENT '情感: positive/negative/neutral',

    created_at       TIMESTAMPTZ     DEFAULT now(),
    UNIQUE (announcement_id)
);

COMMENT ON TABLE quant.announcement_impact IS '公告影响力分析结果';
CREATE INDEX idx_aimpact_level ON quant.announcement_impact (impact_level);
CREATE INDEX idx_aimpact_score ON quant.announcement_impact (impact_score DESC);