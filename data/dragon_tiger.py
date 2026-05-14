import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger

from config.settings import DATA_DIR
from utils.cache import disk_cache
from utils.calendar import get_latest_trading_day

DT_DATA_DIR = DATA_DIR / "dragon_tiger"
DT_DATA_DIR.mkdir(exist_ok=True)


class DragonTigerCollector:
    def __init__(self):
        self.today = get_latest_trading_day()

    @disk_cache(ttl_hours=4)
    def get_daily_dragon_tiger(self, date: Optional[str] = None) -> pd.DataFrame:
        if date is None:
            date = self.today
        try:
            start_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
            df = ak.stock_lhb_detail_daily_sina(date=start_date)
            logger.info(f"龙虎榜({date}): {len(df)} 条记录")
            return df
        except Exception as e:
            logger.warning(f"获取龙虎榜({date})失败: {e}")
        return pd.DataFrame()

    def identify_institution_behavior(self, date: Optional[str] = None) -> dict:
        if date is None:
            date = self.today
        try:
            detail_df = self.get_daily_dragon_tiger(date)
            if detail_df.empty:
                return {}
            start_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
            inst_df = ak.stock_lhb_jgmx_sina()
            if inst_df is None or inst_df.empty:
                return {"total_records": len(detail_df), "date": date}
            inst_df = inst_df[inst_df["交易日期"] == start_date]
            inst_buy = inst_df["机构席位买入额"].sum()
            inst_sell = inst_df["机构席位卖出额"].sum()
            inst_net = inst_buy - inst_sell
            return {
                "date": date,
                "total_records": len(detail_df),
                "institution_count": len(inst_df),
                "institution_buy": round(float(inst_buy) / 1e4, 0),
                "institution_sell": round(float(inst_sell) / 1e4, 0),
                "institution_net": round(float(inst_net) / 1e4, 0),
                "dominant_force": "institution" if inst_net > 0 else "selling",
            }
        except Exception as e:
            logger.warning(f"龙虎榜机构分析失败: {e}")
        return {}

    def get_insider_trading(self, days: int = 30) -> pd.DataFrame:
        try:
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            # 使用 signal 设置超时，防止 AKShare 挂起
            import signal
            import threading

            result_df = None
            exception = None

            def _fetch():
                nonlocal result_df, exception
                try:
                    result_df = ak.stock_hold_management_detail_em()
                except Exception as e:
                    exception = e

            thread = threading.Thread(target=_fetch, daemon=True)
            thread.start()
            thread.join(timeout=30)  # 30 秒超时

            if thread.is_alive():
                logger.warning("高管增减持接口超时(30s)，跳过")
                return pd.DataFrame()

            if exception:
                logger.warning(f"高管增减持获取失败: {exception}")
                return pd.DataFrame()

            df = result_df
            if df is not None and not df.empty:
                df = df[df["变动日期"] >= start] if "变动日期" in df.columns else df
                logger.info(f"高管增减持({days}天): {len(df)} 条")
                return df
        except Exception as e:
            logger.warning(f"高管增减持获取失败: {e}")
        return pd.DataFrame()