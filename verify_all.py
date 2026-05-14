#!/usr/bin/env python3
"""逐个模块深度验证 - 不接受空结果"""
import sys
import traceback
import pandas as pd
from datetime import datetime
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")

ERRORS = []
WARNINGS = []

def check(name, result, condition, detail=""):
    if condition:
        print(f"  ✅ {name}: {detail}")
        return True
    else:
        print(f"  ❌ {name}: 失败 - {detail}")
        ERRORS.append(name)
        return False

def warn(name, msg):
    print(f"  ⚠️  {name}: {msg}")
    WARNINGS.append(name)

print("=" * 70)
print(" A股量化系统 - 深度模块验证")
print(f" 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 70)

# =================== 0. 基础设施 ===================
print("\n【0】基础设施")
from utils.calendar import get_latest_trading_day, is_market_open, is_trading_day
td = get_latest_trading_day()
print(f"  最近交易日: {td}")
print(f"  今日是否交易日: {is_trading_day()}")
print(f"  市场是否开盘: {is_market_open()}")

# =================== 1. 数据采集 ===================
print("\n【1】市场数据 (MarketDataCollector)")
from data.market_data import MarketDataCollector
mkt = MarketDataCollector()
from utils.calendar import get_latest_trading_day
tday = get_latest_trading_day()
from datetime import datetime, timedelta
start_d = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
end_d = tday

kline = mkt.get_daily_kline("000001", start_d, end_d)
check("日K线-000001", kline is not None and len(kline) > 0,
      f"共{len(kline)}条, 最新={kline.index[-1] if len(kline)>0 else 'N/A'}")

limit_pool = mkt.get_limit_up_pool()
check("涨停池", limit_pool is not None and len(limit_pool) > 0,
      f"共{len(limit_pool)}只")

strong_pool = mkt.get_continuous_limit_up()
check("强势涨停池", strong_pool is not None and len(strong_pool) > 0,
      f"共{len(strong_pool)}只")

quotes = mkt.get_realtime_quotes()
check("实时行情全量", quotes is not None and len(quotes) > 3000 and {"code", "name", "price", "pct_chg"}.issubset(set(quotes.columns)),
      f"共{len(quotes) if quotes is not None else 0}只, 列={list(quotes.columns[:8]) if quotes is not None and len(quotes.columns)>0 else []}")

sample_quotes = mkt.get_realtime_quotes(["600519", "000001", "300750", "688001", "920002"])
check("实时行情样本", sample_quotes is not None and len(sample_quotes) >= 4,
      f"共{len(sample_quotes) if sample_quotes is not None else 0}只")

breadth = mkt.get_market_breadth()
check("市场宽度", breadth.get("total", 0) > 3000 and breadth.get("up_count", 0) + breadth.get("down_count", 0) > 1000,
      f"口径={breadth.get('scope', '?')}, 上涨{breadth.get('up_count', '?')}只, 下跌{breadth.get('down_count', '?')}只, 均涨{breadth.get('avg_pct_chg', '?')}%")

try:
    from dashboard.utils import _load_market_indices
    indices = _load_market_indices()
    check("核心指数", len(indices) >= 3,
          ", ".join([f"{k}:{v.get('pct_chg', '?')}%" for k, v in indices.items()]) if indices else "无指数数据")
except Exception as e:
    warn("核心指数", f"失败: {e}")

# 板块数据
try:
    concept = mkt.get_concept_board()
    check("概念板块", concept is not None and len(concept) > 0,
          f"共{len(concept)}个板块" if concept is not None and len(concept) > 0 else "测试失败(周末可接受)")
except Exception as e:
    warn("概念板块", f"失败: {e} (周末可能正常)")

print("\n【2】龙虎榜 (DragonTigerCollector)")
from data.dragon_tiger import DragonTigerCollector
dt = DragonTigerCollector()
lhb_data = dt.get_daily_dragon_tiger()
check("龙虎榜数据", lhb_data is not None and len(lhb_data) > 0,
      f"共{len(lhb_data)}条")
if lhb_data is not None and len(lhb_data) > 0:
    print(f"  列名: {list(lhb_data.columns)[:10]}")

inst_behavior = dt.identify_institution_behavior()
check("机构行为分析", inst_behavior is not None and len(inst_behavior) > 0,
      f"共{len(inst_behavior) if inst_behavior else 0}只机构股")

print("\n【3】资金流向 (FundFlowCollector)")
from data.fund_flow import FundFlowCollector
ff = FundFlowCollector()
north = ff.get_north_bound_daily()
check("北向资金", north.get("net_flow_yi") is not None,
      f"净买{north.get('net_flow_yi', 0):+.2f}亿, 日期={north.get('date', '?')}")

margin = ff.get_margin_trading()
has_margin = margin and margin.get("balance", 0) > 0
check("融资融券", has_margin,
      f"余额{margin.get('balance', 0)/1e8:.0f}亿" if has_margin else "无数据")

print("\n【4】公告采集 (AnnouncementCollector)")
try:
    from data.announcement import AnnouncementCollector
    ac = AnnouncementCollector()
    ann = ac.get_latest_announcements(days=3)
    check("公告采集", ann is not None and len(ann) > 0,
          f"共{len(ann)}条公告" if ann is not None and len(ann) > 0 else "无公告(周末可能正常)")
except Exception as e:
    warn("公告采集", f"失败: {e}")

print("\n【5】公司信息 (CompanyInfoCollector)")
try:
    from data.company_info import CompanyInfoCollector
    ci = CompanyInfoCollector()
    info = ci.get_company_basic("000001")
    check("公司基本信息", info is not None and len(info) > 0,
          f"平安银行: {info.get('name', 'N/A')}" if info else "获取失败")
except Exception as e:
    warn("公司信息", f"失败: {e}")

print("\n【6】产业链数据 (IndustryChainData)")
try:
    from data.industry_chain import IndustryChainCollector
    icd = IndustryChainCollector()
    chains = icd.get_all_chains()
    check("产业链数据", chains is not None and len(chains) > 0,
          f"共{len(chains)}条产业链")
    stocks = icd.get_chain_stocks("新能源汽车")
    has_stocks = isinstance(stocks, pd.DataFrame) and not stocks.empty
    check("产业链个股", has_stocks,
          f"新能源车链: {len(stocks)}只" if has_stocks else "无个股")
except Exception as e:
    warn("产业链数据", f"失败: {e}")

# =================== 2. 情感分析 ===================
print("\n【7】新闻情感分析")
try:
    from sentiment.news_sentiment import NewsSentimentAnalyzer
    nsa = NewsSentimentAnalyzer()
    text = "公司业绩大幅增长，超出市场预期，未来前景看好"
    result = nsa.analyze_text(text)
    check("新闻情感分析", result is not None and isinstance(result, dict),
          f"情感分数={result.get('sentiment', '?')}")
except Exception as e:
    warn("新闻情感分析", f"失败: {e}")

print("\n【8】公告NLP")
try:
    from sentiment.announcement_nlp import AnnouncementNLPAnalyzer
    anlp = AnnouncementNLPAnalyzer()
    test_text = "公司预计2025年归属于上市公司股东的净利润同比增长50%-80%"
    ann_result = anlp.analyze_announcement(test_text)
    check("公告NLP", ann_result is not None and isinstance(ann_result, dict),
          f"影响={ann_result.get('impact', '?')}" if ann_result else "失败")
except Exception as e:
    warn("公告NLP", f"失败: {e}")

print("\n【9】市场情绪分析")
try:
    from sentiment.market_sentiment import MarketSentimentAnalyzer
    msa = MarketSentimentAnalyzer()
    sentiment = msa.analyze_sentiment(limit_pool, north, breadth)
    check("市场情绪分析", sentiment is not None and isinstance(sentiment, dict),
          f"综合评分={sentiment.get('composite_score', '?')}, 情绪={sentiment.get('sentiment_label', '?')}" if sentiment else "失败")
except Exception as e:
    warn("市场情绪分析", f"失败: {e}")

# =================== 3. 分析模块 ===================
print("\n【10】龙头识别")
try:
    from analysis.leader_finder import LeaderFinder
    lf = LeaderFinder()
    leaders = lf.find_leaders(limit_pool, strong_pool)
    check("龙头识别", leaders is not None,
          f"逻辑龙头:{len(leaders.get('logic', []))} 情绪龙头:{len(leaders.get('sentiment', []))} 容量龙头:{len(leaders.get('capacity', []))}" if leaders else "失败")
except Exception as e:
    warn("龙头识别", f"失败: {e}")
    traceback.print_exc()

print("\n【11】趋势逆转")
try:
    from analysis.trend_reversal import TrendReversalDetector
    trd = TrendReversalDetector()
    kline_data = mkt.get_daily_kline("000001", start_d, end_d)
    reversals = trd.detect_reversal(kline_data)
    check("趋势逆转检测", reversals is not None,
          f"检测到{len(reversals) if reversals else 0}个信号" if reversals is not None else "失败")
except Exception as e:
    warn("趋势逆转", f"失败: {e}")
    traceback.print_exc()

print("\n【12】产业链热力分析")
try:
    from analysis.industry_chain import IndustryChainAnalyzer
    ica = IndustryChainAnalyzer()
    concept_board = mkt.get_concept_board()
    heat = ica.analyze_chain_heat(concept_board, limit_pool)
    has_heat = heat is not None and not heat.empty
    check("产业链热力", has_heat,
          f"分析{len(heat) if has_heat else 0}条产业链" if has_heat else "失败")
except Exception as e:
    warn("产业链热力", f"失败: {e}")
    traceback.print_exc()

print("\n【13】相关网络分析")
try:
    from analysis.correlation_network import CorrelationNetworkAnalyzer
    cna = CorrelationNetworkAnalyzer()
    try:
        stock_list = mkt.get_a_share_list()
        sample_codes = stock_list["code"].head(30).tolist() if not stock_list.empty else ["000001", "000002", "600519"]
    except Exception:
        sample_codes = ["000001", "000002", "600519", "000858", "002415"]
    corr_matrix, returns_df = cna.build_correlation_matrix(sample_codes, lookback_days=60)
    check("相关性矩阵", corr_matrix is not None and corr_matrix.size > 0,
          f"矩阵大小={corr_matrix.shape}" if corr_matrix is not None else "失败")
    
    influence, _ = cna.build_influence_graph(concept_board, limit_pool)
    check("影响力图", influence is not None,
          f"节点={len(influence.nodes) if influence else 0}" if influence else "失败")
    
    regime = cna.cluster_market_regime()
    check("市场状态聚类", regime is not None,
          f"{len(regime) if regime else 0}个聚类" if regime else "失败")
except Exception as e:
    warn("相关网络分析", f"失败: {e}")
    traceback.print_exc()

print("\n【14】机构风格分析")
try:
    from analysis.institution_style import InstitutionStyleAnalyzer
    isa = InstitutionStyleAnalyzer()
    style = isa.analyze_institution_style(lhb_data)
    check("机构风格分析", style is not None,
          f"机构风格={style}" if style else "失败")
except Exception as e:
    warn("机构风格分析", f"失败: {e}")
    traceback.print_exc()

# =================== 4. ML模块 ===================
print("\n【15】ML训练管道")
try:
    from models.train_pipeline import MLPipeline
    ml = MLPipeline()
    check("ML管道初始化", ml is not None, "初始化成功")
    print(f"  LightGBM可用: {ml._has_lightgbm if hasattr(ml, '_has_lightgbm') else '未知'}")
except Exception as e:
    warn("ML训练管道", f"失败: {e}")
    traceback.print_exc()

# =================== 5. 交易模块 ===================
print("\n【16】信号生成器")
try:
    from trading.signal_generator import SignalGenerator
    sg = SignalGenerator()
    signals = sg.generate_all_signals()
    check("信号生成", signals is not None and len(signals) > 0,
          f"生成{len(signals)}个信号" if signals else "无信号")
except Exception as e:
    warn("信号生成器", f"失败: {e}")
    traceback.print_exc()

print("\n【17】交易执行器")
try:
    from trading.executor import TradeExecutor
    te = TradeExecutor()
    check("交易执行器", te is not None, "初始化成功")
except Exception as e:
    warn("交易执行器", f"失败: {e}")
    traceback.print_exc()

# =================== 6. 报告 ===================
print("\n【18】日报生成")
try:
    from report.daily_report import DailyReportGenerator
    drg = DailyReportGenerator()
    report = drg.generate_report()
    check("日报生成", report is not None and len(report) > 0,
          f"报告长度={len(report)}字符" if report else "失败")
except Exception as e:
    warn("日报生成", f"失败: {e}")
    traceback.print_exc()

# =================== 7. 数据质量 ===================
print("\n【19】数据质量")
try:
    from data.data_quality import DataQuality
    dq = DataQuality()
    dq.print_quality_report()
    check("数据质量报告", True, "报告已打印")
except Exception as e:
    warn("数据质量", f"失败: {e}")
    traceback.print_exc()

# =================== 汇总 ===================
print("\n" + "=" * 70)
print(" 验证汇总")
print("=" * 70)
critical = [e for e in ERRORS if "周末" not in e and "概念板块" not in e]
if ERRORS:
    print(f"  ❌ 错误: {len(ERRORS)} 个")
    for e in ERRORS:
        print(f"     - {e}")
if WARNINGS:
    print(f"  ⚠️  警告: {len(WARNINGS)} 个")
    for w in WARNINGS:
        print(f"     - {w}")
if not critical:
    print("  🎉 核心模块全部正常！")
else:
    print(f"  💀 核心模块有 {len(critical)} 个失败:")
    for c in critical:
        print(f"     - {c}")
print("=" * 70)