-- ============================================================
-- PostgreSQL DDL: 模型注册表 & 交易信号历史
-- ============================================================

-- 模型注册表
CREATE TABLE IF NOT EXISTS quant.model_registry
(
    id               SERIAL          PRIMARY KEY,
    model_name       VARCHAR(100)    NOT NULL COMMENT '模型名称: lightgbm_classifier_v1',
    model_type       VARCHAR(50)     NOT NULL COMMENT '模型类型: lightgbm/xgboost/lstm',
    model_version    VARCHAR(20)     NOT NULL COMMENT '版本号: v1.0.0',

    -- 训练元数据
    training_date    DATE            NOT NULL COMMENT '训练日期',
    stock_codes      TEXT[]                     COMMENT '训练覆盖的股票列表',
    feature_count    INT                        COMMENT '特征数量',
    training_samples INT                        COMMENT '训练样本数',

    -- 性能指标
    auc_validation   NUMERIC(6,4)              COMMENT '验证集AUC',
    accuracy         NUMERIC(6,4)              COMMENT '准确率',
    f1_score         NUMERIC(6,4)              COMMENT 'F1',

    -- 模型二进制（大文件存对象存储，这里存路径）
    model_path       VARCHAR(500)               COMMENT '模型文件路径',
    scaler_path      VARCHAR(500)               COMMENT '标准化器路径',
    feature_names    TEXT[]                     COMMENT '特征列名列表',

    is_active        BOOLEAN         DEFAULT FALSE COMMENT '是否为当前活跃模型',

    created_at       TIMESTAMPTZ     DEFAULT now(),
    UNIQUE (model_name, model_version)
);

COMMENT ON TABLE quant.model_registry IS '机器学习模型注册表';
CREATE INDEX idx_model_active ON quant.model_registry (is_active) WHERE is_active;

-- 交易信号历史
CREATE TABLE IF NOT EXISTS quant.signal_history
(
    id               BIGSERIAL       PRIMARY KEY,
    signal_time      TIMESTAMPTZ     NOT NULL DEFAULT now() COMMENT '信号产生时间',
    stock_code       VARCHAR(6)      NOT NULL REFERENCES quant.stock_basic(stock_code),

    -- 信号分类
    signal_type      VARCHAR(30)     NOT NULL COMMENT '信号类型: leader/reversal/sentiment/ml_prediction',
    signal_subtype   VARCHAR(30)                COMMENT '子类型: logic_leader/sentiment_leader/capacity_leader/strong_reversal...',
    signal_action    VARCHAR(20)     NOT NULL COMMENT '建议操作: leader_watch/reversal_buy/caution/hold...',

    -- 信号强度
    strength_score   NUMERIC(6,2)              COMMENT '信号强度得分',
    confidence       NUMERIC(5,4)              COMMENT '置信度(0-1)',

    -- 关联分析结果
    concept          VARCHAR(100)               COMMENT '关联概念/板块',
    detail           JSONB                      COMMENT '信号详细信息（灵活存储）',

    -- 模型预测时关联模型
    model_id         INT                        COMMENT '关联模型ID',

    created_at       TIMESTAMPTZ     DEFAULT now()
);

COMMENT ON TABLE quant.signal_history IS '交易信号历史记录';
CREATE INDEX idx_signal_time ON quant.signal_history (signal_time DESC);
CREATE INDEX idx_signal_stock ON quant.signal_history (stock_code, signal_time DESC);
CREATE INDEX idx_signal_type ON quant.signal_history (signal_type, signal_time DESC);
CREATE INDEX idx_signal_detail_gin ON quant.signal_history USING GIN (detail);