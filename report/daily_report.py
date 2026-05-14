import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from config.settings import DATA_DIR
from data.collector import DataCollector
from data.market_data import MarketDataCollector
from sentiment.market_sentiment import MarketSentimentAnalyzer
from sentiment.news_sentiment import NewsSentimentAnalyzer
from sentiment.announcement_nlp import AnnouncementNLPAnalyzer
from analysis.leader_finder import LeaderFinder
from analysis.trend_reversal import TrendReversalDetector
from analysis.industry_chain import IndustryChainAnalyzer
from analysis.institution_style import InstitutionStyleAnalyzer
from trading.signal_generator import SignalGenerator
from utils.redis_manager import get_redis_manager

REPORT_DIR = DATA_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)


class DailyReportGenerator:
    def __init__(self):
        self.console = Console()
        self.collector = DataCollector()
        self.market = MarketDataCollector()
        self.sentiment = MarketSentimentAnalyzer()
        self.news_sentiment = NewsSentimentAnalyzer()
        self.announcement_nlp = AnnouncementNLPAnalyzer()
        self.leader_finder = LeaderFinder()
        self.reversal_detector = TrendReversalDetector()
        self.chain_analyzer = IndustryChainAnalyzer()
        self.institution = InstitutionStyleAnalyzer()
        self.signal_gen = SignalGenerator()
        self.redis = get_redis_manager()
        self.report_date = datetime.now().strftime("%Y-%m-%d")

    def run_full_report(self, output_markdown: bool = True) -> str:
        return self.generate_report(output_markdown)

    def generate_report(self, output_markdown: bool = True) -> str:
        logger.info(f"=== 生成 {self.report_date} 每日综合报告 ====")
        self._print_header()
        data = self.collector.collect_all_daily_data()
        breadth = data.get("market_breadth", {})
        quotes = data.get("realtime_quotes", pd.DataFrame())
        limit_up_pool = data.get("limit_up_pool", pd.DataFrame())
        continuous_limit = data.get("continuous_limit", pd.DataFrame())
        dragon_tiger = data.get("dragon_tiger", pd.DataFrame())
        north_data = data.get("north_bound_daily", {})
        concept_board = data.get("concept_board", pd.DataFrame())
        industry_board = data.get("industry_board", pd.DataFrame())
        self._print_market_overview(breadth, north_data)
        self._print_sentiment_analysis(breadth, north_data, limit_up_pool)
        self._print_industry_overview(industry_board, concept_board, limit_up_pool)
        self._print_leader_analysis()
        self._print_reversal_signals()
        self._print_dragon_tiger_analysis()
        self._print_announcement_alerts()
        self._print_signals_summary()
        if output_markdown:
            self._save_markdown_report()
        logger.info("=== 每日报告生成完毕 ===")
        return self.report_date

    def _load_model_predictions(self, top_n: int = 10) -> List[Dict]:
        predictions = []
        if getattr(self.redis, "client", None):
            try:
                for key in self.redis.client.scan_iter("quant:model:prediction:*"):
                    item = self.redis.hgetall_dict(key)
                    if item:
                        predictions.append(item)
            except Exception as e:
                logger.warning(f"读取模型预测失败: {e}")
        predictions = sorted(
            predictions,
            key=lambda x: float(x.get("up_probability", x.get("confidence", 0)) or 0),
            reverse=True,
        )
        return predictions[:top_n]

    def _load_compound_signals(self, top_n: int = 10) -> List[Dict]:
        signals = []
        if getattr(self.redis, "client", None):
            try:
                for key in self.redis.client.scan_iter("quant:signal:compound:*"):
                    item = self.redis.hgetall_dict(key)
                    if item:
                        signals.append(item)
            except Exception as e:
                logger.warning(f"读取复合信号失败: {e}")
        signals = sorted(
            signals,
            key=lambda x: float(x.get("confidence", 0) or 0),
            reverse=True,
        )
        return signals[:top_n]


    def _print_header(self):
        title = Text(f"A股每日综合分析报告 - {self.report_date}", style="bold white")
        self.console.print(Panel(title, style="bold blue", expand=True))

    def _print_market_overview(self, breadth: Dict, north_data: Dict):
        self.console.print(Panel("【一】市场概览", style="bold yellow"))
        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("指标", style="cyan")
        table.add_column("数值", style="white")
        if breadth:
            table.add_row("上涨家数", str(breadth.get("up_count", "N/A")))
            table.add_row("下跌家数", str(breadth.get("down_count", "N/A")))
            table.add_row("上涨比例", f"{breadth.get('up_ratio', 'N/A')}%")
            table.add_row("涨停家数", str(breadth.get("limit_up_count", "N/A")))
            table.add_row("跌停家数", str(breadth.get("limit_down_count", "N/A")))
            table.add_row("平均涨跌幅", f"{breadth.get('avg_pct_chg', 'N/A')}%")
            table.add_row("涨幅中位数", f"{breadth.get('median_pct_chg', 'N/A')}%")
            table.add_row("涨幅>5%", str(breadth.get("up_gt_5pct", "N/A")))
            table.add_row("跌幅>5%", str(breadth.get("down_gt_5pct", "N/A")))
        if north_data:
            net_yi = north_data.get("net_flow_yi", 0)
            color = "red" if net_yi > 0 else "green"
            table.add_row("北向资金(亿)", f"[{color}]{net_yi:+.2f}[/{color}]")
        self.console.print(table)

    def _print_sentiment_analysis(
        self, breadth: Dict, north_data: Dict, limit_up_pool: pd.DataFrame
    ):
        self.console.print(Panel("【二】市场情绪分析", style="bold yellow"))
        quotes = self.market.get_realtime_quotes()
        volume_sent = self.sentiment.analyze_volume_sentiment(quotes)
        north_sent = self.sentiment.analyze_northbound_sentiment(north_data)
        limit_quality = self.sentiment.analyze_limit_up_quality(limit_up_pool)
        comprehensive = self.sentiment.get_comprehensive_sentiment(
            breadth, volume_sent, north_sent, limit_quality
        )
        score = comprehensive.get("overall_score", 50)
        level = comprehensive.get("level", "未知")
        if score >= 60:
            color = "red"
        elif score >= 40:
            color = "yellow"
        else:
            color = "green"
        self.console.print(f"  综合情绪评分: [{color}]{score:.1f}[/{color}]  [{color}]{level}[/{color}]")
        components = comprehensive.get("components", {})
        self.console.print(f"  宽度评分: {components.get('breadth', 'N/A')}")
        self.console.print(f"  量能活跃: {'是' if components.get('volume_active') else '否'}")
        self.console.print(f"  北向信号: {components.get('north_signal', 'N/A')}")
        self.console.print(f"  涨停质量: {components.get('limit_up_quality', 'N/A')}")

    def _print_industry_overview(
        self, industry_board: pd.DataFrame, concept_board: pd.DataFrame,
        limit_up_pool: pd.DataFrame
    ):
        self.console.print(Panel("【三】行业与产业链热度", style="bold yellow"))
        if industry_board is not None and not industry_board.empty:
            board_sorted = self.sentiment.calculate_board_strength(industry_board)
            table = Table(box=box.SIMPLE)
            table.add_column("排名", style="dim")
            table.add_column("行业", style="cyan")
            table.add_column("涨跌幅", style="white")
            table.add_column("领涨股", style="white")
            for i, (_, row) in enumerate(board_sorted.head(10).iterrows(), 1):
                name = row.get("板块名称", "N/A") if "板块名称" in row.index else "N/A"
                pct = row.get("涨跌幅", 0) if "涨跌幅" in row.index else 0
                table.add_row(str(i), str(name), f"{float(pct):+.2f}%", "")
            self.console.print(table)
        chain_heat = self.chain_analyzer.analyze_chain_heat(concept_board, limit_up_pool)
        if not chain_heat.empty:
            self.console.print("\n  [bold]热门产业链 Top 5:[/bold]")
            for _, row in chain_heat.head(5).iterrows():
                self.console.print(
                    f"  • {row['chain_name']}: 涨停{int(row['limit_up_count'])}只, "
                    f"热度分{int(row['total_heat_score'])}"
                )

    def _print_leader_analysis(self):
        self.console.print(Panel("【四】龙头识别", style="bold yellow"))
        try:
            hot_concepts = self.leader_finder.scan_hot_concepts(top_n=5)
            for concept in hot_concepts[:3]:
                self.console.print(f"\n  [bold cyan]▸ {concept}[/bold cyan]")
                leaders = self.leader_finder.identify_all_leaders(concept)
                if not leaders:
                    continue
                for ltype, df in leaders.items():
                    if df is None or df.empty:
                        continue
                    ltype_cn = {
                        "logic_leaders": "逻辑龙头",
                        "sentiment_leaders": "情绪龙头",
                        "capacity_leaders": "容量龙头",
                    }.get(ltype, ltype)
                    names = df["name"].tolist() if "name" in df.columns else (
                        df["名称"].tolist() if "名称" in df.columns else []
                    )
                    self.console.print(f"    {ltype_cn}: {', '.join(names[:4])}")
                if leaders.get("reversal_candidates") is not None and not leaders["reversal_candidates"].empty:
                    reversal = leaders["reversal_candidates"]
                    rnames = reversal["name"].head(5).tolist()
                    self.console.print(f"    逆转候选: {', '.join(rnames)}")
        except Exception as e:
            logger.warning(f"龙头分析失败: {e}")

    def _print_reversal_signals(self):
        self.console.print(Panel("【五】趋势逆转信号", style="bold yellow"))
        try:
            quotes = self.market.get_realtime_quotes()
            if quotes.empty:
                self.console.print("  无数据")
                return
            active_stocks = quotes[
                (quotes["pct_chg"].abs() > 3) & (quotes["volume_ratio"] > 1.2)
            ]
            codes = active_stocks["code"].head(50).tolist()
            signals = self.signal_gen.generate_reversal_signals(codes)
            if signals:
                table = Table(box=box.SIMPLE)
                table.add_column("股票", style="cyan")
                table.add_column("逆转类型", style="white")
                table.add_column("信号强度", style="white")
                table.add_column("信号详情", style="white")
                for sig in signals[:15]:
                    table.add_row(
                        f"{sig['code']} {sig['name']}", sig["type"],
                        str(sig["strength"]), "|".join(sig.get("signals", [])[:3]),
                    )
                self.console.print(table)
            else:
                self.console.print("  今日无显著逆转信号")
        except Exception as e:
            logger.warning(f"逆转信号分析失败: {e}")

    def _print_dragon_tiger_analysis(self):
        self.console.print(Panel("【六】龙虎榜与机构动向", style="bold yellow"))
        try:
            dt_behavior = self.collector.dragon_tiger.identify_institution_behavior()
            if dt_behavior:
                inst_net = dt_behavior.get("institution_net", 0)
                inst_buy = dt_behavior.get("institution_buy", 0)
                inst_sell = dt_behavior.get("institution_sell", 0)
                dominant = dt_behavior.get("dominant_force", "unknown")
                self.console.print(f"  龙虎榜个股数: {dt_behavior.get('total_records', 0)}")
                self.console.print(f"  机构买入: {inst_buy}万")
                self.console.print(f"  机构卖出: {inst_sell}万")
                self.console.print(f"  机构净买: {inst_net:+.0f}万")
                self.console.print(f"  机构动向: {dominant}")
            else:
                self.console.print("  今日无龙虎榜数据或非交易日")
        except Exception as e:
            logger.warning(f"龙虎榜分析失败: {e}")

    def _print_announcement_alerts(self):
        self.console.print(Panel("【七】公告预警", style="bold yellow"))
        try:
            announcements = self.collector.scan_important_stocks()
            if announcements is not None and not announcements.empty:
                important = announcements[
                    announcements["impact_level"].isin([
                        "strong_bullish", "strong_bearish", "bullish", "bearish"
                    ])
                ]
                if not important.empty:
                    table = Table(box=box.SIMPLE)
                    table.add_column("股票", style="cyan")
                    table.add_column("公告标题", style="white")
                    table.add_column("影响", style="white")
                    for _, row in important.head(10).iterrows():
                        impact = row.get("impact_level", "")
                        color = "red" if "bullish" in str(impact) else "green"
                        table.add_row(
                            str(row.get("stock_code", "")),
                            str(row.get("title", ""))[:60],
                            f"[{color}]{impact}[/{color}]",
                        )
                    self.console.print(table)
                else:
                    self.console.print("  今日无重大利好/利空公告")
            else:
                self.console.print("  今日无重要公告")
        except Exception as e:
            logger.warning(f"公告分析失败: {e}")

    def _print_signals_summary(self):
        self.console.print(Panel("【八】综合信号汇总", style="bold yellow"))
        try:
            predictions = self._load_model_predictions(top_n=5)
            compound_signals = self._load_compound_signals(top_n=5)
            sentiment_signal = self.signal_gen.generate_sentiment_signal()
            limit_signal = self.signal_gen.generate_limit_up_signals()
            leader_signals = self.signal_gen.generate_leader_signals()
            self.console.print(f"  情绪信号: {sentiment_signal.get('sentiment', '')} → [bold]{sentiment_signal.get('action', '')}[/bold]")
            self.console.print(f"  涨停信号: {limit_signal.get('daily_limit_up', 0)}只涨停, 连板{limit_signal.get('continuous_limit_up', 0)}只")
            self.console.print(f"  龙头信号: {len(leader_signals)} 个概念发现龙头")
            if predictions:
                self.console.print("  模型预测 Top5:")
                for item in predictions:
                    self.console.print(
                        f"    • {item.get('code', '')} {item.get('up_probability', item.get('confidence', '0'))}"
                    )
            if compound_signals:
                self.console.print("  复合信号 Top5:")
                for item in compound_signals:
                    self.console.print(
                        f"    • {item.get('code', '')} {item.get('confidence', '0')} {item.get('signal_type', '')}"
                    )
        except Exception as e:
            logger.warning(f"信号汇总失败: {e}")

    def _save_markdown_report(self):
        date_dir = REPORT_DIR / self.report_date
        date_dir.mkdir(exist_ok=True)
        md = []
        md.append(f"# A股量化分析系统 - 每日报告")
        md.append(f"**日期**: {self.report_date}")
        md.append(f"**生成时间**: {datetime.now().strftime('%H:%M:%S')}")
        md.append("")
        try:
            breadth = self.market.get_market_breadth()
            md.append("## 一、市场概览")
            md.append(f"- 上涨: {breadth.get('up_count', 0)} 家 ({breadth.get('up_ratio', 0)}%)")
            md.append(f"- 下跌: {breadth.get('down_count', 0)} 家")
            md.append(f"- 涨停: {breadth.get('limit_up_count', 0)} 家")
            md.append(f"- 跌停: {breadth.get('limit_down_count', 0)} 家")
            md.append(f"- 平均涨跌: {breadth.get('avg_pct_chg', 0):+.2f}%")
            md.append("")
        except Exception:
            pass
        try:
            sentiment_signal = self.signal_gen.generate_sentiment_signal()
            md.append("## 二、情绪信号")
            md.append(f"- 综合情绪: {sentiment_signal.get('sentiment', '')} ({sentiment_signal.get('sentiment_score', '')})")
            md.append(f"- 操作建议: **{sentiment_signal.get('action', '')}**")
            md.append("")
        except Exception:
            pass
        try:
            predictions = self._load_model_predictions(top_n=10)
            compound_signals = self._load_compound_signals(top_n=10)
            md.append("## 四、模型预测与复合信号")
            if predictions:
                md.append("### 模型预测 Top10")
                for item in predictions:
                    md.append(
                        f"- {item.get('code', '')}: 上涨概率 {item.get('up_probability', item.get('confidence', '0'))}"
                    )
            else:
                md.append("- 当前无模型预测结果")
            md.append("")
            if compound_signals:
                md.append("### 复合信号 Top10")
                for item in compound_signals:
                    md.append(
                        f"- {item.get('code', '')}: 置信度 {item.get('confidence', '0')} ({item.get('signal_type', '')})"
                    )
            else:
                md.append("- 当前无复合信号结果")
            md.append("")
        except Exception as e:
            logger.warning(f"写入模型信号章节失败: {e}")
        report_path = date_dir / "daily_report.md"
        report_path.write_text("\n".join(md), encoding="utf-8")
        logger.info(f"Markdown 报告已保存: {report_path}")