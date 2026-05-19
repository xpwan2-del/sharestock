"""市场结构分析可视化组件 - 相关性矩阵、产业链网络、市场聚类、因子驱动解释
深色主题 · 渐变色 · 交互式悬停
"""
import streamlit as st
import pandas as pd
import numpy as np
import networkx as nx
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import Dict, List, Optional, Tuple, Any

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.utils import (
    _load_concept_board,
    _load_realtime_quotes,
    _load_limit_up_pool,
    format_pct,
)

# ---------- 深色主题全局配置 ----------

DARK_THEME = {
    "paper_bgcolor": "#0D1117",
    "plot_bgcolor": "#161B22",
    "font_color": "#C9D1D9",
    "grid_color": "#30363D",
    "primary": "#58A6FF",
    "secondary": "#3FB950",
    "accent": "#D29922",
    "danger": "#F85149",
    "purple": "#BC8CFF",
    "teal": "#39D2C0",
    "orange": "#FFA657",
    "pink": "#FF6B9D",
}

GRADIENT_COLORMAPS = {
    "corr_diverging": [
        [0.0, "#1A3A5C"],
        [0.25, "#2B5EA7"],
        [0.5, "#161B22"],
        [0.75, "#7D2D4C"],
        [1.0, "#C73E3A"],
    ],
    "cluster_spectral": [
        [0.0, "#58A6FF"],
        [0.2, "#3FB950"],
        [0.4, "#D29922"],
        [0.6, "#F85149"],
        [0.8, "#BC8CFF"],
        [1.0, "#39D2C0"],
    ],
    "factor_heat": [
        [0.0, "#BC8CFF"],
        [0.3, "#58A6FF"],
        [0.6, "#39D2C0"],
        [0.85, "#D29922"],
        [1.0, "#F85149"],
    ],
    "network_blues": [
        [0.0, "#0D419D"],
        [0.5, "#58A6FF"],
        [1.0, "#39D2C0"],
    ],
}

CLUSTER_NAMES = {
    0: "活跃追涨型",
    1: "温和成长型",
    2: "低波动防守型",
    3: "高换手博弈型",
    4: "超跌反弹型",
    5: "强势突破型",
    6: "震荡整理型",
    7: "资金推动型",
}


def _apply_dark_theme(fig: go.Figure) -> go.Figure:
    """应用统一的深色主题样式"""
    fig.update_layout(
        paper_bgcolor=DARK_THEME["paper_bgcolor"],
        plot_bgcolor=DARK_THEME["plot_bgcolor"],
        font=dict(color=DARK_THEME["font_color"], size=12),
        xaxis=dict(
            gridcolor=DARK_THEME["grid_color"],
            zerolinecolor=DARK_THEME["grid_color"],
        ),
        yaxis=dict(
            gridcolor=DARK_THEME["grid_color"],
            zerolinecolor=DARK_THEME["grid_color"],
        ),
    )
    return fig


def _neural_style_metric_card(
    label: str,
    value,
    sub_value: str = "",
    color: str = DARK_THEME["primary"],
    icon: str = "",
) -> str:
    """神经风格指标卡片"""
    return f"""
    <div style="
        background: linear-gradient(135deg, #161B22 0%, #1C2333 100%);
        border: 1px solid #30363D;
        border-radius: 10px;
        padding: 14px 18px;
        text-align: center;
        transition: all 0.3s ease;
    ">
        <div style="font-size: 11px; color: #8B949E; margin-bottom: 6px;
                    letter-spacing: 0.5px; text-transform: uppercase;">
            {icon} {label}
        </div>
        <div style="font-size: 24px; font-weight: 700; color: {color};
                    font-family: 'SF Mono', 'Consolas', monospace;">
            {value}
        </div>
        <div style="font-size: 11px; color: #6E7681; margin-top: 2px;">
            {sub_value}
        </div>
    </div>
    """


# ================================================================
# 主渲染入口
# ================================================================

def render_neural_analysis(cache):
    """渲染神经网络分析页面"""
    st.markdown("""
    <div style="
        background: linear-gradient(90deg, #58A6FF, #BC8CFF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 28px;
        font-weight: 800;
        margin-bottom: 4px;
    ">市场结构分析</div>
    <div style="color: #8B949E; font-size: 13px; margin-bottom: 24px;">
        用行情特征解释市场共振、资金扩散、风险聚集和关键驱动因子 · 不是黑盒预测
    </div>
    """, unsafe_allow_html=True)

    # 加载数据
    with st.spinner("正在加载市场数据..."):
        quotes = cache.get("quotes", _load_realtime_quotes)
        concept_board = cache.get("concept_board", _load_concept_board)
        limit_up_pool = cache.get("limit_up_pool", _load_limit_up_pool)

    # ---------- 指标概览 ----------
    _render_network_metrics(quotes, concept_board, limit_up_pool)
    _render_market_structure_summary(quotes, concept_board, limit_up_pool)

    analysis_type = st.radio(
        "选择要查看的分析",
        ["相关性矩阵", "产业链影响力", "市场状态分层", "因子驱动解释"],
        horizontal=True,
    )

    if analysis_type == "相关性矩阵":
        _render_correlation_heatmap(quotes, cache)
    elif analysis_type == "产业链影响力":
        _render_influence_network(concept_board, limit_up_pool, cache)
    elif analysis_type == "市场状态分层":
        _render_market_clustering(quotes, cache)
    else:
        _render_factor_importance(quotes, cache)


# ================================================================
# 指标概览
# ================================================================

