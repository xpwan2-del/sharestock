-- ============================================================
-- PostgreSQL DDL: 情绪分析结果表
-- 数据来源: MarketSentimentAnalyzer + NewsSentimentAnalyzer + AnnouncementNLPAnalyzer
-- ============================================================

-- 每日综合市场情绪
CREATE TABLE IF NOT EXISTS quant.sentiment_daily
(
    id               BIGSERIAL       PRIMARY KEY,
    trade_date       DATE            NOT NULL UNIQUE COMMENT '交易日期',

    -- 综合评分
    overall_score    NUMERIC(5,1)    NOT NULL COMMENT '综合情绪评分(0-100)',
    level            VARCHAR(20)     NOT NULL COMMENT '情绪等级: 极度亢奋/偏乐观/中性/偏悲观/极度恐慌',

    -- 子维度
    breadth_score    NUMERIC(5,1)               COMMENT '市场宽度得分(0-100)',
    breadth_sentiment VARCHAR(20)               COMMENT '市场宽度情绪',
    up_ratio         NUMERIC(5,1)               COMMENT '上涨占比(%)',
    limit_up_count   INT                        COMMENT '涨停家数',
    limit_down_count INT                        COMMENT '跌停家数',
    avg_pct_chg      NUMERIC(5,2)               COMMENT '平均涨跌幅',

    -- 量能情绪
    volume_active    BOOLEAN                    COMMENT '量能是否活跃',
    high_vol_ratio   NUMERIC(5,1)               COMMENT '高量比占比(%)',
    avg_volume_ratio NUMERIC(6,2)               COMMENT '平均量比',

    -- 北向情绪
    north_signal     VARCHAR(20)                COMMENT '北向信号: strong_inflow/inflow/neutral/outflow/strong_outflow',
    north_net_flow   NUMERIC(18,2)              COMMENT '北向净流入',

    -- 涨停质量
    limit_up_quality VARCHAR(20)                COMMENT '涨停质量: high/medium/low',
    solid_count      INT                        COMMENT '一字板/硬板数',
    fragile_count    INT                        COMMENT '烂板数',

    created_at       TIMESTAMPTZ     DEFAULT now()
);

COMMENT ON TABLE quant.sentiment_daily IS '每日综合市场情绪';
CREATE INDEX idx_sentiment_date ON quant.sentiment_daily (trade_date DESC);

-- 新闻/公告文本情感分析
CREATE TABLE IF NOT EXISTS quant.news_sentiment
(
    id               BIGSERIAL       PRIMARY KEY,
    source_type      VARCHAR(20)     NOT NULL COMMENT '来源类型: news/announcement/social',
    source_id        VARCHAR(200)                COMMENT '来源ID（公告ID/新闻URL等）',
    stock_code       VARCHAR(6)                  COMMENT '关联股票（可为空，全局新闻）',
    title            VARCHAR(1000)               COMMENT '标题',
    pub_date         TIMESTAMPTZ                 COMMENT '发布时间',

    -- 情感分析
    sentiment        VARCHAR(20)     NOT NULL COMMENT '情感: positive/slightly_positive/neutral/slightly_negative/negative',
    score            NUMERIC(6,4)    NOT NULL COMMENT '情感得分(-1~1)',
    confidence       NUMERIC(6,4)               COMMENT '置信度(0-1)',

    -- 分析细节
    snownlp_score    NUMERIC(6,4)               COMMENT 'SnowNLP 原始得分',
    keyword_score    NUMERIC(6,4)               COMMENT '关键词得分',

    -- 关键词
    key_bullish_words TEXT[]                     COMMENT '看多关键词',
    key_bearish_words TEXT[]                     COMMENT '看空关键词',

    -- 与原公告/新闻关联
    announcement_id  BIGINT                     COMMENT '关联公告ID',

    created_at       TIMESTAMPTZ     DEFAULT now()
);

COMMENT ON TABLE quant.news_sentiment IS '新闻/公告情感分析结果';
CREATE INDEX idx_ns_stock_date ON quant.news_sentiment (stock_code, pub_date DESC NULLS LAST);
CREATE INDEX idx_ns_sentiment ON quant.news_sentiment (sentiment);
CREATE INDEX idx_ns_announcement ON quant.news_sentiment (announcement_id);