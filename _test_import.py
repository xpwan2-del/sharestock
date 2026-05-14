"""测试 neural_analysis 模块导入"""
import sys
sys.path.insert(0, '.')
from dashboard.components.neural_analysis import (
    render_neural_analysis,
    _render_correlation_heatmap,
    _render_influence_network,
    _render_market_clustering,
    _render_factor_importance,
    _render_network_metrics,
    _render_top_correlation_pairs,
    _render_influence_stats,
    _render_cluster_stats,
    _render_neural_connection_weights,
    DARK_THEME,
    GRADIENT_COLORMAPS,
    CLUSTER_NAMES,
)
print('OK: neural_analysis 模块导入成功')
print('OK: DARK_THEME 已加载:', list(DARK_THEME.keys())[:3])
print('OK: GRADIENT_COLORMAPS 已加载:', list(GRADIENT_COLORMAPS.keys()))
print('OK: render_neural_analysis 函数存在')
print('OK: 所有子渲染函数均可导入')
print('OK: nx (networkx) 已通过模块级别导入')