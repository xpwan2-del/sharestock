"""TDX 中间件集成测试

验证 `TDXDataCollector` 及其在 `MarketDataCollector` 中的集成是否能跑通。
"""

import shutil
import unittest
from unittest.mock import patch

import pandas as pd
from loguru import logger

from data.market_data import MarketDataCollector
from data.tdx_collector import TDXDataCollector
from utils.cache import CACHE_DIR
from utils.calendar import get_latest_trading_day, is_market_open


class TestTDXIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logger.remove()
        cls.latest_trading_day = get_latest_trading_day()
        cls.is_open = is_market_open()

    def setUp(self):
        if CACHE_DIR.exists():
            shutil.rmtree(CACHE_DIR)
        CACHE_DIR.mkdir(exist_ok=True)
        self.market = MarketDataCollector()
        self.tdx = TDXDataCollector()

    def test_01_tdx_collector_initialization(self):
        self.assertIsInstance(self.tdx, TDXDataCollector)
        self.assertGreater(len(self.tdx.servers), 0)

    def test_02_tdx_get_daily_kline_real_network(self):
        start = (pd.Timestamp(self.latest_trading_day) - pd.Timedelta(days=90)).strftime("%Y%m%d")
        df = self.tdx.get_daily_kline("000001", start_date=start, end_date=self.latest_trading_day)
        self.assertIsInstance(df, pd.DataFrame)
        if df.empty:
            logger.warning("TDX 真实网络 K 线为空，说明免费中间件当前不可作为稳定主数据源")
        else:
            self.assertIn("close", df.columns)
            self.assertIn("date", df.columns)

    def test_03_market_collector_uses_tdx_for_kline(self):
        with patch.object(self.market.tdx, "get_daily_kline") as mock_tdx_kline:
            mock_tdx_kline.return_value = pd.DataFrame({"close": [1, 2, 3], "date": pd.date_range("2024-01-01", periods=3)})
            df = self.market.get_daily_kline("000001", "20240101", "20240131")
            mock_tdx_kline.assert_called_once()
            self.assertEqual(len(df), 3)

    def test_04_tdx_fallback_to_akshare_for_kline(self):
        with patch.object(self.market.tdx, "get_daily_kline") as mock_tdx_kline, patch("akshare.stock_zh_a_hist") as mock_ak_kline:
            mock_tdx_kline.side_effect = Exception("TDX connection failed")
            mock_ak_kline.return_value = pd.DataFrame({
                "日期": pd.to_datetime(["2024-01-01"]),
                "开盘": [9.8],
                "收盘": [10.0],
                "最高": [10.2],
                "最低": [9.7],
                "成交量": [1000],
                "成交额": [10000],
                "涨跌幅": [1.2],
                "涨跌额": [0.1],
            })
            df = self.market.get_daily_kline("000001", "20240101", "20240131")
            mock_tdx_kline.assert_called_once()
            mock_ak_kline.assert_called_once()
            self.assertFalse(df.empty)
            self.assertEqual(float(df["close"].iloc[0]), 10.0)

    def test_05_tdx_get_realtime_quotes_real_network(self):
        df = self.tdx.get_realtime_quotes(symbols=["000001", "600519"])
        self.assertIsInstance(df, pd.DataFrame)
        if df.empty:
            self.assertFalse(self.is_open, "开盘时间 TDX 实时行情未返回数据")
        else:
            self.assertIn("price", df.columns)
            self.assertIn("code", df.columns)

    def test_06_market_collector_uses_tdx_for_quotes(self):
        with patch.object(self.market.tdx, "get_realtime_quotes") as mock_tdx_quotes:
            mock_tdx_quotes.return_value = pd.DataFrame({"code": ["000001"], "price": [10.0]})
            df = self.market.get_realtime_quotes(symbols=["000001"])
            mock_tdx_quotes.assert_called_once()
            self.assertFalse(df.empty)
            self.assertEqual(float(df["price"].iloc[0]), 10.0)

    def test_07_tdx_fallback_to_akshare_for_quotes(self):
        with patch.object(self.market.tdx, "get_realtime_quotes") as mock_tdx_quotes, patch("akshare.stock_zh_a_spot_em") as mock_ak_quotes:
            mock_tdx_quotes.side_effect = Exception("TDX connection failed")
            mock_ak_quotes.return_value = pd.DataFrame({
                "代码": ["000001"],
                "名称": ["平安银行"],
                "最新价": [12.0],
                "涨跌幅": [1.0],
                "涨跌额": [0.12],
                "成交量": [1000],
                "成交额": [12000],
            })
            df = self.market.get_realtime_quotes(symbols=["000001"])
            mock_tdx_quotes.assert_called_once()
            mock_ak_quotes.assert_called_once()
            self.assertFalse(df.empty)
            self.assertEqual(float(df["price"].iloc[0]), 12.0)


if __name__ == "__main__":
    unittest.main()