def _render_network_metrics(
    quotes: pd.DataFrame,
    concept_board: pd.DataFrame,
    limit_up_pool: pd.DataFrame,
):
    """渲染神经网络分析概览指标卡片"""
    total_stocks = len(quotes) if quotes is not None and not quotes.empty else 0
    total_concepts = len(concept_board) if concept_board is not None and not concept_board.empty else 0
    total_limit_up = len(limit_up_pool) if limit_up_pool is not None and not limit_up_pool.empty else 0

    avg_pct = 0.0
    up_ratio = 0.0
    if quotes is not None and not quotes.empty and "pct_chg" in quotes.columns:
        avg_pct = float(quotes["pct_chg"].mean())
        up_ratio = (quotes["pct_chg"] > 0).sum() / len(quotes) * 100

    st.markdown("### 网络分析概览")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown(
            _neural_style_metric_card(
                "样本节点", f"{total_stocks}", "全市场股票数量",
                color=DARK_THEME["primary"], icon="&#9673;"
            ),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            _neural_style_metric_card(
                "概念维度", f"{total_concepts}", "概念板块数量",
                color=DARK_THEME["purple"], icon="&#9702;"
            ),
            unsafe_allow_html=True,
        )
    with col3:
        pct_color = DARK_THEME["danger"] if avg_pct > 0 else DARK_THEME["secondary"]
        st.markdown(
            _neural_style_metric_card(
                "平均涨跌幅", f"{avg_pct:+.2f}%", f"上涨比例 {up_ratio:.1f}%",
                color=pct_color, icon="&#9650;"
            ),
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            _neural_style_metric_card(
                "涨停节点", f"{total_limit_up}", "信号强度",
                color=DARK_THEME["accent"], icon="&#9889;"
            ),
            unsafe_allow_html=True,
        )
    with col5:
        # 网络密度估算
        density_val = min(99.9, (total_limit_up / max(total_stocks, 1)) * 1000)
        st.markdown(
            _neural_style_metric_card(
                "网络密度", f"{density_val:.1f}‰", "涨停/全市场",
                color=DARK_THEME["teal"], icon="&#9632;"
            ),
            unsafe_allow_html=True,
        )


# ================================================================
# Tab 1: 股票关联热力图 (相关性矩阵)
# ================================================================

def _render_market_structure_summary(
    quotes: pd.DataFrame,
    concept_board: pd.DataFrame,
    limit_up_pool: pd.DataFrame,
):
    if quotes is None or quotes.empty:
        st.info("暂无行情数据，无法生成市场结构结论。")
        return
    q = quotes.copy()
    pct = pd.to_numeric(q.get("pct_chg", pd.Series(dtype="float")), errors="coerce")
    amount = pd.to_numeric(q.get("amount", pd.Series(dtype="float")), errors="coerce")
    volume_ratio = pd.to_numeric(q.get("volume_ratio", pd.Series(dtype="float")), errors="coerce")
    up_ratio = float((pct > 0).mean()) if len(pct.dropna()) else 0
    strong_ratio = float((pct >= 3).mean()) if len(pct.dropna()) else 0
    weak_ratio = float((pct <= -3).mean()) if len(pct.dropna()) else 0
    avg_volume_ratio = float(volume_ratio.dropna().mean()) if len(volume_ratio.dropna()) else 1
    limit_count = len(limit_up_pool) if limit_up_pool is not None else 0
    top_concepts = []
    if concept_board is not None and not concept_board.empty:
        board = concept_board.copy()
        if "涨跌幅" in board.columns:
            board["涨跌幅"] = pd.to_numeric(board["涨跌幅"], errors="coerce")
            name_col = "板块名称" if "板块名称" in board.columns else board.columns[0]
            top_concepts = board.nlargest(3, "涨跌幅")[name_col].astype(str).tolist()
        elif "pct_chg" in board.columns:
            board["pct_chg"] = pd.to_numeric(board["pct_chg"], errors="coerce")
            name_col = "name" if "name" in board.columns else board.columns[0]
            top_concepts = board.nlargest(3, "pct_chg")[name_col].astype(str).tolist()
    if up_ratio >= 0.62 and strong_ratio >= 0.08:
        state = "资金扩散偏强"
        action = "可以重点看主线内强势股和回踩确认机会，但避免无脑追高。"
        risk = "若涨停数下降或高位股回落，容易从扩散转为分歧。"
    elif weak_ratio >= 0.08 or up_ratio <= 0.38:
        state = "风险收缩偏弱"
        action = "优先控制仓位，关注防守、超跌修复和趋势未破位的核心股。"
        risk = "弱势环境下买点胜率会下降，短线接力要降低预期。"
    elif avg_volume_ratio >= 1.25:
        state = "高波动轮动"
        action = "适合观察板块轮动和资金突然放大的方向，买点要等确认。"
        risk = "轮动快时容易冲高回落，不能只看红色热力。"
    else:
        state = "震荡均衡"
        action = "优先做有趋势、有业绩或有明确主线的股票，减少随机交易。"
        risk = "震荡市信号容易反复，需要结合止损和仓位管理。"
    strongest = "、".join(top_concepts) if top_concepts else "暂无明确板块"
    st.markdown("### 今日市场结构结论")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("市场状态", state)
    c2.metric("上涨占比", f"{up_ratio:.1%}")
    c3.metric("强势股占比", f"{strong_ratio:.1%}")
    c4.metric("涨停样本", f"{limit_count}只")
    st.success(f"当前最值得关注的是：{strongest}。{action}")
    st.warning(f"风险提醒：{risk}")
    st.caption("说明：本页不是预测明天涨跌，而是把实时行情特征翻译成市场结构、资金共振和风险集中度，帮助判断哪些信号更可信。")



