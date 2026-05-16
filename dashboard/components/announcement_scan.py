"""
个股公告扫描组件 - 重要公告识别、影响分析、情绪判断
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
    format_amount,
)


def render_announcement_scan(cache):
    """渲染公告扫描页面"""
    st.markdown('''
    <div class="module-hero">
        <div class="module-kicker">ANNOUNCEMENT SCAN</div>
        <div class="module-title">个股公告扫描</div>
        <div class="module-subtitle">重要事项识别 · NLP 情绪分析 · 影响力评估 · 快速筛选</div>
    </div>
    ''', unsafe_allow_html=True)

    # ---------- 扫描模式选择 ----------
    mode = st.radio(
        "扫描模式",
        options=["自动扫描（高关注度股票）", "手动指定股票", "批量导入股票列表"],
        horizontal=True,
    )

    st.markdown("---")

    if mode == "自动扫描（高关注度股票）":
        _auto_scan_mode(cache)
    elif mode == "手动指定股票":
        _manual_scan_mode(cache)
    else:
        _batch_import_mode(cache)


def _auto_scan_mode(cache):
    """自动扫描模式：筛选高关注度股票"""
    with st.spinner("正在加载实时行情..."):
        quotes = cache.get("quotes", _load_realtime_quotes)

    if quotes.empty:
        st.warning("暂无行情数据")
        return

    # 筛选高关注度股票
    high_attention = _filter_high_attention_stocks(quotes)

    st.markdown(f"### 自动筛选高关注度股票 ({len(high_attention)} 只)")
    st.caption("条件: 涨跌幅绝对值 > 5% 或 量比 > 2 或 换手率 > 10%")

    if high_attention.empty:
        st.info("当前没有符合条件的高关注度股票")
        return

    # 显示筛选结果
    display_cols = [c for c in ["code", "name", "price", "pct_chg", "volume_ratio", "turnover", "amount"]
                    if c in high_attention.columns]

    display_df = high_attention[display_cols].head(50).copy()
    if "pct_chg" in display_df.columns:
        display_df["涨跌幅"] = display_df["pct_chg"].apply(lambda x: f"{x:+.2f}%")
        display_df.drop(columns=["pct_chg"], inplace=True)
    if "amount" in display_df.columns:
        display_df["成交额"] = display_df["amount"].apply(format_amount)
        display_df.drop(columns=["amount"], inplace=True)

    st.dataframe(display_df, use_container_width=True, hide_index=True, height=300)

    # 手动选择扫描范围
    codes = high_attention["code"].tolist()
    selected_codes = st.multiselect(
        "选择要扫描的股票（默认全选前20只）",
        options=codes,
        default=codes[:20],
    )

    if st.button("🔍 开始扫描公告", type="primary", use_container_width=True):
        if selected_codes:
            _scan_and_display_announcements(cache, selected_codes, quotes)
        else:
            st.warning("请选择至少一只股票")


def _manual_scan_mode(cache):
    """手动指定股票模式"""
    st.markdown("### 手动输入股票代码")

    code_input = st.text_area(
        "输入股票代码（每行一个，或逗号分隔）",
        placeholder="000001\n600519\n300750",
        height=120,
    )

    if st.button("🔍 开始扫描公告", type="primary", use_container_width=True):
        codes = _parse_stock_codes(code_input)
        if codes:
            quotes = cache.get("quotes", _load_realtime_quotes)
            _scan_and_display_announcements(cache, codes, quotes)
        else:
            st.warning("请输入有效的股票代码")


def _batch_import_mode(cache):
    """批量导入股票列表"""
    st.markdown("### 上传股票列表文件")

    uploaded_file = st.file_uploader(
        "上传 CSV 或 TXT 文件（每行一个股票代码）",
        type=["csv", "txt"],
    )

    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file)
                # 尝试找到代码列
                for col in ["code", "代码", "stock_code", "股票代码"]:
                    if col in df.columns:
                        codes = df[col].astype(str).str.zfill(6).tolist()
                        break
                else:
                    codes = df.iloc[:, 0].astype(str).str.zfill(6).tolist()
            else:
                content = uploaded_file.getvalue().decode("utf-8")
                codes = _parse_stock_codes(content)

            st.success(f"成功导入 {len(codes)} 只股票")

            if st.button("🔍 开始扫描公告", type="primary", use_container_width=True):
                quotes = cache.get("quotes", _load_realtime_quotes)
                _scan_and_display_announcements(cache, codes, quotes)
        except Exception as e:
            st.error(f"文件解析失败: {e}")


def _filter_high_attention_stocks(quotes: pd.DataFrame) -> pd.DataFrame:
    """筛选高关注度股票"""
    conditions = pd.Series(False, index=quotes.index)

    if "pct_chg" in quotes.columns:
        conditions |= quotes["pct_chg"].abs() > 5

    if "volume_ratio" in quotes.columns:
        conditions |= quotes["volume_ratio"] > 2

    if "turnover" in quotes.columns:
        conditions |= quotes["turnover"] > 10

    return quotes[conditions].copy()


def _parse_stock_codes(text: str) -> List[str]:
    """解析股票代码"""
    import re
    # 按换行或逗号分隔
    parts = re.split(r"[\n,;\s]+", text.strip())
    codes = []
    for p in parts:
        p = p.strip()
        if re.match(r"^\d{6}$", p):
            codes.append(p)
    return codes


def _scan_and_display_announcements(cache, codes: List[str],
                                     quotes: pd.DataFrame):
    """扫描并展示公告"""
    total_codes = len(codes)
    st.info(f"正在扫描 {total_codes} 只股票的公告...")

    # 使用 AnnouncementCollector 扫描
    from data.announcement import AnnouncementCollector
    from sentiment.announcement_nlp import AnnouncementNLPAnalyzer

    collector = AnnouncementCollector()
    nlp_analyzer = AnnouncementNLPAnalyzer()

    progress_bar = st.progress(0)
    status_text = st.empty()

    all_results = []

    for idx, code in enumerate(codes):
        try:
            # 获取公告
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            announcements = collector.fetch_cninfo_announcements(
                code, start_date, end_date, max_pages=1
            )

            if announcements.empty:
                # 尝试东方财富源
                announcements = collector.fetch_eastmoney_notices(code, max_days=1)

            if not announcements.empty:
                for _, ann in announcements.iterrows():
                    title = ann.get("title", "")
                    # 检查影响力
                    impact = collector.check_announcement_impact(title)
                    if impact["level"] != "neutral":
                        # NLP 分析
                        try:
                            nlp_result = nlp_analyzer.analyze_announcement(title, "")
                        except Exception:
                            nlp_result = {"combined_level": impact["level"], "combined_score": impact["score"]}

                        all_results.append({
                            "stock_code": code,
                            "stock_name": _get_stock_name(code, quotes),
                            "title": title[:100],
                            "pub_date": ann.get("pub_date", ""),
                            "source": ann.get("source", ""),
                            "impact_level": impact["level"],
                            "impact_category": impact.get("category", "other"),
                            "impact_score": impact["score"],
                            "sentiment_level": nlp_result.get("combined_level", "neutral"),
                            "keywords": ",".join(impact.get("keywords_matched", [])[:5]),
                        })

        except Exception as e:
            pass  # 静默处理单个股票的错误

        if (idx + 1) % 5 == 0 or idx == total_codes - 1:
            progress_bar.progress((idx + 1) / total_codes)
            status_text.text(f"已扫描 {idx + 1}/{total_codes}... 发现 {len(all_results)} 条重要公告")

    progress_bar.progress(1.0)

    if not all_results:
        status_text.text("扫描完成！")
        st.success(f"扫描了 {total_codes} 只股票，未发现重要公告")
        return

    status_text.text(f"扫描完成！发现 {len(all_results)} 条重要公告")

    # ---------- 展示结果 ----------
    st.markdown(f"### 公告扫描结果 ({len(all_results)} 条)")

    # 影响等级过滤
    impact_filter = st.multiselect(
        "按影响等级过滤",
        options=["strong_bullish", "bullish", "bearish", "strong_bearish"],
        default=["strong_bullish", "bullish", "bearish", "strong_bearish"],
        format_func=lambda x: {
            "strong_bullish": "重大利好",
            "bullish": "利好",
            "bearish": "利空",
            "strong_bearish": "重大利空",
        }.get(x, x),
    )

    # 分类过滤
    categories = list(set(r["impact_category"] for r in all_results))
    category_filter = st.multiselect(
        "按公告类型过滤",
        options=categories,
        default=categories,
    )

    # 应用过滤
    filtered = [
        r for r in all_results
        if r["impact_level"] in impact_filter
        and r["impact_category"] in category_filter
    ]

    if not filtered:
        st.info("过滤后无匹配的公告")
        return

    # 构建展示 DataFrame
    rows = []
    for r in sorted(filtered, key=lambda x: abs(x["impact_score"]), reverse=True):
        impact_label = {
            "strong_bullish": "重大利好",
            "bullish": "利好",
            "bearish": "利空",
            "strong_bearish": "重大利空",
            "neutral": "中性",
        }.get(r["impact_level"], r["impact_level"])

        rows.append({
            "股票代码": r["stock_code"],
            "股票名称": r["stock_name"],
            "公告标题": r["title"],
            "影响等级": impact_label,
            "公告类型": r["impact_category"],
            "影响评分": r["impact_score"],
            "关键词": r["keywords"],
            "日期": r["pub_date"],
            "来源": r["source"],
        })

    df = pd.DataFrame(rows)

    # 应用样式
    def _color_impact(val):
        colors = {
            "重大利好": "color: #E63946; font-weight: bold",
            "利好": "color: #FF8C00",
            "利空": "color: #4169E1",
            "重大利空": "color: #228B22; font-weight: bold",
        }
        return colors.get(val, "")

    styled_df = df.style.applymap(_color_impact, subset=["影响等级"])

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        height=min(500, 35 * len(df) + 38),
    )

    # ---------- 统计图表 ----------
    st.markdown("### 公告统计")

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        # 影响等级分布饼图
        level_counts = df["影响等级"].value_counts()
        fig = go.Figure(go.Pie(
            labels=level_counts.index,
            values=level_counts.values,
            hole=0.4,
            marker=dict(colors=["#E63946", "#FF8C00", "#4169E1", "#228B22"]),
        ))
        fig.update_layout(
            title="公告影响等级分布",
            height=300,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_chart2:
        # 公告类型分布
        cat_counts = df["公告类型"].value_counts()
        fig = go.Figure(go.Bar(
            x=cat_counts.index,
            y=cat_counts.values,
            marker_color="#FF6B35",
            text=cat_counts.values,
            textposition="outside",
        ))
        fig.update_layout(
            title="公告类型分布",
            height=300,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    # 公告详情展开
    with st.expander("查看所有公告详情"):
        for r in sorted(filtered, key=lambda x: abs(x["impact_score"]), reverse=True):
            impact_level = r["impact_level"]
            impact_label = {
                "strong_bullish": "重大利好",
                "bullish": "利好",
                "bearish": "利空",
                "strong_bearish": "重大利空",
            }.get(impact_level, impact_level)
            color = {
                "strong_bullish": "#E63946",
                "bullish": "#FF8C00",
                "bearish": "#4169E1",
                "strong_bearish": "#228B22",
            }.get(impact_level, "#999")

            st.markdown(f"""
            <div style="
                border-left: 3px solid {color};
                padding: 8px 14px;
                margin-bottom: 8px;
                background: #fafafa;
                border-radius: 4px;
            ">
                <b>{r['stock_code']} {r['stock_name']}</b>
                <span class="impact-{impact_level}">
                    {impact_label}
                </span>
                <br>
                <span style="font-size:13px;">{r['title']}</span>
                <br>
                <span style="font-size:11px;color:#999;">
                    评分: {r['impact_score']} | 类型: {r['impact_category']}
                    | 关键词: {r['keywords']} | {r['pub_date']}
                </span>
            </div>
            """, unsafe_allow_html=True)


def _get_stock_name(code: str, quotes: pd.DataFrame) -> str:
    """从行情数据获取股票名称"""
    if quotes.empty:
        return code
    match = quotes[quotes["code"] == code]
    if not match.empty and "name" in match.columns:
        return match.iloc[0]["name"]
    return code