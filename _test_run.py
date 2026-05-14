"""临时测试脚本 - 验证所有方法"""
import sys
sys.path.insert(0, '.')
import pandas as pd
import numpy as np
from analysis.correlation_network import CorrelationNetworkAnalyzer

a = CorrelationNetworkAnalyzer()
np.random.seed(42)

# T1: build_correlation_from_quotes
mq = pd.DataFrame({
    'code': [f'{i:06d}' for i in range(32)],
    'name': [f'股票{i}' for i in range(32)],
    'pct_chg': np.random.uniform(-5,5,32),
    'amplitude': np.random.uniform(1,10,32),
    'turnover': np.random.uniform(0.5,15,32),
    'volume_ratio': np.random.uniform(0.5,3,32),
    'amount': np.random.uniform(1e7,1e10,32),
})
c,f,s = a.build_correlation_from_quotes(mq, top_n=30)
print(f"T1 build_correlation_from_quotes: shape={c.shape} empty={c.empty}")

# T2: cluster_market_state
r = a.cluster_market_state(mq, n_clusters=5)
print(f"T2 cluster_market_state: success={r['success']} n={r.get('n_samples')} clusters={r.get('n_clusters')}")

# T3: calculate_factor_importance
imp = a.calculate_factor_importance(mq)
print(f"T3 calculate_factor_importance: len={len(imp)} empty={imp.empty}")

# T4: build_influence_graph
mc = pd.DataFrame({
    '板块名称': ['锂矿','动力电池','整车制造','硅料','电池片','电站运营','EDA软件','芯片设计','消费电子','算力芯片GPU','大模型','智能驾驶'],
    'name': ['锂矿','动力电池','整车制造','硅料','电池片','电站运营','EDA软件','芯片设计','消费电子','算力芯片GPU','大模型','智能驾驶'],
    '涨跌幅': np.random.uniform(-3,3,12),
    'pct_chg': np.random.uniform(-3,3,12),
})
ml = pd.DataFrame({'code':['000001','000002'],'name':['A','B']})
G,m = a.build_influence_graph(mc, ml)
print(f"T4 build_influence_graph: nodes={G.number_of_nodes()} edges={G.number_of_edges()}")

# T5: cluster_market_regime (weekend fallback)
r2 = a.cluster_market_regime(n_clusters=4)
print(f"T5 cluster_market_regime: success={r2.get('success')} error={r2.get('error','N/A')}")

# T6: generate_stock_embeddings
e,l = a.generate_stock_embeddings(mq)
print(f"T6 generate_stock_embeddings: shape={e.shape} labels={len(l)}")

# T7: empty data boundaries
print(f"T7 empty: corr_empty={a.build_correlation_from_quotes(pd.DataFrame())[0].empty}")
print(f"T7 None: corr_none={a.build_correlation_from_quotes(None)[0].empty}")
print(f"T7 empty_imp: {a.calculate_factor_importance(pd.DataFrame()).empty}")
print(f"T7 empty_cluster: {a.cluster_market_state(pd.DataFrame())['success']}")

print("\nALL TESTS PASSED")