#!/usr/bin/env python3
"""
A股量化分析系统 - 主入口
========================
支持三种运行模式:
  daily    - 盘后全量分析 + 生成日报
  realtime - 盘中实时监控
  train    - 模型训练
  dashboard - 启动可视化看板
  scan     - 自定义扫描模式

用法:
  python main.py daily
  python main.py realtime --watch 000001,600519
  python main.py realtime --auto-hot
  python main.py train --stocks 000001,600519
  python main.py train --batch 50
  python main.py dashboard
  python main.py scan --concept "新能源汽车"
"""
import sys
import argparse
import asyncio
import time as sleep_time
from datetime import datetime, time
from loguru import logger

from config.settings import DAILY_RUN_TIME, REALTIME_CONFIG, ML_CONFIG
from data.collector import DataCollector
from data.data_quality import DataQuality
from data.market_data import MarketDataCollector
from utils.calendar import (
    get_latest_trading_day,
    get_next_daily_run_datetime,
    is_market_open,
    is_trading_day,
)
from report.daily_report import DailyReportGenerator
from data.realtime_publisher import RealtimeDataPublisher
from trading.realtime_monitor import RealtimeMonitor
from trading.signal_generator import SignalGenerator
from models.feedback_loop import start_ml_feedback_loop
from models.train_pipeline import MLPipeline
from analysis.leader_finder import LeaderFinder
from analysis.trend_reversal import TrendReversalDetector
from analysis.institution_style import InstitutionStyleAnalyzer
from sentiment.market_sentiment import MarketSentimentAnalyzer


def run_daily():
    logger.info("=== 启动每日盘后分析 ===")
    generator = DailyReportGenerator()
    generator.run_full_report(output_markdown=True)
    if ML_CONFIG.get("enable_daily_training", True):
        logger.info("启动盘后模型训练与预测闭环")
        run_train(batch_size=ML_CONFIG.get("daily_train_batch_size", 20))
    logger.info("=== 每日分析完成 ===")


def run_daily_scheduler(run_time: str = DAILY_RUN_TIME):
    logger.info(f"=== 启动交易日定时任务模式，执行时间: {run_time} ===")
    try:
        while True:
            next_run = get_next_daily_run_datetime(run_time=run_time, now=datetime.now())
            while True:
                now = datetime.now()
                wait_seconds = int((next_run - now).total_seconds())
                if wait_seconds <= 0:
                    break
                logger.info(f"下次交易日任务: {next_run.strftime('%Y-%m-%d %H:%M:%S')}，等待 {wait_seconds} 秒")
                sleep_time.sleep(min(wait_seconds, 60))
            if not is_trading_day(next_run.date()):
                logger.info(f"{next_run.strftime('%Y-%m-%d')} 不是交易日，跳过执行")
                sleep_time.sleep(60)
                continue
            logger.info(f"开始执行 {next_run.strftime('%Y-%m-%d')} 的 daily 任务")
            run_daily()
            sleep_time.sleep(61)
    except KeyboardInterrupt:
        logger.info("收到退出信号，定时任务已停止")


def run_realtime(watch_list=None, auto_hot=False):
    logger.info("=== 启动实时监控模式 ===")
    monitor = RealtimeMonitor(watch_list=watch_list)
    publisher = RealtimeDataPublisher(watch_list=watch_list)
    if auto_hot:
        logger.info("自动加载热门概念龙头到监控列表...")
        monitor.set_hot_watch_from_leaders()
    if watch_list:
        monitor.add_watch(watch_list)
    monitor_thread = monitor.start_background()
    publisher_thread = None
    import threading
    def run_publisher():
        asyncio.run(publisher.start())
    publisher_thread = threading.Thread(target=run_publisher, daemon=True, name="RealtimeDataPublisher")
    publisher_thread.start()
    logger.info("实时行情发布服务已启动")
    logger.info("监控已启动，按 Ctrl+C 退出...")
    try:
        import time as _time
        while True:
            if datetime.now().time() > time(15, 5):
                logger.info("收盘后，自动退出监控")
                break
            _time.sleep(60)
    except KeyboardInterrupt:
        logger.info("收到退出信号")
    finally:
        publisher.stop()
        monitor.stop()
        alerts = monitor.get_alerts()
        if alerts:
            logger.info(f"本次监控共产生 {len(alerts)} 条警报")


