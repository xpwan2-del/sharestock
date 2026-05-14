-- ============================================================
-- ClickHouse DDL: 模型训练特征表
-- 存储 FeatureEngineer.build_features() 的输出
-- 宽表设计，每行 ~50 个特征列
-- 数据量: 5000只 x 每次训练 ~120行( lookback ) = 60万行/批次
-- ============================================================

CREATE TABLE IF NOT EXISTS quant_ts.model_features
(
    stock_code        FixedString(6)  COMMENT '股票代码',
    feature_date      Date            COMMENT '特征对应交易日',  -- 用 feature_date 而不是 trade_date 避免歧义

    -- 价格动量特征
    ma5               Nullable(Float64) COMMENT 'MA5',
    ma10              Nullable(Float64) COMMENT 'MA10',
    ma20              Nullable(Float64) COMMENT 'MA20',
    ma60              Nullable(Float64) COMMENT 'MA60',
    ma5_volume        Nullable(Float64) COMMENT '5日均量',
    volume_ratio      Nullable(Float64) COMMENT '量比',

    -- 技术指标
    rsi14             Nullable(Float64) COMMENT 'RSI(14)',
    macd              Nullable(Float64) COMMENT 'MACD DIF',
    macd_signal       Nullable(Float64) COMMENT 'MACD DEA',
    macd_hist         Nullable(Float64) COMMENT 'MACD 柱',
    atr14             Nullable(Float64) COMMENT 'ATR(14)',
    boll_mid          Nullable(Float64) COMMENT '布林中轨',
    boll_upper        Nullable(Float64) COMMENT '布林上轨',
    boll_lower        Nullable(Float64) COMMENT '布林下轨',

    -- 价格位置特征
    ret_1d            Nullable(Float64) COMMENT '1日收益率',
    ret_5d            Nullable(Float64) COMMENT '5日收益率',
    ret_20d           Nullable(Float64) COMMENT '20日收益率',
    volatility_20d    Nullable(Float64) COMMENT '20日波动率',
    pct_chg           Nullable(Float64) COMMENT '当日涨跌幅',

    -- 多周期价格偏离 MA
    open_ma5_ret      Nullable(Float64) COMMENT '开盘价/MA5-1',
    open_ma10_ret     Nullable(Float64) COMMENT '开盘价/MA10-1',
    open_ma20_ret     Nullable(Float64) COMMENT '开盘价/MA20-1',
    open_ma60_ret     Nullable(Float64) COMMENT '开盘价/MA60-1',
    high_ma5_ret      Nullable(Float64) COMMENT '最高价/MA5-1',
    high_ma10_ret     Nullable(Float64) COMMENT '最高价/MA10-1',
    high_ma20_ret     Nullable(Float64) COMMENT '最高价/MA20-1',
    high_ma60_ret     Nullable(Float64) COMMENT '最高价/MA60-1',
    low_ma5_ret       Nullable(Float64) COMMENT '最低价/MA5-1',
    low_ma10_ret      Nullable(Float64) COMMENT '最低价/MA10-1',
    low_ma20_ret      Nullable(Float64) COMMENT '最低价/MA20-1',
    low_ma60_ret      Nullable(Float64) COMMENT '最低价/MA60-1',
    close_ma5_ret     Nullable(Float64) COMMENT '收盘价/MA5-1',
    close_ma10_ret    Nullable(Float64) COMMENT '收盘价/MA10-1',
    close_ma20_ret    Nullable(Float64) COMMENT '收盘价/MA20-1',
    close_ma60_ret    Nullable(Float64) COMMENT '收盘价/MA60-1',

    -- 波动率
    volatility_5d     Nullable(Float64) COMMENT '5日波动率',
    volatility_10d    Nullable(Float64) COMMENT '10日波动率',
    volatility_20d_col Nullable(Float64) COMMENT '20日波动率(别名)',

    -- 成交量比
    volume_ma5_ratio  Nullable(Float64) COMMENT '量/5日均量',
    volume_ma10_ratio Nullable(Float64) COMMENT '量/10日均量',
    volume_ma20_ratio Nullable(Float64) COMMENT '量/20日均量',

    -- 日内形态
    high_low_ratio    Nullable(Float64) COMMENT '(高-低)/收',
    close_open_ratio  Nullable(Float64) COMMENT '收/开',
    daily_range       Nullable(Float64) COMMENT '(高-低)/开',

    -- 动量
    momentum_5d       Nullable(Float64) COMMENT '5日动量(收/5日收-1)',
    momentum_10d      Nullable(Float64) COMMENT '10日动量',
    momentum_20d      Nullable(Float64) COMMENT '20日动量',
    momentum_60d      Nullable(Float64) COMMENT '60日动量',

    -- 最大回撤
    max_dd_5d         Nullable(Float64) COMMENT '5日最大回撤',
    max_dd_10d        Nullable(Float64) COMMENT '10日最大回撤',
    max_dd_20d        Nullable(Float64) COMMENT '20日最大回撤',
    max_dd_60d        Nullable(Float64) COMMENT '60日最大回撤',

    -- 指标变化
    rsi_divergence    Nullable(Float64) COMMENT 'RSI与5日前差值',
    macd_divergence   Nullable(Float64) COMMENT 'MACD与5日前差值',

    -- 价格距均线
    close_ma5_dist    Nullable(Float64) COMMENT '(收-MA5)/MA5',
    close_ma10_dist   Nullable(Float64) COMMENT '(收-MA10)/MA10',

    -- 量能趋势
    volume_trend      Nullable(Float64) COMMENT '量/20日前量',
    price_position    Nullable(Float64) COMMENT '60日价格位置(0-1)',

    -- 标签（训练目标）
    target_5d         Nullable(Float64) COMMENT '5日后收益率（训练标签-回归）',
    target_direction_5d Nullable(UInt8) COMMENT '5日后涨跌方向（训练标签-分类）',

    -- 元数据
    batch_id          String           COMMENT '训练批次ID',
    created_at        DateTime         DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(feature_date)
ORDER BY (stock_code, feature_date)
SETTINGS index_granularity = 8192
COMMENT '模型训练特征宽表';