"""
龙虎榜分析组件 - 席位分析、机构动向、游资风格
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.utils import (
    _load_dragon_tiger,
    _load_north_bound,
    format_amount,
    get_today_str,
)


def render_dragon_tiger(cache):
    """渲染龙虎榜分析页面"""
    st.markdown('''
    <div class="module-hero">
        <div class="module-kicker">DRAGON TIGER LIST</div>
        <div class="module-title">龙虎榜分析与机构动向</div>
        <div class="module-subtitle">席位跟踪 · 机构净买 · 游资风格 · 高管增减持</div>
    </div>
    ''', unsafe_allow_html=True)

    # 日期选择
    today = get_today_str()
    col_date1, col_date2 = st.columns([3, 1])

    with col_date1:
        date_input = st.text_input("分析日期 (YYYYMMDD)", value=today, max_chars=8,
                                    help="输入要分析的龙虎榜日期")

    with col_date2:
        st.markdown("<br>", unsafe_allow_html=True)  # 对齐
        analyze_btn = st.button("🔍 分析", type="primary", use_container_width=True)

    if analyze_btn or st.session_state.get("_dt_analyzed_date") == date_input:
        st.session_state._dt_analyzed_date = date_input
        _perform_analysis(cache, date_input)
    else:
        _show_dragon_tiger_info()


def _perform_analysis(cache, date: str):
    """执行龙虎榜分析"""
    with st.spinner(f"正在分析 {date} 龙虎榜数据..."):
        try:
            dt_data = cache.get(f"dragon_tiger_{date}", _load_dragon_tiger, date)
        except Exception as e:
            st.error(f"获取龙虎榜数据失败: {e}")
            return

        if dt_data is None or dt_data.empty:
            st.warning(f"{date} 暂无龙虎榜数据（可能非交易日或数据未更新）")
            # 尝试用今天的数据
            today = get_today_str()
            if date != today:
                st.info("尝试获取最近数据...")
                try:
                    dt_data = cache.get(f"dragon_tiger_{today}", _load_dragon_tiger, today)
                    if dt_data is not None and not dt_data.empty:
                        st.success(f"已切换到 {today} 的数据")
                        date = today
                    else:
                        return
                except Exception:
                    return
            else:
                return

    # ---------- 总体统计 ----------
    _render_dt_summary(dt_data)

    # ---------- Tab: 席位分析 / 机构动向 / 高管增减持 ----------
    tab1, tab2, tab3 = st.tabs(["席位分析", "机构资金流向", "高管增减持"])

    with tab1:
        _render_seat_analysis(dt_data)

    with tab2:
        _render_institution_flow(dt_data, cache, date)

    with tab3:
        _render_insider_trading(cache, date)


def _render_dt_summary(dt_data: pd.DataFrame):
    """渲染龙虎榜总览"""
    st.markdown("### 龙虎榜总览")

    # 基础统计
    total_records = len(dt_data)

    # 统计买卖金额
    buy_col = None
    sell_col = None
    for col in ["买入金额", "buy_amount"]:
        if col in dt_data.columns:
            buy_col = col
            break
    for col in ["卖出金额", "sell_amount"]:
        if col in dt_data.columns:
            sell_col = col
            break

    total_buy = dt_data[buy_col].sum() if buy_col else 0
    total_sell = dt_data[sell_col].sum() if sell_col else 0
    net_flow = total_buy - total_sell

    # 统计上榜股票数
    code_col = None
    for col in ["代码", "code", "stock_code"]:
        if col in dt_data.columns:
            code_col = col
            break

    unique_stocks = dt_data[code_col].nunique() if code_col else 0

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("上榜记录", total_records)
    with col2:
        st.metric("上榜股票", unique_stocks)
    with col3:
        st.metric("总买入", format_amount(total_buy))
    with col4:
        st.metric("总卖出", format_amount(total_sell))
    with col5:
        net_label = "净流入" if net_flow >= 0 else "净流出"
        st.metric(net_label, format_amount(abs(net_flow)),
                  delta=format_amount(net_flow))

    # 识别机构和游资行为
    from data.dragon_tiger import DragonTigerCollector
    dt_collector = DragonTigerCollector()
    behavior = dt_collector.identify_institution_behavior()
    st.markdown("### 机构买卖统计")
    if behavior:
        b_col1, b_col2, b_col3 = st.columns(3)
        b_col1.metric("机构买入(万)", behavior.get("institution_buy", 0))
        b_col2.metric("机构卖出(万)", behavior.get("institution_sell", 0))
        b_col3.metric("机构净买(万)", behavior.get("institution_net", 0))
        st.info(f"机构动向: {behavior.get('dominant_force', '')}")

        with b_col1:
            inst_net = behavior.get("institution_net", 0)
            inst_ratio = behavior.get("institution_ratio", 0)
            st.metric(
                "机构净额",
                format_amount(inst_net),
                delta=f"占比 {inst_ratio*100:.1f}%",
            )

        with b_col2:
            venture_net = behavior.get("venture_net", 0)
            venture_ratio = behavior.get("venture_ratio", 0)
            st.metric(
                "游资净额",
                format_amount(venture_net),
                delta=f"占比 {venture_ratio*100:.1f}%",
            )

        with b_col3:
            dominant = behavior.get("dominant_force", "unknown")
            dominant_label = "机构主导" if dominant == "institution" else "游资主导"
            st.metric("主导力量", dominant_label)


def _render_seat_analysis(dt_data: pd.DataFrame):
    """渲染席位分析"""
    st.markdown("### 活跃席位分析")

    # 按席位聚合
    seat_col = None
    for col in ["席位名称", "seat_name"]:
        if col in dt_data.columns:
            seat_col = col
            break

    if seat_col is None:
        st.info("暂无席位数据")
        return

    buy_col = None
    sell_col = None
    for col in ["买入金额", "buy_amount"]:
        if col in dt_data.columns:
            buy_col = col
            break
    for col in ["卖出金额", "sell_amount"]:
        if col in dt_data.columns:
            sell_col = col
            break

    if buy_col is None:
        seat_counts = dt_data.groupby(seat_col).size().reset_index(name="上榜次数")
        seat_counts = seat_counts.sort_values("上榜次数", ascending=False)
        st.dataframe(seat_counts.head(20), use_container_width=True, hide_index=True)
        return

    seat_stats = dt_data.groupby(seat_col).agg(
        上榜次数=(seat_col, "count"),
        总买入=(buy_col, "sum"),
        总卖出=(sell_col, "sum") if sell_col else (buy_col, lambda x: 0),
    ).reset_index()

    seat_stats["净额"] = seat_stats["总买入"] - seat_stats["总卖出"]
    seat_stats["风格"] = seat_stats.apply(
        lambda r: (
            "激进买入" if r["总买入"] > r["总卖出"] * 2
            else "净买入" if r["总买入"] > r["总卖出"]
            else "净卖出" if r["总卖出"] > r["总买入"]
            else "平衡"
        ),
        axis=1,
    )

    seat_stats = seat_stats.sort_values("上榜次数", ascending=False)

    # 格式化金额
    seat_stats["总买入"] = seat_stats["总买入"].apply(format_amount)
    seat_stats["总卖出"] = seat_stats["总卖出"].apply(format_amount)
    seat_stats["净额"] = seat_stats["净额"].apply(format_amount)

    st.dataframe(
        seat_stats.head(30),
        use_container_width=True,
        hide_index=True,
        height=500,
    )

    # 机构 vs 游资 分类统计
    st.markdown("### 机构席位 vs 游资席位")

    institution_names = [
        "机构专用", "深股通", "沪股通", "中国银河", "中信证券",
        "华泰证券", "海通证券", "国泰君安", "招商证券", "广发证券",
        "中国国际金融", "中信建投",
    ]
    venture_names = [
        "财通证券", "华鑫证券", "申港证券", "甬兴证券", "国盛证券",
        "东方证券", "光大证券", "长江证券", "天风证券", "兴业证券",
    ]

    inst_seats = seat_stats[seat_stats[seat_col].apply(
        lambda x: any(name in str(x) for name in institution_names)
    )]
    venture_seats = seat_stats[seat_stats[seat_col].apply(
        lambda x: any(name in str(x) for name in venture_names)
    )]

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**机构席位**")
        if not inst_seats.empty:
            st.dataframe(inst_seats, use_container_width=True, hide_index=True, height=250)
        else:
            st.info("暂无机构席位上榜")

    with col_b:
        st.markdown("**游资席位**")
        if not venture_seats.empty:
            st.dataframe(venture_seats, use_container_width=True, hide_index=True, height=250)
        else:
            st.info("暂无游资席位上榜")


def _render_institution_flow(dt_data: pd.DataFrame, cache, date: str):
    """渲染机构资金流向"""
    st.markdown("### 机构资金流向")

    # 使用 InstitutionStyleAnalyzer
    try:
        from analysis.institution_style import InstitutionStyleAnalyzer
        analyzer = InstitutionStyleAnalyzer()

        # 分析席位模式
        with st.spinner("正在分析机构模式..."):
            patterns = analyzer.analyze_dragon_tiger_patterns(days=30)

        if patterns:
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("统计席位", patterns.get("total_seats", 0))
            with col_b:
                st.metric("机构席位", patterns.get("institution_count", 0))
            with col_c:
                st.metric("游资席位", patterns.get("venture_count", 0))

            # 机构净流向
            inst_net = patterns.get("institution_net_flow", 0)
            venture_net = patterns.get("venture_net_flow", 0)

            flow_col1, flow_col2 = st.columns(2)
            with flow_col1:
                st.metric("机构月度净流向", format_amount(inst_net),
                          delta="持续流入" if inst_net > 0 else "持续流出")
            with flow_col2:
                st.metric("游资月度净流向", format_amount(venture_net),
                          delta="活跃" if abs(venture_net) > 0 else "不活跃")
    except Exception as e:
        st.warning(f"机构分析模块异常: {e}")

    # 北向资金
    st.markdown("### 北向资金监控")
    north_data = cache.get("north_bound", _load_north_bound)

    if north_data and "net_flow" in north_data:
        net_yi = north_data["net_flow"] / 1e8
        flow_direction = "流入" if net_yi > 0 else "流出"

        st.metric(
            f"北向资金净{flow_direction}",
            f"{abs(net_yi):.2f} 亿",
            delta=f"{net_yi:+.2f} 亿",
        )

        history = north_data.get("data")
        if history is not None and not history.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=history.index if history.index.dtype == 'datetime64[ns]' else history.iloc[:, 0],
                y=history.iloc[:, 1] if history.shape[1] > 1 else history.iloc[:, 0],
                marker_color=["#FF3333" if v > 0 else "#33AA33" for v in (
                    history.iloc[:, 1] if history.shape[1] > 1 else history.iloc[:, 0]
                )],
                name="北向净流入",
                opacity=0.8,
            ))
            fig.update_layout(
                title="北向资金近期流向",
                height=300,
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暂无北向资金数据")


def _render_insider_trading(cache, date: str):
    """渲染高管增减持"""
    st.markdown("### 高管增减持")

    try:
        from data.dragon_tiger import DragonTigerCollector
        dt_collector = DragonTigerCollector()
        insider = dt_collector.get_insider_trading(days=30)

        if insider is None or insider.empty:
            st.info("暂无高管增减持数据")
            return

        # 分类统计
        buy_count = 0
        sell_count = 0
        if "变动方向" in insider.columns:
            buy_count = insider["变动方向"].str.contains("增持", na=False).sum()
            sell_count = insider["变动方向"].str.contains("减持", na=False).sum()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("增持记录", buy_count)
        with col2:
            st.metric("减持记录", sell_count)

        # 显示最近记录
        st.markdown("### 最近增减持记录")
        display_cols = [c for c in insider.columns if c in [
            "股票代码", "股票简称", "变动日期", "变动方向",
            "变动数量", "变动后持股", "变动人", "董监高姓名",
        ]]
        if display_cols:
            st.dataframe(
                insider[display_cols].head(30),
                use_container_width=True,
                hide_index=True,
                height=400,
            )
    except Exception as e:
        st.warning(f"高管增减持数据获取失败: {e}")


def _show_dragon_tiger_info():
    """展示龙虎榜分析说明"""
    st.markdown("### 龙虎榜分析功能")
    st.markdown("""
    - **席位追踪**: 分析活跃营业部的买卖偏好
    - **机构识别**: 区分机构专用席位与游资席位
    - **资金流向**: 计算机构和游资的净买入/卖出
    - **高管动向**: 监控高管增减持行为
    - **北向资金**: 跟踪北向资金的流入流出

    输入日期后点击「分析」按钮查看详细数据。
    """)