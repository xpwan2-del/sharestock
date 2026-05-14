import akshare as ak
import pandas as pd
from datetime import datetime
from typing import Optional
from loguru import logger

from config.settings import DATA_DIR
from utils.cache import disk_cache
from utils.calendar import get_latest_trading_day

FUND_DIR = DATA_DIR / "fund_flow"
FUND_DIR.mkdir(exist_ok=True)


class FundFlowCollector:
    def __init__(self):
        self.today = get_latest_trading_day()

    @disk_cache(ttl_hours=4)
    def get_north_bound_flow(self) -> pd.DataFrame:
        try:
            df = ak.stock_hsgt_hist_em(symbol="沪股通")
            logger.info(f"北向资金历史: {len(df)} 天")
            return df
        except Exception as e:
            logger.warning(f"北向资金获取失败: {e}")
        return pd.DataFrame()

    @disk_cache(ttl_hours=4)
    def get_north_bound_daily(self) -> dict:
        try:
            df = ak.stock_hsgt_fund_flow_summary_em()
            if df is not None and not df.empty:
                north_data = df[df["资金方向"] == "北向"]
                if north_data.empty:
                    return {"date": "", "net_flow": 0, "data": None}
                latest_date = str(north_data.iloc[0]["交易日"])
                total_net = north_data["成交净买额"].sum()
                total_inflow = north_data["资金净流入"].sum()
                return {
                    "date": latest_date,
                    "net_flow": float(total_net),
                    "net_flow_yi": round(float(total_net) / 1e8, 2),
                    "total_inflow": float(total_inflow),
                    "data": north_data,
                }
        except Exception as e:
            logger.warning(f"北向资金获取失败: {e}")
        return {}

    @disk_cache(ttl_hours=4)
    def get_margin_trading(self) -> dict:
        from datetime import timedelta
        today = datetime.now()
        start = (today - timedelta(days=5)).strftime("%Y%m%d")
        end = today.strftime("%Y%m%d")
        try:
            df_sh = ak.stock_margin_sse(start_date=start, end_date=end)
            if df_sh is not None and not df_sh.empty:
                latest = df_sh.iloc[-1]
                return {
                    "date": str(latest.get("信用交易日期", "")),
                    "balance": float(latest.get("融资余额", 0)),
                    "buy_amount": float(latest.get("融资买入额", 0)),
                }
        except Exception as e:
            logger.warning(f"融资融券获取失败: {e}")
        return {}

    @disk_cache(ttl_hours=2)
    def get_stock_fund_flow(self, symbol: str) -> pd.DataFrame:
        try:
            df = ak.stock_individual_fund_flow(stock=symbol, market="sh")
            logger.debug(f"个股资金流向 {symbol}: {len(df)} 天")
            return df
        except Exception as e:
            logger.warning(f"个股资金流向 {symbol} 失败: {e}")
        return pd.DataFrame()

    def get_main_force_flow_ranking(self) -> pd.DataFrame:
        try:
            df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
            logger.info(f"主力资金流排行: {len(df)} 个板块")
            return df
        except Exception as e:
            logger.warning(f"主力资金流排行失败: {e}")
        return pd.DataFrame()