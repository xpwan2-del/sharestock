import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.smart_money_strategies import CUSTOM_FIELD_LABELS, get_builtin_strategy_name_map, get_builtin_strategy_profiles
from analysis.trade_signal_engine import TradeSignalEngine
from data.watchlist_store import WatchlistStore
from dashboard.components.watchlist_monitor import render_watchlist_monitor
from dashboard.utils import _load_realtime_quotes, format_pct


def render_trade_signals(cache):
    st.markdown('''
    <div class="module-hero">
        <div class="module-kicker">SIGNAL & WIN RATE</div>
        <div class="module-title">买卖点提醒与历史胜率</div>
        <div class="module-subtitle">买入信号 · 卖出信号 · 止盈止损 · 历史回测胜率 · 风险提示</div>
    </div>
    ''', unsafe_allow_html=True)

    st.warning("量化买卖点仅为历史数据和规则模型生成的参考信号，不构成投资建议。请结合风险承受能力独立判断。")

    tab_single, tab_market, tab_watchlist, tab_strategy = st.tabs(["单股买卖点", "市场信号雷达", "自选股监控", "策略配置"])
    with tab_single:
        _render_single_stock(cache)
    with tab_market:
        _render_market_scan(cache)
    with tab_watchlist:
        render_watchlist_monitor(cache)
    with tab_strategy:
        _render_strategy_config()


def _render_single_stock(cache):
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        code = st.text_input("股票代码", value="000001", max_chars=6, help="输入6位A股代码，例如 000001、600519")
    with col2:
        name = st.text_input("股票名称", value="", help="可选，仅用于页面显示")
    with col3:
        years = st.selectbox("回测区间", options=[1, 2, 3], index=1, help="用最近几年历史数据统计信号胜率")

    if st.button("生成买卖点与胜率", type="primary", use_container_width=True):
        engine = TradeSignalEngine()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * years)
        with st.spinner(f"正在分析 {code} 的买卖点、胜率和风险..."):
            result = engine.analyze_stock(
                code=code.strip().zfill(6),
                name=name.strip(),
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
            )
        if not result.get("has_data"):
            st.error(result.get("message", "暂无可用数据"))
            return
        _display_signal_summary(result)
        _display_market_style(result)
        _display_signal_chart(result)
        _display_signal_table(result)
        _display_performance(result)
    else:
        st.info("输入股票代码后点击按钮，系统会生成买卖点、止盈止损和历史胜率。")


def _render_market_scan(cache):
    col1, col2 = st.columns([1, 1])
    with col1:
        scan_limit = st.slider("扫描活跃股票数量", min_value=20, max_value=150, value=60, step=10)
    with col2:
        min_strength = st.slider("最低信号强度", min_value=1, max_value=5, value=3, step=1)

    if st.button("扫描市场买卖点", type="primary", use_container_width=True):
        with st.spinner("正在加载实时行情..."):
            quotes = cache.get("quotes", _load_realtime_quotes)
        if quotes.empty:
            st.warning("暂无实时行情数据")
            return
        engine = TradeSignalEngine()
        with st.spinner("正在扫描市场买卖点和历史胜率..."):
            signals = engine.scan_market(quotes, limit=scan_limit, min_strength=min_strength)
        if signals.empty:
            st.info("当前未发现满足条件的买卖点信号")
            return
        display = signals.copy()
        display["win_rate_10d"] = display["win_rate_10d"].apply(lambda x: format_pct(x) if pd.notna(x) else "样本不足")
        display["avg_return_10d"] = display["avg_return_10d"].apply(lambda x: format_pct(x) if pd.notna(x) else "-")
        display = display.rename(columns={
            "code": "代码",
            "name": "名称",
            "signal_type": "信号",
            "strategy_name": "策略",
            "strength": "强度",
            "style_group": "风格归属",
            "style_weight": "风格权重",
            "weighted_strength": "加权强度",
            "market_style": "当前风格",
            "market_regime": "风格阶段",
            "score": "综合分",
            "risk_level": "风险",
            "suggestion": "行动建议",
            "price": "触发价",
            "date": "触发日期",
            "reason": "原因",
            "win_rate_10d": "10日胜率",
            "avg_return_10d": "10日均收益",
            "sample_count_10d": "样本数",
            "current_pct_chg": "今日涨跌幅",
        })
        st.dataframe(display, use_container_width=True, hide_index=True)


