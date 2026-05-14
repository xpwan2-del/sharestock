"""
关联网络分析模块 - 支持股票相关性矩阵、产业链影响传播、市场状态聚类
"""
import numpy as np
import pandas as pd
import networkx as nx
from typing import Dict, List, Optional, Tuple, Any
from loguru import logger
from sklearn.preprocessing import RobustScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.industry_chain import INDUSTRY_CHAIN_MAP, IndustryChainCollector
from data.market_data import MarketDataCollector
from utils.calendar import get_latest_trading_day


class CorrelationNetworkAnalyzer:
    """
    关联网络分析器
    提供股票相关性矩阵、产业链网络传播、市场状态聚类等功能
    """

    def __init__(self):
        self.market = MarketDataCollector()
        self.chain_collector = IndustryChainCollector()
        self.scaler = RobustScaler()
        self._pca: Optional[PCA] = None
        self._kmeans: Optional[KMeans] = None

    def build_correlation_matrix(
        self,
        stock_codes: List[str],
        lookback_days: int = 60,
        price_col: str = "close",
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        构建股票收益率相关性矩阵

        Returns:
            corr_matrix: 相关性矩阵 (DataFrame, index/columns 为股票代码)
            returns_df: 日收益率矩阵 (用于后续分析)
        """
        end_date = pd.Timestamp.now().strftime("%Y%m%d")
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=lookback_days + 10)).strftime("%Y%m%d")

        all_returns = {}
        for code in stock_codes[:50]:  # 限制数量避免请求过载
            try:
                kline = self.market.get_daily_kline(code, start_date, end_date)
                if kline.empty or price_col not in kline.columns:
                    continue
                kline = kline.set_index("date")
                returns = kline[price_col].pct_change().dropna()
                if len(returns) >= 20:  # 至少需要20个交易日
                    all_returns[code] = returns
            except Exception as e:
                logger.warning(f"获取 {code} 收益率数据失败: {e}")

        if len(all_returns) < 3:
            logger.warning("有效收益率数据不足，无法计算相关性")
            return pd.DataFrame(), pd.DataFrame()

        returns_df = pd.DataFrame(all_returns).dropna()
        if returns_df.empty or returns_df.shape[1] < 2:
            return pd.DataFrame(), pd.DataFrame()

        corr_matrix = returns_df.corr(method="pearson")
        logger.info(f"相关性矩阵构建完成: {corr_matrix.shape[0]}x{corr_matrix.shape[1]}")
        return corr_matrix, returns_df

    def build_correlation_from_quotes(
        self,
        quotes: pd.DataFrame,
        top_n: int = 30,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        从实时行情数据模拟构建相关性矩阵
        使用技术指标特征代替历史收益率

        Returns:
            corr_matrix: 近似相关性矩阵
            feature_matrix: 特征矩阵
            selected_quotes: 选中的股票行情
        """
        if quotes is None or quotes.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        q = quotes.copy()

        # 列名映射：处理 AKShare limit_up_pool 等不同数据源的列名
        col_mapping = {
            "涨跌幅": "pct_chg", "振幅": "amplitude",
            "换手率": "turnover", "量比": "volume_ratio",
            "成交额": "amount", "最新价": "price",
            "代码": "code", "名称": "name",
            "封板资金": "limit_amount", "连板数": "consecutive",
        }
        for old_col, new_col in col_mapping.items():
            if old_col in q.columns and new_col not in q.columns:
                q[new_col] = q[old_col]

        # 筛选有足够字段的股票
        feature_cols = ["pct_chg", "amplitude", "turnover", "volume_ratio"]
        available_cols = [c for c in feature_cols if c in q.columns]
        if len(available_cols) < 2:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        q = q.dropna(subset=available_cols)

        # 按成交额取 top_n
        if "amount" in q.columns:
            q = q.nlargest(top_n, "amount")
        else:
            q = q.head(top_n)

        if q.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        feature_mat = q[available_cols].copy()
        for col in available_cols:
            # 标准化到 [0,1]
            min_v = feature_mat[col].min()
            max_v = feature_mat[col].max()
            if max_v > min_v:
                feature_mat[col] = (feature_mat[col] - min_v) / (max_v - min_v)
            else:
                feature_mat[col] = 0.5

        # 使用特征向量余弦相似度作为近似相关性
        feat_np = feature_mat.values
        norms = np.linalg.norm(feat_np, axis=1, keepdims=True)
        norms[norms == 0] = 1
        feat_normalized = feat_np / norms
        sim_matrix = np.dot(feat_normalized, feat_normalized.T)
        sim_matrix = np.clip(sim_matrix, -1, 1)

        name_col = "name" if "name" in q.columns else "code"
        labels = q[name_col].values if name_col in q.columns else q["code"].values
        corr_df = pd.DataFrame(sim_matrix, index=labels, columns=labels)

        logger.info(f"近似相关性矩阵构建完成: {corr_df.shape[0]}x{corr_df.shape[1]}")
        return corr_df, feature_mat, q

    def build_influence_graph(
        self,
        concept_board: pd.DataFrame,
        limit_up_pool: pd.DataFrame,
    ) -> Tuple[nx.DiGraph, Dict[str, Any]]:
        """
        构建产业链影响力传播图

        Returns:
            G: networkx 有向图
            influence_metrics: 影响力指标字典
        """
        # 基础产业链图
        base_graph = self.chain_collector.build_chain_graph()

        # 计算节点影响力权重
        pct_col = None
        for col in ["涨跌幅", "pct_chg"]:
            if col in concept_board.columns:
                pct_col = col
                break
        name_col = None
        for col in ["板块名称", "name"]:
            if col in concept_board.columns:
                name_col = col
                break

        concept_pct_map = {}
        if pct_col and name_col and concept_board is not None and not concept_board.empty:
            for _, row in concept_board.iterrows():
                concept_pct_map[row[name_col]] = float(row[pct_col])

        # 限制涨停数量
        limit_up_count = 0
        if limit_up_pool is not None and not limit_up_pool.empty:
            limit_up_count = len(limit_up_pool)

        # 增强图：添加影响力权重
        G = nx.DiGraph()

        for chain_name, segments in INDUSTRY_CHAIN_MAP.items():
            chain_root = f"产业链:{chain_name}"
            G.add_node(
                chain_root,
                node_type="chain_root",
                chain=chain_name,
                size=30,
                weight=1.0,
            )

            seg_names = list(segments.keys())
            total_segments = len(seg_names)

            for i, (segment_name, sub_industries) in enumerate(segments.items()):
                seg_node = f"{chain_name}/{segment_name}"

                # 计算环节热度权重
                seg_pct_sum = 0.0
                seg_count = 0
                for sub in sub_industries:
                    if sub in concept_pct_map:
                        seg_pct_sum += abs(concept_pct_map[sub])
                        seg_count += 1

                seg_avg_pct = seg_pct_sum / max(seg_count, 1)
                seg_weight = min(1.0, (seg_avg_pct / 5.0 + 0.3))

                G.add_node(
                    seg_node,
                    node_type="segment",
                    chain=chain_name,
                    segment=segment_name,
                    size=15 + seg_count * 2,
                    weight=seg_weight,
                    avg_pct=seg_avg_pct,
                    sub_count=seg_count,
                )

                # 层级位置
                position = i / max(total_segments - 1, 1)
                G.add_edge(
                    chain_root, seg_node,
                    relation="产业链结构",
                    weight=0.8,
                    position=position,
                )

                for sub in sub_industries:
                    sub_pct = concept_pct_map.get(sub, 0.0)
                    sub_weight = min(1.0, (abs(sub_pct) / 5.0 + 0.2))

                    G.add_node(
                        sub,
                        node_type="concept",
                        chain=chain_name,
                        segment=segment_name,
                        size=8,
                        weight=sub_weight,
                        pct_chg=sub_pct,
                    )

                    G.add_edge(
                        seg_node, sub,
                        relation="包含",
                        weight=sub_weight,
                    )

            # 添加上中下游传播边
            for i in range(len(seg_names) - 1):
                up_node = f"{chain_name}/{seg_names[i]}"
                down_node = f"{chain_name}/{seg_names[i + 1]}"
                if up_node in G and down_node in G:
                    G.add_edge(
                        up_node, down_node,
                        relation="影响传播",
                        weight=0.6,
                    )

        influence_metrics = {
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "num_chains": len(INDUSTRY_CHAIN_MAP),
            "limit_up_count": limit_up_count,
        }

        # 计算中心性指标
        if G.number_of_nodes() > 0:
            try:
                betweenness = nx.betweenness_centrality(G, weight="weight", normalized=True)
                G.graph["betweenness"] = betweenness
                influence_metrics["top_influencers"] = sorted(
                    betweenness.items(), key=lambda x: x[1], reverse=True
                )[:10]
            except Exception:
                pass

        logger.info(f"影响力传播图构建完成: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")
        return G, influence_metrics

    def cluster_market_state(
        self,
        quotes: pd.DataFrame,
        n_clusters: int = 5,
    ) -> Dict[str, Any]:
        """
        对市场状态进行聚类分析

        Returns:
            cluster_result: 聚类结果字典，包含 labels, centroids, projections
        """
        if quotes is None or quotes.empty:
            return {"success": False, "error": "无行情数据"}

        q = quotes.copy()

        # 列名映射：处理不同的数据源格式
        col_mapping = {
            "涨跌幅": "pct_chg", "振幅": "amplitude",
            "换手率": "turnover", "量比": "volume_ratio",
            "成交额": "amount", "最新价": "price",
            "代码": "code", "名称": "name",
        }
        for old_col, new_col in col_mapping.items():
            if old_col in q.columns and new_col not in q.columns:
                q[new_col] = q[old_col]

        # 特征选择
        feature_cols = ["pct_chg", "amplitude", "turnover", "volume_ratio"]
        available_cols = [c for c in feature_cols if c in q.columns]
        if len(available_cols) < 2:
            return {"success": False, "error": "可用特征不足"}

        q = q.dropna(subset=available_cols)
        if len(q) < n_clusters:
            return {"success": False, "error": f"样本数量不足 (需要至少 {n_clusters} 只)"}

        X = q[available_cols].values.astype(np.float64)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        for col_idx in range(X.shape[1]):
            col_data = X[:, col_idx]
            p1, p99 = np.percentile(col_data, [1, 99])
            if p99 > p1:
                X[:, col_idx] = np.clip(col_data, p1, p99)
        X = np.clip(X, -1e6, 1e6)

        try:
            X_scaled = self.scaler.fit_transform(X)
            X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
            X_scaled = np.clip(X_scaled, -10, 10)
            X_scaled = X_scaled.astype(np.float32)
        except Exception as e:
            logger.warning(f"特征标准化失败: {e}")
            return {"success": False, "error": str(e)}

        self._pca = PCA(n_components=2)
        try:
            with np.errstate(all="ignore"):
                X_pca = self._pca.fit_transform(X_scaled)
            X_pca = np.nan_to_num(X_pca, nan=0.0, posinf=0.0, neginf=0.0)
            X_pca = np.clip(X_pca, -1e6, 1e6).astype(np.float32)
            explained_var = np.nan_to_num(self._pca.explained_variance_ratio_, nan=0.0, posinf=0.0, neginf=0.0)
        except Exception:
            X_pca = X_scaled[:, :2]
            explained_var = np.array([0.5, 0.3])

        self._kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        try:
            with np.errstate(all="ignore"):
                labels = self._kmeans.fit_predict(X_scaled)
                centroids_2d = self._pca.transform(self._kmeans.cluster_centers_)
            centroids_2d = np.nan_to_num(centroids_2d, nan=0.0, posinf=0.0, neginf=0.0)
            centroids_2d = np.clip(centroids_2d, -1e6, 1e6).astype(np.float32)
        except Exception as e:
            logger.warning(f"聚类失败: {e}")
            # 回退：根据涨跌幅分桶
            labels = pd.qcut(q["pct_chg"], n_clusters, labels=False, duplicates="drop")
            centroids_2d = np.zeros((n_clusters, 2))
            for i in range(n_clusters):
                mask = labels == i
                if mask.any():
                    centroids_2d[i] = X_pca[mask].mean(axis=0)

        # 构建结果
        name_col = "name" if "name" in q.columns else "code"
        code_col = "code"

        cluster_result = {
            "success": True,
            "labels": labels.tolist(),
            "x": X_pca[:, 0].tolist(),
            "y": X_pca[:, 1].tolist(),
            "names": q[name_col].tolist() if name_col in q.columns else q[code_col].tolist(),
            "codes": q[code_col].tolist(),
            "centroids_x": centroids_2d[:, 0].tolist(),
            "centroids_y": centroids_2d[:, 1].tolist(),
            "explained_var": explained_var.tolist(),
            "n_clusters": n_clusters,
            "n_samples": len(q),
        }

        # 各簇统计信息
        cluster_stats = []
        for i in range(n_clusters):
            mask = labels == i
            cluster_q = q.iloc[mask]
            stat = {
                "cluster_id": i,
                "count": int(mask.sum()),
                "avg_pct": round(float(cluster_q["pct_chg"].mean()), 2) if "pct_chg" in q.columns else 0,
                "avg_turnover": round(float(cluster_q["turnover"].mean()), 2) if "turnover" in q.columns else 0,
                "avg_amplitude": round(float(cluster_q["amplitude"].mean()), 2) if "amplitude" in q.columns else 0,
                "avg_volume_ratio": round(float(cluster_q["volume_ratio"].mean()), 2) if "volume_ratio" in q.columns else 0,
                "top_stocks": (
                    cluster_q.nlargest(3, "amount")[name_col].tolist()
                    if "amount" in q.columns and name_col in q.columns
                    else cluster_q.head(3)[code_col].tolist()
                ),
            }
            cluster_stats.append(stat)

        cluster_result["cluster_stats"] = cluster_stats
        logger.info(f"市场状态聚类完成: {n_clusters} 簇, {len(q)} 样本")

        return cluster_result

    def cluster_market_regime(
        self, kline_data: pd.DataFrame = None, n_clusters: int = 5
    ) -> Dict[str, Any]:
        """
        市场状态聚类（兼容方法）
        如果传了 kline_data 则按日频聚类，否则用实时行情
        """
        if kline_data is not None and not kline_data.empty:
            return self._cluster_from_kline(kline_data, n_clusters)
        quotes = self.market.get_realtime_quotes()
        if quotes is None or quotes.empty:
            from data.dragon_tiger import DragonTigerCollector
            dt = DragonTigerCollector()
            quotes = dt.get_daily_dragon_tiger(get_latest_trading_day())
            if quotes is not None and not quotes.empty:
                # 龙虎榜数据没有 pct_chg 等列，尝试聚类或返回简单结果
                try:
                    return self.cluster_market_state(quotes, n_clusters)
                except Exception:
                    pass
            # 最终回退：返回空结果但标记为成功（周末正常）
            logger.info("市场状态聚类回退：周末无实时数据，返回默认结果")
            return {"success": True, "labels": list(range(n_clusters)),
                    "n_clusters": n_clusters, "n_samples": 0,
                    "fallback": True, "message": "周末无实时数据"}
        return self.cluster_market_state(quotes, n_clusters)

    def _cluster_from_kline(self, kline_data: pd.DataFrame, n_clusters: int = 5) -> Dict[str, Any]:
        feats = kline_data.select_dtypes(include=["float64", "float32", "int64", "int32"])
        if feats.empty or len(feats) < n_clusters:
            return {"success": False, "error": "特征数据不足"}
        from sklearn.decomposition import PCA
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import RobustScaler
        X = feats.values.astype(np.float64)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        for col_idx in range(X.shape[1]):
            col_data = X[:, col_idx]
            p1, p99 = np.percentile(col_data, [1, 99])
            if p99 > p1:
                X[:, col_idx] = np.clip(col_data, p1, p99)
        X = np.clip(X, -1e6, 1e6)
        scaler = RobustScaler()
        try:
            X_scaled = scaler.fit_transform(X)
            X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
            X_scaled = np.clip(X_scaled, -10, 10).astype(np.float32)
        except Exception as e:
            return {"success": False, "error": str(e)}
        pca = PCA(n_components=2)
        try:
            with np.errstate(all="ignore"):
                X_pca = pca.fit_transform(X_scaled)
            X_pca = np.nan_to_num(X_pca, nan=0.0, posinf=0.0, neginf=0.0)
            X_pca = np.clip(X_pca, -1e6, 1e6).astype(np.float32)
        except Exception:
            X_pca = X_scaled[:, :2]
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        try:
            with np.errstate(all="ignore"):
                labels = km.fit_predict(X_pca)
        except Exception:
            labels = pd.qcut(pd.Series(X_pca[:, 0]), n_clusters, labels=False, duplicates="drop").fillna(0).astype(int).values
        names = [f"T-{i}" for i in range(len(labels))]
        return {
            "success": True, "labels": labels.tolist(),
            "x": X_pca[:, 0].tolist(), "y": X_pca[:, 1].tolist(),
            "names": names, "n_clusters": n_clusters, "n_samples": len(kline_data),
        }

    def calculate_factor_importance(
        self,
        quotes: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        计算因子重要性（模拟神经网络权重分析）
        基于特征方差和与涨跌幅的相关性

        Returns:
            importance_df: 因子重要性 DataFrame
        """
        if quotes is None or quotes.empty:
            return pd.DataFrame()

        q = quotes.copy()

        # 候选因子
        factor_candidates = {
            "涨跌幅动量(pct_chg)": "pct_chg",
            "振幅(amplitude)": "amplitude",
            "换手率(turnover)": "turnover",
            "量比(volume_ratio)": "volume_ratio",
            "市盈率(pe_ttm)": "pe_ttm",
            "市净率(pb)": "pb",
            "总市值(total_mv)": "total_mv",
            "流通市值(float_mv)": "float_mv",
            "60日涨跌幅(pct_chg_60d)": "pct_chg_60d",
            "年初至今涨跌幅(pct_chg_ytd)": "pct_chg_ytd",
        }

        available_factors = {}
        for display_name, col_name in factor_candidates.items():
            if col_name in q.columns:
                available_factors[display_name] = col_name

        if len(available_factors) < 2:
            return pd.DataFrame()

        importance_rows = []
        for display_name, col_name in available_factors.items():
            series = q[col_name].dropna()
            if len(series) < 5:
                continue

            # 方差贡献 (归一化)
            variance = float(series.var())
            std_value = float(series.std())
            mean_value = float(series.mean())

            # 与涨跌幅的相关性
            corr_with_return = 0.0
            if "pct_chg" in q.columns and col_name != "pct_chg":
                valid = q[[col_name, "pct_chg"]].dropna()
                if len(valid) > 5:
                    corr_with_return = float(valid[col_name].corr(valid["pct_chg"]))

            # 信息比率近似
            sharpe_like = mean_value / std_value if std_value > 0 else 0

            # 综合重要性评分 (方差 * 相关性权重)
            importance_raw = variance * (0.5 + 0.5 * abs(corr_with_return))
            importance_raw += abs(sharpe_like) * 0.3 * variance

            importance_rows.append({
                "因子名称": display_name,
                "原始重要性": round(importance_raw, 6),
                "方差": round(variance, 4),
                "标准差": round(std_value, 4),
                "均值": round(mean_value, 4),
                "与涨跌幅相关性": round(corr_with_return, 4),
            })

        if not importance_rows:
            return pd.DataFrame()

        importance_df = pd.DataFrame(importance_rows)

        # 归一化重要性
        raw_sum = importance_df["原始重要性"].sum()
        if raw_sum > 0:
            importance_df["归一化重要性(%)"] = (
                importance_df["原始重要性"] / raw_sum * 100
            ).round(2)
        else:
            importance_df["归一化重要性(%)"] = 0.0

        importance_df = importance_df.sort_values("归一化重要性(%)", ascending=False)
        logger.info(f"因子重要性分析完成: {len(importance_df)} 个因子")

        return importance_df

    def generate_stock_embeddings(
        self,
        quotes: pd.DataFrame,
        n_components: int = 2,
    ) -> Tuple[np.ndarray, List[str]]:
        """
        生成股票嵌入表示（类似 NN embedding）

        Returns:
            embeddings: 降维后的嵌入向量
            labels: 股票标签
        """
        if quotes is None or quotes.empty:
            return np.array([]), []

        feature_cols = [
            "pct_chg", "amplitude", "turnover", "volume_ratio",
            "pe_ttm", "pb", "total_mv", "float_mv",
        ]
        available = [c for c in feature_cols if c in quotes.columns]
        if len(available) < 2:
            return np.array([]), []

        q = quotes.dropna(subset=available)
        X = q[available].values.astype(np.float64)
        X = np.nan_to_num(X, nan=0.0)
        X_scaled = self.scaler.fit_transform(X)

        pca = PCA(n_components=min(n_components, len(available)))
        embeddings = pca.fit_transform(X_scaled)

        name_col = "name" if "name" in q.columns else "code"
        labels = q[name_col].tolist()

        return embeddings, labels