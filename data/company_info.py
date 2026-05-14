import re
import requests
import pandas as pd
from datetime import datetime
from typing import List, Optional, Dict
from loguru import logger

from config.settings import DATA_DIR
from utils.cache import disk_cache

COMPANY_DIR = DATA_DIR / "company_info"
COMPANY_DIR.mkdir(exist_ok=True)


class CompanyInfoCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36",
        })

    @disk_cache(ttl_hours=24)
    def get_company_basic_info(self, stock_code: str) -> dict:
        import akshare as ak
        try:
            df = ak.stock_individual_info_em(symbol=stock_code)
            info = {}
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    key = row.get("item", "")
                    val = row.get("value", "")
                    info[key] = val
            logger.debug(f"获取 {stock_code} 基本信息完成")
            return info
        except Exception as e:
            logger.warning(f"获取 {stock_code} 基本信息失败: {e}")
        return {}

    def get_company_basic(self, stock_code: str) -> dict:
        """便捷方法：获取公司基本信息"""
        info = self.get_company_basic_info(stock_code)
        return {
            "code": stock_code,
            "name": info.get("股票简称", ""),
            "full_name": info.get("公司名称", ""),
            "listing_date": info.get("上市时间", ""),
            "total_shares": info.get("总股本", ""),
            "float_shares": info.get("流通股", ""),
        }

    @disk_cache(ttl_hours=24)
    def get_company_profile(self, stock_code: str) -> dict:
        import akshare as ak
        try:
            df = ak.stock_profile_cninfo(symbol=stock_code)
            if df is not None and not df.empty:
                profile = df.iloc[0].to_dict() if len(df) > 0 else df.to_dict()
                return {str(k): str(v) for k, v in profile.items()}
        except Exception as e:
            logger.warning(f"获取 {stock_code} 公司概况失败: {e}")
        return {}

    @disk_cache(ttl_hours=12)
    def get_financial_statements(self, stock_code: str) -> dict:
        import akshare as ak
        result = {}
        try:
            balance = ak.stock_balance_sheet_by_report_em(symbol=stock_code)
            if balance is not None and not balance.empty:
                result["balance_sheet"] = balance.head(4)
        except Exception as e:
            logger.warning(f"资产负债表 {stock_code} 失败: {e}")
        try:
            income = ak.stock_profit_sheet_by_report_em(symbol=stock_code)
            if income is not None and not income.empty:
                result["income_statement"] = income.head(4)
        except Exception as e:
            logger.warning(f"利润表 {stock_code} 失败: {e}")
        try:
            cashflow = ak.stock_cash_flow_sheet_by_report_em(symbol=stock_code)
            if cashflow is not None and not cashflow.empty:
                result["cash_flow"] = cashflow.head(4)
        except Exception as e:
            logger.warning(f"现金流量表 {stock_code} 失败: {e}")
        return result

    @disk_cache(ttl_hours=24)
    def get_shareholder_structure(self, stock_code: str) -> dict:
        import akshare as ak
        result = {}
        try:
            top10 = ak.stock_gdfx_top_10_em(symbol=stock_code)
            if top10 is not None and not top10.empty:
                result["top10_holders"] = top10.to_dict("records")
        except Exception as e:
            logger.warning(f"十大股东 {stock_code} 失败: {e}")
        try:
            sh_change = ak.stock_sharehold_change_em(symbol=stock_code)
            if sh_change is not None and not sh_change.empty:
                result["shareholder_changes"] = sh_change.tail(4).to_dict("records")
        except Exception as e:
            logger.warning(f"股东变化 {stock_code} 失败: {e}")
        try:
            holder_count = ak.stock_holder_number_em(symbol=stock_code)
            if holder_count is not None and not holder_count.empty:
                result["holder_number"] = holder_count.tail(6).to_dict("records")
        except Exception as e:
            logger.warning(f"股东户数 {stock_code} 失败: {e}")
        return result

    def check_registration_changes(self, stock_code: str) -> dict:
        profile = self.get_company_profile(stock_code)
        changes = {
            "name_changed": False,
            "address_changed": False,
            "legal_rep_changed": False,
            "business_scope_changed": False,
            "alerts": [],
        }
        if not profile:
            return changes
        try:
            import akshare as ak
            history = ak.stock_profile_cninfo(symbol=stock_code)
            if history is not None and len(history) > 1:
                latest = history.iloc[0].to_dict()
                previous = history.iloc[1].to_dict()
                if str(latest.get("name")) != str(previous.get("name")):
                    changes["name_changed"] = True
                    changes["alerts"].append(f"公司名称变更: {previous.get('name')} → {latest.get('name')}")
        except Exception:
            pass
        return changes

    def get_official_website_info(self, stock_code: str) -> dict:
        basic = self.get_company_basic_info(stock_code)
        return {
            "stock_code": stock_code,
            "name": basic.get("股票简称", ""),
            "full_name": basic.get("公司名称", ""),
            "listing_date": basic.get("上市时间", ""),
            "total_shares": basic.get("总股本", ""),
            "float_shares": basic.get("流通股", ""),
        }