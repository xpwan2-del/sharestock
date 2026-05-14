import akshare as ak
import pandas as pd
import networkx as nx
from typing import Dict, List, Set, Optional
from loguru import logger

from config.settings import DATA_DIR
from utils.cache import disk_cache

CHAIN_DIR = DATA_DIR / "industry_chains"
CHAIN_DIR.mkdir(exist_ok=True)


INDUSTRY_CHAIN_MAP = {
    "新能源汽车": {
        "上游": ["锂矿", "钴矿", "镍矿", "稀土永磁", "石墨负极", "电解液", "隔膜", "正极材料"],
        "中游": ["动力电池", "电机电控", "热管理", "轻量化", "汽车电子", "IGBT"],
        "下游": ["整车制造", "充电桩", "换电", "汽车后市场"],
    },
    "光伏": {
        "上游": ["硅料", "硅片", "光伏银浆", "光伏玻璃", "胶膜"],
        "中游": ["电池片", "组件", "逆变器", "支架", "金刚线"],
        "下游": ["电站运营", "储能", "BIPV"],
    },
    "半导体": {
        "上游": ["EDA软件", "IP核", "半导体设备", "硅片", "光刻胶", "特种气体", "靶材"],
        "中游": ["芯片设计", "晶圆代工", "封装测试"],
        "下游": ["消费电子", "汽车电子", "工业控制", "数据中心", "通信设备"],
    },
    "人工智能": {
        "上游": ["算力芯片GPU", "光模块", "服务器", "数据中心", "数据标注"],
        "中游": ["大模型", "AI应用开发", "机器视觉", "NLP", "智能语音"],
        "下游": ["智能驾驶", "智能家居", "工业AI", "医疗AI", "金融AI"],
    },
    "医药医疗": {
        "上游": ["原料药", "中间体", "CXO", "生命科学服务", "医疗设备零部件"],
        "中游": ["创新药", "仿制药", "医疗器械", "IVD体外诊断", "疫苗"],
        "下游": ["医院", "连锁药房", "互联网医疗", "医美"],
    },
    "机器人": {
        "上游": ["减速器", "伺服电机", "控制器", "传感器", "丝杠"],
        "中游": ["工业机器人本体", "人形机器人", "协作机器人", "AGV/AMR"],
        "下游": ["汽车制造", "3C电子", "金属加工", "物流仓储", "医疗服务"],
    },
    "低空经济": {
        "上游": ["碳纤维", "航空发动机", "飞控系统", "导航系统", "复合材料"],
        "中游": ["eVTOL制造", "无人机", "通用航空器", "飞行汽车"],
        "下游": ["低空物流", "低空旅游", "应急救援", "农业植保", "城市空中交通"],
    },
    "消费电子": {
        "上游": ["芯片", "面板", "结构件", "PCB", "电池", "声学部件", "光学镜头"],
        "中游": ["手机制造", "PC制造", "可穿戴设备", "VR/AR", "智能音箱"],
        "下游": ["品牌商", "渠道", "回收"],
    },
}


class IndustryChainCollector:
    def __init__(self):
        self.chain_map = INDUSTRY_CHAIN_MAP
        self._chain_graph = None

    def get_all_chains(self) -> Dict[str, Dict]:
        return self.chain_map

    def get_chain_stocks(self, chain_name: str) -> pd.DataFrame:
        """获取产业链的样本股票列表（通过子行业概念成分股）"""
        import akshare as ak
        all_stocks = []
        segments = self.get_chain_segments(chain_name)
        if not segments:
            return pd.DataFrame()
        for segment_name, sub_industries in segments.items():
            for sub in sub_industries[:3]:  # 每个环节取前3个子行业
                try:
                    df = ak.stock_board_concept_cons_em(symbol=sub)
                    if df is not None and not df.empty:
                        all_stocks.append(df)
                except Exception:
                    pass
        if all_stocks:
            result = pd.concat(all_stocks, ignore_index=True)
            result = result.drop_duplicates(subset=["代码"] if "代码" in result.columns else None)
            return result.head(50)
        return pd.DataFrame()

    def get_chain_segments(self, chain_name: str) -> Optional[Dict[str, List[str]]]:
        return self.chain_map.get(chain_name)

    def get_all_sub_industries(self) -> Set[str]:
        sub_industries = set()
        for chain in self.chain_map.values():
            for segments in chain.values():
                sub_industries.update(segments)
        return sub_industries

    def get_stocks_by_concept(self, concept_name: str) -> pd.DataFrame:
        try:
            df = ak.stock_board_concept_cons_em(symbol=concept_name)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(f"获取概念成分股 {concept_name} 失败: {e}")
        return pd.DataFrame()

    def build_chain_graph(self) -> nx.DiGraph:
        G = nx.DiGraph()
        for chain_name, segments in self.chain_map.items():
            for segment_name, sub_industries in segments.items():
                seg_node = f"{chain_name}/{segment_name}"
                G.add_node(seg_node, chain=chain_name, segment=segment_name)
                for sub in sub_industries:
                    G.add_node(sub, chain=chain_name, segment=segment_name)
                    G.add_edge(sub, seg_node, relation="属于")
            segments_list = list(segments.keys())
            for i in range(len(segments_list) - 1):
                up = f"{chain_name}/{segments_list[i]}"
                down = f"{chain_name}/{segments_list[i + 1]}"
                G.add_edge(up, down, relation="供给→")
        self._chain_graph = G
        logger.info(f"产业链图谱构建完成: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")
        return G

    def get_upstream(self, chain_name: str, concept: str) -> List[str]:
        if self._chain_graph is None:
            self.build_chain_graph()
        upstream = []
        for predecessor in self._chain_graph.predecessors(concept):
            upstream.append(predecessor)
        return upstream

    def get_downstream(self, chain_name: str, concept: str) -> List[str]:
        if self._chain_graph is None:
            self.build_chain_graph()
        downstream = []
        for successor in self._chain_graph.successors(concept):
            downstream.append(successor)
        return downstream

    def find_chain_for_stock(
        self, stock_concepts: List[str]
    ) -> List[Dict[str, str]]:
        results = []
        all_sub_industries = self.get_all_sub_industries()
        for concept in stock_concepts:
            if concept in all_sub_industries:
                for chain_name, segments in self.chain_map.items():
                    for segment_name, sub_industries in segments.items():
                        if concept in sub_industries:
                            results.append({
                                "chain": chain_name,
                                "segment": segment_name,
                                "sub_industry": concept,
                            })
        return results