def _render_correlation_heatmap(quotes: pd.DataFrame, cache):
    """渲染股票相关性热力图"""
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
        <span style="color: #58A6FF; font-size: 18px;">&#9673;</span>
        <span style="color: #C9D1D9; font-weight: 600;">股票特征相关性矩阵</span>
        <span style="color: #8B949E; font-size: 12px;">— 余弦相似度 · 特征空间关联</span>
    </div>
    """, unsafe_allow_html=True)

    st.info("怎么看：颜色越接近红色，说明这些股票在涨跌幅、振幅、换手、量比等特征上越相似，后续可能同涨同跌；不是越红越可以买。")
    st.caption("怎么用：高相似股票适合做板块共振和风险传导观察，如果一组高相似强势股同时转弱，要警惕共振回撤。")

    if quotes is None or quotes.empty:
        st.warning("暂无行情数据，无法构建相关性矩阵")
        return

    try:
        from analysis.correlation_network import CorrelationNetworkAnalyzer
        analyzer = CorrelationNetworkAnalyzer()
        corr_matrix, feature_mat, selected = analyzer.build_correlation_from_quotes(
            quotes, top_n=30
        )
    except Exception as e:
        st.error(f"相关性分析失败: {e}")
        return

    if corr_matrix.empty:
        st.info("无法构建相关性矩阵，请检查数据")
        return

    # 热力图
    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns.tolist(),
        y=corr_matrix.index.tolist(),
        colorscale=GRADIENT_COLORMAPS["corr_diverging"],
        zmid=0,
        zmin=-1,
        zmax=1,
        colorbar=dict(
            title=dict(text="相似度", font=dict(color=DARK_THEME["font_color"])),
            tickfont=dict(color=DARK_THEME["font_color"]),
            thickness=15,
            len=0.7,
        ),
        hovertemplate=(
            "<b>%{y}</b> ↔ <b>%{x}</b><br>"
            "特征相似度: %{z:.3f}<br>"
            "<extra></extra>"
        ),
    ))

    fig.update_xaxes(
        tickangle=45,
        tickfont=dict(size=8, color="#8B949E"),
        side="bottom",
    )
    fig.update_yaxes(
        tickfont=dict(size=8, color="#8B949E"),
    )

    fig.update_layout(
        title=dict(
            text="股票特征相关性热力图 (Top 30 成交额)",
            font=dict(color=DARK_THEME["font_color"], size=15),
        ),
        height=650,
        margin=dict(l=80, r=40, t=50, b=100),
    )
    _apply_dark_theme(fig)
    st.plotly_chart(fig, use_container_width=True)

    # 高关联股票对
    st.markdown("####  高关联股票对 (相似度 Top 15)")
    _render_top_correlation_pairs(corr_matrix)


def _render_top_correlation_pairs(corr_matrix: pd.DataFrame):
    """渲染高关联股票对"""
    pairs = []
    for i in range(len(corr_matrix)):
        for j in range(i + 1, len(corr_matrix)):
            val = corr_matrix.iloc[i, j]
            pairs.append({
                "股票A": corr_matrix.index[i],
                "股票B": corr_matrix.columns[j],
                "相似度": round(val, 4),
            })

    pairs_df = pd.DataFrame(pairs).sort_values("相似度", ascending=False).head(15)

    if pairs_df.empty:
        return

    cols = st.columns(3)
    for idx, (_, row) in enumerate(pairs_df.iterrows()):
        val = row["相似度"]
        # 颜色根据相似度
        if val > 0.7:
            bar_color = DARK_THEME["danger"]
        elif val > 0.5:
            bar_color = DARK_THEME["orange"]
        else:
            bar_color = DARK_THEME["primary"]

        with cols[idx % 3]:
            st.markdown(f"""
            <div style="
                background: #161B22;
                border: 1px solid #30363D;
                border-radius: 8px;
                padding: 10px 14px;
                margin-bottom: 6px;
            ">
                <div style="font-size: 12px; color: #8B949E;">
                    {row['股票A']} <span style="color:#484F58;">↔</span> {row['股票B']}
                </div>
                <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
                    <div style="
                        flex: 1;
                        height: 4px;
                        background: #21262D;
                        border-radius: 2px;
                        overflow: hidden;
                    ">
                        <div style="
                            width: {val * 100}%;
                            height: 100%;
                            background: linear-gradient(90deg, {bar_color}, {bar_color}88);
                            border-radius: 2px;
                        "></div>
                    </div>
                    <span style="font-size: 13px; font-weight: 600; color: {bar_color};
                                 font-family: monospace;">{val:.3f}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ================================================================
# Tab 2: 产业链影响力传播图 (NetworkX + Plotly)
# ================================================================

