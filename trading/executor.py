import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger

from config.settings import MARKET_CONFIG, DATA_DIR
from data.market_data import MarketDataCollector

TRADING_DIR = DATA_DIR / "trading"
TRADING_DIR.mkdir(exist_ok=True)


class TradeExecutor:
    def __init__(self, initial_capital: float = 1000000):
        self.market = MarketDataCollector()
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions: Dict[str, Dict] = {}
        self.orders: List[Dict] = []
        self.trade_history: List[Dict] = []

    def calculate_position_size(
        self, price: float, risk_per_trade: float = 0.02, stop_loss_pct: float = 0.05
    ) -> int:
        risk_amount = self.capital * risk_per_trade
        shares = int(risk_amount / (price * stop_loss_pct))
        cost = shares * price
        if cost > self.capital * 0.3:
            shares = int(self.capital * 0.3 / price)
        return int(shares / 100) * 100

    def simulate_buy(
        self, code: str, name: str, price: float, shares: Optional[int] = None,
        risk_per_trade: float = 0.02,
    ) -> Dict:
        if shares is None:
            shares = self.calculate_position_size(price, risk_per_trade)
        if shares <= 0:
            return {"success": False, "reason": "仓位计算为0"}
        commission = max(shares * price * MARKET_CONFIG["commission_rate"], MARKET_CONFIG["min_commission"])
        stamp_tax = shares * price * MARKET_CONFIG["stamp_tax_rate"]
        slippage = shares * price * MARKET_CONFIG["slippage_rate"]
        total_cost = shares * price + commission + stamp_tax + slippage
        if total_cost > self.capital:
            return {"success": False, "reason": f"资金不足 ({total_cost:.0f} > {self.capital:.0f})"}
        actual_price = price * (1 + MARKET_CONFIG["slippage_rate"])
        self.capital -= total_cost
        position = {
            "code": code,
            "name": name,
            "shares": shares,
            "avg_price": actual_price,
            "cost": total_cost,
            "buy_date": datetime.now().strftime("%Y-%m-%d"),
            "stop_loss": actual_price * (1 - 0.05),
            "take_profit": actual_price * (1 + 0.10),
        }
        self.positions[code] = position
        order = {
            "type": "buy",
            "code": code,
            "name": name,
            "shares": shares,
            "price": actual_price,
            "commission": commission,
            "stamp_tax": stamp_tax,
            "slippage": slippage,
            "total": total_cost,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.orders.append(order)
        self.trade_history.append(order)
        logger.info(f"模拟买入 {name}({code}): {shares}股 @ {actual_price:.2f}, 成本{total_cost:.0f}")
        return {"success": True, "order": order}

    def simulate_sell(self, code: str, price: float, shares: Optional[int] = None) -> Dict:
        if code not in self.positions:
            return {"success": False, "reason": f"无 {code} 持仓"}
        pos = self.positions[code]
        sell_shares = shares or pos["shares"]
        sell_shares = min(sell_shares, pos["shares"])
        commission = max(sell_shares * price * MARKET_CONFIG["commission_rate"], MARKET_CONFIG["min_commission"])
        stamp_tax = sell_shares * price * MARKET_CONFIG["stamp_tax_rate"]
        slippage = sell_shares * price * MARKET_CONFIG["slippage_rate"]
        actual_price = price * (1 - MARKET_CONFIG["slippage_rate"])
        revenue = sell_shares * actual_price - commission - stamp_tax - slippage
        profit = revenue - pos["avg_price"] * sell_shares
        profit_pct = profit / (pos["avg_price"] * sell_shares) * 100 if pos["avg_price"] > 0 else 0
        self.capital += revenue
        pos["shares"] -= sell_shares
        if pos["shares"] <= 0:
            del self.positions[code]
        order = {
            "type": "sell",
            "code": code,
            "name": pos["name"],
            "shares": sell_shares,
            "price": actual_price,
            "profit": profit,
            "profit_pct": profit_pct,
            "revenue": revenue,
            "commission": commission,
            "stamp_tax": stamp_tax,
            "slippage": slippage,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.orders.append(order)
        self.trade_history.append(order)
        logger.info(f"模拟卖出 {pos['name']}({code}): {sell_shares}股 @ {actual_price:.2f}, "
                    f"收益{profit:+.0f}({profit_pct:+.1f}%)")
        return {"success": True, "order": order}

    def check_stop_loss(self, quotes: pd.DataFrame) -> List[Dict]:
        triggered = []
        for code, pos in list(self.positions.items()):
            stock_quote = quotes[quotes["code"] == code]
            if stock_quote.empty:
                continue
            current_price = stock_quote.iloc[0]["price"]
            if current_price <= pos["stop_loss"]:
                result = self.simulate_sell(code, current_price)
                if result["success"]:
                    result["reason"] = "止损触发"
                    triggered.append(result)
            elif current_price >= pos["take_profit"]:
                result = self.simulate_sell(code, current_price)
                if result["success"]:
                    result["reason"] = "止盈触发"
                    triggered.append(result)
        if triggered:
            logger.info(f"止盈止损触发: {len(triggered)} 笔")
        return triggered

    def get_portfolio_summary(self) -> Dict:
        quotes = self.market.get_realtime_quotes()
        total_market_value = 0
        total_cost = 0
        for code, pos in self.positions.items():
            current_price = pos["avg_price"]
            if not quotes.empty:
                stock_quote = quotes[quotes["code"] == code]
                if not stock_quote.empty:
                    current_price = stock_quote.iloc[0]["price"]
            total_market_value += pos["shares"] * current_price
            total_cost += pos["cost"]
        total_asset = self.capital + total_market_value
        total_profit = total_asset - self.initial_capital
        return {
            "capital": round(self.capital, 2),
            "market_value": round(total_market_value, 2),
            "total_asset": round(total_asset, 2),
            "total_profit": round(total_profit, 2),
            "total_return": round(total_profit / self.initial_capital * 100, 2),
            "position_count": len(self.positions),
            "positions": [
                {
                    "code": code,
                    "name": pos["name"],
                    "shares": pos["shares"],
                    "avg_price": round(pos["avg_price"], 2),
                    "cost": round(pos["cost"], 2),
                }
                for code, pos in self.positions.items()
            ],
        }

    def execute_signal(
        self, signal: Dict, max_position_pct: float = 0.2
    ) -> Optional[Dict]:
        signal_type = signal.get("signal", "")
        if signal_type in ("leader_watch", "reversal_buy", "buy"):
            code = signal.get("code", "")
            name = signal.get("name", "")
            if not code:
                return None
            if code in self.positions:
                logger.debug(f"{code} 已持仓，跳过")
                return None
            quotes = self.market.get_realtime_quotes([code])
            if quotes.empty:
                return None
            price = quotes.iloc[0]["price"]
            return self.simulate_buy(code, name, price)
        return None