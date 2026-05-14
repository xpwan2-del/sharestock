-- ============================================================
-- PostgreSQL 数据库初始化
-- A股量化分析系统 - 元数据/业务数据存储层
-- ============================================================

-- 创建数据库（需用 superuser 执行）
-- CREATE DATABASE quant_meta OWNER quant_user ENCODING 'UTF8' LC_COLLATE 'zh_CN.UTF-8';

-- 所有表集中在 quant  schema 下
CREATE SCHEMA IF NOT EXISTS quant;
COMMENT ON SCHEMA quant IS '量化系统业务数据';

-- 常用扩展（全文搜索、UUID、向量）
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- 模糊文本搜索
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- UUID 生成
-- CREATE EXTENSION IF NOT EXISTS "pgvector";   -- 可选：向量相似度搜索