def _render_influence_network(
    concept_board: pd.DataFrame,
    limit_up_pool: pd.DataFrame,
    cache,
):
    """渲染产业链影响力传播网络图"""
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
        <span style="color: #BC8CFF; font-size: 18px;">&#9702;</span>
        <span style="color: #C9D1D9; font-weight: 600;">产业链影响力传播网络</span>
        <span style="color: #8B949E; font-size: 12px;">— 有向图 · 上下游传播 · 中介中心性</span>
    </div>
    """, unsafe_allow_html=True)

    st.caption("节点大小 = 影响力权重，边 = 上下游传播关系。悬停查看详细指标。")
    st.info("怎么看：节点越大代表该产业环节影响力越强，颜色越红代表当前表现越强；处在多条路径中间的节点，往往是资金扩散枢纽。")
    st.caption("怎么用：如果涨停池和强势概念集中在同一产业链，说明主线更清晰；如果节点很多但分散，说明轮动快、追涨风险高。")

    try:
        from analysis.correlation_network import CorrelationNetworkAnalyzer
        analyzer = CorrelationNetworkAnalyzer()
        G, influence_metrics = analyzer.build_influence_graph(
            concept_board, limit_up_pool
        )
    except Exception as e:
        st.error(f"构建影响力网络失败: {e}")
        return

    if G.number_of_nodes() == 0:
        st.info("网络为空，请检查概念板块数据")
        return

    # 使用 Kamada-Kawai 布局以获得更好的可视化效果
    try:
        pos = nx.kamada_kawai_layout(G, weight="weight")
    except Exception:
        try:
            pos = nx.spring_layout(G, k=1.5, iterations=50, seed=42)
        except Exception:
            pos = nx.random_layout(G, seed=42)

    # 提取节点类型分类
    chain_root_nodes = [n for n, d in G.nodes(data=True) if d.get("node_type") == "chain_root"]
    segment_nodes = [n for n, d in G.nodes(data=True) if d.get("node_type") == "segment"]
    concept_nodes = [n for n, d in G.nodes(data=True) if d.get("node_type") == "concept"]

    # ===== Chain Root 边的 Trace =====
    edge_x_root = []
    edge_y_root = []
    edge_text_root = []
    for u, v, d in G.edges(data=True):
        if u in chain_root_nodes or v in chain_root_nodes:
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x_root.extend([x0, x1, None])
            edge_y_root.extend([y0, y1, None])
            edge_text_root.append(d.get("relation", ""))

    edge_trace_root = go.Scatter(
        x=edge_x_root, y=edge_y_root,
        line=dict(width=1.5, color="#30363D"),
        hoverinfo="none",
        mode="lines",
        showlegend=False,
    )

    # ===== Segment 传播边的 Trace =====
    edge_x_seg = []
    edge_y_seg = []
    edge_text_seg = []
    for u, v, d in G.edges(data=True):
        rel = d.get("relation", "")
        if rel == "影响传播":
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x_seg.extend([x0, x1, None])
            edge_y_seg.extend([y0, y1, None])
            edge_text_seg.append(f"{u} → {v}")

    edge_trace_seg = go.Scatter(
        x=edge_x_seg, y=edge_y_seg,
        line=dict(width=2, color="#D29922", dash="dash"),
        hoverinfo="text",
        text=edge_text_seg,
        mode="lines",
        showlegend=False,
        opacity=0.7,
    )

    # ===== 概念包含边 =====
    edge_x_conc = []
    edge_y_conc = []
    for u, v, d in G.edges(data=True):
        rel = d.get("relation", "")
        if rel == "包含":
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x_conc.extend([x0, x1, None])
            edge_y_conc.extend([y0, y1, None])

    edge_trace_conc = go.Scatter(
        x=edge_x_conc, y=edge_y_conc,
        line=dict(width=0.5, color="#484F58"),
        hoverinfo="none",
        mode="lines",
        showlegend=False,
    )

    # ===== 节点 =====
    # Chain Root 节点
    node_x_root, node_y_root, node_text_root, node_size_root = [], [], [], []
    for node in chain_root_nodes:
        x, y = pos[node]
        node_x_root.append(x)
        node_y_root.append(y)
        chain = G.nodes[node].get("chain", node)
        node_text_root.append(chain)
        node_size_root.append(G.nodes[node].get("size", 30))

    node_trace_root = go.Scatter(
        x=node_x_root, y=node_y_root,
        mode="markers+text",
        text=node_text_root,
        textposition="top center",
        textfont=dict(color="#BC8CFF", size=12, family="Arial Black"),
        marker=dict(
            size=node_size_root,
            color="#BC8CFF",
            symbol="diamond",
            line=dict(width=2, color="#BC8CFF"),
        ),
        hovertemplate="<b>%{text}</b><br>产业链根节点<extra></extra>",
        name="产业链",
    )

    # Segment 节点
    betweenness = G.graph.get("betweenness", {})
    node_x_seg, node_y_seg, node_text_seg = [], [], []
    node_size_seg, node_color_seg, hover_seg = [], [], []
    for node in segment_nodes:
        x, y = pos[node]
        node_x_seg.append(x)
        node_y_seg.append(y)
        seg = G.nodes[node].get("segment", node)
        node_text_seg.append(seg)
        raw_size = G.nodes[node].get("size", 15)
        bc = betweenness.get(node, 0.05)
        node_size_seg.append(raw_size * (1 + bc * 5))
        avg_pct = G.nodes[node].get("avg_pct", 0)
        node_color_seg.append(avg_pct)
        sub_count = G.nodes[node].get("sub_count", 0)
        hover_seg.append(
            f"<b>{node}</b><br>"
            f"环节: {seg}<br>"
            f"子行业数: {sub_count}<br>"
            f"平均涨跌幅: {avg_pct:+.2f}%<br>"
            f"中介中心性: {bc:.3f}"
        )

    node_trace_seg = go.Scatter(
        x=node_x_seg, y=node_y_seg,
        mode="markers+text",
        text=node_text_seg,
        textposition="middle center",
        textfont=dict(color="#C9D1D9", size=8),
        marker=dict(
            size=node_size_seg,
            color=node_color_seg,
            colorscale=GRADIENT_COLORMAPS["corr_diverging"],
            cmin=-5,
            cmax=5,
            showscale=True,
            colorbar=dict(
                title=dict(text="涨跌幅%", font=dict(color=DARK_THEME["font_color"])),
                tickfont=dict(color=DARK_THEME["font_color"]),
                thickness=10,
                x=1.02,
            ),
            symbol="circle",
            line=dict(width=1, color="#30363D"),
        ),
        hovertemplate="%{hovertext}<extra></extra>",
        hovertext=hover_seg,
        name="环节节点",
    )

    # Concept 节点 (只显示权重 TOP 部分，避免过于密集)
    concept_with_weight = []
    for node in concept_nodes:
        w = G.nodes[node].get("weight", 0.2)
        concept_with_weight.append((node, w))

    concept_with_weight.sort(key=lambda x: x[1], reverse=True)
    top_concepts = concept_with_weight[:50]

    node_x_conc, node_y_conc, node_text_conc = [], [], []
    node_size_conc, node_color_conc, hover_conc = [], [], []
    for node, _ in top_concepts:
        x, y = pos[node]
        node_x_conc.append(x)
        node_y_conc.append(y)
        node_text_conc.append(node)
        w = G.nodes[node].get("weight", 0.2)
        node_size_conc.append(max(3, w * 12))
        pct = G.nodes[node].get("pct_chg", 0)
        node_color_conc.append(pct)
        hover_conc.append(
            f"<b>{node}</b><br>"
            f"涨跌幅: {pct:+.2f}%<br>"
            f"影响力权重: {w:.3f}"
        )

    node_trace_conc = go.Scatter(
        x=node_x_conc, y=node_y_conc,
        mode="markers",
        marker=dict(
            size=node_size_conc,
            color=node_color_conc,
            colorscale=GRADIENT_COLORMAPS["corr_diverging"],
            cmin=-5,
            cmax=5,
            symbol="circle-open",
            line=dict(width=1, color="#58A6FF"),
        ),
        hovertemplate="%{hovertext}<extra></extra>",
        hovertext=hover_conc,
        name="概念节点",
        showlegend=False,
    )

    fig = go.Figure(
        data=[
            edge_trace_root,
            edge_trace_conc,
            edge_trace_seg,
            node_trace_conc,
            node_trace_seg,
            node_trace_root,
        ]
    )

    fig.update_layout(
        title=dict(
            text=f"产业链影响力传播图 ({G.number_of_nodes()} 节点, {G.number_of_edges()} 边)",
            font=dict(color=DARK_THEME["font_color"], size=15),
        ),
        height=700,
        margin=dict(l=20, r=80, t=50, b=20),
        showlegend=True,
        legend=dict(
            font=dict(color=DARK_THEME["font_color"]),
            bgcolor="rgba(22, 27, 34, 0.53)",
            bordercolor="#30363D",
        ),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    )
    _apply_dark_theme(fig)
    st.plotly_chart(fig, use_container_width=True)

    # 影响力统计
    _render_influence_stats(influence_metrics, betweenness)


def _render_influence_stats(influence_metrics: Dict, betweenness: Dict):
    """渲染影响力统计"""
    st.markdown("####  网络中心性分析")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(f"""
        <div style="
            background: #161B22;
            border: 1px solid #30363D;
            border-radius: 8px;
            padding: 14px;
        ">
            <div style="color: #58A6FF; font-weight: 600; margin-bottom: 8px;">
                网络拓扑指标
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                <div>
                    <span style="color: #8B949E; font-size: 12px;">总节点</span><br>
                    <span style="color: #C9D1D9; font-size: 18px; font-weight: 600;">
                        {influence_metrics.get('total_nodes', 0)}
                    </span>
                </div>
                <div>
                    <span style="color: #8B949E; font-size: 12px;">总边数</span><br>
                    <span style="color: #C9D1D9; font-size: 18px; font-weight: 600;">
                        {influence_metrics.get('total_edges', 0)}
                    </span>
                </div>
                <div>
                    <span style="color: #8B949E; font-size: 12px;">产业链数</span><br>
                    <span style="color: #C9D1D9; font-size: 18px; font-weight: 600;">
                        {influence_metrics.get('num_chains', 0)}
                    </span>
                </div>
                <div>
                    <span style="color: #8B949E; font-size: 12px;">涨停信号</span><br>
                    <span style="color: #D29922; font-size: 18px; font-weight: 600;">
                        {influence_metrics.get('limit_up_count', 0)}
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_b:
        top_influencers = influence_metrics.get("top_influencers", [])
        if top_influencers:
            items_html = ""
            for i, (node, bc) in enumerate(top_influencers[:8]):
                # 渐变色条
                bar_width = min(int(bc * 1000), 100)
                if i < 3:
                    bar_color = "#F85149"
                elif i < 5:
                    bar_color = "#D29922"
                else:
                    bar_color = "#58A6FF"
                items_html += f"""
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                    <span style="color: #8B949E; font-size: 10px; width: 16px;">#{i + 1}</span>
                    <span style="color: #C9D1D9; font-size: 11px; min-width: 140px;
                                 overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        {node[:30]}
                    </span>
                    <div style="flex:1; height:6px; background:#21262D; border-radius:3px;">
                        <div style="width:{bar_width}%; height:100%; background:{bar_color};
                                    border-radius:3px;"></div>
                    </div>
                    <span style="color:{bar_color}; font-size:11px; font-weight:600;
                                 font-family:monospace; min-width:40px; text-align:right;">
                        {bc:.4f}
                    </span>
                </div>
                """

            st.markdown(f"""
            <div style="
                background: #161B22;
                border: 1px solid #30363D;
                border-radius: 8px;
                padding: 14px;
            ">
                <div style="color: #BC8CFF; font-weight: 600; margin-bottom: 8px;">
                    中介中心性 Top 8 (影响力排行)
                </div>
                {items_html}
            </div>
            """, unsafe_allow_html=True)


