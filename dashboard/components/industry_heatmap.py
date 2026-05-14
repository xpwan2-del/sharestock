"""
产业链热力图组件 - 热门产业链热度可视化
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, List

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.utils import (
    _load_concept_board,
    _load_industry_board,
    _load_limit_up_pool,
    _load_realtime_quotes,
    format_pct,
)


def render_industry_heatmap(cache):
    """渲染产业链热力图页面"""
    st.markdown('''
    <div class="module-hero">
        <div class="module-kicker">SECTOR HEATMAP</div>
        <div class="module-title">产业链热力图</div>
        <div class="module-subtitle">概念强度 · 行业轮动 · 产业链全景 · 涨停节点扫描</div>
    </div>
    ''', unsafe_allow_html=True)

    with st.spinner("正在加载板块数据..."):
        concept_board = cache.get("concept_board", _load_concept_board)
        industry_board = cache.get("industry_board", _load_industry_board)
        limit_up_pool = cache.get("limit_up_pool", _load_limit_up_pool)
        quotes = cache.get("quotes", _load_realtime_quotes)

    # ---------- Tab 切换：概念板块 / 行业板块 / 产业链 ----------
    tab1, tab2, tab3 = st.tabs(["概念板块热力图", "行业板块分析", "产业链全景"])

    with tab1:
        _render_concept_heatmap(concept_board)

    with tab2:
        _render_industry_analysis(industry_board, quotes)

    with tab3:
        _render_chain_panorama(concept_board, limit_up_pool)


def _render_concept_heatmap(concept_board: pd.DataFrame):
    """渲染概念板块热力图"""
    if concept_board is None or concept_board.empty:
        st.warning("暂无概念板块数据")
        return

    # 查找涨跌幅列
    pct_col = None
    name_col = None
    for col in ["涨跌幅", "pct_chg"]:
        if col in concept_board.columns:
            pct_col = col
            break
    for col in ["板块名称", "name"]:
        if col in concept_board.columns:
            name_col = col
            break

    if pct_col is None or name_col is None:
        st.warning("板块数据格式不匹配")
        st.dataframe(concept_board.head(20), width="stretch")
        return

    # 排序取 Top 50
    sorted_board = concept_board.sort_values(pct_col, ascending=False)
    top50 = sorted_board.head(50)

    # 准备热力图数据
    names = top50[name_col].tolist()
    values = top50[pct_col].tolist()

    # 颜色映射
    max_val = max(max(values), abs(min(values))) if values else 10
    colors = []
    for v in values:
        if v >= 0:
            intensity = min(v / max_val, 1.0) if max_val > 0 else 0
            r = int(220 + 35 * intensity)
            g = int(60 - 60 * intensity)
            b = int(60 - 60 * intensity)
        else:
            intensity = min(abs(v) / max_val, 1.0) if max_val > 0 else 0
            r = int(60 - 60 * intensity)
            g = int(140 + 80 * intensity)
            b = int(60 - 60 * intensity)
        colors.append(f"rgb({r},{g},{b})")

    # Treemap 热力图
    fig = go.Figure(go.Treemap(
        labels=names,
        parents=["概念板块"] * len(names),
        values=[abs(v) + 1 for v in values],
        text=[f"{n}<br>{v:+.2f}%" for n, v in zip(names, values)],
        textinfo="label+text",
        marker=dict(
            colors=values,
            colorscale=[
                [0, "#228B22"],
                [0.35, "#4169E1"],
                [0.5, "#999999"],
                [0.65, "#FF8C00"],
                [1, "#E63946"],
            ],
            cmin=-max_val,
            cmax=max_val,
            colorbar=dict(title="涨跌幅(%)", thickness=15),
        ),
        hovertemplate="<b>%{label}</b><br>涨跌幅: %{color:.2f}%<extra></extra>",
    ))

    fig.update_layout(
        title="概念板块热力图 (Top 50)",
        height=600,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig, width="stretch")

    # 涨跌 Top 10 并列展示
    st.markdown("### 涨幅 / 跌幅 Top 10")
    col_a, col_b = st.columns(2)

    top10_up = sorted_board.head(10)
    top10_down = sorted_board.tail(10).sort_values(pct_col, ascending=True)

    with col_a:
        st.markdown("#### 🔴 涨幅榜")
        display_up = top10_up[[name_col, pct_col]].copy()
        display_up.columns = ["板块", "涨跌幅(%)"]
        display_up["涨跌幅(%)"] = display_up["涨跌幅(%)"].apply(lambda x: f"+{x:.2f}%" if x >= 0 else f"{x:.2f}%")
        st.dataframe(display_up, width="stretch", hide_index=True, height=350)

    with col_b:
        st.markdown("#### 🟢 跌幅榜")
        display_down = top10_down[[name_col, pct_col]].copy()
        display_down.columns = ["板块", "涨跌幅(%)"]
        display_down["涨跌幅(%)"] = display_down["涨跌幅(%)"].apply(lambda x: f"{x:.2f}%")
        st.dataframe(display_down, width="stretch", hide_index=True, height=350)


def _render_industry_analysis(industry_board: pd.DataFrame, quotes: pd.DataFrame):
    """渲染行业板块分析"""
    if industry_board is None or industry_board.empty:
        st.warning("暂无行业板块数据")
        return

    # 查找列名
    pct_col = None
    name_col = None
    for col in ["涨跌幅", "pct_chg"]:
        if col in industry_board.columns:
            pct_col = col
            break
    for col in ["板块名称", "name"]:
        if col in industry_board.columns:
            name_col = col
            break

    if pct_col is None or name_col is None:
        st.warning("行业数据格式不匹配")
        st.dataframe(industry_board.head(20), width="stretch")
        return

    sorted_board = industry_board.sort_values(pct_col, ascending=False)

    # 行业板块条形图
    top20 = sorted_board.head(20)
    bottom10 = sorted_board.tail(10)

    display_data = pd.concat([top20, bottom10])

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=display_data[name_col],
        x=display_data[pct_col],
        orientation="h",
        marker_color=[
            "#E63946" if v > 0 else "#228B22"
            for v in display_data[pct_col]
        ],
        text=display_data[pct_col].apply(lambda x: f"{x:+.2f}%"),
        textposition="outside",
        opacity=0.85,
    ))

    fig.update_layout(
        title="行业板块涨跌排行",
        xaxis_title="涨跌幅 (%)",
        height=500,
        margin=dict(l=20, r=60, t=40, b=20),
        showlegend=False,
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, width="stretch")


def _render_chain_panorama(concept_board: pd.DataFrame, limit_up_pool: pd.DataFrame):
    """渲染产业链全景图"""
    from data.industry_chain import INDUSTRY_CHAIN_MAP
    from analysis.industry_chain import IndustryChainAnalyzer

    st.markdown("### 产业链全景分析")

    if concept_board is None or concept_board.empty:
        st.warning("暂无板块数据")
        return

    # 使用 IndustryChainAnalyzer 分析产业链热度
    try:
        analyzer = IndustryChainAnalyzer()
        chain_heat = analyzer.analyze_chain_heat(concept_board, limit_up_pool)

        if chain_heat is None or chain_heat.empty:
            st.info("暂无产业链热度数据")
            # 回退到展示产业链结构
            _render_chain_structure()
            return

        # 产业链热力条形图
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=chain_heat["chain_name"],
            x=chain_heat["total_heat_score"],
            orientation="h",
            marker=dict(
                color=chain_heat["total_heat_score"],
                colorscale="Reds",
                showscale=True,
                colorbar=dict(title="热度", thickness=15),
            ),
            text=chain_heat["limit_up_count"].apply(lambda x: f"涨停{x}只"),
            textposition="outside",
            opacity=0.9,
        ))

        fig.update_layout(
            title="产业链热度排行",
            xaxis_title="热度评分",
            height=400,
            margin=dict(l=20, r=20, t=40, b=20),
            showlegend=False,
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, width="stretch")

        # 展开显示每个产业链的上中下游
        st.markdown("### 产业链细分")
        for _, row in chain_heat.iterrows():
            chain_name = row["chain_name"]
            segments = row.get("segments", [])
            with st.expander(f"{chain_name} (涨停{row['limit_up_count']}只, 热度{row['total_heat_score']})"):
                if segments:
                    seg_data = []
                    for seg in segments:
                        seg_data.append({
                            "环节": seg["segment"],
                            "涨停数量": seg["limit_up_count"],
                            "涵盖子行业": "、".join(seg.get("sub_industries", [])[:5]),
                        })
                    st.dataframe(pd.DataFrame(seg_data), width="stretch", hide_index=True)

    except Exception as e:
        st.error(f"产业链分析失败: {e}")
        _render_chain_structure()


def _render_chain_structure():
    """渲染产业链结构（回退方案）"""
    from data.industry_chain import INDUSTRY_CHAIN_MAP

    st.markdown("### 内置产业链结构")

    tabs = st.tabs(list(INDUSTRY_CHAIN_MAP.keys()))

    for chain_name, tab in zip(INDUSTRY_CHAIN_MAP.keys(), tabs):
        with tab:
            segments = INDUSTRY_CHAIN_MAP[chain_name]
            for segment_name, sub_industries in segments.items():
                st.markdown(f"**{segment_name}**")
                st.markdown(" | ".join(sub_industries))
                st.markdown("---")