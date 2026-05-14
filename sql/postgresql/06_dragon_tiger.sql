-- ============================================================
-- PostgreSQL DDL: 龙虎榜数据
-- 数据来源: DragonTigerCollector
-- ============================================================

-- 龙虎榜明细（席位级别）
CREATE TABLE IF NOT EXISTS quant.dragon_tiger_detail
(
    id               BIGSERIAL       PRIMARY KEY,
    trade_date       DATE            NOT NULL COMMENT '交易日期',
    stock_code       VARCHAR(6)      NOT NULL REFERENCES quant.stock_basic(stock_code),
    stock_name       VARCHAR(50)                 COMMENT '股票名称',

    -- 席位信息
    seat_name        VARCHAR(200)    NOT NULL COMMENT '席位名称',
    seat_type        VARCHAR(20)                 COMMENT '席位类型: institution/venture/retail',
    direction        VARCHAR(10)     NOT NULL COMMENT '买卖方向: 买入/卖出',

    buy_amount       NUMERIC(18,2)   DEFAULT 0 COMMENT '买入金额',
    sell_amount      NUMERIC(18,2)   DEFAULT 0 COMMENT '卖出金额',
    net_amount       NUMERIC(18,2)   DEFAULT 0 COMMENT '净买入',

    -- 涨跌停
    pct_chg          NUMERIC(8,2)               COMMENT '当日涨跌幅(%)',

    created_at       TIMESTAMPTZ     DEFAULT now(),
    UNIQUE (trade_date, stock_code, seat_name, direction)
);

COMMENT ON TABLE quant.dragon_tiger_detail IS '龙虎榜席位明细';
CREATE INDEX idx_dt_detail_date ON quant.dragon_tiger_detail (trade_date DESC);
CREATE INDEX idx_dt_detail_stock ON quant.dragon_tiger_detail (stock_code, trade_date DESC);
CREATE INDEX idx_dt_detail_seat ON quant.dragon_tiger_detail (seat_name, trade_date DESC);

-- 龙虎榜个股每日汇总
CREATE TABLE IF NOT EXISTS quant.dragon_tiger_summary
(
    id               BIGSERIAL       PRIMARY KEY,
    trade_date       DATE            NOT NULL,
    stock_code       VARCHAR(6)      NOT NULL REFERENCES quant.stock_basic(stock_code),

    -- 汇总统计
    total_buy        NUMERIC(18,2)   DEFAULT 0 COMMENT '总买入',
    total_sell       NUMERIC(18,2)   DEFAULT 0 COMMENT '总卖出',
    net_flow         NUMERIC(18,2)   DEFAULT 0 COMMENT '净流入',

    -- 机构分类
    institution_buy  NUMERIC(18,2)   DEFAULT 0 COMMENT '机构买入',
    institution_sell NUMERIC(18,2)   DEFAULT 0 COMMENT '机构卖出',
    institution_net  NUMERIC(18,2)   DEFAULT 0 COMMENT '机构净买',

    venture_buy      NUMERIC(18,2)   DEFAULT 0 COMMENT '游资买入',
    venture_sell     NUMERIC(18,2)   DEFAULT 0 COMMENT '游资卖出',
    venture_net      NUMERIC(18,2)   DEFAULT 0 COMMENT '游资净买',

    institution_ratio NUMERIC(6,3)   DEFAULT 0 COMMENT '机构占比',
    venture_ratio    NUMERIC(6,3)    DEFAULT 0 COMMENT '游资占比',
    dominant_force   VARCHAR(20)                COMMENT '主导力量: institution/venture',

    -- 上榜原因
    reason           TEXT                       COMMENT '上榜原因',

    created_at       TIMESTAMPTZ     DEFAULT now(),
    UNIQUE (trade_date, stock_code)
);

COMMENT ON TABLE quant.dragon_tiger_summary IS '龙虎榜每日个股汇总';
CREATE INDEX idx_dt_summary_date ON quant.dragon_tiger_summary (trade_date DESC);
CREATE INDEX idx_dt_summary_net ON quant.dragon_tiger_summary (net_flow DESC);

-- 高管增减持
CREATE TABLE IF NOT EXISTS quant.insider_trading
(
    id               BIGSERIAL       PRIMARY KEY,
    stock_code       VARCHAR(6)      NOT NULL REFERENCES quant.stock_basic(stock_code),
    trade_date       DATE            NOT NULL COMMENT '变动日期',

    insider_name     VARCHAR(100)                COMMENT '高管姓名',
    position         VARCHAR(100)                COMMENT '职位',
    direction        VARCHAR(10)     NOT NULL COMMENT '变动方向: 增持/减持',
    shares_changed   BIGINT                     COMMENT '变动股数',
    avg_price        NUMERIC(10,2)              COMMENT '变动均价',
    reason           TEXT                       COMMENT '变动原因',

    created_at       TIMESTAMPTZ     DEFAULT now(),
    UNIQUE (stock_code, trade_date, insider_name)
);

COMMENT ON TABLE quant.insider_trading IS '高管增减持记录';
CREATE INDEX idx_insider_stock ON quant.insider_trading (stock_code, trade_date DESC);
CREATE INDEX idx_insider_date ON quant.insider_trading (trade_date DESC);