def run_train(stock_codes=None, batch_size=0, output: str = None):
    logger.info("=== 启动模型训练 ===")
    pipeline = MLPipeline()
    feedback_loop = start_ml_feedback_loop()
    if stock_codes:
        codes = stock_codes if isinstance(stock_codes, list) else stock_codes.split(",")
        logger.info(f"训练指定股票: {codes}")
        pipeline.batch_train(codes)
        pipeline.predict_batch(codes)
    elif batch_size > 0:
        market = MarketDataCollector()
        all_stocks = market.get_a_share_list()
        codes = all_stocks["code"].head(batch_size).tolist()
        logger.info(f"批量训练 {len(codes)} 只股票")
        pipeline.batch_train(codes)
        pipeline.predict_batch(codes)
    else:
        market = MarketDataCollector()
        quotes = market.get_realtime_quotes()
        if quotes.empty:
            logger.warning("无实时行情数据")
            return
        active = quotes[quotes["pct_chg"].abs() > 2]
        codes = active["code"].head(20).tolist()
        logger.info(f"训练活跃股票: {len(codes)} 只")
        pipeline.batch_train(codes)
        pipeline.predict_batch(codes)
    logger.info(f"=== 模型训练完成，复合信号闭环已启动: {feedback_loop.__class__.__name__} ===")


def run_dashboard():
    logger.info("=== 启动可视化看板 ===")
    import subprocess
    import os
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard", "app.py")
    logger.info(f"Streamlit 启动中... http://localhost:8501")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", dashboard_path,
        "--server.port", "8501",
    ])


def run_scan(concept=None, stock=None, top_n=10):
    logger.info("=== 启动自定义扫描 ===")
    if concept:
        finder = LeaderFinder()
        logger.info(f"扫描概念: {concept}")
        leaders = finder.identify_all_leaders(concept)
        for ltype, df in leaders.items():
            if df is not None and not df.empty:
                print(f"\n{'='*40}")
                print(f"  {ltype}")
                print(f"{'='*40}")
                cols = ["code", "name"] if "code" in df.columns else ["代码", "名称"]
                for col in cols:
                    if col in df.columns:
                        print(df[col].to_string(index=False))
                        break
    if stock:
        detector = TrendReversalDetector()
        result = detector.comprehensive_reversal_scan(stock)
        print(f"\n{'='*40}")
        print(f"  {stock} 趋势逆转分析")
        print(f"{'='*40}")
        print(f"  逆转类型: {result.get('reversal_type', 'N/A')}")
        print(f"  逆转评分: {result.get('reversal_score', 'N/A')}")
        print(f"  信号: {result.get('signals', [])}")
        print(f"  最新收盘价: {result.get('latest_close', 'N/A')}")
    if not concept and not stock:
        finder = LeaderFinder()
        hot_concepts = finder.scan_hot_concepts(top_n=top_n)
        print(f"\n热门概念 Top {top_n}:")
        for i, c in enumerate(hot_concepts, 1):
            print(f"  {i}. {c}")


def main():
    parser = argparse.ArgumentParser(
        description="A股量化分析系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "mode",
        choices=["daily", "realtime", "train", "dashboard", "scan"],
        help="运行模式",
    )
    parser.add_argument(
        "--watch",
        type=str,
        default=None,
        help="实时监控股票列表，逗号分隔 (如: 000001,600519)",
    )
    parser.add_argument(
        "--auto-hot",
        action="store_true",
        help="自动加载热门概念龙头到监控列表",
    )
    parser.add_argument(
        "--stocks",
        type=str,
        default=None,
        help="训练指定股票列表，逗号分隔",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=0,
        help="批量训练前N只股票",
    )
    parser.add_argument(
        "--concept",
        type=str,
        default=None,
        help="扫描指定概念板块",
    )
    parser.add_argument(
        "--stock",
        type=str,
        default=None,
        help="扫描单只股票的趋势逆转",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="显示前N个热门概念",
    )
    parser.add_argument(
        "--run-time",
        type=str,
        default=DAILY_RUN_TIME,
        help="daily 定时执行时间，格式 HH:MM",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="以交易日定时方式持续运行 daily 任务",
    )
    args = parser.parse_args()

    logger.info(f"A股量化系统 v1.0 启动 - 模式: {args.mode}")

    # 市场状态
    latest_day = get_latest_trading_day()
    market_open = is_market_open()
    is_weekday = is_trading_day()
    logger.info(f"最近交易日: {latest_day}")
    logger.info(f"市场状态: {'交易中' if market_open else '休市' if is_weekday else '非交易日(周末)'}")

    quality = DataQuality()
    quality.print_quality_report()
    cap = quality.check_realtime_capability()
    if cap.get("warning"):
        logger.warning(cap["warning"])
    if not market_open:
        logger.info("当前非盘中交易时段，实时数据不可用（正常现象）")

    t0 = datetime.now()
    if args.mode == "daily":
        if args.schedule:
            run_daily_scheduler(run_time=args.run_time)
        else:
            run_daily()
    elif args.mode == "realtime":
        watch = args.watch.split(",") if args.watch else None
        run_realtime(watch_list=watch, auto_hot=args.auto_hot)
    elif args.mode == "train":
        stocks = args.stocks.split(",") if args.stocks else None
        run_train(stock_codes=stocks, batch_size=args.batch)
    elif args.mode == "dashboard":
        run_dashboard()
    elif args.mode == "scan":
        run_scan(concept=args.concept, stock=args.stock, top_n=args.top_n)
    elapsed = (datetime.now() - t0).total_seconds()
    logger.info(f"系统运行完成，耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()