import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime, timedelta
from loguru import logger
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.ensemble import GradientBoostingClassifier

try:
    import lightgbm as lgb
    _HAS_LIGHTGBM = True
except (ImportError, OSError) as e:
    logger.warning(f"LightGBM 不可用 ({e})，回退到 scikit-learn GradientBoostingClassifier")
    lgb = None
    _HAS_LIGHTGBM = False

from config.settings import ML_CONFIG, DATA_DIR
from data.market_data import MarketDataCollector
from utils.cache import disk_cache
from utils.event_bus import get_event_bus
from utils.redis_manager import get_redis_manager

MODEL_DIR = DATA_DIR / "models_cache"
MODEL_DIR.mkdir(exist_ok=True)


class FeatureEngineer:
    def __init__(self):
        self.market = MarketDataCollector()

    def build_features(self, stock_code: str, lookback_days: int = 120) -> pd.DataFrame:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=lookback_days + 100)).strftime("%Y%m%d")
        kline = self.market.get_daily_kline(stock_code, start_date, end_date)
        if kline.empty or len(kline) < 60:
            return pd.DataFrame()
        kline = self.market.calculate_technical_indicators(kline)
        df = kline.copy()
        df["ret_1d"] = df["close"].pct_change()
        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            for window in [5, 10, 20, 60]:
                df[f"{col}_ma{window}_ret"] = df[col] / df[col].shift(window) - 1
        for window in [5, 10, 20]:
            df[f"volatility_{window}d"] = df["ret_1d"].rolling(window).std()
            df[f"volume_ma{window}_ratio"] = df["volume"] / df["volume"].rolling(window).mean()
        df["high_low_ratio"] = (df["high"] - df["low"]) / df["close"]
        df["close_open_ratio"] = df["close"] / df["open"]
        df["daily_range"] = (df["high"] - df["low"]) / df["open"]
        for n in [5, 10, 20, 60]:
            df[f"momentum_{n}d"] = df["close"] / df["close"].shift(n) - 1
            df[f"max_dd_{n}d"] = df["close"].rolling(n).apply(
                lambda x: (x.cummax() - x).max() / x.cummax().max() if x.cummax().max() > 0 else 0
            )
        df["rsi_divergence"] = df["rsi14"] - df["rsi14"].shift(5)
        df["macd_divergence"] = df["macd"] - df["macd"].shift(5)
        for period in [5, 10]:
            df[f"close_ma{period}_dist"] = (df["close"] - df[f"ma{period}"]) / df[f"ma{period}"]
        df["volume_trend"] = df["volume"] / df["volume"].shift(20)
        df["price_position"] = (df["close"] - df["close"].rolling(60).min()) / (
            df["close"].rolling(60).max() - df["close"].rolling(60).min()
        )
        df["target_5d"] = df["close"].shift(-5) / df["close"] - 1
        df["target_direction_5d"] = (df["target_5d"] > 0).astype(int)
        return df.dropna(subset=["target_5d"])


