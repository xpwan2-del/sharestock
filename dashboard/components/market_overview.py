"""
市场概览组件 - 实时市场宽度、情绪仪表盘、涨停跌停统计
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from typing import Dict

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from streamlit_echarts import st_echarts
    HAS_ECHARTS = True
except ImportError:
    HAS_ECHARTS = False

import plotly.express as px

from dashboard.utils import (
    _load_market_breadth,
    _load_realtime_quotes,
    _load_limit_up_pool,
    _load_north_bound,
    _load_market_indices,
    format_amount,
    format_pct,
    color_pct,
)



def _safe_echarts(options: Dict, height: str, key: str, fallback_df: pd.DataFrame = None, x_col: str = None, y_col: str = None, chart_type: str = "bar"):
    if HAS_ECHARTS:
        st_echarts(options=options, height=height, key=key)
        return
    if fallback_df is not None and not fallback_df.empty and x_col in fallback_df.columns and y_col in fallback_df.columns:
        if chart_type == "line":
            fig = px.line(fallback_df, x=x_col, y=y_col, template="plotly_dark")
        else:
            fig = px.bar(fallback_df, x=x_col, y=y_col, template="plotly_dark")
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#e5e7eb"},
            height=int(height.replace("px", "")) if isinstance(height, str) and height.endswith("px") else 320,
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("图表组件未安装，暂无可展示数据")


def _build_gauge_chart(value: float, title: str, min_val: float = 0, max_val: float = 100,
                       thresholds: Dict = None) -> go.Figure:
    """构建暗色金融终端风格仪表盘图表"""
    if thresholds is None:
        thresholds = {
            "极度恐慌": (0, 20, "#00c853"),
            "偏悲观": (20, 40, "#2563eb"),
            "中性": (40, 60, "#64748b"),
            "偏乐观": (60, 80, "#f59e0b"),
            "极度亢奋": (80, 100, "#ff4d4f"),
        }

    fig = go.Figure()
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=value,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": title, "font": {"size": 16, "color": "#e5e7eb"}},
        number={"font": {"size": 42, "color": "#f8fafc"}, "suffix": ""},
        gauge={
            "axis": {"range": [min_val, max_val], "tickwidth": 1, "tickcolor": "#64748b"},
            "bar": {"color": "#38bdf8", "thickness": 0.18},
            "bgcolor": "rgba(15,23,42,0.65)",
            "borderwidth": 1,
            "bordercolor": "rgba(148,163,184,0.25)",
            "steps": [
                {"range": [low, high], "color": color} for _, (low, high, color) in thresholds.items()
            ],
            "threshold": {
                "line": {"color": "#f8fafc", "width": 4},
                "thickness": 0.78,
                "value": value,
            },
        },
    ))

    fig.update_layout(
        height=280,
        margin=dict(l=20, r=20, t=44, b=18),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"size": 12, "color": "#94a3b8"},
    )
    return fig


def _build_metric_card(label: str, value, delta=None, color_mode: str = "auto"):
    """构建自定义指标卡片"""
    delta_str = ""
    if delta is not None:
        try:
            d = float(delta)
            if d > 0:
                delta_str = f'<span class="up">+{d}</span>'
            elif d < 0:
                delta_str = f'<span class="down">{d}</span>'
            else:
                delta_str = f'<span class="flat">{d}</span>'
        except (ValueError, TypeError):
            delta_str = str(delta)

    # 根据颜色模式决定值的显示颜色
    if color_mode == "pct":
        try:
            v = float(str(value).replace("%", ""))
            if v > 0:
                val_style = "up"
            elif v < 0:
                val_style = "down"
            else:
                val_style = "flat"
        except (ValueError, TypeError):
            val_style = ""
    else:
        val_style = ""

    val_html = f'<span class="{val_style}">{value}</span>' if val_style else str(value)

    return f"""
    <div class="terminal-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{val_html}</div>
        <div class="metric-delta">{delta_str}</div>
    </div>
    """


def _calculate_breadth_from_quotes(quotes: pd.DataFrame) -> Dict:
    if quotes is None or quotes.empty or "pct_chg" not in quotes.columns:
        return {}
    source = quotes
    if "code" in quotes.columns:
        code = quotes["code"].astype(str).str.lower().str.replace(r"^(sh|sz|bj)", "", regex=True)
        hs = quotes[code.str.match(r"^(0|3|6)")]
        if not hs.empty:
            source = hs
    pct = pd.to_numeric(source["pct_chg"], errors="coerce").dropna()
    if pct.empty:
        return {}
    up_count = int((pct > 0).sum())
    down_count = int((pct < 0).sum())
    total = int(len(pct))
    return {
        "scope": "沪深A股",
        "total": total,
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": int((pct == 0).sum()),
        "limit_up_count": int((pct >= 9.8).sum()),
        "limit_down_count": int((pct <= -9.8).sum()),
        "avg_pct_chg": round(float(pct.mean()), 2),
        "median_pct_chg": round(float(pct.median()), 2),
        "up_gt_5pct": int((pct > 5).sum()),
        "down_gt_5pct": int((pct < -5).sum()),
        "up_ratio": round(up_count / total * 100, 1) if total else 0,
    }


def _format_panel_pct(value) -> str:
    try:
        value = float(value)
        return f"{value:+.2f}%"
    except (TypeError, ValueError):
        return "--"


def _format_panel_amount(value) -> str:
    try:
        return format_amount(float(value))
    except (TypeError, ValueError):
        return "--"


def _split_market_quotes(quotes: pd.DataFrame):
    if quotes is None or quotes.empty or "code" not in quotes.columns:
        return pd.DataFrame(), pd.DataFrame()
    code = quotes["code"].astype(str).str.lower().str.replace(r"^(sh|sz|bj)", "", regex=True)
    hs_mask = code.str.match(r"^(0|3|6)")
    bj_mask = code.str.match(r"^(4|8|9)")
    return quotes[hs_mask].copy(), quotes[bj_mask].copy()


def _calculate_panel_stats(df: pd.DataFrame) -> Dict:
    if df is None or df.empty or "pct_chg" not in df.columns:
        return {"total": 0, "up": 0, "down": 0, "flat": 0, "up_ratio": 0, "avg": 0, "median": 0, "amount": 0, "strong_up": 0, "strong_down": 0, "limit_up": 0, "limit_down": 0}
    pct = pd.to_numeric(df["pct_chg"], errors="coerce").dropna()
    amount = pd.to_numeric(df.get("amount", pd.Series(dtype=float)), errors="coerce").fillna(0)
    total = int(len(pct))
    up = int((pct > 0).sum())
    down = int((pct < 0).sum())
    return {
        "total": total,
        "up": up,
        "down": down,
        "flat": int((pct == 0).sum()),
        "up_ratio": round(up / total * 100, 1) if total else 0,
        "avg": round(float(pct.mean()), 2) if total else 0,
        "median": round(float(pct.median()), 2) if total else 0,
        "amount": float(amount.sum()),
        "strong_up": int((pct >= 5).sum()),
        "strong_down": int((pct <= -5).sum()),
        "limit_up": int((pct >= 9.8).sum()),
        "limit_down": int((pct <= -9.8).sum()),
    }


def _market_status(stats: Dict, market: str = "hs") -> str:
    if stats.get("total", 0) <= 0:
        return "NO DATA"
    if stats.get("avg", 0) >= 1 and stats.get("up_ratio", 0) >= 55:
        return "BULL BROAD"
    if stats.get("strong_up", 0) >= 80 and market == "hs":
        return "HOT MONEY"
    if stats.get("avg", 0) < 0 and stats.get("up_ratio", 0) < 40:
        return "RISK OFF"
    if stats.get("up_ratio", 0) < 45 and stats.get("avg", 0) > 0:
        return "INDEX ONLY"
    return "MIXED"


def _top_rows(df: pd.DataFrame, n: int = 3, ascending: bool = False) -> pd.DataFrame:
    if df is None or df.empty or "pct_chg" not in df.columns:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["pct_chg"] = pd.to_numeric(tmp["pct_chg"], errors="coerce")
    return tmp.dropna(subset=["pct_chg"]).sort_values("pct_chg", ascending=ascending).head(n)


def _render_top_list(df: pd.DataFrame, title: str, ascending: bool = False):
    top = _top_rows(df, ascending=ascending)
    st.markdown(f'<div class="market-terminal-mini-title">{title}</div>', unsafe_allow_html=True)
    if top.empty:
        st.caption("暂无数据")
        return
    for _, row in top.iterrows():
        name = str(row.get("name", row.get("code", "--")))[:8]
        pct = pd.to_numeric(row.get("pct_chg"), errors="coerce")
        pct_class = "up" if pct > 0 else "down" if pct < 0 else "flat"
        st.markdown(
            f'<div class="market-terminal-row"><span class="market-terminal-label">{name}</span><span class="market-terminal-value {pct_class}">{pct:+.2f}%</span></div>',
            unsafe_allow_html=True,
        )


def _render_market_column(title: str, subtitle: str, stats: Dict, df: pd.DataFrame, market: str):
    status = _market_status(stats, market)
    st.markdown(
        f'''
        <div class="market-terminal-panel">
            <div class="market-terminal-header">
                <div>
                    <div class="market-terminal-title">{title}</div>
                    <div class="market-terminal-subtitle">{subtitle}</div>
                </div>
                <div class="market-terminal-status">{status}</div>
            </div>
            <div class="market-terminal-row"><span class="market-terminal-label">股票数量</span><span class="market-terminal-value">{stats.get('total', 0)}</span></div>
            <div class="market-terminal-row"><span class="market-terminal-label">上涨 / 下跌 / 平盘</span><span class="market-terminal-value"><span class="up">{stats.get('up', 0)}</span> / <span class="down">{stats.get('down', 0)}</span> / <span class="flat">{stats.get('flat', 0)}</span></span></div>
            <div class="market-terminal-row"><span class="market-terminal-label">上涨占比</span><span class="market-terminal-value">{stats.get('up_ratio', 0):.1f}%</span></div>
            <div class="market-terminal-row"><span class="market-terminal-label">平均 / 中位数</span><span class="market-terminal-value"><span class="{'up' if stats.get('avg', 0) > 0 else 'down' if stats.get('avg', 0) < 0 else 'flat'}">{stats.get('avg', 0):+.2f}%</span> / {stats.get('median', 0):+.2f}%</span></div>
            <div class="market-terminal-row"><span class="market-terminal-label">强涨 / 强跌</span><span class="market-terminal-value"><span class="up">{stats.get('strong_up', 0)}</span> / <span class="down">{stats.get('strong_down', 0)}</span></span></div>
            <div class="market-terminal-row"><span class="market-terminal-label">成交额</span><span class="market-terminal-value">{_format_panel_amount(stats.get('amount', 0))}</span></div>
        </div>
        ''',
        unsafe_allow_html=True,
    )
    with st.container():
        st.markdown('<div class="market-terminal-section">', unsafe_allow_html=True)
        left, right = st.columns(2)
        with left:
            _render_top_list(df, "TOP GAINERS", ascending=False)
        with right:
            _render_top_list(df, "TOP LOSERS", ascending=True)
        st.markdown('</div>', unsafe_allow_html=True)


def _render_index_linkage_column(indices: Dict, hs_stats: Dict, bj_stats: Dict, north_data: Dict):
    if hs_stats.get("avg", 0) > 0.8 and hs_stats.get("up_ratio", 0) >= 52:
        signal = "指数与个股共振"
    elif hs_stats.get("avg", 0) > 0 and hs_stats.get("up_ratio", 0) < 45:
        signal = "指数强于个股"
    elif bj_stats.get("avg", 0) > hs_stats.get("avg", 0):
        signal = "北交所相对活跃"
    else:
        signal = "结构分化观察"
    st.markdown(
        f'''
        <div class="market-terminal-panel">
            <div class="market-terminal-header">
                <div>
                    <div class="market-terminal-title">指数联动</div>
                    <div class="market-terminal-subtitle">INDEX LINKAGE / CROSS MARKET</div>
                </div>
                <div class="market-terminal-status">LINK</div>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )
    if indices:
        for name, item in indices.items():
            pct = pd.to_numeric(item.get("pct_chg"), errors="coerce")
            price = pd.to_numeric(item.get("price"), errors="coerce")
            pct_class = "up" if pct > 0 else "down" if pct < 0 else "flat"
            st.markdown(
                f'<div class="market-terminal-row"><span class="market-terminal-label">{name}</span><span class="market-terminal-value {pct_class}">{price:.2f} / {pct:+.2f}%</span></div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("指数数据暂不可用")
    net_flow = north_data.get("net_flow", 0) if north_data else 0
    st.markdown(
        f'''
        <div class="market-terminal-section">
            <div class="market-terminal-row"><span class="market-terminal-label">沪深A赚钱效应</span><span class="market-terminal-value">{hs_stats.get('up_ratio', 0):.1f}%</span></div>
            <div class="market-terminal-row"><span class="market-terminal-label">北交所平均涨幅</span><span class="market-terminal-value">{bj_stats.get('avg', 0):+.2f}%</span></div>
            <div class="market-terminal-row"><span class="market-terminal-label">北向净流</span><span class="market-terminal-value">{format_amount(net_flow)}</span></div>
            <div class="market-terminal-row"><span class="market-terminal-label">联动判断</span><span class="market-terminal-value">{signal}</span></div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def _render_three_column_terminal_panel(quotes: pd.DataFrame, breadth: Dict, indices: Dict, north_data: Dict):
    hs_quotes, bj_quotes = _split_market_quotes(quotes)
    hs_stats = _calculate_panel_stats(hs_quotes)
    bj_stats = _calculate_panel_stats(bj_quotes)
    st.markdown("### 三市场联动终端")
    col_hs, col_bj, col_index = st.columns(3, gap="medium")
    with col_hs:
        _render_market_column("沪深A", "SH/SZ MAIN · STAR · CHINEXT", hs_stats, hs_quotes, "hs")
    with col_bj:
        _render_market_column("北交所", "BEIJING STOCK EXCHANGE", bj_stats, bj_quotes, "bj")
    with col_index:
        _render_index_linkage_column(indices, hs_stats, bj_stats, north_data)



def render_market_overview(cache):
    """渲染市场概览页面"""
    st.markdown('''
    <div class="module-hero">
        <div class="module-kicker">MARKET OVERVIEW</div>
        <div class="module-title">实时市场概览</div>
        <div class="module-subtitle">市场宽度 · 涨跌分布 · 资金热度 · 北向资金监控</div>
    </div>
    ''', unsafe_allow_html=True)

    # 先加载快速摘要，尽早展示首屏信息
    limit_up_pool = cache.get("limit_up_pool", _load_limit_up_pool)
    north_data = cache.get("north_bound", _load_north_bound)
    indices = cache.get("market_indices", _load_market_indices)

    st.markdown("### 快速摘要")
    quick_col1, quick_col2, quick_col3 = st.columns(3)
    with quick_col1:
        st.markdown('<div class="terminal-card"><div class="metric-label">涨停池</div><div class="metric-value">' + str(len(limit_up_pool) if limit_up_pool is not None and not limit_up_pool.empty else 0) + '</div></div>', unsafe_allow_html=True)
    with quick_col2:
        net_flow = north_data.get("net_flow", 0) if north_data else 0
        st.markdown('<div class="terminal-card"><div class="metric-label">北向净流</div><div class="metric-value">' + format_amount(net_flow) + '</div></div>', unsafe_allow_html=True)
    with quick_col3:
        idx_items = len(indices) if indices else 0
        st.markdown('<div class="terminal-card"><div class="metric-label">核心指数</div><div class="metric-value">' + str(idx_items) + '</div></div>', unsafe_allow_html=True)

    # 再加载全量行情，用于市场宽度与分布图
    with st.spinner("正在获取实时市场数据..."):
        quotes = cache.get("quotes", _load_realtime_quotes)
        breadth = _calculate_breadth_from_quotes(quotes)

    _render_three_column_terminal_panel(quotes, breadth, indices, north_data)

    # ---------- 第一行：核心指标卡片 ----------
    st.markdown("### 核心指标")

    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)

    up_count = breadth.get("up_count", 0)
    down_count = breadth.get("down_count", 0)
    flat_count = breadth.get("flat_count", 0)
    total = breadth.get("total", 1)
    up_ratio = breadth.get("up_ratio", 50)
    limit_up = breadth.get("limit_up_count", 0)
    limit_down = breadth.get("limit_down_count", 0)
    avg_pct = breadth.get("avg_pct_chg", 0)
    median_pct = breadth.get("median_pct_chg", 0)

    with col1:
        st.markdown(
            _build_metric_card("上涨家数", up_count, delta=f"{up_ratio}%"),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            _build_metric_card("下跌家数", down_count, delta=f"{round(100-up_ratio, 1)}%"),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            _build_metric_card("涨停", limit_up),
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            _build_metric_card("跌停", limit_down),
            unsafe_allow_html=True,
        )
    with col5:
        st.markdown(
            _build_metric_card("平均涨幅", f"{avg_pct:+.2f}%", color_mode="pct"),
            unsafe_allow_html=True,
        )
    with col6:
        st.markdown(
            _build_metric_card("中位数涨幅", f"{median_pct:+.2f}%", color_mode="pct"),
            unsafe_allow_html=True,
        )
    with col7:
        st.markdown(
            _build_metric_card("平盘", flat_count),
            unsafe_allow_html=True,
        )

    # ---------- 第二行：分布图 + 情绪仪表盘 ----------
    st.markdown("### 市场情绪与分布")
    col_left, col_right = st.columns([1, 1])

    with col_left:
        _render_pct_distribution(quotes)

    with col_right:
        # 计算情绪分数
        sentiment_score = _calculate_sentiment_score(breadth, north_data, limit_up_pool)
        _render_sentiment_dashboard(sentiment_score, breadth, north_data, limit_up_pool)

    # ---------- 第三行：区间分布快速统计 ----------
    st.markdown("### 涨跌区间分布")
    _render_interval_breakdown(quotes)

    # ---------- 第四行：北向资金 + 涨停板质量 ----------
    col_a, col_b = st.columns([1, 1])

    with col_a:
        _render_north_bound_section(north_data)

    with col_b:
        _render_limit_up_quality(limit_up_pool)

    # ---------- 第五行：成交额 TOP 20 ----------
    st.markdown("### 成交额 TOP 20")
    _render_top_turnover(quotes)


def _render_pct_distribution(quotes: pd.DataFrame):
    """渲染 ECharts 涨跌幅分布直方图"""
    if quotes.empty or "pct_chg" not in quotes.columns:
        st.warning("暂无行情数据")
        return

    pct_data = quotes["pct_chg"].dropna()
    pct_data = pct_data[(pct_data >= -10) & (pct_data <= 10)]
    if pct_data.empty:
        st.warning("暂无有效涨跌幅数据")
        return

    bins = pd.cut(pct_data, bins=40)
    hist = bins.value_counts().sort_index()
    x_labels = [f"{interval.left:.1f}~{interval.right:.1f}" for interval in hist.index]
    y_values = hist.astype(int).tolist()
    bar_colors = ["#00c853" if interval.mid < 0 else ("#ff4d4f" if interval.mid > 0 else "#94a3b8") for interval in hist.index]

    mean_val = pct_data.mean()
    median_val = pct_data.median()
    options = {
        "backgroundColor": "transparent",
        "animationDuration": 1200,
        "animationEasing": "cubicOut",
        "title": {
            "text": "全市场涨跌幅分布",
            "left": "center",
            "textStyle": {"color": "#e5e7eb", "fontSize": 15, "fontWeight": 600},
        },
        "grid": {"left": 44, "right": 28, "top": 58, "bottom": 54},
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
            "backgroundColor": "rgba(15,23,42,0.96)",
            "borderColor": "rgba(56,189,248,0.38)",
            "textStyle": {"color": "#e5e7eb"},
        },
        "dataZoom": [
            {"type": "inside", "start": 0, "end": 100},
            {"type": "slider", "height": 18, "bottom": 16, "borderColor": "rgba(148,163,184,0.28)", "textStyle": {"color": "#94a3b8"}},
        ],
        "xAxis": {
            "type": "category",
            "data": x_labels,
            "axisLabel": {"color": "#94a3b8", "rotate": 35, "fontSize": 10},
            "axisLine": {"lineStyle": {"color": "rgba(148,163,184,0.32)"}},
        },
        "yAxis": {
            "type": "value",
            "name": "股票数量",
            "nameTextStyle": {"color": "#94a3b8"},
            "axisLabel": {"color": "#94a3b8"},
            "splitLine": {"lineStyle": {"color": "rgba(148,163,184,0.10)"}},
        },
        "series": [{
            "name": "数量",
            "type": "bar",
            "data": [{"value": value, "itemStyle": {"color": bar_colors[idx]}} for idx, value in enumerate(y_values)],
            "barWidth": "74%",
            "markLine": {
                "symbol": "none",
                "label": {"color": "#f8fafc"},
                "lineStyle": {"type": "dashed", "width": 1.5},
                "data": [
                    {"name": "均值", "xAxis": min(range(len(hist.index)), key=lambda i: abs(hist.index[i].mid - mean_val)), "lineStyle": {"color": "#f59e0b"}, "label": {"formatter": f"均值 {mean_val:+.2f}%"}},
                    {"name": "中位数", "xAxis": min(range(len(hist.index)), key=lambda i: abs(hist.index[i].mid - median_val)), "lineStyle": {"color": "#38bdf8"}, "label": {"formatter": f"中位数 {median_val:+.2f}%"}},
                ],
            },
        }],
    }
    distribution_df = pd.DataFrame({"区间": x_labels, "数量": y_values})
    _safe_echarts(options=options, height="370px", key="pct_distribution_echarts", fallback_df=distribution_df, x_col="区间", y_col="数量")


def _calculate_sentiment_score(breadth: Dict, north_data: Dict,
                                limit_up_pool: pd.DataFrame) -> float:
    """计算市场情绪综合分数"""
    score = 50.0

    if breadth:
        up_ratio = breadth.get("up_ratio", 50)
        score += (up_ratio - 50) * 0.5
        score += min(breadth.get("limit_up_count", 0), 200) * 0.1
        score -= min(breadth.get("limit_down_count", 0), 200) * 0.2
        score += breadth.get("avg_pct_chg", 0) * 2

    if north_data:
        net_flow = north_data.get("net_flow", 0)
        net_yi = net_flow / 1e8
        score += min(max(net_yi / 2, -15), 15)

    if limit_up_pool is not None and not limit_up_pool.empty:
        score += min(len(limit_up_pool) * 0.2, 10)

    return max(0, min(100, score))


def _render_sentiment_dashboard(score: float, breadth: Dict,
                                 north_data: Dict, limit_up_pool: pd.DataFrame):
    """渲染情绪仪表盘"""
    # 判断等级
    if score >= 80:
        level = "极度亢奋"
        advice = "市场过热，注意回调风险"
    elif score >= 65:
        level = "偏乐观"
        advice = "市场情绪积极，可适当参与"
    elif score >= 45:
        level = "中性"
        advice = "市场情绪平稳，精选个股"
    elif score >= 30:
        level = "偏悲观"
        advice = "市场谨慎，控制仓位"
    else:
        level = "极度恐慌"
        advice = "市场恐慌，存在超跌机会"

    fig = _build_gauge_chart(score, f"市场情绪: {level}")
    st.plotly_chart(fig, width="stretch")

    st.markdown(f'<div class="terminal-advice"><b>操作建议</b>: {advice}</div>', unsafe_allow_html=True)

    comp_col1, comp_col2 = st.columns(2)
    with comp_col1:
        st.metric("市场宽度分", round(float(breadth.get("up_ratio", 50)), 1),
                  delta=f"{breadth.get('up_ratio', 50) - 50:+.1f}")
        st.metric("涨停数量", breadth.get("limit_up_count", 0))
        st.metric("平均涨跌幅", f"{breadth.get('avg_pct_chg', 0):+.2f}%")
    with comp_col2:
        if north_data:
            net_yi = north_data.get("net_flow", 0) / 1e8
            st.metric("北向净流入(亿)", f"{net_yi:.2f}")
        else:
            st.metric("北向净流入(亿)", "暂无数据")
        if limit_up_pool is not None and not limit_up_pool.empty:
            st.metric("涨停池数量", len(limit_up_pool))
        else:
            st.metric("涨停池数量", 0)


def _render_interval_breakdown(quotes: pd.DataFrame):
    """渲染 ECharts 涨跌区间分布"""
    if quotes.empty or "pct_chg" not in quotes.columns:
        return

    pct = quotes["pct_chg"].dropna()
    if pct.empty:
        return

    intervals = [
        ("涨停 (>=9.9%)", (9.9, 100), "#ff4d4f"),
        ("大涨 (5%~9.9%)", (5, 9.9), "#f59e0b"),
        ("小涨 (2%~5%)", (2, 5), "#fbbf24"),
        ("微涨 (0%~2%)", (0, 2), "#fde047"),
        ("微跌 (-2%~0%)", (-2, 0), "#86efac"),
        ("小跌 (-5%~-2%)", (-5, -2), "#34d399"),
        ("大跌 (-9.9%~-5%)", (-9.9, -5), "#60a5fa"),
        ("跌停 (<=-9.9%)", (-100, -9.9), "#00c853"),
    ]

    counts = []
    for label, (low, high), color in intervals:
        if label.startswith("跌停"):
            count = (pct <= high).sum()
        elif label.startswith("涨停"):
            count = (pct >= low).sum()
        else:
            count = ((pct >= low) & (pct < high)).sum()
        counts.append({"name": label, "value": int(count), "itemStyle": {"color": color}})

    options = {
        "backgroundColor": "transparent",
        "title": {
            "text": "涨跌区间分布",
            "left": "center",
            "textStyle": {"color": "#e5e7eb", "fontSize": 15, "fontWeight": 600},
        },
        "tooltip": {
            "trigger": "item",
            "backgroundColor": "rgba(15,23,42,0.96)",
            "borderColor": "rgba(245,158,11,0.38)",
            "textStyle": {"color": "#e5e7eb"},
            "formatter": "{b}<br/>{c}只 ({d}%)",
        },
        "legend": {
            "bottom": 0,
            "textStyle": {"color": "#94a3b8"},
            "type": "scroll",
        },
        "series": [{
            "name": "涨跌区间",
            "type": "pie",
            "radius": ["38%", "70%"],
            "center": ["50%", "48%"],
            "avoidLabelOverlap": False,
            "itemStyle": {
                "borderColor": "#0b1220",
                "borderWidth": 2,
                "shadowBlur": 12,
                "shadowColor": "rgba(0,0,0,0.35)",
            },
            "label": {"color": "#e5e7eb", "formatter": "{b}\n{c}只"},
            "labelLine": {"lineStyle": {"color": "rgba(148,163,184,0.5)"}},
            "data": counts,
            "emphasis": {
                "itemStyle": {
                    "shadowBlur": 20,
                    "shadowOffsetX": 0,
                    "shadowColor": "rgba(56,189,248,0.25)",
                }
            },
            "animationType": "scale",
            "animationEasing": "elasticOut",
        }],
    }
    interval_df = pd.DataFrame({"区间": [item["name"] for item in counts], "数量": [item["value"] for item in counts]})
    _safe_echarts(options=options, height="360px", key="interval_breakdown_echarts", fallback_df=interval_df, x_col="区间", y_col="数量")


def _render_north_bound_section(north_data: Dict):
    """渲染北向资金区域"""
    st.markdown("#### 北向资金")

    if not north_data or "net_flow" not in north_data:
        st.info("暂无北向资金数据")
        return

    net_flow = north_data.get("net_flow", 0)
    net_yi = net_flow / 1e8

    direction = "流入" if net_flow > 0 else "流出"
    st.metric(
        label=f"北向资金净{direction}",
        value=f"{abs(net_yi):.2f} 亿",
        delta=f"{net_yi:+.2f} 亿",
    )

    history = north_data.get("data")
    if history is not None and not history.empty:
        x_data = history.index.astype(str).tolist() if hasattr(history.index, "astype") else history.iloc[:, 0].astype(str).tolist()
        y_data = pd.to_numeric(history.iloc[:, 1], errors='coerce').fillna(0).tolist() if history.shape[1] > 1 else history.iloc[:, 0].astype(float).tolist()
        options = {
            "backgroundColor": "transparent",
            "title": {
                "text": "北向资金近期走势",
                "left": "center",
                "textStyle": {"color": "#e5e7eb", "fontSize": 15, "fontWeight": 600},
            },
            "tooltip": {
                "trigger": "axis",
                "backgroundColor": "rgba(15,23,42,0.96)",
                "borderColor": "rgba(245,158,11,0.38)",
                "textStyle": {"color": "#e5e7eb"},
            },
            "grid": {"left": 40, "right": 24, "top": 56, "bottom": 36},
            "xAxis": {
                "type": "category",
                "data": x_data,
                "boundaryGap": False,
                "axisLabel": {"color": "#94a3b8", "rotate": 30, "fontSize": 10},
                "axisLine": {"lineStyle": {"color": "rgba(148,163,184,0.32)"}},
            },
            "yAxis": {
                "type": "value",
                "axisLabel": {"color": "#94a3b8"},
                "splitLine": {"lineStyle": {"color": "rgba(148,163,184,0.10)"}},
            },
            "series": [{
                "name": "北向净流入",
                "type": "line",
                "data": y_data,
                "smooth": True,
                "symbol": "circle",
                "symbolSize": 7,
                "lineStyle": {"color": "#38bdf8", "width": 3},
                "itemStyle": {"color": "#38bdf8"},
                "areaStyle": {"color": "rgba(56,189,248,0.14)"},
                "emphasis": {"focus": "series"},
            }],
        }
        _safe_echarts(options=options, height="300px", key="north_flow_echarts", fallback_df=history, x_col=history.columns[0] if hasattr(history, 'columns') and len(history.columns) > 0 else None, y_col=history.columns[1] if hasattr(history, 'columns') and len(history.columns) > 1 else None, chart_type="line")


def _render_limit_up_quality(limit_up_pool: pd.DataFrame):
    """渲染涨停板质量分析"""
    st.markdown("#### 涨停板质量分析")

    if limit_up_pool is None or limit_up_pool.empty:
        st.info("暂无涨停板数据")
        return

    total = len(limit_up_pool)
    st.metric("涨停总数", total)

    solid = 0
    fragile = 0
    if not limit_up_pool.empty:
        for _, row in limit_up_pool.iterrows():
            open_pct_col = None
            for col_name in ["open_pct", "开盘涨幅", "open"]:
                if col_name in row.index:
                    open_pct_col = col_name
                    break

            if open_pct_col:
                try:
                    open_pct = float(row[open_pct_col])
                    if open_pct > 8:
                        solid += 1
                    elif open_pct < 3:
                        fragile += 1
                except (ValueError, TypeError):
                    pass

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("一字/高开板", solid, delta=f"{round(solid/total*100, 1)}%" if total else "0%")
    with col_b:
        st.metric("午后烂板", fragile, delta=f"{round(fragile/total*100, 1)}%" if total else "0%")

    quality = "高" if solid > total * 0.3 else ("中" if solid > total * 0.15 else "低")
    st.metric("封板质量评级", quality)


def _render_top_turnover(quotes: pd.DataFrame):
    """渲染成交额 TOP 20"""
    if quotes.empty:
        st.info("暂无行情数据")
        return

    # 确保有成交额列
    amount_col = None
    for col_name in ["amount", "成交额"]:
        if col_name in quotes.columns:
            amount_col = col_name
            break

    if amount_col is None:
        st.info("暂无成交额数据")
        return

    top20 = quotes.nlargest(20, amount_col)
    display_cols = []
    for col in ["code", "name", "price", "pct_chg", "amount", "turnover", "volume_ratio"]:
        if col in top20.columns:
            display_cols.append(col)

    display_df = top20[display_cols].copy()

    # 格式化
    if "amount" in display_df.columns:
        display_df["成交额"] = display_df["amount"].apply(lambda x: f"{x/1e8:.2f}亿")
        display_df.drop(columns=["amount"], inplace=True)

    if "pct_chg" in display_df.columns:
        display_df["涨跌幅"] = display_df["pct_chg"].apply(lambda x: f"{x:+.2f}%")
        display_df.drop(columns=["pct_chg"], inplace=True)

    if "turnover" in display_df.columns:
        display_df["换手率"] = display_df["turnover"].apply(lambda x: f"{x:.2f}%")

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        height=400,
    )