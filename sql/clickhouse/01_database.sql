-- ============================================================
-- ClickHouse 数据库初始化
-- A股量化分析系统 - 时序数据存储层
-- ============================================================

CREATE DATABASE IF NOT EXISTS quant_ts
ENGINE = Atomic
COMMENT '量化系统时序数据库';

-- 集群模式（生产环境多副本时启用）
-- CREATE DATABASE IF NOT EXISTS quant_ts ON CLUSTER quant_cluster
-- ENGINE = Atomic;