def _display_signal_summary(result):
    latest = result.get("latest_signal")
    latest_buy = result.get("latest_buy")
    latest_sell = result.get("latest_sell")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("当前价格", f"{result.get('current_price', 0):.2f}")
    with col2:
        st.metric("最新信号", _signal_label(latest.get("signal_type")) if latest else "暂无")
    with col3:
        st.metric("最新买点", _format_signal_date(latest_buy))
    with col4:
        st.metric("最新卖点", _format_signal_date(latest_sell))

    if latest:
        color = _signal_color(latest.get("signal_type"))
        style_group = latest.get("style_group", "未知")
        style_weight = float(latest.get("style_weight", 1) or 1)
        weighted_strength = float(latest.get("weighted_strength", latest.get("strength", 0)) or 0)
        st.markdown(f'''
        <div style="border-left:6px solid {color}; padding:16px; background:#f8fafc; border-radius:10px; margin:12px 0;">
            <div style="font-size:20px; font-weight:800; color:{color};">{_signal_label(latest.get("signal_type"))} · {latest.get("strategy_name")} · 强度 {latest.get("strength")}/5 · 加权 {weighted_strength:.2f}</div>
            <div style="margin-top:8px; color:#334155;">风格归属：{style_group} ｜ 动态权重：{style_weight:.2f} ｜ 触发价：{latest.get("price", 0):.2f} ｜ 触发日期：{pd.to_datetime(latest.get("date")).strftime("%Y-%m-%d")}</div>
            <div style="margin-top:8px; color:#334155;">触发原因：{latest.get("reason")}</div>
            <div style="margin-top:8px; color:#b91c1c;">风险提示：{latest.get("risk")}</div>
        </div>
        ''', unsafe_allow_html=True)


def _display_market_style(result):
    style = result.get("market_style") or {}
    if not style:
        return
    st.markdown("### 市场风格自学习")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("主导风格", style.get("dominant_style", "未知"))
    with col2:
        st.metric("风格阶段", style.get("regime", "未知"))
    with col3:
        st.metric("综合评分", _format_style_score(style))
    with col4:
        st.metric("分析样本", f"{(style.get('metrics') or {}).get('recent_days', 0)}日")
    st.info(style.get("advice", "暂无风格建议"))

    score_rows = []
    style_scores = style.get("style_scores") or {}
    price_scores = style.get("price_style_scores") or {}
    perf_scores = style.get("performance_style_scores") or {}
    for name, score in style_scores.items():
        score_rows.append({
            "风格": name,
            "综合分": score,
            "价格结构分": price_scores.get(name),
            "历史胜率分": perf_scores.get(name),
        })
    if score_rows:
        st.dataframe(pd.DataFrame(score_rows).sort_values("综合分", ascending=False), use_container_width=True, hide_index=True)

    weights = style.get("strategy_weights") or {}
    if weights:
        names = {
            "ma_cross_v1": "均线金叉/死叉",
            "macd_cross_v1": "MACD金叉/死叉",
            "rsi_rebound_v1": "RSI超卖反弹",
            "breakout_v1": "放量突破",
            "risk_control_v1": "止盈止损",
        }
        names.update(get_builtin_strategy_name_map())
        weight_rows = [{"策略": names.get(strategy_id, strategy_id), "策略ID": strategy_id, "动态权重": weight} for strategy_id, weight in weights.items()]
        with st.expander("查看策略动态权重", expanded=False):
            st.dataframe(pd.DataFrame(weight_rows).sort_values("动态权重", ascending=False), use_container_width=True, hide_index=True)



def _display_signal_chart(result):
    df = result.get("data")
    signals = result.get("signals")
    if df is None or df.empty:
        return
    recent = df.tail(180)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=recent["date"],
        open=recent["open"],
        high=recent["high"],
        low=recent["low"],
        close=recent["close"],
        name="K线",
    ))
    if "ma5" in recent.columns:
        fig.add_trace(go.Scatter(x=recent["date"], y=recent["ma5"], mode="lines", name="MA5"))
    if "ma20" in recent.columns:
        fig.add_trace(go.Scatter(x=recent["date"], y=recent["ma20"], mode="lines", name="MA20"))
    if signals is not None and not signals.empty:
        visible = signals[signals["date"] >= recent["date"].min()]
        for signal_type, marker, color in [
            ("BUY", "triangle-up", "#dc2626"),
            ("SELL", "triangle-down", "#16a34a"),
            ("TAKE_PROFIT", "star", "#f97316"),
            ("STOP_LOSS", "x", "#1d4ed8"),
        ]:
            part = visible[visible["signal_type"] == signal_type]
            if not part.empty:
                fig.add_trace(go.Scatter(
                    x=part["date"],
                    y=part["price"],
                    mode="markers",
                    name=_signal_label(signal_type),
                    marker=dict(symbol=marker, size=13, color=color),
                    text=part["reason"],
                    hovertemplate="%{x}<br>%{y:.2f}<br>%{text}<extra></extra>",
                ))
    fig.update_layout(height=520, xaxis_rangeslider_visible=False, template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)


