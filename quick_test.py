import time
import pandas as pd
from utils.calendar import get_latest_trading_day
from data.market_data import MarketDataCollector
from data.dragon_tiger import DragonTigerCollector
from data.fund_flow import FundFlowCollector
from data.announcement import AnnouncementCollector

latest = get_latest_trading_day()
mkt = MarketDataCollector()
dt = DragonTigerCollector()
ff = FundFlowCollector()
ann = AnnouncementCollector()

print("=" * 55)
print(f"  最近交易日: {latest}")
print(f"  采集器日期: mkt={mkt.today} dt={dt.today} ff={ff.today}")

lp = mkt.get_limit_up_pool(latest)
sl = mkt.get_continuous_limit_up()
lhb = dt.get_daily_dragon_tiger(latest)
north = ff.get_north_bound_daily()
margin = ff.get_margin_trading()

print(f"  涨停池 : {len(lp) if lp is not None else 0}只")
print(f"  强势池 : {len(sl) if sl is not None else 0}只")
print(f"  龙虎榜 : {len(lhb) if lhb is not None else 0}条")
print(f"  北向   : 日期={north.get('date')} 净买={north.get('net_flow_yi',0):+.2f}亿")
print(f"  融资   : 日期={margin.get('date')} 余额={margin.get('balance',0):.0f}")

af = ann.fetch_cninfo_announcements("000001", "2026-05-01", "2026-05-10", max_pages=1)
print(f"  公告   : {len(af) if af is not None else 0}条")

from analysis.correlation_network import CorrelationNetworkAnalyzer
cna = CorrelationNetworkAnalyzer()
# 使用涨停池数据构建近似关联矩阵
lp_for_corr = mkt.get_limit_up_pool(latest)
cm, _, _ = cna.build_correlation_from_quotes(lp_for_corr, top_n=20) if lp_for_corr is not None and not lp_for_corr.empty else (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
clusters = cna.cluster_market_regime()
print(f"  关联矩阵: {cm.shape}")
print(f"  聚类    : {len(clusters)}只 {len(set(clusters['labels'])) if clusters.get('labels') else 0}类")

all_ok = (
    mkt.today == latest and dt.today == latest and ff.today == latest
    and north.get("date","").replace("-","") == latest
)
print()
print("  数据新鲜度:", "PASS - 全部最新" if all_ok else "FAIL")
print("=" * 55)