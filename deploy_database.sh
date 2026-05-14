#!/bin/bash
# ============================================================
# A股量化分析系统 - 数据库一键部署脚本
# 用法: bash deploy_database.sh [init|reset|status]
# ============================================================

set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

ACTION="${1:-init}"

case "$ACTION" in
  init|start)
    log_info "=== 启动数据库服务 ==="

    # 检查 .env
    if [ ! -f ".env" ]; then
      log_warn ".env 文件不存在，从 .env.example 复制"
      cp .env.example .env
      log_info "请编辑 .env 修改默认密码后重新运行"
      exit 1
    fi

    # 启动容器
    docker compose up -d

    log_info "等待 PostgreSQL 就绪..."
    for i in $(seq 1 30); do
      if docker exec quant-postgres pg_isready -U quant_user -d quant_meta > /dev/null 2>&1; then
        log_info "PostgreSQL 就绪 (${i}s)"
        break
      fi
      sleep 1
    done

    log_info "等待 ClickHouse 就绪..."
    for i in $(seq 1 30); do
      if docker exec quant-clickhouse clickhouse-client --query "SELECT 1" > /dev/null 2>&1; then
        log_info "ClickHouse 就绪 (${i}s)"
        break
      fi
      sleep 1
    done

    log_info "=== 数据库初始化完成 ==="
    docker compose ps
    ;;

  reset)
    log_warn "!!! 此操作将删除所有数据 !!!"
    read -p "确认重置数据库？(yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
      log_info "已取消"
      exit 0
    fi

    log_info "停止并删除容器和数据卷..."
    docker compose down -v
    log_info "重新初始化..."
    docker compose up -d
    log_info "=== 数据库已重置 ==="
    ;;

  status)
    docker compose ps
    echo ""
    echo "=== PostgreSQL 表 ==="
    docker exec quant-postgres psql -U quant_user -d quant_meta -c \
      "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
       FROM pg_tables WHERE schemaname = 'quant' ORDER BY tablename;"

    echo ""
    echo "=== ClickHouse 表 ==="
    docker exec quant-clickhouse clickhouse-client --query \
      "SELECT database, name, engine, formatReadableSize(total_bytes) as size
       FROM system.tables WHERE database = 'quant_ts' ORDER BY name;"
    ;;

  stop)
    log_info "停止数据库服务..."
    docker compose stop
    log_info "已停止"
    ;;

  *)
    echo "用法: $0 {init|start|reset|status|stop}"
    echo "  init    - 启动所有数据库 (默认)"
    echo "  reset   - 删除数据并重新初始化"
    echo "  status  - 查看数据库状态"
    echo "  stop    - 停止数据库服务"
    exit 1
    ;;
esac