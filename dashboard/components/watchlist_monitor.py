from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.trade_signal_engine import TradeSignalEngine
from data.watchlist_store import WatchlistStore
from dashboard.utils import format_pct


SIGNAL_LABELS = {
    "BUY": "买入提示",
    "SELL": "卖出提示",
    "TAKE_PROFIT": "止盈提醒",
    "STOP_LOSS": "止损提醒",
    "WATCH": "观察",
    "ERROR": "分析失败",
}


@st.cache_resource
def _get_watchlist_store():
    return WatchlistStore()


def render_watchlist_monitor(cache):
    st.markdown('''
    <div class="module-hero">
        <div class="module-kicker">WATCHLIST MONITOR</div>
        <div class="module-title">自选股监控与站内提醒</div>
        <div class="module-subtitle">自选股管理 · 批量买卖点扫描 · 强信号提醒 · 风险提示</div>
    </div>
    ''', unsafe_allow_html=True)

    st.warning("自选股监控用于辅助发现量化信号，不构成任何投资建议。")
    store = _get_watchlist_store()
    unread = store.unread_count()
    tab_watchlist, tab_alerts = st.tabs([f"自选股监控", f"站内提醒（{unread}）"])
    with tab_watchlist:
        _render_watchlist_tab(store)
    with tab_alerts:
        _render_alerts_tab(store)


def _render_watchlist_tab(store: WatchlistStore):
    with st.expander("添加 / 更新自选股", expanded=True):
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1.4])
        with col1:
            code = st.text_input("代码", value="000001", max_chars=6, key="watch_code")
        with col2:
            name = st.text_input("名称", value="平安银行", key="watch_name")
        with col3:
            group_name = st.text_input("分组", value="默认", key="watch_group")
        with col4:
            note = st.text_input("备注", value="", key="watch_note")
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("加入自选股", type="primary", use_container_width=True):
                store.add_stock(code, name=name, group_name=group_name, note=note)
                st.success(f"已加入/更新 {code.zfill(6)}")
        with c2:
            if st.button("删除该股票", use_container_width=True):
                store.remove_stock(code)
                st.info(f"已删除 {code.zfill(6)}")

    watchlist = store.list_watchlist()
    if watchlist.empty:
        st.info("暂无自选股，先添加几只股票，例如 000001、600519、300750。")
        return

    st.markdown("### 我的自选股")
    st.dataframe(watchlist, use_container_width=True, hide_index=True)

    if st.button("刷新自选股买卖点监控", type="primary", use_container_width=True):
        engine = TradeSignalEngine()
        with st.spinner("正在批量扫描自选股买卖点、胜率和风险..."):
            snapshot = engine.build_watchlist_snapshot(watchlist)
            for alert in engine.build_alerts_from_snapshot(snapshot):
                store.create_alert(alert)
        if snapshot.empty:
            st.warning("本次未生成监控结果")
            return
        _display_watchlist_snapshot(snapshot)
    else:
        st.info("点击刷新后，将对所有自选股生成当前信号、综合评分、历史10日胜率和行动建议。")


def _display_watchlist_snapshot(snapshot: pd.DataFrame):
    c1, c2, c3, c4 = st.columns(4)
    buy_count = int((snapshot["signal_type"] == "BUY").sum())
    risk_count = int(snapshot["signal_type"].isin(["SELL", "STOP_LOSS"]).sum())
    avg_score = snapshot["score"].mean() if "score" in snapshot else 0
    high_risk = int(snapshot["risk_level"].isin(["高", "中高"]).sum())
    c1.metric("买入提示", buy_count)
    c2.metric("卖出/止损", risk_count)
    c3.metric("平均评分", f"{avg_score:.1f}")
    c4.metric("中高风险", high_risk)

    display = snapshot.copy()
    display["signal_type"] = display["signal_type"].map(lambda x: SIGNAL_LABELS.get(x, x))
    display["win_rate_10d"] = display["win_rate_10d"].apply(lambda x: format_pct(x) if pd.notna(x) else "样本不足")
    display["avg_return_10d"] = display["avg_return_10d"].apply(lambda x: format_pct(x) if pd.notna(x) else "-")
    if "trade_date" in display.columns:
        display["trade_date"] = pd.to_datetime(display["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    display = display.rename(columns={
        "code": "代码",
        "name": "名称",
        "group_name": "分组",
        "current_price": "现价",
        "trade_date": "日期",
        "signal_type": "信号",
        "strategy_name": "策略",
        "strength": "强度",
        "score": "综合分",
        "risk_level": "风险",
        "suggestion": "行动建议",
        "reason": "原因",
        "win_rate_10d": "10日胜率",
        "avg_return_10d": "10日均收益",
        "sample_count_10d": "样本数",
    })
    st.dataframe(display, use_container_width=True, hide_index=True)


def _render_alerts_tab(store: WatchlistStore):
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("全部标记已读", use_container_width=True):
            store.mark_read()
            st.success("已全部标记已读")
    with col2:
        st.metric("未读提醒", store.unread_count())

    alerts = store.list_alerts(limit=100)
    if alerts.empty:
        st.info("暂无提醒。刷新自选股监控后，强买入、卖出、止盈止损会自动生成站内提醒。")
        return

    for _, alert in alerts.iterrows():
        severity = alert.get("severity", "medium")
        color = "#dc2626" if severity == "high" else "#f97316"
        read_badge = "已读" if int(alert.get("is_read", 0)) else "未读"
        with st.container(border=True):
            st.markdown(f"<b style='color:{color};'>{alert.get('title')}</b> · {read_badge} · {alert.get('created_at')}", unsafe_allow_html=True)
            st.write(alert.get("content"))
            if st.button("标记已读", key=f"read_{alert.get('id')}"):
                store.mark_read(int(alert.get("id")))
                st.success("已标记已读")