class MLPipeline:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_engineer = FeatureEngineer()
        self.event_bus = get_event_bus()
        self.redis = get_redis_manager()
        self.model_registry: Dict[str, Dict[str, object]] = {}

    def _feature_columns(self, features_df: pd.DataFrame) -> List[str]:
        excluded = [
            "target_5d", "target_direction_5d", "date", "code", "name",
            "open", "high", "low", "close", "volume", "amount",
        ]
        feature_cols = [c for c in features_df.columns if c not in excluded]
        return [c for c in feature_cols if features_df[c].dtype in [np.float64, np.float32, np.int64, np.int32]]

    def _publish_training_event(self, stock_code: str, train_score: float, valid_score: float, model_name: str):
        payload = {
            "stock_code": stock_code,
            "train_score": round(float(train_score), 4),
            "valid_score": round(float(valid_score), 4),
            "model_type": model_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.event_bus.publish("MODEL_TRAINED", payload, source="MLPipeline")
        if getattr(self.redis, "client", None):
            self.redis.hset_dict(f"quant:model:training:{stock_code}", payload, ex=86400)

    def _publish_prediction_event(self, prediction: Dict):
        payload = {**prediction, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self.event_bus.publish("MODEL_PREDICTION_READY", payload, source="MLPipeline")
        if getattr(self.redis, "client", None):
            self.redis.hset_dict(f"quant:model:prediction:{prediction['code']}", payload, ex=86400)

    def train_single_stock(self, stock_code: str) -> Optional[Union[GradientBoostingClassifier, object]]:
        features_df = self.feature_engineer.build_features(stock_code)
        if features_df.empty or len(features_df) < 60:
            logger.warning(f"{stock_code} 特征数据不足，跳过训练")
            return None
        feature_cols = self._feature_columns(features_df)
        X = features_df[feature_cols].values
        y = features_df["target_direction_5d"].values
        X = np.nan_to_num(X, nan=0.0)
        split_idx = int(len(X) * 0.8)
        X_train, X_valid = X[:split_idx], X[split_idx:]
        y_train, y_valid = y[:split_idx], y[split_idx:]
        if len(X_train) < 30:
            return None
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_valid_scaled = scaler.transform(X_valid)

        if _HAS_LIGHTGBM:
            model = lgb.LGBMClassifier(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                num_leaves=31,
                min_child_samples=20,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                verbose=-1,
            )
        else:
            model = GradientBoostingClassifier(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                random_state=42,
            )

        if _HAS_LIGHTGBM:
            model.fit(
                X_train_scaled, y_train,
                eval_set=[(X_valid_scaled, y_valid)],
            )
        else:
            model.fit(X_train_scaled, y_train)
        self.model = model
        self.scaler = scaler
        self.model_registry[stock_code] = {
            "model": model,
            "scaler": scaler,
            "feature_cols": feature_cols,
            "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        train_score = model.score(X_train_scaled, y_train)
        valid_score = model.score(X_valid_scaled, y_valid)
        self._publish_training_event(stock_code, train_score, valid_score, model.__class__.__name__)
        logger.info(f"{stock_code} 模型训练完成, 验证准确率: {valid_score:.3f}")
        return model

    def predict(self, stock_code: str) -> Optional[Dict]:
        registry = self.model_registry.get(stock_code)
        if registry:
            model = registry["model"]
            scaler = registry["scaler"]
            feature_cols = registry["feature_cols"]
        else:
            if self.model is None:
                logger.warning("模型未训练")
                return None
            model = self.model
            scaler = self.scaler
            feature_cols = None
        features_df = self.feature_engineer.build_features(stock_code, lookback_days=30)
        if features_df.empty:
            return None
        feature_cols = feature_cols or self._feature_columns(features_df)
        latest = features_df[feature_cols].iloc[-1:].values
        latest = np.nan_to_num(latest, nan=0.0)
        latest_scaled = scaler.transform(latest)
        proba = model.predict_proba(latest_scaled)[0]
        prediction = {
            "code": stock_code,
            "up_probability": round(float(proba[1]), 4),
            "down_probability": round(float(proba[0]), 4),
            "prediction": "bullish" if proba[1] > 0.55 else ("bearish" if proba[1] < 0.45 else "neutral"),
        }
        self._publish_prediction_event(prediction)
        return prediction

    def predict_batch(self, stock_codes: List[str]) -> Dict[str, Dict]:
        results = {}
        for code in stock_codes:
            try:
                pred = self.predict(code)
                if pred:
                    results[code] = pred
            except Exception as e:
                logger.warning(f"预测 {code} 失败: {e}")
        if results:
            self.event_bus.publish(
                "MODEL_BATCH_PREDICTION_READY",
                {"count": len(results), "codes": list(results.keys()), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                source="MLPipeline",
            )
        return results

    def train_and_predict(self, stock_codes: List[str]) -> Dict[str, Dict]:
        models = self.batch_train(stock_codes)
        return self.predict_batch(list(models.keys()))

    def batch_train(self, stock_codes: List[str]) -> Dict[str, object]:
        models = {}
        for i, code in enumerate(stock_codes):
            try:
                model = self.train_single_stock(code)
                if model is not None:
                    models[code] = model
                if i % 5 == 0:
                    logger.info(f"训练进度: {i + 1}/{len(stock_codes)}")
            except Exception as e:
                logger.warning(f"训练 {code} 失败: {e}")
        logger.info(f"批量训练完成: {len(models)}/{len(stock_codes)} 只股票")
        self.event_bus.publish(
            "MODEL_BATCH_TRAINED",
            {"count": len(models), "codes": list(models.keys()), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
            source="MLPipeline",
        )
        return models
