"""
趋势逆转股票列表组件 - 技术面底部/顶部识别
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
    _load_realtime_quotes,
    _load_limit_up_pool,
    format_pct,
)


def render_trend_reversal(cache):
    """渲染趋势逆转页面"""
    st.markdown('''
    <div class="module-hero">
        <div class="module-kicker">REVERSAL SCANNER</div>
        <div class="module-title">趋势逆转识别</div>
        <div class="module-subtitle">技术底部 · 强势突破 · 动量修复 · 反转候选池</div>
    </div>
    ''', unsafe_allow_html=True)

    with st.spinner("正在加载数据..."):
        quotes = cache.get("quotes", _load_realtime_quotes)

    if quotes.empty:
        st.warning("暂无行情数据")
        return

    # ---------- 控制面板 ----------
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([2, 1, 1])

    with col_ctrl1:
        min_score = st.slider(
            "逆转信号最低阈值",
            min_value=20,
            max_value=100,
            value=40,
            step=5,
            help="只显示逆转评分 >= 此值的股票",
        )

    with col_ctrl2:
        scan_mode = st.selectbox(
            "扫描模式",
            options=["全市场快速扫描", "精选扫描 (前200只活跃股)", "单股深度扫描"],
            index=0,
        )

    with col_ctrl3:
        if scan_mode == "单股深度扫描":
            search_code = st.text_input("股票代码", placeholder="例: 000001", max_chars=6)
        else:
            lookback = st.selectbox("回看天数", options=[30, 60, 90, 120], index=1)

    # 执行扫描
    if st.button("🔍 开始扫描趋势逆转", type="primary", use_container_width=True):
        if scan_mode == "单股深度扫描":
            if search_code:
                _deep_scan_single_stock(search_code)
            else:
                st.warning("请输入股票代码")
        else:
            _batch_scan_reversal(quotes, min_score, scan_mode, lookback)
    else:
        # 默认展示
        _show_reversal_methodology()


def _batch_scan_reversal(quotes: pd.DataFrame, min_score: int,
                          scan_mode: str, lookback_days: int):
    """批量扫描趋势逆转"""
    from analysis.leader_finder import LeaderFinder
    from analysis.trend_reversal import TrendReversalDetector

    with st.spinner(f"正在扫描趋势逆转信号 (阈值 >= {min_score})..."):
        finder = LeaderFinder()
        detector = TrendReversalDetector()

        # 第一步：使用 finder 的方法快速筛选
        filtered = quotes.copy()
        if scan_mode == "精选扫描 (前200只活跃股)":
            if "amount" in filtered.columns:
                filtered = filtered.nlargest(200, "amount")
            elif "turnover" in filtered.columns:
                filtered = filtered.nlargest(200, "turnover")

        # 筛选初步候选 (涨跌幅 3%~9.5%)
        candidates = filtered[
            (filtered["pct_chg"] > 3) & (filtered["pct_chg"] < 9.5)
        ].copy()

        if candidates.empty:
            st.info("当前没有符合条件的初步候选股")
            return

        st.info(f"初步筛选: {len(candidates)} 只候选股，正在逐一分析...")

        # 进度条
        progress_bar = st.progress(0)
        status_text = st.empty()

        reversal_results = []
        total = len(candidates)

        for idx, (_, stock) in enumerate(candidates.iterrows()):
            code = stock["code"]
            name = stock.get("name", "")

            try:
                result = detector.comprehensive_reversal_scan(code, name)
                if result.get("has_data") and result["reversal_score"] >= min_score:
                    if result["reversal_type"] in ("strong_reversal", "potential_reversal"):
                        reversal_results.append(result)
            except Exception:
                pass

            if (idx + 1) % 10 == 0:
                progress_bar.progress((idx + 1) / total)
                status_text.text(f"已分析 {idx + 1}/{total}... 发现 {len(reversal_results)} 只")

        progress_bar.progress(1.0)
        status_text.text(f"扫描完成! 发现 {len(reversal_results)} 只趋势逆转候选")

        # 展示结果
        if reversal_results:
            _display_reversal_results(reversal_results)
        else:
            st.info(f"未发现评分 >= {min_score} 的趋势逆转股票")


def _deep_scan_single_stock(code: str):
    """对单只股票进行深度扫描"""
    from analysis.trend_reversal import TrendReversalDetector
    from data.market_data import MarketDataCollector

    detector = TrendReversalDetector()
    market = MarketDataCollector()

    with st.spinner(f"正在深度分析 {code}..."):
        # 获取股票名称
        name = ""
        try:
            stock_list = market.get_a_share_list()
            match = stock_list[stock_list["code"] == code]
            if not match.empty:
                name = match.iloc[0]["name"]
        except Exception:
            pass

        result = detector.comprehensive_reversal_scan(code, name)

        if not result.get("has_data"):
            st.error(f"无法获取 {code} 的行情数据（可能停牌或代码错误）")
            return

        # 展示详细结果
        _display_single_reversal_detail(result, code, name)


def _display_single_reversal_detail(result: Dict, code: str, name: str):
    """展示单股深度扫描详细结果"""
    st.markdown(f"### {name} ({code}) 深度分析")

    reversal_type = result.get("reversal_type", "no_signal")
    reversal_score = result.get("reversal_score", 0)

    type_labels = {
        "strong_reversal": ("强逆转信号", "#E63946", "多个技术指标共振，底部确认概率高"),
        "potential_reversal": ("潜在逆转信号", "#FF8C00", "部分指标发出逆转信号，关注确认"),
        "no_signal": ("无明显信号", "#888888", "暂无明确的趋势逆转信号"),
        "potential_top": ("潜在顶部信号", "#4169E1", "部分指标提示顶部风险"),
        "strong_top_signal": ("强顶部信号", "#228B22", "多个指标共振提示顶部风险"),
    }

    label, color, desc = type_labels.get(reversal_type, ("未知", "#999", ""))

    # 主指标卡片
    st.markdown(f"""
    <div style="
        border: 2px solid {color};
        border-radius: 12px;
        padding: 20px;
        margin: 16px 0;
        text-align: center;
        background: #fafafa;
    ">
        <div style="font-size: 14px; color: #999;">逆转评分</div>
        <div style="font-size: 48px; font-weight: 700; color: {color};">{reversal_score}</div>
        <div style="font-size: 18px; color: {color}; font-weight: 600;">{label}</div>
        <div style="font-size: 13px; color: #666; margin-top: 8px;">{desc}</div>
    </div>
    """, unsafe_allow_html=True)

    # 技术指标详情
    col1, col2, col3, col4 = st.columns(4)

    macd = result.get("macd_divergence", {})
    volume = result.get("volume_breakout", {})
    ma = result.get("ma_convergence", {})
    rsi = result.get("rsi_signal", {})
    pattern = result.get("bottom_pattern", {})

    with col1:
        st.metric("MACD背离", macd.get("type", "none"),
                  delta=f"强度: {macd.get('strength', 0)}")

    with col2:
        st.metric("放量突破", "是" if volume.get("breakout") else "否",
                  delta=f"比率: {volume.get('ratio', 1.0)}")

    with col3:
        st.metric("均线粘合", "是" if ma.get("converged") else "否",
                  delta=f"方向: {ma.get('direction', 'none')}")

    with col4:
        st.metric("RSI信号", rsi.get("signal", "none"),
                  delta=f"RSI: {rsi.get('value', 50)}")

    # 底部形态
    st.markdown(f"**底部形态**: {pattern.get('pattern', 'none')} "
                f"(置信度: {pattern.get('confidence', 0)})")

    # 信号列表
    signals = result.get("signals", [])
    if signals:
        st.markdown("**触发信号**:")
        for s in signals:
            st.markdown(f"- {s}")

    # K线图
    _plot_kline_with_signals(code, name)


def _display_reversal_results(results: List[Dict]):
    """展示批量扫描结果"""
    st.markdown(f"### 趋势逆转候选 ({len(results)} 只)")

    # 构建 DataFrame
    rows = []
    for r in results:
        rows.append({
            "代码": r.get("code", ""),
            "名称": r.get("name", ""),
            "逆转评分": r.get("reversal_score", 0),
            "逆转类型": {
                "strong_reversal": "强逆转",
                "potential_reversal": "潜在逆转",
            }.get(r.get("reversal_type", ""), r.get("reversal_type", "")),
            "触发信号": " | ".join(r.get("signals", [])[:4]),
            "最新价": r.get("latest_close", 0),
            "今日涨幅": f"{r.get('pct_chg_today', 0):+.2f}%",
        })

    df = pd.DataFrame(rows).sort_values("逆转评分", ascending=False)

    # 应用条件格式
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(400, 35 * len(df) + 38),
        column_config={
            "逆转评分": st.column_config.ProgressColumn(
                "逆转评分",
                min_value=0,
                max_value=100,
                format="%d",
            ),
        },
    )

    # 可视化
    if len(df) > 0:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=df["名称"].head(15),
            x=df["逆转评分"].head(15),
            orientation="h",
            marker=dict(
                color=df["逆转评分"].head(15),
                colorscale=[
                    [0, "#999"],
                    [0.4, "#FF8C00"],
                    [0.6, "#FF6600"],
                    [1.0, "#E63946"],
                ],
                showscale=True,
                colorbar=dict(title="评分", thickness=15),
            ),
            text=df["逆转评分"].head(15),
            textposition="outside",
        ))

        fig.update_layout(
            title="趋势逆转评分 Top 15",
            height=400,
            margin=dict(l=20, r=20, t=40, b=20),
            showlegend=False,
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # 点击查看详情
    if len(df) > 0:
        selected = st.selectbox("选择股票查看详情", df["代码"].tolist(),
                                 format_func=lambda x: f"{x} - {df[df['代码']==x]['名称'].iloc[0]}")
        if selected:
            _deep_scan_single_stock(selected)


def _plot_kline_with_signals(code: str, name: str):
    """绘制K线图并标注信号"""
    from data.market_data import MarketDataCollector

    market = MarketDataCollector()
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")

    kline = market.get_daily_kline(code, start_date, end_date)
    if kline.empty:
        return

    kline = market.calculate_technical_indicators(kline)
    recent = kline.tail(60)

    fig = go.Figure()

    # K线
    fig.add_trace(go.Candlestick(
        x=recent["date"],
        open=recent["open"],
        high=recent["high"],
        low=recent["low"],
        close=recent["close"],
        name="K线",
        increasing_line_color="#FF3333",
        decreasing_line_color="#33AA33",
    ))

    # 均线
    for ma_name, color in [("ma5", "#FF6600"), ("ma20", "#4169E1"), ("ma60", "#228B22")]:
        if ma_name in recent.columns:
            fig.add_trace(go.Scatter(
                x=recent["date"],
                y=recent[ma_name],
                mode="lines",
                name=ma_name.upper(),
                line=dict(color=color, width=1.5, dash="dot"),
                opacity=0.7,
            ))

    fig.update_layout(
        title=f"{name} ({code}) - 近期走势",
        xaxis_title="日期",
        yaxis_title="价格",
        height=450,
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis_rangeslider_visible=False,
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)

    # MACD 图表
    if "macd" in recent.columns:
        fig_macd = go.Figure()
        fig_macd.add_trace(go.Bar(
            x=recent["date"],
            y=recent["macd_hist"],
            name="MACD柱",
            marker_color=["#FF3333" if v > 0 else "#33AA33" for v in recent["macd_hist"]],
            opacity=0.6,
        ))
        fig_macd.add_trace(go.Scatter(
            x=recent["date"],
            y=recent["macd"],
            mode="lines",
            name="MACD",
            line=dict(color="#FF6600", width=1.5),
        ))
        fig_macd.add_trace(go.Scatter(
            x=recent["date"],
            y=recent["macd_signal"],
            mode="lines",
            name="Signal",
            line=dict(color="#4169E1", width=1.5),
        ))
        fig_macd.update_layout(
            title="MACD",
            height=250,
            margin=dict(l=20, r=20, t=40, b=20),
            template="plotly_white",
        )
        st.plotly_chart(fig_macd, use_container_width=True)


def _show_reversal_methodology():
    """展示趋势逆转方法论"""
    st.markdown("### 趋势逆转识别方法")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        #### 底部逆转信号
        - **MACD底背离**: 股价新低, MACD 未创新低
        - **放量突破**: 成交量放大至 20 日均量 1.5 倍以上
        - **均线粘合突破**: 多均线收敛后向上发散
        - **RSI超卖反弹**: RSI < 30 后回升
        - **底部形态**: 晨星、V型反转、双底
        - **上穿MA20/MA60**: 价格突破关键均线
        """)

    with col2:
        st.markdown("""
        #### 顶部逆转信号
        - **MACD顶背离**: 股价新高, MACD 未创新高
        - **放量滞涨**: 成交量放大但涨幅缩小
        - **均线粘合向下**: 多均线收敛后向下发散
        - **RSI超买回落**: RSI > 70 后回落
        - **高位放量长阴**: 大阴线伴随巨量

        #### 评分规则
        - >= 60: 强逆转信号
        - 30~59: 潜在逆转信号
        - 0~29: 无明显信号
        - < 0: 顶部风险信号
        """)