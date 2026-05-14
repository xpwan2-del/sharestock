-- ============================================================
-- ClickHouse DDL: 实时监控警报表
-- 存储 RealtimeMonitor._alerts (PriceAlert dataclass)
-- 保留90天用于事后分析
-- ============================================================

CREATE TABLE IF NOT EXISTS quant_ts.trading_alerts
(
    alert_time        DateTime        COMMENT '警报触发时间',
    stock_code        FixedString(6)  COMMENT '股票代码',
    stock_name        String          COMMENT '股票名称',

    alert_type        LowCardinality(String) COMMENT '警报类型: surge/plunge/volume_breakout/breakout',
    alert_message     String          COMMENT '警报描述',
    price             Float64         COMMENT '触发价格',
    pct_chg           Float64         COMMENT '涨跌幅(%)',

    created_at        DateTime        DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(alert_time)
ORDER BY (alert_time, alert_type, stock_code)
TTL alert_time + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 256
COMMENT '实时监控警报（保留90天）';