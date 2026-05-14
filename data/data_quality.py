from datetime import datetime
from typing import Dict, Optional
from loguru import logger

from config.settings import DATA_LATENCY, ACTIVE_DATA_TIER, DATA_SOURCE_TIER


class DataQuality:
    def __init__(self):
        self.tier = ACTIVE_DATA_TIER
        self.sources = DATA_SOURCE_TIER.get(self.tier, DATA_SOURCE_TIER["eod"])

    def get_latency(self, data_type: str) -> Dict:
        source = self.sources.get(data_type, "akshare_free")
        latencies = DATA_LATENCY.get(source, {})
        result = latencies.get(data_type, {"latency": "未知", "reliable": False})
        result["source"] = source
        result["tier"] = self.tier
        return result

    def is_reliable(self, data_type: str) -> bool:
        return self.get_latency(data_type).get("reliable", False)

    def annotate_data(self, data: dict, data_types: list) -> dict:
        annotations = {}
        for dt in data_types:
            q = self.get_latency(dt)
            annotations[dt] = {
                "source": q["source"],
                "latency": q["latency"],
                "reliable": q["reliable"],
            }
        data["_data_quality"] = annotations
        return data

    def print_quality_report(self):
        logger.info(f"=== 数据质量报告 (层级: {self.tier}) ===")
        for data_type, source in self.sources.items():
            q = self.get_latency(data_type)
            status = "✅ 可靠" if q["reliable"] else "⚠️ 不稳定"
            logger.info(f"  {data_type}: {source} [{q['latency']}] {status}")

    def check_realtime_capability(self) -> Dict:
        realtime_ok = False
        realtime_source = self.sources.get("realtime_quote", "")
        if realtime_source in ("broker_xtp", "tushare_pro"):
            realtime_ok = True
        report = {
            "tier": self.tier,
            "realtime_capable": realtime_ok,
            "warning": "",
        }
        if not realtime_ok:
            if self.tier == "eod":
                report["warning"] = (
                    "当前为盘后模式，实时行情依赖免费AKShare接口，"
                    "盘中高频轮询会频繁断连，不适合做实时交易。"
                    "如需实时交易，请设置 DATA_TIER=realtime 并配置 Tushare Pro Token 或券商接口。"
                )
        return report