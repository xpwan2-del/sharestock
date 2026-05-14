import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from loguru import logger

from config.settings import DATA_DIR
from data.dragon_tiger import DragonTigerCollector
from data.market_data import MarketDataCollector

ANALYSIS_DIR = DATA_DIR / "analysis"
ANALYSIS_DIR.mkdir(exist_ok=True)


class InstitutionStyleAnalyzer:
    def __init__(self):
        self.dragon_tiger = DragonTigerCollector()
        self.market = MarketDataCollector()

    def analyze_dragon_tiger_patterns(self, days: int = 30) -> Dict:
        all_data = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            try:
                df = self.dragon_tiger.get_daily_dragon_tiger(date)
                if not df.empty:
                    df["trade_date"] = date
                    all_data.append(df)
            except Exception:
                continue
            if i % 10 == 0:
                logger.debug(f"龙虎榜采集: {i}/{days}")
        if not all_data:
            return {}
        combined = pd.concat(all_data, ignore_index=True)

        if "席位名称" in combined.columns:
            seat_col = "席位名称"
        elif "股票名称" in combined.columns:
            seat_col = "股票名称"
        else:
            seat_col = combined.columns[0]

        seat_stats = (
            combined.groupby(seat_col)
            .agg(
                appear_count=(seat_col, "count"),
            )
            .reset_index()
        )
        seat_stats.columns = ["席位名称", "出现次数"]
        seat_stats = seat_stats.sort_values("出现次数", ascending=False)

        logger.info(f"席位分析: {len(seat_stats)} 条记录, "
                    f"最活跃: {seat_stats.iloc[0].get('席位名称', '')} "
                    f"({seat_stats.iloc[0].get('出现次数', 0)}次)")

        return {
            "total_seats": len(seat_stats),
            "top_active_seats": seat_stats.head(20).to_dict("records"),
        }

    def analyze_trading_style(
        self, stock_code: str, lookback_days: int = 60
    ) -> Dict:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")
        kline = self.market.get_daily_kline(stock_code, start_date, end_date)
        if kline.empty or len(kline) < 30:
            return {"code": stock_code, "has_data": False}
        kline = self.market.calculate_technical_indicators(kline)
        volume_mean = kline["volume"].mean()
        volume_std = kline["volume"].std()
        volume_spike_days = (kline["volume"] > volume_mean + 2 * volume_std).sum()
        gap_up_days = (kline["open"] > kline["close"].shift(1) * 1.02).sum()
        reversal_days = 0
        for i in range(1, len(kline)):
            if kline["close"].iloc[i] > kline["open"].iloc[i]:
                if kline["open"].iloc[i] < kline["close"].iloc[i - 1]:
                    reversal_days += 1
            else:
                if kline["open"].iloc[i] > kline["close"].iloc[i - 1]:
                    reversal_days += 1
        reversal_ratio = reversal_days / len(kline)
        avg_turnover = kline["turnover"].mean() if "turnover" in kline.columns else 0
        style = "unknown"
        if volume_spike_days > len(kline) * 0.1 and avg_turnover > 5:
            style = "活跃游资"
        elif avg_turnover > 8 and gap_up_days > 5:
            style = "一字板打板"
        elif reversal_ratio > 0.25:
            style = "频繁震荡"
        elif volume_spike_days < len(kline) * 0.02 and avg_turnover < 2:
            style = "机构锁仓"
        else:
            style = "普通交易"
        return {
            "code": stock_code,
            "has_data": True,
            "style": style,
            "volume_spike_days": volume_spike_days,
            "volume_spike_ratio": round(volume_spike_days / len(kline), 2),
            "gap_up_days": gap_up_days,
            "reversal_ratio": round(reversal_ratio, 2),
            "avg_turnover": round(avg_turnover, 2),
            "days_analyzed": len(kline),
        }

    def identify_institution_portfolio(self) -> List[str]:
        import akshare as ak
        try:
            df = ak.stock_hold_organization_em()
            if df is not None and not df.empty and "股票代码" in df.columns:
                top_held = df.sort_values("持股比例", ascending=False).head(50)
                return top_held["股票代码"].tolist()
        except Exception:
            pass
        try:
            df = ak.stock_fund_hold_em()
            if df is not None and not df.empty:
                logger.info(f"基金持仓数据: {len(df)} 条")
                return df["股票代码"].head(50).tolist() if "股票代码" in df.columns else []
        except Exception as e:
            logger.warning(f"获取机构持仓失败: {e}")
        return []

    def analyze_institution_style(self, lhb_data: pd.DataFrame = None) -> Dict:
        """便捷方法：分析机构风格"""
        if lhb_data is not None and not lhb_data.empty:
            seat_col = None
            for col in ["席位名称", "股票名称"]:
                if col in lhb_data.columns:
                    seat_col = col
                    break
            if seat_col:
                seat_stats = lhb_data.groupby(seat_col).size().sort_values(ascending=False)
                top_seats = seat_stats.head(10).index.tolist()
                return {
                    "total_records": len(lhb_data),
                    "active_seats": len(seat_stats),
                    "top_seats": top_seats[:5],
                    "style": "活跃席位分析完成",
                }
        return {"style": "无数据", "total_records": 0}

    def generate_institution_report(self) -> Dict:
        logger.info("=== 生成机构手法分析报告 ===")
        dragon_patterns = self.analyze_dragon_tiger_patterns(days=5)
        insider_trading = pd.DataFrame()
        try:
            insider_trading = self.dragon_tiger.get_insider_trading(days=5)
        except Exception as e:
            logger.warning(f"高管增减持获取失败（非致命）: {e}")
        report = {
            "dragon_tiger_analysis": dragon_patterns,
            "insider_activity": {
                "total_records": len(insider_trading),
                "buy_count": len(insider_trading[insider_trading["变动方向"].str.contains("增持", na=False)]) if not insider_trading.empty and "变动方向" in insider_trading.columns else 0,
                "sell_count": len(insider_trading[insider_trading["变动方向"].str.contains("减持", na=False)]) if not insider_trading.empty and "变动方向" in insider_trading.columns else 0,
            },
        }
        return report