def _display_signal_table(result):
    signals = result.get("signals")
    if signals is None or signals.empty:
        st.info("该区间内暂无买卖点信号")
        return
    st.markdown("### 最近买卖点记录")
    display = signals.tail(30).sort_values("date", ascending=False).copy()
    for days in [3, 5, 10, 20]:
        col = f"return_{days}d"
        if col in display.columns:
            display[col] = display[col].apply(lambda x: format_pct(x) if pd.notna(x) else "待验证")
    display["signal_type"] = display["signal_type"].apply(_signal_label)
    display["date"] = pd.to_datetime(display["date"]).dt.strftime("%Y-%m-%d")
    columns = ["date", "signal_type", "strategy_name", "strength", "price", "reason", "return_3d", "return_5d", "return_10d", "return_20d"]
    optional_columns = ["style_group", "style_weight", "weighted_strength"]
    columns = columns[:4] + [item for item in optional_columns if item in display.columns] + columns[4:]
    display = display[columns]
    display = display.rename(columns={
        "date": "日期",
        "signal_type": "信号",
        "strategy_name": "策略",
        "strength": "强度",
        "style_group": "风格归属",
        "style_weight": "风格权重",
        "weighted_strength": "加权强度",
        "price": "触发价",
        "reason": "原因",
        "return_3d": "3日收益",
        "return_5d": "5日收益",
        "return_10d": "10日收益",
        "return_20d": "20日收益",
    })
    st.dataframe(display, use_container_width=True, hide_index=True)


def _display_performance(result):
    performance = result.get("performance", {})
    if not performance:
        st.info("历史信号样本不足，暂时无法统计稳定胜率")
        return
    st.markdown("### 策略历史胜率")
    rows = []
    names = {
        "ma_cross_v1": "均线金叉/死叉",
        "macd_cross_v1": "MACD金叉/死叉",
        "rsi_rebound_v1": "RSI超卖反弹",
        "breakout_v1": "放量突破",
        "risk_control_v1": "止盈止损",
    }
    names.update(get_builtin_strategy_name_map())
    for strategy_id, periods in performance.items():
        for days, stat in periods.items():
            rows.append({
                "策略": names.get(strategy_id, strategy_id),
                "持有周期": f"{days}日",
                "样本数": stat.get("sample_count"),
                "胜率": format_pct(stat.get("win_rate")),
                "平均收益": format_pct(stat.get("avg_return")),
                "中位收益": format_pct(stat.get("median_return")),
                "最大收益": format_pct(stat.get("max_return")),
                "最大亏损": format_pct(stat.get("max_loss")),
                "盈亏比": f"{stat.get('profit_loss_ratio'):.2f}" if pd.notna(stat.get("profit_loss_ratio")) else "-",
                "可靠性": _sample_reliability(stat.get("sample_count", 0)),
            })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _signal_label(signal_type):
    return {
        "BUY": "买入提示",
        "SELL": "卖出提示",
        "TAKE_PROFIT": "止盈提醒",
        "STOP_LOSS": "止损提醒",
    }.get(signal_type, signal_type or "未知")


