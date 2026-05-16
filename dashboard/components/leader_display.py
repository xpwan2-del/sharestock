"""
龙头识别展示组件 - 逻辑龙头/情绪龙头/容量龙头
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from typing import Dict, List, Optional

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.utils import (
    _load_realtime_quotes,
    _load_concept_board,
    _load_limit_up_pool,
    format_amount,
    format_pct,
)


def render_leader_display(cache):
    """渲染龙头识别页面"""
    st.markdown('''
    <div class="module-hero">
        <div class="module-kicker">LEADER RADAR</div>
        <div class="module-title">龙头识别引擎</div>
        <div class="module-subtitle">逻辑龙头 · 情绪龙头 · 容量龙头 · 板块核心资产识别</div>
    </div>
    ''', unsafe_allow_html=True)

    with st.spinner("正在加载数据..."):
        quotes = cache.get("quotes", _load_realtime_quotes)
        concept_board = cache.get("concept_board", _load_concept_board)
        limit_up_pool = cache.get("limit_up_pool", _load_limit_up_pool)

    # ---------- 热门概念选择器 ----------
    st.markdown("### 选择分析概念")

    # 获取热门概念列表
    hot_concepts = _get_hot_concepts(concept_board)

    if not hot_concepts:
        hot_concepts = [
            "人工智能", "机器人", "半导体", "新能源汽车", "光伏",
            "储能", "医疗器械", "白酒", "锂电池", "军工",
        ]
        st.caption("概念板块接口暂不可用，已提供默认热门概念")

    # 概念选择
    selected_concepts = st.multiselect(
        "选择要分析的概念/板块",
        options=hot_concepts,
        default=hot_concepts[:3] if len(hot_concepts) >= 3 else hot_concepts,
        help="可多选概念进行分析",
    )

    if not selected_concepts:
        st.info("请选择至少一个概念进行分析")
        return

    # 分析按钮
    if st.button("🔍 分析龙头", type="primary", use_container_width=True):
        with st.spinner("正在识别龙头..."):
            for concept in selected_concepts:
                _analyze_and_display_leaders(concept, quotes, limit_up_pool)
    else:
        # 默认展示提示
        st.info("选择概念后点击「分析龙头」开始识别")
        _show_leader_explanation()


def _get_hot_concepts(concept_board: pd.DataFrame) -> List[str]:
    """获取热门概念列表"""
    if concept_board is None or concept_board.empty:
        return []

    # 查找名称列
    name_col = None
    pct_col = None
    for col in ["板块名称", "name"]:
        if col in concept_board.columns:
            name_col = col
            break
    for col in ["涨跌幅", "pct_chg"]:
        if col in concept_board.columns:
            pct_col = col
            break

    if name_col is None:
        return concept_board.iloc[:, 0].head(50).tolist()

    if pct_col:
        concept_board = concept_board.sort_values(pct_col, ascending=False)

    return concept_board[name_col].head(30).tolist()


def _analyze_and_display_leaders(concept: str, quotes: pd.DataFrame,
                                  limit_up_pool: pd.DataFrame):
    """分析并展示龙头"""
    from analysis.leader_finder import LeaderFinder

    st.markdown(f"---")
    st.markdown(f"### 📌 {concept}")

    finder = LeaderFinder()

    try:
        # 获取概念成分股（带会话缓存）
        cache_key = f"concept_comp_{concept}"
        concept_stocks = st.session_state.cache.get(
            cache_key, finder.market.get_concept_board_components, concept
        )
        if concept_stocks is None or (hasattr(concept_stocks, 'empty') and concept_stocks.empty):
            st.warning(f"「{concept}」成分股数据接口暂不可用（AKShare 超时），请稍后重试")
            return

        st.caption(f"成分股数量: {len(concept_stocks)}")

        # 三列并排展示三类龙头
        col1, col2, col3 = st.columns(3)

        with col1:
            _display_logic_leaders(finder, concept, concept_stocks, quotes)

        with col2:
            _display_sentiment_leaders(finder, limit_up_pool, concept_stocks, quotes)

        with col3:
            _display_capacity_leaders(finder, concept_stocks, quotes)

        # 概念内涨停股预览
        _display_concept_limit_up(concept_stocks, limit_up_pool, quotes)

    except Exception as e:
        st.error(f"分析「{concept}」龙头时出错: {e}")


def _display_logic_leaders(finder, concept: str, concept_stocks: pd.DataFrame,
                            quotes: pd.DataFrame):
    """展示逻辑龙头"""
    st.markdown("#### 🧠 逻辑龙头")
    st.caption("产业链最受益、基本面最正")

    try:
        leaders = finder.find_logic_leaders(concept, concept_stocks, quotes)

        if leaders.empty:
            st.info("未发现逻辑龙头")
            return

        for _, row in leaders.iterrows():
            name = row.get("name", row.get("名称", "未知"))
            code = row.get("code", row.get("代码", ""))
            score = row.get("logic_score", 0)
            pct = row.get("pct_chg", 0)
            pe = row.get("pe_ttm", None)
            mv = row.get("total_mv", None)

            with st.container():
                st.markdown(f"""
                <div style="
                    border: 1px solid #FF6B35;
                    border-radius: 8px;
                    padding: 10px 14px;
                    margin-bottom: 8px;
                    background: #FFF8F5;
                ">
                    <b>{name}</b> <span style="color:#999;font-size:12px;">{code}</span>
                    <br>
                    <span style="font-size:12px;color:#666;">
                        评分: {score:.1f} | 涨幅: <span style="color:{'#FF3333' if pct > 0 else '#33AA33'};">
                        {pct:+.2f}%</span>
                        {f"| PE: {pe:.1f}" if pe and pe > 0 else ""}
                        {f"| 市值: {format_amount(mv)}" if mv else ""}
                    </span>
                </div>
                """, unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"逻辑龙头分析失败: {e}")


def _display_sentiment_leaders(finder, limit_up_pool: pd.DataFrame,
                                concept_stocks: pd.DataFrame, quotes: pd.DataFrame):
    """展示情绪龙头"""
    st.markdown("#### 🔥 情绪龙头")
    st.caption("连板数多、封单强、市场关注度最高")

    try:
        leaders = finder.find_sentiment_leaders(limit_up_pool, concept_stocks, quotes)

        if leaders.empty:
            st.info("未发现情绪龙头")
            return

        for _, row in leaders.iterrows():
            name = row.get("名称", row.get("name", "未知"))
            code = row.get("代码", row.get("code", ""))
            score = row.get("sentiment_score", 0)
            consecutive = row.get("连板数", "-")
            seal_time = row.get("首次封板时间", "-")
            seal_amount = row.get("封单资金", 0)

            with st.container():
                st.markdown(f"""
                <div style="
                    border: 1px solid #E63946;
                    border-radius: 8px;
                    padding: 10px 14px;
                    margin-bottom: 8px;
                    background: #FFF0F0;
                ">
                    <b>{name}</b> <span style="color:#999;font-size:12px;">{code}</span>
                    <br>
                    <span style="font-size:12px;color:#666;">
                        评分: {score:.1f} | 连板: {consecutive}
                        {f"| 封单: {format_amount(seal_amount)}" if seal_amount else ""}
                        <br>封板时间: {seal_time}
                    </span>
                </div>
                """, unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"情绪龙头分析失败: {e}")


def _display_capacity_leaders(finder, concept_stocks: pd.DataFrame,
                               quotes: pd.DataFrame):
    """展示容量龙头"""
    st.markdown("#### 💰 容量龙头")
    st.caption("大市值+高成交额,大资金可进出")

    try:
        leaders = finder.find_capacity_leaders(concept_stocks, quotes)

        if leaders.empty:
            st.info("未发现容量龙头")
            return

        for _, row in leaders.iterrows():
            name = row.get("name", row.get("名称", "未知"))
            code = row.get("code", row.get("代码", ""))
            score = row.get("capacity_score", 0)
            pct = row.get("pct_chg", 0)
            mv = row.get("total_mv", None)
            amount = row.get("amount", None)
            turnover = row.get("turnover", None)

            with st.container():
                st.markdown(f"""
                <div style="
                    border: 1px solid #457B9D;
                    border-radius: 8px;
                    padding: 10px 14px;
                    margin-bottom: 8px;
                    background: #F0F7FA;
                ">
                    <b>{name}</b> <span style="color:#999;font-size:12px;">{code}</span>
                    <br>
                    <span style="font-size:12px;color:#666;">
                        评分: {score:.1f} | 涨幅: <span style="color:{'#FF3333' if pct > 0 else '#33AA33'};">
                        {pct:+.2f}%</span>
                        {f"| 市值: {format_amount(mv)}" if mv else ""}
                        {f"<br>成交额: {format_amount(amount)}" if amount else ""}
                        {f"| 换手: {turnover:.2f}%" if turnover else ""}
                    </span>
                </div>
                """, unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"容量龙头分析失败: {e}")


def _display_concept_limit_up(concept_stocks: pd.DataFrame,
                                limit_up_pool: pd.DataFrame,
                                quotes: pd.DataFrame):
    """展示概念内涨停股"""
    if limit_up_pool is None or limit_up_pool.empty:
        return

    # 获取概念成分股代码
    code_col = "代码" if "代码" in concept_stocks.columns else (
        "code" if "code" in concept_stocks.columns else None
    )
    if code_col is None:
        return

    concept_codes = set(concept_stocks[code_col].tolist())

    # 获取涨停池代码
    limit_code_col = "代码" if "代码" in limit_up_pool.columns else (
        "code" if "code" in limit_up_pool.columns else None
    )
    if limit_code_col is None:
        return

    limit_codes = set(limit_up_pool[limit_code_col].tolist())

    intersection = concept_codes & limit_codes
    if not intersection:
        return

    with st.expander(f"概念内涨停股 ({len(intersection)}只)"):
        matched = limit_up_pool[limit_up_pool[limit_code_col].isin(intersection)]
        display_cols = [c for c in [limit_code_col, "名称", "name", "连板数", "封单资金", "首次封板时间"] if c in matched.columns]
        if display_cols:
            st.dataframe(matched[display_cols], use_container_width=True, hide_index=True)


def _show_leader_explanation():
    """展示龙头分类说明"""
    st.markdown("### 龙头分类说明")
    exp_col1, exp_col2, exp_col3 = st.columns(3)

    with exp_col1:
        st.markdown("""
        **🧠 逻辑龙头**
        - 产业链中最受益的股票
        - 主营业务占比高
        - ROE优、估值合理
        - 行业地位高
        - 综合评分: PE + PB + 市值 + 涨幅 + 换手
        """)

    with exp_col2:
        st.markdown("""
        **🔥 情绪龙头**
        - 短线资金聚焦标的
        - 连续涨停、封单强
        - 封板时间早
        - 换手率适中
        - 综合评分: 连板数 + 封板时间 + 封单 + 换手
        """)

    with exp_col3:
        st.markdown("""
        **💰 容量龙头**
        - 大资金可进出的标的
        - 市值 > 200亿
        - 日成交额 > 5亿
        - 换手率合理
        - 趋势健康
        - 综合评分: 市值 + 成交额 + 换手率 + 趋势
        """)