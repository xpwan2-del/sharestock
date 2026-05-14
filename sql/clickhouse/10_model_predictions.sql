-- ============================================================
-- ClickHouse DDL: 模型预测结果表
-- 存储 MLPipeline.predict() 的输出
-- ============================================================

CREATE TABLE IF NOT EXISTS quant_ts.model_predictions
(
    stock_code        FixedString(6)  COMMENT '股票代码',
    predict_date      Date            COMMENT '预测日期',

    -- LightGBM 输出
    up_probability    Float64         COMMENT '上涨概率(0-1)',
    down_probability  Float64         COMMENT '下跌概率(0-1)',
    prediction        LowCardinality(String) COMMENT '预测方向: bullish/bearish/neutral',

    -- 模型元数据
    model_name        String          COMMENT '模型名称，如 lightgbm_v2',
    model_version     String          COMMENT '模型版本',
    feature_batch_id  String          COMMENT '使用的特征批次ID',
    auc_validation    Nullable(Float64) COMMENT '验证集AUC',

    created_at        DateTime        DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(predict_date)
ORDER BY (stock_code, predict_date)
SETTINGS index_granularity = 4096
COMMENT '模型预测结果';

-- 跳数索引：快速筛选高概率预测
ALTER TABLE quant_ts.model_predictions
ADD INDEX idx_up_prob up_probability TYPE minmax GRANULARITY 4;