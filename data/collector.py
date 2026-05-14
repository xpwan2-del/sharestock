import pandas as pd
from typing import List, Optional, Dict
from loguru import logger

from data.market_data import MarketDataCollector
from data.announcement import AnnouncementCollector
from data.company_info import CompanyInfoCollector
from data.dragon_tiger import DragonTigerCollector
from data.fund_flow import FundFlowCollector
from data.industry_chain import IndustryChainCollector


class DataCollector:
    def __init__(self):
        self.market = MarketDataCollector()
        self.announcement = AnnouncementCollector()
        self.company_info = CompanyInfoCollector()
        self.dragon_tiger = DragonTigerCollector()
        self.fund_flow = FundFlowCollector()
        self.industry_chain = IndustryChainCollector()

    def collect_all_daily_data(self) -> Dict:
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        logger.info("=== 开始采集当日全量数据 ===")
        results = {}
        results["market_breadth"] = self.market.get_market_breadth()
        results["realtime_quotes"] = self.market.get_realtime_quotes()
        results["limit_up_pool"] = self.market.get_limit_up_pool(today)
        results["continuous_limit"] = self.market.get_continuous_limit_up()
        results["dragon_tiger"] = self.dragon_tiger.get_daily_dragon_tiger(today)
        results["north_bound_daily"] = self.fund_flow.get_north_bound_daily()
        results["margin"] = self.fund_flow.get_margin_trading()
        results["industry_board"] = self.market.get_industry_board()
        results["concept_board"] = self.market.get_concept_board()
        logger.info("=== 当日数据采集完成 ===")
        return results

    def scan_important_stocks(
        self, stock_codes: Optional[List[str]] = None
    ) -> pd.DataFrame:
        logger.info("=== 扫描重点关注股票 ===")
        if stock_codes is None:
            quotes = self.market.get_realtime_quotes()
            if quotes.empty:
                return pd.DataFrame()
            quotes = quotes[quotes["pct_chg"].between(-11, 11)]
            high_attention = quotes[
                (quotes["pct_chg"].abs() > 5) |
                (quotes["volume_ratio"] > 2) |
                (quotes["turnover"] > 10)
            ]
            stock_codes = high_attention["code"].tolist()
            logger.info(f"自动筛选关注股票: {len(stock_codes)} 只")
        if not stock_codes:
            return pd.DataFrame()
        announcements = self.announcement.scan_important_announcements(
            stock_codes, days=1
        )
        if announcements.empty:
            announcements = pd.DataFrame(columns=[
                "stock_code", "title", "impact_level", "impact_score"
            ])
        dragon_tiger_behavior = self.dragon_tiger.identify_institution_behavior()
        logger.info(f"重要公告 {len(announcements)} 条, 龙虎榜分析完成")
        return announcements