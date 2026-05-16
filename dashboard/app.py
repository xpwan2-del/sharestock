"""
A股量化分析系统 - 交互式前端看板
技术栈: Streamlit + Plotly
"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
from datetime import datetime

# 页面配置
st.set_page_config(
    page_title="A股量化分析看板",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 导入各组件模块
from dashboard.components.market_overview import render_market_overview
from dashboard.components.industry_heatmap import render_industry_heatmap
from dashboard.components.leader_display import render_leader_display
from dashboard.components.trend_reversal import render_trend_reversal
from dashboard.components.dragon_tiger import render_dragon_tiger
from dashboard.components.announcement_scan import render_announcement_scan
from dashboard.components.neural_analysis import render_neural_analysis
from dashboard.components.daily_report_viewer import render_daily_report_viewer
from dashboard.utils import SessionCache

# ---------- 自定义 CSS ----------
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css(PROJECT_ROOT / "dashboard" / "style.css")


def init_session_state():
    """初始化 Session State"""
    if "cache" not in st.session_state:
        st.session_state.cache = SessionCache()
    if "refreshed_at" not in st.session_state:
        st.session_state.refreshed_at = None
    if "auto_refresh" not in st.session_state:
        st.session_state.auto_refresh = False


def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.markdown('<div style="font-size:20px; font-weight:800; color:#f8fafc; margin-bottom:1rem;">📊 ALPHA TERMINAL</div>', unsafe_allow_html=True)
        st.markdown("---")

        # 导航菜单
        st.markdown('<div style="font-size:13px; color:#94a3b8; margin-bottom:0.5rem; letter-spacing:0.1em;">MODULES</div>', unsafe_allow_html=True)
        page = st.radio(
            "选择模块",
            options=[
                "📈 市场概览",
                "🔥 产业链热力图",
                "👑 龙头识别",
                "🔄 趋势逆转",
                "🐉 龙虎榜分析",
                "📋 公告扫描",
                "🧠 神经网络分析",
                "📋 每日报告",
            ],
            index=0,
            label_visibility="collapsed",
        )

        st.markdown("---")

        # 刷新控制
        st.markdown('<div style="font-size:13px; color:#94a3b8; margin-bottom:0.5rem; letter-spacing:0.1em;">SYSTEM CONTROL</div>', unsafe_allow_html=True)
        auto_refresh = st.checkbox("自动刷新 (60s)", value=st.session_state.auto_refresh)
        st.session_state.auto_refresh = auto_refresh

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 刷新", use_container_width=True):
                st.session_state.cache.clear()
                st.session_state.refreshed_at = datetime.now()
                st.rerun()

        with col2:
            if st.button("🗑️ 清理", use_container_width=True):
                st.session_state.cache.clear()
                st.rerun()

        # 显示上次刷新时间
        if st.session_state.refreshed_at:
            st.caption(f"SYNC AT: {st.session_state.refreshed_at.strftime('%H:%M:%S')}")

        # 自动刷新逻辑：不阻塞主线程，到期后下一次渲染时刷新
        if auto_refresh:
            now = datetime.now()
            if not st.session_state.refreshed_at:
                st.session_state.refreshed_at = now
            elif (now - st.session_state.refreshed_at).total_seconds() >= 60:
                st.session_state.cache.clear()
                st.session_state.refreshed_at = now
                st.rerun()

        st.markdown("---")
        st.caption(f"FEED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return page


def main():
    """主入口"""
    init_session_state()
    page = render_sidebar()

    # 页面标题
    st.markdown(
        f'''
        <div class="dashboard-shell">
            <div class="dashboard-title">A股量化交易终端</div>
            <div class="dashboard-subtitle">DATA-DRIVEN ALPHA TERMINAL · QUANT DECISION ENGINE · {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
            <div class="terminal-pill"><span class="terminal-dot"></span>REALTIME FEED ACTIVE</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    # 路由到对应模块
    if "市场概览" in page:
        render_market_overview(st.session_state.cache)
    elif "产业链热力图" in page:
        render_industry_heatmap(st.session_state.cache)
    elif "龙头识别" in page:
        render_leader_display(st.session_state.cache)
    elif "趋势逆转" in page:
        render_trend_reversal(st.session_state.cache)
    elif "龙虎榜分析" in page:
        render_dragon_tiger(st.session_state.cache)
    elif "公告扫描" in page:
        render_announcement_scan(st.session_state.cache)
    elif "每日报告" in page:
        render_daily_report_viewer(st.session_state.cache)
    elif "神经网络分析" in page:
        render_neural_analysis(st.session_state.cache)


if __name__ == "__main__":
    main()