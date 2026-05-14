-- ============================================================
-- PostgreSQL DDL: 产业链拓扑结构
-- 数据来源: INDUSTRY_CHAIN_MAP (8大产业链, 上游/中游/下游)
-- 关系表 + 映射表 支持灵活查询
-- ============================================================

-- 产业链定义
CREATE TABLE IF NOT EXISTS quant.industry_chain_def
(
    id               SERIAL         PRIMARY KEY,
    chain_name       VARCHAR(100)   NOT NULL UNIQUE COMMENT '产业链名称: 新能源汽车/光伏/半导体...',
    chain_desc       TEXT                       COMMENT '产业链描述',
    is_active        BOOLEAN        DEFAULT TRUE,

    created_at       TIMESTAMPTZ    DEFAULT now()
);

COMMENT ON TABLE quant.industry_chain_def IS '产业链定义表';

-- 产业链环节
CREATE TABLE IF NOT EXISTS quant.chain_segment
(
    id               SERIAL         PRIMARY KEY,
    chain_id         INT            NOT NULL REFERENCES quant.industry_chain_def(id),
    segment_name     VARCHAR(50)    NOT NULL COMMENT '环节: 上游/中游/下游',
    sort_order       SMALLINT       NOT NULL DEFAULT 0 COMMENT '上下游顺序: 1上游 2中游 3下游',

    UNIQUE (chain_id, segment_name)
);

COMMENT ON TABLE quant.chain_segment IS '产业链上中下游定义';

-- 子行业（细分概念）
CREATE TABLE IF NOT EXISTS quant.chain_sub_industry
(
    id               SERIAL         PRIMARY KEY,
    segment_id       INT            NOT NULL REFERENCES quant.chain_segment(id),
    sub_name         VARCHAR(100)   NOT NULL COMMENT '子行业名称: 锂矿/动力电池/整车...',

    UNIQUE (segment_id, sub_name)
);

COMMENT ON TABLE quant.chain_sub_industry IS '产业链细分子行业';

-- 股票-子行业映射（N:N 关系）
CREATE TABLE IF NOT EXISTS quant.stock_chain_mapping
(
    id               SERIAL         PRIMARY KEY,
    stock_code       VARCHAR(6)     NOT NULL REFERENCES quant.stock_basic(stock_code),
    chain_id         INT            NOT NULL REFERENCES quant.industry_chain_def(id),
    sub_industry_id  INT            NOT NULL REFERENCES quant.chain_sub_industry(id),
    confidence       SMALLINT       DEFAULT 100 COMMENT '映射置信度(0-100)',

    created_at       TIMESTAMPTZ    DEFAULT now(),
    UNIQUE (stock_code, sub_industry_id)
);

COMMENT ON TABLE quant.stock_chain_mapping IS '股票-产业链映射关系';
CREATE INDEX idx_scm_stock ON quant.stock_chain_mapping (stock_code);
CREATE INDEX idx_scm_chain ON quant.stock_chain_mapping (chain_id);
CREATE INDEX idx_scm_sub ON quant.stock_chain_mapping (sub_industry_id);

-- 产业链上下游关系（有向边）
CREATE TABLE IF NOT EXISTS quant.chain_relation
(
    id               SERIAL         PRIMARY KEY,
    chain_id         INT            NOT NULL REFERENCES quant.industry_chain_def(id),
    from_node        VARCHAR(200)   NOT NULL COMMENT '上游节点',
    to_node          VARCHAR(200)   NOT NULL COMMENT '下游节点',
    relation_type    VARCHAR(20)    DEFAULT 'supply' COMMENT '关系类型: supply/属于',

    UNIQUE (chain_id, from_node, to_node)
);

COMMENT ON TABLE quant.chain_relation IS '产业链有向关系边';