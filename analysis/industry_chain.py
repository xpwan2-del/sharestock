import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from loguru import logger

from config.settings import LEADER_THRESHOLDS, DATA_DIR
from data.industry_chain import IndustryChainCollector, INDUSTRY_CHAIN_MAP
from data.market_data import MarketDataCollector

ANALYSIS_DIR = DATA_DIR / "analysis"
ANALYSIS_DIR.mkdir(exist_ok=True)


class IndustryChainAnalyzer:
    def __init__(self):
        self.chain_collector = IndustryChainCollector()
        self.market = MarketDataCollector()

    def analyze_chain_heat(
        self, concept_board: pd.DataFrame, limit_up_pool: pd.DataFrame
    ) -> pd.DataFrame:
        if concept_board.empty or limit_up_pool.empty:
            return pd.DataFrame()
        all_sub_industries = set()
        for segments in INDUSTRY_CHAIN_MAP.values():
            for sub_list in segments.values():
                all_sub_industries.update(sub_list)

        chain_heat = []
        for chain_name, segments in INDUSTRY_CHAIN_MAP.items():
            all_keywords = [chain_name]
            for seg_name, sub_industries in segments.items():
                all_keywords.append(seg_name)
                all_keywords.extend(sub_industries)

            def match_stock(row):
                industry = str(row.get("所属行业", "") or row.get("行业", ""))
                name = str(row.get("名称", "") or row.get("name", ""))
                for kw in all_keywords:
                    if kw in industry or kw in name:
                        return True
                return False

            matched_stocks = limit_up_pool[limit_up_pool.apply(match_stock, axis=1)]

            # Also match via concept board: find concepts related to this chain
            if "板块名称" in concept_board.columns:
                related_concepts = concept_board[
                    concept_board["板块名称"].apply(
                        lambda x: any(kw in str(x) for kw in all_keywords)
                    )
                ]
                for _, rc in related_concepts.iterrows():
                    cn = rc["板块名称"]
                    try:
                        components = self.market.get_concept_board_components(cn)
                        if not components.empty and "代码" in components.columns:
                            comp_codes = set(components["代码"].tolist())
                            if comp_codes and "代码" in limit_up_pool.columns:
                                extra = limit_up_pool[limit_up_pool["代码"].isin(comp_codes)]
                                if not extra.empty:
                                    matched_stocks = pd.concat([matched_stocks, extra]).drop_duplicates(subset=["代码"] if "代码" in matched_stocks.columns else None)
                    except Exception:
                        pass
            heat = {
                "chain_name": chain_name,
                "limit_up_count": len(matched_stocks),
                "segments": [],
                "total_heat_score": 0,
            }
            for segment_name, sub_industries in segments.items():
                seg_stocks = matched_stocks[
                    matched_stocks.apply(
                        lambda row: any(
                            concept in str(row.get("所属行业", "") or row.get("行业", ""))
                            for concept in sub_industries
                        ),
                        axis=1,
                    )
                ]
                seg_heat = {
                    "segment": segment_name,
                    "limit_up_count": len(seg_stocks),
                    "sub_industries": sub_industries,
                }
                heat["segments"].append(seg_heat)
                heat["total_heat_score"] += len(seg_stocks)
            chain_heat.append(heat)
        df = pd.DataFrame(chain_heat)
        df = df.sort_values("total_heat_score", ascending=False)
        if not df.empty:
            top_chain = df.iloc[0]
            logger.info(
                f"最热产业链: {top_chain['chain_name']} "
                f"(涨停{top_chain['limit_up_count']}只)"
            )
        return df