# ================================================================
# Tab 3: 市场状态聚类散点图
# ================================================================

def _render_market_clustering(quotes: pd.DataFrame, cache):
    """渲染市场状态聚类散点图"""
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
        <span style="color: #39D2C0; font-size: 18px;">&#9632;</span>
        <span style="color: #C9D1D9; font-weight: 600;">市场状态聚类分析</span>
        <span style="color: #8B949E; font-size: 12px;">— PCA降维 · KMeans聚类 · 状态标签</span>
    </div>
    """, unsafe_allow_html=True)

    st.caption("基于 pct_chg, amplitude, turnover, volume_ratio 将全市场股票分为不同状态簇。")

    if quotes is None or quotes.empty:
        st.warning("暂无行情数据")
        return

    st.info("怎么看：同一颜色/簇里的股票，代表当天涨跌幅、换手、振幅、量比等特征相似。它不是预测，而是告诉你市场资金正在把股票分成哪些类型。")
    st.caption("怎么用：强势放量簇适合观察主线扩散，低波动簇偏防守，高波动下跌簇要回避；不要只因为某个点在红色区域就买入。")

    # 聚类数选择
    n_clusters = st.slider(
        "聚类簇数",
        min_value=3,
        max_value=8,
        value=5,
        step=1,
        help="KMeans 聚类数量，推荐 4-6 簇",
    )

    try:
        from analysis.correlation_network import CorrelationNetworkAnalyzer
        analyzer = CorrelationNetworkAnalyzer()
        cluster_result = analyzer.cluster_market_state(
            quotes, n_clusters=n_clusters
        )
    except Exception as e:
        st.error(f"聚类分析失败: {e}")
        return

    if not cluster_result.get("success", False):
        st.warning(f"聚类失败: {cluster_result.get('error', '未知错误')}")
        return

    # 散点图
    fig = go.Figure()

    labels = np.array(cluster_result["labels"])
    for i in range(cluster_result["n_clusters"]):
        mask = labels == i
        if not mask.any():
            continue

        cluster_name = _describe_cluster(cluster_result.get("cluster_stats", []), i)

        # 网格线增强效果
        fig.add_trace(go.Scatter(
            x=np.array(cluster_result["x"])[mask],
            y=np.array(cluster_result["y"])[mask],
            mode="markers",
            name=cluster_name,
            marker=dict(
                size=7,
                opacity=0.75,
                line=dict(width=0.5, color="#0D1117"),
                symbol="circle",
            ),
            hovertemplate=(
                "<b>%{hovertext}</b><br>"
                "簇: " + cluster_name + "<br>"
                "PC1: %{x:.2f}<br>"
                "PC2: %{y:.2f}<br>"
                "<extra></extra>"
            ),
            hovertext=[
                n for j, n in enumerate(cluster_result["names"])
                if labels[j] == i
            ],
        ))

    # 质心
    fig.add_trace(go.Scatter(
        x=cluster_result["centroids_x"],
        y=cluster_result["centroids_y"],
        mode="markers+text",
        text=[_describe_cluster(cluster_result.get("cluster_stats", []), i) for i in range(cluster_result["n_clusters"])],
        textposition="top center",
        textfont=dict(color="#FFFFFF", size=11, family="Arial Black"),
        marker=dict(
            size=20,
            symbol="x-thin",
            color="#FFFFFF",
            line=dict(width=2, color="#FFFFFF"),
        ),
        name="簇质心",
        hovertemplate="<b>质心 %{text}</b><br>PC1: %{x:.2f}<br>PC2: %{y:.2f}<extra></extra>",
    ))

    ev = cluster_result["explained_var"]
    fig.update_layout(
        title=dict(
            text=f"市场状态聚类 (PCA 2D投影 | PC1 {ev[0]*100:.1f}% + PC2 {ev[1]*100:.1f}% = {sum(ev)*100:.1f}%)",
            font=dict(color=DARK_THEME["font_color"], size=15),
        ),
        xaxis_title=f"主成分 1 ({ev[0]*100:.1f}% 方差)",
        yaxis_title=f"主成分 2 ({ev[1]*100:.1f}% 方差)",
        height=550,
        margin=dict(l=60, r=40, t=50, b=60),
        legend=dict(
            font=dict(color=DARK_THEME["font_color"]),
            bgcolor="rgba(22, 27, 34, 0.53)",
            bordercolor="#30363D",
            itemsizing="constant",
        ),
    )
    _apply_dark_theme(fig)
    fig.update_coloraxes(colorscale=GRADIENT_COLORMAPS["cluster_spectral"])
    st.plotly_chart(fig, use_container_width=True)

    # 簇统计
    _render_cluster_stats(cluster_result.get("cluster_stats", []))


def _render_cluster_stats(cluster_stats: List[Dict]):
    """渲染聚类簇统计"""
    if not cluster_stats:
        return

    st.markdown("####  各簇状态卡片")

    cols = st.columns(min(len(cluster_stats), 4))
    cluster_colors = [
        DARK_THEME["primary"],
        DARK_THEME["secondary"],
        DARK_THEME["accent"],
        DARK_THEME["danger"],
        DARK_THEME["purple"],
        DARK_THEME["teal"],
        DARK_THEME["orange"],
        DARK_THEME["pink"],
    ]

    for i, (stat, col) in enumerate(zip(cluster_stats, cols * 2)):
        color = cluster_colors[i % len(cluster_colors)]
        cluster_name = _describe_cluster(cluster_stats, stat["cluster_id"])
        avg_pct = stat.get("avg_pct", 0)
        pct_color = DARK_THEME["danger"] if avg_pct > 0 else DARK_THEME["secondary"]

        top_stocks_str = ", ".join(stat.get("top_stocks", [])[:2])

        with col:
            st.markdown(f"""
            <div style="
                background: #161B22;
                border-left: 3px solid {color};
                border-radius: 6px;
                padding: 12px 14px;
                margin-bottom: 8px;
            ">
                <div style="color: {color}; font-weight: 700; font-size: 13px;
                            margin-bottom: 6px;">
                    {cluster_name}
                </div>
                <div style="font-size: 11px; color: #8B949E; line-height: 1.6;">
                    数量: <b style="color:#C9D1D9;">{stat['count']}</b> 只<br>
                    均涨幅: <b style="color:{pct_color};">{avg_pct:+.2f}%</b><br>
                    均换手: <b style="color:#C9D1D9;">{stat.get('avg_turnover', 0):.1f}%</b><br>
                    均振幅: <b style="color:#C9D1D9;">{stat.get('avg_amplitude', 0):.1f}%</b><br>
                    量比: <b style="color:#C9D1D9;">{stat.get('avg_volume_ratio', 0):.2f}</b>
                </div>
                <div style="font-size: 9px; color: #484F58; margin-top: 6px;
                            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    {top_stocks_str}
                </div>
            </div>
            """, unsafe_allow_html=True)


# ================================================================
# Tab 4: 因子重要性条形图 (神经网络权重可视化)
# ================================================================

def _describe_cluster(cluster_stats: list, cluster_id: int) -> str:
    stat = next((item for item in cluster_stats if item.get("cluster_id") == cluster_id), {})
    avg_pct = float(stat.get("avg_pct", 0) or 0)
    avg_turnover = float(stat.get("avg_turnover", 0) or 0)
    avg_amplitude = float(stat.get("avg_amplitude", 0) or 0)
    size = int(stat.get("size", 0) or 0)
    if avg_pct >= 3 and avg_turnover >= 6:
        return "强势放量活跃"
    if avg_pct >= 1.2 and avg_amplitude <= 5:
        return "温和趋势上行"
    if avg_pct <= -2 and avg_amplitude >= 4:
        return "高波动下跌"
    if avg_turnover <= 2.5 and avg_amplitude <= 3.5:
        return "低波动防守"
    if avg_amplitude >= 6 and abs(avg_pct) < 2:
        return "剧烈分歧震荡"
    if size >= 80 and abs(avg_pct) < 1:
        return "中性横盘群体"
    return f"结构簇 {cluster_id + 1}"



def _render_factor_importance(quotes: pd.DataFrame, cache):
    """渲染因子重要性条形图"""
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
        <span style="color: #FFA657; font-size: 18px;">&#9889;</span>
        <span style="color: #C9D1D9; font-weight: 600;">因子驱动解释</span>
        <span style="color: #8B949E; font-size: 12px;">— 方差贡献 · 涨跌幅相关 · 信息比率</span>
    </div>
    """, unsafe_allow_html=True)

    st.info("怎么看：这里展示当前市场分化主要由哪些因子解释，比如量比、换手、振幅、涨跌幅。它不是黑盒模型真实权重，而是行情横截面的因子驱动解释。")
    st.caption("怎么用：如果量比和换手重要性高，说明短线资金主导；如果波动因子重要性高，说明风险和分歧加大；如果涨跌幅因子高，说明趋势动量更强。")

    if quotes is None or quotes.empty:
        st.warning("暂无行情数据")
        return

    try:
        from analysis.correlation_network import CorrelationNetworkAnalyzer
        analyzer = CorrelationNetworkAnalyzer()
        importance_df = analyzer.calculate_factor_importance(quotes)
    except Exception as e:
        st.error(f"因子重要性计算失败: {e}")
        return

    if importance_df.empty:
        st.info("无法计算因子重要性")
        return

    # ===== 水平条形图 =====
    importance_df_display = importance_df.sort_values("归一化重要性(%)", ascending=True)

    fig = go.Figure()

    # 渐变色映射
    max_imp = importance_df_display["归一化重要性(%)"].max()
    colors = []
    for imp in importance_df_display["归一化重要性(%)"]:
        ratio = imp / max_imp if max_imp > 0 else 0
        if ratio > 0.7:
            colors.append(DARK_THEME["danger"])
        elif ratio > 0.4:
            colors.append(DARK_THEME["orange"])
        elif ratio > 0.2:
            colors.append(DARK_THEME["primary"])
        else:
            colors.append("#484F58")

    fig.add_trace(go.Bar(
        y=importance_df_display["因子名称"],
        x=importance_df_display["归一化重要性(%)"],
        orientation="h",
        marker=dict(
            color=importance_df_display["归一化重要性(%)"],
            colorscale=GRADIENT_COLORMAPS["factor_heat"],
            showscale=True,
            colorbar=dict(
                title=dict(text="重要性%", font=dict(color=DARK_THEME["font_color"])),
                tickfont=dict(color=DARK_THEME["font_color"]),
                thickness=12,
            ),
            line=dict(width=1, color="#0D1117"),
        ),
        text=importance_df_display["归一化重要性(%)"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside",
        textfont=dict(color=DARK_THEME["font_color"], size=11),
        opacity=0.9,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "重要性: %{x:.2f}%<br>"
            "方差: %{customdata[0]:.4f}<br>"
            "与涨跌幅相关性: %{customdata[1]:.4f}<br>"
            "<extra></extra>"
        ),
        customdata=importance_df_display[["方差", "与涨跌幅相关性"]].values,
    ))

    fig.update_layout(
        title=dict(
            text="因子驱动解释：当前市场由哪些特征主导",
            font=dict(color=DARK_THEME["font_color"], size=15),
        ),
        xaxis_title="归一化重要性 (%)",
        height=400,
        margin=dict(l=20, r=80, t=50, b=20),
        showlegend=False,
        yaxis=dict(autorange="reversed"),
    )
    _apply_dark_theme(fig)
    st.plotly_chart(fig, use_container_width=True)

    # ===== 雷达图 (多维度因子对比) =====
    st.markdown("####  因子雷达图 (Top 6 因子多维对比)")
    top6 = importance_df.head(6)

    radar_categories = ["方差贡献", "涨跌幅相关", "稳定性(1/σ)", "信息比率"]
    radar_fig = go.Figure()

    for _, row in top6.iterrows():
        name = row["因子名称"]
        variance = row["方差"]
        corr = abs(row["与涨跌幅相关性"])
        std_val = row["标准差"]
        stability = 1.0 / (std_val + 1e-8) if std_val > 0 else 0
        sharpe_like = abs(row["均值"] / (std_val + 1e-8)) if std_val > 0 else 0

        # 归一化
        radar_values = [variance, corr, stability, sharpe_like]
        max_vals = [max(v, 1e-8) for v in radar_values]
        radar_normalized = [v / mv for v, mv in zip(radar_values, max_vals)]

        radar_fig.add_trace(go.Scatterpolar(
            r=radar_normalized,
            theta=radar_categories,
            name=name[:15],
            fill="toself",
            opacity=0.6,
        ))

    radar_fig.update_layout(
        polar=dict(
            bgcolor="#161B22",
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                gridcolor=DARK_THEME["grid_color"],
                tickfont=dict(color="#8B949E", size=9),
            ),
            angularaxis=dict(
                gridcolor=DARK_THEME["grid_color"],
                tickfont=dict(color=DARK_THEME["font_color"], size=10),
            ),
        ),
        title=dict(
            text="因子多维特征雷达图",
            font=dict(color=DARK_THEME["font_color"], size=14),
        ),
        height=420,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(
            font=dict(color=DARK_THEME["font_color"], size=10),
            bgcolor="rgba(22, 27, 34, 0.53)",
            bordercolor="#30363D",
        ),
    )
    _apply_dark_theme(radar_fig)
    st.plotly_chart(radar_fig, use_container_width=True)

    # ===== 因子影响强度模拟 =====
    st.markdown("####  因子影响强度模拟")
    _render_neural_connection_weights(importance_df)


