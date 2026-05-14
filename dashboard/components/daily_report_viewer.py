from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from config.settings import DATA_DIR


@dataclass(frozen=True)
class ReportRecord:
    date: str
    path: Path
    size_kb: float
    modified_at: str


def _report_root() -> Path:
    return DATA_DIR / "reports"


def _list_report_records() -> list[ReportRecord]:
    root = _report_root()
    if not root.exists():
        return []
    records = []
    for report_path in root.rglob("daily_report.md"):
        if not report_path.is_file():
            continue
        report_date = report_path.parent.name
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
            continue
        stat = report_path.stat()
        records.append(
            ReportRecord(
                date=report_date,
                path=report_path,
                size_kb=stat.st_size / 1024,
                modified_at=__import__("datetime").datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
    return sorted(records, key=lambda item: item.date, reverse=True)


def _extract_section(content: str, title: str) -> str:
    pattern = rf"##\s+{re.escape(title)}[\s\S]*?(?=\n##\s+|\Z)"
    match = re.search(pattern, content)
    return match.group(0).strip() if match else ""


def _extract_meta(content: str) -> dict[str, str]:
    meta = {}
    for line in content.splitlines()[:12]:
        date_match = re.match(r"\*\*日期\*\*:\s*(.+)", line)
        time_match = re.match(r"\*\*生成时间\*\*:\s*(.+)", line)
        if date_match:
            meta["date"] = date_match.group(1).strip()
        if time_match:
            meta["time"] = time_match.group(1).strip()
    return meta


def _metric_from_line(content: str, label: str, default: str = "--") -> str:
    for line in content.splitlines():
        if line.strip().startswith(f"- {label}"):
            return line.split(":", 1)[-1].strip() if ":" in line else line.strip()
    return default


def _render_terminal_card(title: str, body: str):
    st.markdown(
        f'''
        <div style="border:1px solid rgba(56,189,248,0.22); border-radius:16px; padding:16px; background:linear-gradient(145deg, rgba(15,23,42,0.92), rgba(2,6,23,0.96)); box-shadow:0 0 24px rgba(14,165,233,0.08); margin-bottom:14px;">
            <div style="font-size:12px; color:#38bdf8; letter-spacing:0.18em; font-weight:800; margin-bottom:10px;">{title}</div>
            <div style="color:#cbd5e1; font-size:13px; line-height:1.7;">{body}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def render_daily_report_viewer(cache=None):
    st.markdown('''
    <div class="module-hero">
        <div class="module-kicker">DAILY REPORT</div>
        <div class="module-title">每日报告中心</div>
        <div class="module-subtitle">历史日报 · 交易复盘 · 模型预测 · 复合信号 · 盘后作战终端</div>
    </div>
    ''', unsafe_allow_html=True)

    records = _list_report_records()
    if not records:
        st.warning("当前还没有生成日报，请先运行 daily 模式。")
        return

    left_col, main_col = st.columns([0.28, 0.72], gap="large")

    with left_col:
        st.markdown("### REPORT INDEX")
        selected_date = st.selectbox(
            "选择报告日期",
            options=[item.date for item in records],
            index=0,
            label_visibility="collapsed",
        )
        selected = next(item for item in records if item.date == selected_date)
        try:
            content = selected.path.read_text(encoding="utf-8")
        except Exception as e:
            st.error(f"读取日报失败: {e}")
            return

        meta = _extract_meta(content)
        st.metric("报告日期", meta.get("date", selected.date))
        st.metric("生成时间", meta.get("time", "--"))
        st.metric("报告大小", f"{selected.size_kb:.1f} KB")
        st.caption(f"LAST WRITE: {selected.modified_at}")
        st.caption(f"PATH: {selected.path}")

        st.markdown("---")
        st.markdown("### MARKET SNAPSHOT")
        m1, m2 = st.columns(2)
        with m1:
            st.metric("上涨", _metric_from_line(content, "上涨"))
            st.metric("涨停", _metric_from_line(content, "涨停"))
        with m2:
            st.metric("下跌", _metric_from_line(content, "下跌"))
            st.metric("跌停", _metric_from_line(content, "跌停"))
        st.metric("平均涨跌", _metric_from_line(content, "平均涨跌"))

        st.markdown("---")
        st.markdown("### HISTORY")
        for item in records[:12]:
            marker = "●" if item.date == selected_date else "○"
            st.caption(f"{marker} {item.date} · {item.size_kb:.1f} KB")

    with main_col:
        top_left, top_right = st.columns([0.58, 0.42], gap="medium")
        with top_left:
            sentiment = _extract_section(content, "二、情绪信号")
            if sentiment:
                st.markdown(sentiment)
            else:
                _render_terminal_card("SENTIMENT", "暂无情绪信号章节")
        with top_right:
            model_signals = _extract_section(content, "四、模型预测与复合信号")
            if model_signals:
                st.markdown(model_signals)
            else:
                _render_terminal_card("MODEL SIGNALS", "暂无模型预测与复合信号章节")

        st.markdown("---")
        tab_summary, tab_full = st.tabs(["终端分栏复盘", "完整 Markdown 报告"])
        with tab_summary:
            market = _extract_section(content, "一、市场概览")
            col_a, col_b = st.columns(2, gap="medium")
            with col_a:
                if market:
                    st.markdown(market)
                else:
                    _render_terminal_card("MARKET BREADTH", "暂无市场概览章节")
            with col_b:
                if model_signals:
                    st.markdown(model_signals)
                else:
                    _render_terminal_card("COMPOUND SIGNAL", "暂无复合信号章节")
        with tab_full:
            st.markdown(content)
