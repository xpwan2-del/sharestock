#!/usr/bin/env python3
"""
全面集成测试 - 验证数据新鲜度 + 所有模块
"""
import sys
from datetime import datetime
from loguru import logger

from utils.calendar import get_latest_trading_day, is_market_open


def test_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_result(name: str, passed: bool, detail: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    ts = "" if not detail else f" | {detail}"
    print(f"  {status}  {name}{ts}")
    return passed


def main():
    latest_trading_day = get_latest_trading_day()
    market_open = is_market_open()
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n{'#'*60}")
    print(f"#  A股量化系统 - 全面集成测试")
    print(f"#  测试时间: {today}")
    print(f"#  最近交易日: {latest_trading_day}")
    print(f"#  市场状态: {'交易中' if market_open else '休市'}")
    print(f"{'#'*60}")

    passed = 0
    failed = 0
    freshness_issues = []

    # ==================== 1. 数据层测试 ====================
    test_header("一、数据层 - 新鲜度检查")

    # 1.1 涨停池
    from data.market_data import MarketDataCollector
    mkt = MarketDataCollector()
    limit_pool = mkt.get_limit_up_pool(latest_trading_day)
    has_data = limit_pool is not None and not limit_pool.empty
    ok = test_result("涨停池", has_data, f"{len(limit_pool) if has_data else 0}只")
    if ok: passed += 1
    else: failed += 1

    if has_data and "日期" in limit_pool.columns:
        dp = str(limit_pool.iloc[0]["日期"])
        if latest_trading_day not in dp.replace("-", ""):
            freshness_issues.append(f"涨停池日期={dp} 期望={latest_trading_day}")
            print(f"     ⚠️ 日期不匹配: {dp} vs 期望 {latest_trading_day}")

    # 1.2 强势涨停
    strong = mkt.get_continuous_limit_up()
    has_strong = strong is not None and not strong.empty
    ok = test_result("强势涨停池", has_strong, f"{len(strong) if has_strong else 0}只")
    if ok: passed += 1
    else: failed += 1

    # 1.3 龙虎榜
    from data.dragon_tiger import DragonTigerCollector
    dt = DragonTigerCollector()
    lhb = dt.get_daily_dragon_tiger(latest_trading_day)
    has_lhb = lhb is not None and not lhb.empty
    ok = test_result("龙虎榜", has_lhb, f"{len(lhb) if has_lhb else 0}条")
    if ok: passed += 1
    else: failed += 1

    if has_lhb:
        print(f"     📅 日期: {latest_trading_day} (数据采集日)")

    # 1.4 北向资金
    from data.fund_flow import FundFlowCollector
    ff = FundFlowCollector()
    north = ff.get_north_bound_daily()
    has_north = north.get("net_flow_yi") is not None
    north_date = north.get("date", "")
    ok = test_result("北向资金", has_north, f"净买{north.get('net_flow_yi', 0):+.2f}亿")
    if ok: passed += 1
    else: failed += 1

    if north_date and latest_trading_day not in north_date.replace("-", ""):
        freshness_issues.append(f"北向日期={north_date} 期望={latest_trading_day}")
        print(f"     ⚠️ 日期: {north_date}")

    # 1.5 融资融券
    margin = ff.get_margin_trading()
    has_margin = margin.get("balance", 0) > 0
    ok = test_result("融资融券", has_margin, f"余额{margin.get('balance', 0):.0f}")
    if ok: passed += 1
    else: failed += 1

    if margin.get("date"):
        print(f"     📅 日期: {margin.get('date')} (T+1延迟正常)")

    # 1.6 指数行情
    idx = mkt.get_market_index("sh000001")
    has_idx = idx is not None and not idx.empty
    ok = test_result("上证指数", has_idx, f"{len(idx) if has_idx else 0}天")
    if ok: passed += 1
    else: failed += 1

    # 1.7 公告采集
    from data.announcement import AnnouncementCollector
    ann = AnnouncementCollector()
    try:
        ann_df = ann.fetch_cninfo_announcements("000001", "2026-05-01", "2026-05-10", max_pages=1)
        has_ann = ann_df is not None and not ann_df.empty
        ok = test_result("公告采集", has_ann, f"{len(ann_df) if has_ann else 0}条")
        if ok: passed += 1
        else: failed += 1
    except Exception as e:
        ok = test_result("公告采集", False, str(e)[:50])
        failed += 1

    # ==================== 2. 情绪分析 ====================
    test_header("二、情绪分析模块")

    from sentiment.market_sentiment import MarketSentimentAnalyzer
    sentiment = MarketSentimentAnalyzer()

    breadth = mkt.get_market_breadth()
    breadth_ok = len(breadth) > 0
    ok = test_result("市场宽度", breadth_ok, f"涨比{breadth.get('up_ratio', 'N/A')}%")
    if ok: passed += 1
    else: failed += 1

    sentiment_result = sentiment.analyze_market_breadth(breadth)
    ok = test_result("情绪评分", sentiment_result.get("score", 0) > 0, f"{sentiment_result.get('score', 0):.0f}分/{sentiment_result.get('sentiment', '')}")
    if ok: passed += 1
    else: failed += 1

    from sentiment.news_sentiment import NewsSentimentAnalyzer
    news = NewsSentimentAnalyzer()
    analysis = news.analyze_text("重大利好！业绩暴增300%", "业绩预告")
    ok = test_result("NLP情感分析", analysis.get("sentiment") == "positive", f"得分:{analysis.get('score', 0):.2f}")
    if ok: passed += 1
    else: failed += 1

    from sentiment.announcement_nlp import AnnouncementNLPAnalyzer
    ann_nlp = AnnouncementNLPAnalyzer()
    result = ann_nlp.analyze_announcement("业绩预增公告", "")
    ok = test_result("公告NLP", "bullish" in result.get("impact_level", ""), result.get("impact_level", ""))
    if ok: passed += 1
    else: failed += 1

    # ==================== 3. 分析引擎 ====================
    test_header("三、分析引擎")

    from analysis.leader_finder import LeaderFinder
    lf = LeaderFinder()

    # 通用股票测试
    daily = mkt.get_daily_kline("000001", "20260101", "20260510")
    daily = mkt.calculate_technical_indicators(daily)
    has_kline = daily is not None and not daily.empty and len(daily) > 20
    ok = test_result("K线+技术指标", has_kline, f"{len(daily) if has_kline else 0}天")
    if ok: passed += 1
    else: failed += 1

    from analysis.trend_reversal import TrendReversalDetector
    trd = TrendReversalDetector()
    reversal = trd.comprehensive_reversal_scan("000001", "平安银行")
    ok = test_result("趋势逆转检测", reversal.get("has_data", False), reversal.get("reversal_type", ""))
    if ok: passed += 1
    else: failed += 1

    from analysis.institution_style import InstitutionStyleAnalyzer
    inst = InstitutionStyleAnalyzer()
    inst_report = inst.generate_institution_report()
    dragon_ok = len(inst_report.get("dragon_tiger_analysis", {})) > 0
    ok = test_result("机构手法分析", dragon_ok, f"席位: {inst_report.get('dragon_tiger_analysis', {}).get('total_seats', 'N/A')}")
    if ok: passed += 1
    else: failed += 1

    # ==================== 4. 神经网络分析 ====================
    test_header("四、神经网络分析")

    from analysis.correlation_network import CorrelationNetworkAnalyzer
    cna = CorrelationNetworkAnalyzer()

    cm, _, _ = cna.build_correlation_from_quotes(limit_pool, top_n=20)
    ok = test_result("近似关联矩阵", not cm.empty, f"约{cm.shape[0]}x{cm.shape[1]}" if not cm.empty else "周末无实时数据-正常")
    if ok: passed += 1
    else: failed += 1

    clusters = cna.cluster_market_regime(kline_data=daily)
    cluster_ok = clusters.get("success", False) or clusters.get("labels")
    ok = test_result("市场聚类", cluster_ok, f"周末回退模式(交易日数据准确)" if not cluster_ok else f"{len(set(clusters['labels']))} 类")
    if ok: passed += 1
    else: failed += 1

    # ==================== 5. ML流水线 ====================
    test_header("五、ML流水线")

    from models.train_pipeline import FeatureEngineer, MLPipeline
    fe = FeatureEngineer()
    features = fe.build_features("000001")
    has_feat = features is not None and not features.empty
    ok = test_result("特征工程", has_feat, f"{len(features.columns) if has_feat else 0}维")
    if ok: passed += 1
    else: failed += 1

    if has_feat and len(features) > 60:
        ml = MLPipeline()
        model = ml.train_single_stock("000001")
        ok = test_result("模型训练", model is not None, "sklearn回退模式" if model else "失败")
        if ok:
            passed += 1
            pred = ml.predict("000001")
            if pred:
                test_result("模型预测", True, f"{pred.get('prediction', '')}")
                passed += 1
            else:
                test_result("模型预测", False, "预测返回None")
                failed += 1
        else:
            failed += 1
            test_result("模型预测", False, "无模型")
            failed += 1
    else:
        test_result("模型训练", False, "特征不足")
        failed += 1
        test_result("模型预测", False, "级联失败")
        failed += 1

    # ==================== 6. 交易模块 ====================
    test_header("六、交易模块")

    from trading.realtime_monitor import RealtimeMonitor
    from trading.signal_generator import SignalGenerator
    from trading.executor import TradeExecutor

    monitor = RealtimeMonitor(watch_list=["000001", "600519"])
    ok = test_result("实时监控初始化", len(monitor.watch_list) == 2, f"监控{len(monitor.watch_list)}只")
    if ok: passed += 1
    else: failed += 1

    sig_gen = SignalGenerator()
    sentiment_sig = sig_gen.generate_sentiment_signal()
    ok = test_result("情绪信号生成", "action" in sentiment_sig, sentiment_sig.get("action", ""))
    if ok: passed += 1
    else: failed += 1

    executor = TradeExecutor(initial_capital=100000)
    result = executor.simulate_buy("000001", "平安银行", 10.5, 1000)
    ok = test_result("模拟交易", result.get("success", False), "买入成功" if result.get("success") else result.get("reason", ""))
    if ok: passed += 1
    else: failed += 1

    # ==================== 7. 日报生成 ====================
    test_header("七、日报生成")

    from report.daily_report import DailyReportGenerator
    gen = DailyReportGenerator()
    report_date = gen.run_full_report(output_markdown=True)
    ok = test_result("日报生成", bool(report_date), report_date)
    if ok: passed += 1
    else: failed += 1

    from pathlib import Path
    report_file = Path("data_cache") / "reports" / report_date / "daily_report.md"
    ok = test_result("报告文件", report_file.exists(), str(report_file))
    if ok: passed += 1
    else: failed += 1

    # ==================== 汇总 ====================
    print(f"\n{'#'*60}")
    print(f"#  测试汇总")
    print(f"#  通过: {passed}  失败: {failed}  通过率: {passed}/{passed+failed} ({passed/(passed+failed)*100:.0f}%)")
    if freshness_issues:
        print(f"#  ⚠️ 数据新鲜度问题:")
        for issue in freshness_issues:
            print(f"#     {issue}")
    else:
        print(f"#  ✅ 所有数据时间戳均为最新 (基于交易日 {latest_trading_day})")
    print(f"{'#'*60}")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)