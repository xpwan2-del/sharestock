import time
import pandas as pd

results = []

def test(name, fn):
    t = time.perf_counter()
    try:
        r = fn()
        if r is None:
            results.append(('FAIL', name, '返回 None', round(time.perf_counter()-t,2)))
        elif isinstance(r, pd.DataFrame) and r.empty:
            results.append(('WARN', name, '返回空DataFrame', round(time.perf_counter()-t,2)))
        elif isinstance(r, dict) and len(r) == 0:
            results.append(('WARN', name, '返回空dict', round(time.perf_counter()-t,2)))
        elif isinstance(r, list) and len(r) == 0:
            results.append(('WARN', name, '返回空list', round(time.perf_counter()-t,2)))
        else:
            count = len(r) if hasattr(r, '__len__') else 'ok'
            results.append(('OK', name, f'{count}条', round(time.perf_counter()-t,2)))
        return r
    except Exception as e:
        results.append(('FAIL', name, f'{type(e).__name__}: {str(e)[:80]}', round(time.perf_counter()-t,2)))
        return None

print('=' * 60)
print('  【1】数据层测试')
print('=' * 60)

from data.market_data import MarketDataCollector
from data.fund_flow import FundFlowCollector
mc = MarketDataCollector()
ff = FundFlowCollector()

test('A股列表', mc.get_a_share_list)
test('实时行情样本5只', lambda: mc.get_realtime_quotes(['600519','000001','300750','688001','920002']))
test('涨停池', mc.get_limit_up_pool)
test('北向资金', ff.get_north_bound_daily)
test('概念板块', mc.get_concept_board)
test('行业板块', mc.get_industry_board)

from dashboard.utils import _load_market_indices
test('核心指数', _load_market_indices)

print()
print('=' * 60)
print('  【2】分析层测试')
print('=' * 60)

from analysis.leader_finder import LeaderFinder
lf = LeaderFinder()
test('龙头-FindLeaders', lambda: lf.find_leaders(
    limit_pool=mc.get_limit_up_pool(), strong_pool=pd.DataFrame()
))

from trading.signal_generator import SignalGenerator
sg = SignalGenerator()
test('信号生成-AllSignals', sg.generate_all_signals)

from sentiment.market_sentiment import MarketSentimentAnalyzer
sa = MarketSentimentAnalyzer()
test('市场情绪分析', sa.analyze_sentiment)

from analysis.trend_reversal import TrendReversalDetector
tr = TrendReversalDetector()
test('趋势逆转-comprehensive', lambda: tr.comprehensive_reversal_scan('600519', '贵州茅台'))

print()
print('=' * 60)
print('  【3】ML层测试')
print('=' * 60)

from models.train_pipeline import MLPipeline
ml = MLPipeline()
test('ML Pipeline初始化', lambda: ml)

from models.feedback_loop import MLFeedbackLoop
fl = MLFeedbackLoop()
test('反馈环初始化', lambda: fl)

print()
print('=' * 60)
print('  【4】交易层测试')
print('=' * 60)

from trading.executor import TradeExecutor
te = TradeExecutor()
test('交易执行器组合摘要', te.get_portfolio_summary)

from trading.realtime_monitor import RealtimeMonitor
rm = RealtimeMonitor()
test('实时监控初始化', lambda: rm)

print()
print('=' * 60)
print('  【5】日报层测试')
print('=' * 60)

from report.daily_report import DailyReportGenerator
dg = DailyReportGenerator()
test('日报生成器初始化', lambda: dg)
try:
    dg._print_header()
    results.append(('OK', '日报_header', '打印成功', 0))
except Exception as e:
    results.append(('FAIL', '日报_header', f'{type(e).__name__}: {str(e)[:80]}', 0))

print()
print('=' * 60)
print('  【6】Dashboard组件编译测试')
print('=' * 60)

import py_compile
dashboard_files = [
    'dashboard/app.py',
    'dashboard/utils.py',
    'dashboard/components/market_overview.py',
    'dashboard/components/leader_display.py',
    'dashboard/components/neural_analysis.py',
    'dashboard/components/dragon_tiger.py',
    'dashboard/components/announcement_scan.py',
    'dashboard/components/trend_reversal.py',
    'dashboard/components/industry_heatmap.py',
    'dashboard/components/daily_report_viewer.py',
]
for f in dashboard_files:
    try:
        py_compile.compile(f, doraise=True)
        results.append(('OK', f'编译 {f}', '通过', 0))
    except Exception as e:
        results.append(('FAIL', f'编译 {f}', f'{type(e).__name__}: {str(e)[:60]}', 0))

print()
print('=' * 60)
print('  全量测试汇总')
print('=' * 60)
for status, name, detail, t in results:
    icon = {'OK': '✅', 'WARN': '⚠️ ', 'FAIL': '❌'}[status]
    time_str = f' ({t}s)' if t > 0 else ''
    print(f'  {icon} {name}: {detail}{time_str}')
fails = [r for r in results if r[0] == 'FAIL']
warns = [r for r in results if r[0] == 'WARN']
oks = [r for r in results if r[0] == 'OK']
print()
print(f'  合计: {len(results)}项 | ✅通过 {len(oks)} | ⚠️ 警告 {len(warns)} | ❌失败 {len(fails)}')
if fails:
    print()
    print('  失败项:')
    for _, name, detail, _ in fails:
        print(f'    ❌ {name}: {detail}')
