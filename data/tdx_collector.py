"""TDX 通达信行情采集器

用于从公开通达信行情服务器获取 A 股的准实时行情和 K 线数据。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
from loguru import logger

try:
    from pytdx.hq import TdxHq_API
except Exception as e:  # pragma: no cover
    TdxHq_API = None
    logger.warning(f"pytdx 导入失败: {e}")


@dataclass
class TDXServer:
    ip: str
    port: int = 7709


DEFAULT_SERVERS: List[TDXServer] = [
    TDXServer("119.147.212.81", 7709),
    TDXServer("61.152.107.141", 7709),
    TDXServer("124.74.236.94", 7709),
    TDXServer("202.108.253.130", 7709),
    TDXServer("59.173.18.140", 7709),
]


class TDXDataCollector:
    def __init__(self, servers: Optional[List[Tuple[str, int]]] = None):
        self.servers = [TDXServer(ip, port) for ip, port in (servers or [])] or DEFAULT_SERVERS
        self._code_name_map = None

    @staticmethod
    def _market_from_code(code: str) -> int:
        return 1 if str(code).startswith(("6", "9")) else 0

    def _load_code_name_map(self) -> Dict[str, str]:
        if self._code_name_map is not None:
            return self._code_name_map
        try:
            import akshare as ak

            df = ak.stock_info_a_code_name()
            if df is not None and not df.empty:
                code_col = "code" if "code" in df.columns else df.columns[0]
                name_col = "name" if "name" in df.columns else df.columns[1]
                self._code_name_map = dict(zip(df[code_col].astype(str), df[name_col].astype(str)))
            else:
                self._code_name_map = {}
        except Exception as e:
            logger.warning(f"加载 A 股代码映射失败: {e}")
            self._code_name_map = {}
        return self._code_name_map

    def _connect(self):
        if TdxHq_API is None:
            return None, None
        api = TdxHq_API(heartbeat=True, auto_retry=True)
        for server in self.servers:
            try:
                if api.connect(server.ip, server.port):
                    logger.info(f"TDX 连接成功: {server.ip}:{server.port}")
                    return api, server
            except Exception as e:
                logger.debug(f"TDX 连接失败 {server.ip}:{server.port} - {e}")
        try:
            api.disconnect()
        except Exception:
            pass
        return None, None

    def _normalize_quotes(self, items: Iterable[dict]) -> pd.DataFrame:
        rows = []
        name_map = self._load_code_name_map()
        for row in items or []:
            code = str(row.get("code", ""))
            if not code:
                continue
            price = row.get("price") or row.get("close") or 0
            open_ = row.get("open") or 0
            high = row.get("high") or price
            low = row.get("low") or price
            vol = row.get("vol") or row.get("volume") or 0
            amount = row.get("amount") or 0
            pre_close = row.get("last_close") or row.get("pre_close") or 0
            pct_chg = 0.0
            change = 0.0
            try:
                if pre_close:
                    change = float(price) - float(pre_close)
                    pct_chg = change / float(pre_close) * 100
            except Exception:
                pass
            rows.append(
                {
                    "code": code,
                    "name": row.get("name") or name_map.get(code, ""),
                    "price": float(price) if price is not None else 0.0,
                    "open": float(open_) if open_ is not None else 0.0,
                    "high": float(high) if high is not None else 0.0,
                    "low": float(low) if low is not None else 0.0,
                    "volume": float(vol) if vol is not None else 0.0,
                    "amount": float(amount) if amount is not None else 0.0,
                    "pre_close": float(pre_close) if pre_close is not None else 0.0,
                    "change": float(change),
                    "pct_chg": float(pct_chg),
                    "datetime": row.get("datetime") or row.get("time") or "",
                }
            )
        return pd.DataFrame(rows)

    def get_realtime_quotes(self, symbols: Optional[List[str]] = None) -> pd.DataFrame:
        api, server = self._connect()
        if api is None:
            return pd.DataFrame()
        try:
            if symbols:
                items = []
                for code in symbols:
                    market = self._market_from_code(code)
                    items.append((market, str(code)))
                data = []
                for market, code in items:
                    try:
                        res = api.get_security_quotes([(market, code)])
                        data.extend(res or [])
                    except Exception as e:
                        logger.debug(f"TDX 读取行情失败 {code}: {e}")
                return self._normalize_quotes(data)
            data = api.get_security_quotes([(0, "000001"), (1, "000001")])
            return self._normalize_quotes(data)
        except Exception as e:
            logger.warning(f"TDX 获取实时行情失败: {e}")
            return pd.DataFrame()
        finally:
            try:
                api.disconnect()
            except Exception:
                pass

    def get_daily_kline(self, symbol: str, start_date: str, end_date: str, adjust: str = "") -> pd.DataFrame:
        api, server = self._connect()
        if api is None:
            return pd.DataFrame()
        try:
            market = self._market_from_code(symbol)
            code = str(symbol)
            candidates = [9, 0]
            bars = []
            for category in candidates:
                try:
                    res = api.get_security_bars(category, market, code, 0, 800)
                    if res:
                        bars = res
                        break
                except Exception as e:
                    logger.debug(f"TDX 获取K线失败 category={category} {code}: {e}")
            if not bars:
                return pd.DataFrame()
            df = pd.DataFrame(bars)
            if df.empty:
                return df
            if "datetime" in df.columns:
                df["date"] = pd.to_datetime(df["datetime"])
            elif "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
            else:
                df["date"] = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq="B")
            rename_map = {
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "vol": "volume",
                "amount": "amount",
            }
            df = df.rename(columns=rename_map)
            keep_cols = [c for c in ["date", "open", "high", "low", "close", "volume", "amount"] if c in df.columns]
            df = df[keep_cols].copy()
            df = df.sort_values("date").reset_index(drop=True)
            if "close" in df.columns:
                df["change"] = df["close"].diff().fillna(0)
            if "close" in df.columns and "change" in df.columns:
                prev = df["close"].shift(1)
                df["pct_chg"] = ((df["close"] - prev) / prev * 100).replace([pd.NA, pd.NaT], 0).fillna(0)
            df["symbol"] = symbol
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]
            return df.reset_index(drop=True)
        except Exception as e:
            logger.warning(f"TDX 获取 {symbol} K线失败: {e}")
            return pd.DataFrame()
        finally:
            try:
                api.disconnect()
            except Exception:
                pass


__all__ = ["TDXDataCollector", "TDXServer"]