def _render_neural_connection_weights(importance_df: pd.DataFrame):
    """渲染神经网络风格的连接权重可视化"""
    top_factors = importance_df.head(8)

    cols = st.columns(4)
    # 渐变色序列
    gradient_stops = [
        ("#39D2C0", "#58A6FF"),
        ("#58A6FF", "#BC8CFF"),
        ("#BC8CFF", "#FF6B9D"),
        ("#FF6B9D", "#FFA657"),
        ("#FFA657", "#D29922"),
        ("#D29922", "#F85149"),
        ("#58A6FF", "#3FB950"),
        ("#3FB950", "#39D2C0"),
    ]

    for idx, (_, row) in enumerate(top_factors.iterrows()):
        with cols[idx % 4]:
            name = row["因子名称"][:12]
            imp = row["归一化重要性(%)"]
            corr = row["与涨跌幅相关性"]
            start_c, end_c = gradient_stops[idx % len(gradient_stops)]

            # 模拟激活强度
            activation = min(imp / 30, 1.0)
            node_size = 6 + int(activation * 28)

            st.markdown(f"""
            <div style="
                background: #161B22;
                border: 1px solid #30363D;
                border-radius: 8px;
                padding: 10px;
                text-align: center;
                margin-bottom: 8px;
            ">
                <div style="
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    margin-bottom: 6px;
                ">
                    <div style="
                        width: {node_size}px;
                        height: {node_size}px;
                        border-radius: 50%;
                        background: radial-gradient(circle, {start_c}, {end_c});
                        box-shadow: 0 0 {int(activation * 20)}px {start_c}88;
                        opacity: {0.3 + activation * 0.7};
                    "></div>
                </div>
                <div style="
                    font-size: 9px;
                    color: #8B949E;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    margin-bottom: 4px;
                ">{name}</div>
                <div style="display: flex; justify-content: space-between;
                            font-size: 10px; font-family: monospace;">
                    <span style="color: {start_c};">{imp:.1f}%</span>
                    <span style="color: #6E7681;">r={corr:+.2f}</span>
                </div>
                <div style="
                    margin-top: 5px;
                    height: 3px;
                    background: #21262D;
                    border-radius: 2px;
                    overflow: hidden;
                ">
                    <div style="
                        width: {activation * 100}%;
                        height: 100%;
                        background: linear-gradient(90deg, {start_c}, {end_c});
                        border-radius: 2px;
                    "></div>
                </div>
            </div>
            """, unsafe_allow_html=True)