def _render_strategy_config():
    st.markdown("### 游资/机构/量化内置策略")
    st.info("系统已把首板、接力、弱转强、龙头首阴、情绪修复、量化动量、机构游资合力、箱体突破回踩、主线趋势波段、超跌均值回归、顶部背离、趋势破位等策略纳入买卖点和胜率统计。")
    profiles = pd.DataFrame(get_builtin_strategy_profiles())
    if not profiles.empty:
        st.dataframe(profiles.rename(columns={
            "strategy_id": "策略ID",
            "name": "策略名称",
            "style": "资金风格",
            "description": "识别逻辑",
            "risk": "风险提示",
        }), use_container_width=True, hide_index=True)

    st.markdown("### 人工策略配置")
    store = WatchlistStore()
    with st.expander("新增 / 更新人工买卖点策略", expanded=True):
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            strategy_id = st.text_input("策略ID", value="custom_volume_breakout", help="用于回测统计的唯一ID，建议英文和下划线")
        with col2:
            name = st.text_input("策略名称", value="人工放量突破")
        with col3:
            signal_type = st.selectbox("信号类型", options=["BUY", "SELL", "TAKE_PROFIT", "STOP_LOSS"], format_func=_signal_label)
        description = st.text_area("策略说明", value="用户自定义条件组合，满足后生成买卖点并统计后续胜率。")
        st.caption("最多配置3个条件，条件之间为 AND 关系。数值说明：涨跌幅单位是百分数，例如 3 表示涨3%；close_vs_ma20 输入 0.02 表示收盘价高于MA20约2%；收盘位置越接近1代表越接近日内高点。")
        conditions = []
        fields = list(CUSTOM_FIELD_LABELS.keys())
        operators = [">=", ">", "<=", "<", "=="]
        defaults = [("pct_chg", ">=", 3.0), ("volume_ratio", ">=", 1.3), ("close_vs_ma20", ">=", 0.0)]
        for idx in range(3):
            c1, c2, c3, c4 = st.columns([1.5, 0.8, 1, 0.8])
            with c1:
                field = st.selectbox(f"条件{idx + 1}字段", options=fields, index=fields.index(defaults[idx][0]), format_func=lambda x: CUSTOM_FIELD_LABELS.get(x, x), key=f"custom_field_{idx}")
            with c2:
                operator = st.selectbox("比较", options=operators, index=operators.index(defaults[idx][1]), key=f"custom_operator_{idx}")
            with c3:
                value = st.number_input("阈值", value=float(defaults[idx][2]), step=0.1, key=f"custom_value_{idx}")
            with c4:
                enabled = st.checkbox("启用", value=idx < 2, key=f"custom_condition_enabled_{idx}")
            if enabled:
                conditions.append({"field": field, "operator": operator, "value": value})
        r1, r2 = st.columns([1, 2])
        with r1:
            strength = st.slider("信号强度", min_value=1, max_value=5, value=3)
        with r2:
            risk = st.text_input("风控提示", value="人工策略需结合仓位和止损，避免单一条件误判")
        enabled_strategy = st.checkbox("策略启用", value=True)
        if st.button("保存人工策略", type="primary", use_container_width=True):
            if not conditions:
                st.warning("至少启用一个条件")
            else:
                store.save_custom_strategy(
                    name=name,
                    strategy_id=strategy_id.strip(),
                    signal_type=signal_type,
                    description=description,
                    conditions=conditions,
                    risk_rule={"strength": strength, "risk": risk},
                    enabled=enabled_strategy,
                )
                st.success("人工策略已保存，后续单股分析、市场雷达和自选股监控会自动纳入该策略。")

    strategies = store.list_custom_strategies()
    st.markdown("### 已保存人工策略")
    if strategies.empty:
        st.info("暂无人工策略，可先创建一个放量突破、回踩均线或止损类策略。")
        return
    display = strategies.copy()
    display["enabled"] = display["enabled"].map(lambda x: "启用" if int(x) else "停用")
    display = display.rename(columns={
        "strategy_id": "策略ID",
        "name": "名称",
        "description": "说明",
        "signal_type": "信号类型",
        "enabled": "状态",
        "conditions_json": "条件",
        "risk_rule_json": "风控",
        "updated_at": "更新时间",
    })
    st.dataframe(display[["策略ID", "名称", "说明", "信号类型", "状态", "条件", "风控", "更新时间"]], use_container_width=True, hide_index=True)
    col_enable, col_delete = st.columns([1, 1])
    selected = st.selectbox("选择要操作的策略", options=strategies["strategy_id"].tolist())
    with col_enable:
        if st.button("切换启用/停用", use_container_width=True):
            row = strategies[strategies["strategy_id"] == selected].iloc[0]
            store.set_custom_strategy_enabled(selected, not bool(int(row.get("enabled", 1))))
            st.success("策略状态已更新")
    with col_delete:
        if st.button("删除策略", use_container_width=True):
            store.delete_custom_strategy(selected)
            st.warning("策略已删除")


def _signal_color(signal_type):
    return {
        "BUY": "#dc2626",
        "SELL": "#16a34a",
        "TAKE_PROFIT": "#f97316",
        "STOP_LOSS": "#1d4ed8",
    }.get(signal_type, "#64748b")


def _format_signal_date(signal):
    if not signal:
        return "暂无"
    return pd.to_datetime(signal.get("date")).strftime("%Y-%m-%d")


def _format_style_score(style):
    dominant = style.get("dominant_style")
    scores = style.get("style_scores") or {}
    score = scores.get(dominant)
    return f"{score:.1f}" if isinstance(score, (int, float)) else "-"



def _sample_reliability(sample_count):
    if sample_count < 10:
        return "样本很少"
    if sample_count < 30:
        return "仅供参考"
    return "相对稳定"
