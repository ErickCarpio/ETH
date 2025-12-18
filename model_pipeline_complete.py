"""
Model Pipeline - Pipeline Completo de Entrenamiento
Incluye: Descarga de datos, feature engineering, target labeling, entrenamiento y evaluación
ACTUALIZADO: Soporte para 15MIN + 4H macro
"""

import xgboost as xgb
import optuna
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit, train_test_split
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.utils.class_weight import compute_class_weight
from typing import Dict, Optional
import joblib
import logging
import warnings
from pathlib import Path
import json
import sys

# Imports locales
from feature_engineering import FeatureEngineer
from target_labeling import RegimeLabeler
from weighting_logic import TemporalWeighting

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


class XGBoostRegimeModel:

    def __init__(self,
                 n_classes: int = 3,
                 optuna_trials: int = 50,
                 model_dir: str = "./models"):
        self.n_classes = n_classes
        self.optuna_trials = optuna_trials
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True)

        self.model = None
        self.best_params = None
        self.feature_importance = None

    def _calculate_balanced_weights(self, y_train, temporal_weights):
        """Combina pesos temporales con pesos de clase para corregir desbalance"""
        classes = np.unique(y_train)
        class_weights = compute_class_weight(
            class_weight='balanced',
            classes=classes,
            y=y_train
        )
        class_weight_dict = dict(zip(classes, class_weights))
        sample_class_weights = np.array([class_weight_dict[y] for y in y_train])
        final_weights = temporal_weights * sample_class_weights
        return final_weights

    def optimize_hyperparameters(self, X_train, y_train, sample_weights, n_splits=3):
        logger.info(f"Iniciando optimización ({self.optuna_trials} trials)...")
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        balanced_weights = self._calculate_balanced_weights(y_train, sample_weights)

        def objective(trial):
            params = {
                'objective': 'multi:softmax',
                'num_class': self.n_classes,
                'eval_metric': 'mlogloss',
                'tree_method': 'hist',
                'device': 'cpu',
                'max_depth': trial.suggest_int('max_depth', 3, 12),
                'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.3, log=True),
                'n_estimators': trial.suggest_int('n_estimators', 100, 800),
                'min_child_weight': trial.suggest_int('min_child_weight', 1, 20),
                'subsample': trial.suggest_float('subsample', 0.5, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
                'gamma': trial.suggest_float('gamma', 0, 10),
                'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 20.0, log=True),
                'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 20.0, log=True),
            }

            tscv = TimeSeriesSplit(n_splits=n_splits)
            scores = []

            for train_idx, val_idx in tscv.split(X_train):
                X_f_train = X_train.iloc[train_idx]
                y_f_train = y_train.iloc[train_idx]
                w_f_train = balanced_weights[train_idx]

                X_f_val = X_train.iloc[val_idx]
                y_f_val = y_train.iloc[val_idx]

                model = xgb.XGBClassifier(**params, random_state=42)
                model.fit(X_f_train, y_f_train, sample_weight=w_f_train, verbose=False)

                y_pred = model.predict(X_f_val)
                score = f1_score(y_f_val, y_pred, average='weighted')
                scores.append(score)

            return np.mean(scores)

        study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=self.optuna_trials, show_progress_bar=True)

        self.best_params = study.best_params
        self.best_params.update({
            'objective': 'multi:softmax',
            'num_class': self.n_classes,
            'eval_metric': 'mlogloss',
            'tree_method': 'hist',
            'device': 'cpu',
            'random_state': 42
        })

        logger.info(f"Optimización completada. Best F1: {study.best_value:.4f}")
        return self.best_params

    def train(self, X_train, y_train, sample_weights, X_val=None, y_val=None, optimize=True):
        logger.info("=" * 60)
        logger.info("ENTRENAMIENTO DE MODELO (BALANCEADO)")
        logger.info("=" * 60)

        final_weights = self._calculate_balanced_weights(y_train, sample_weights)

        if optimize or self.best_params is None:
            self.optimize_hyperparameters(X_train, y_train, sample_weights)

        logger.info("Entrenando modelo final...")
        self.model = xgb.XGBClassifier(**self.best_params)

        eval_set = [(X_train, y_train)]
        if X_val is not None and y_val is not None:
            eval_set.append((X_val, y_val))

        self.model.fit(
            X_train, y_train,
            sample_weight=final_weights,
            eval_set=eval_set,
            verbose=False
        )

        self.feature_importance = pd.DataFrame({
            'feature': X_train.columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)

        logger.info(f"\nTop Features:\n{self.feature_importance.head(5).to_string(index=False)}")

        if X_val is not None and y_val is not None:
            y_val_pred = self.model.predict(X_val)

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                logger.info("\nReporte de Clasificación (Validación):")
                print(classification_report(y_val, y_val_pred, zero_division=0))

        return self.model

    def predict(self, X): return self.model.predict(X)
    def predict_proba(self, X): return self.model.predict_proba(X)

    def save_model(self, model_name="xgboost_model.json"):
        if self.model is None: return
        model_path = self.model_dir / model_name
        self.model.save_model(model_path)

        metadata = {
            'best_params': self.best_params,
            'feature_importance': self.feature_importance.to_dict(),
            'n_classes': self.n_classes
        }
        joblib.dump(metadata, self.model_dir / f"{model_name.replace('.json', '_metadata.pkl')}")
        logger.info(f"Modelo guardado en: {model_path}")

    def load_model(self, model_name="xgboost_model.json"):
        model_path = self.model_dir / model_name
        if not model_path.exists(): raise FileNotFoundError(f"Modelo no encontrado: {model_path}")

        self.model = xgb.XGBClassifier()
        self.model.load_model(model_path)

        metadata_path = self.model_dir / f"{model_name.replace('.json', '_metadata.pkl')}"
        if metadata_path.exists():
            metadata = joblib.load(metadata_path)
            self.best_params = metadata['best_params']
            self.feature_importance = pd.DataFrame(metadata['feature_importance'])
            self.n_classes = metadata['n_classes']
        logger.info(f"Modelo cargado desde: {model_path}")


def download_binance_data(symbol='ETHUSDT', timeframe='15m', limit=5000):
    """Descarga datos de Binance"""
    import ccxt

    exchange = ccxt.binance({'enableRateLimit': True})

    logger.info(f"Descargando {limit} velas de {symbol} ({timeframe})...")

    # Calcular milliseconds por vela según timeframe
    timeframe_ms = {
        '1m': 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '30m': 30 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000,
    }

    candle_ms = timeframe_ms.get(timeframe, 15 * 60 * 1000)  # Default 15min

    all_candles = []
    since = exchange.milliseconds() - (limit * candle_ms)

    while len(all_candles) < limit:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not candles:
                break
            all_candles.extend(candles)
            since = candles[-1][0] + 1
        except Exception as e:
            logger.error(f"Error descargando: {e}")
            break

    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)

    # Limitar a las últimas 'limit' velas
    if len(df) > limit:
        df = df.iloc[-limit:]

    logger.info(f"✓ Descargado {len(df)} velas ({df.index[0]} a {df.index[-1]})")

    return df


def main():
    """Pipeline principal de entrenamiento"""
    logger.info("=" * 80)
    logger.info("INICIANDO PIPELINE DE ENTRENAMIENTO - 1H + 1D MACRO")
    logger.info("=" * 80)

    # 1. Cargar configuración
    logger.info("\n1. Cargando configuración...")
    try:
        # Intentar cargar config_15min.json
        config_path = Path('config_15min.json')
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info("✓ Configuración cargada desde config_15min.json")
        else:
            raise FileNotFoundError("config_15min.json no encontrado")
    except:
        logger.warning("No se pudo cargar config_15min.json, usando valores por defecto")
        config = {
            'exchange': {'symbol': 'ETHUSDT'},
            'data': {'timeframe': '15m'},
            'model': {
                'n_classes': 3,
                'forward_window': 16,
                'optuna_trials': 100
            }
        }

    symbol = config.get('exchange', {}).get('symbol', 'ETHUSDT')
    timeframe = config.get('data', {}).get('timeframe', '15m')
    n_classes = config.get('model', {}).get('n_classes', 3)
    optuna_trials = config.get('model', {}).get('optuna_trials', 100)
    forward_window = config.get('model', {}).get('forward_window', 16)

    logger.info(f"   ✓ Symbol: {symbol}")
    logger.info(f"   ✓ Timeframe: {timeframe}")
    logger.info(f"   ✓ N_classes: {n_classes}")
    logger.info(f"   ✓ Forward window: {forward_window}")
    logger.info(f"   ✓ Optuna trials: {optuna_trials}")

    # 2. Descargar datos
    logger.info("\n2. Descargando datos...")

    # 1H para trading (10000 velas ≈ 417 días ≈ 1.1 años)
    df_1h = download_binance_data(symbol, timeframe='1h', limit=10000)
    logger.info(f"   ✓ Datos 1H: {len(df_1h)} velas ({len(df_1h)/24:.0f} días)")

    # 1D para contexto macro (730 velas = 2 años)
    df_1d = download_binance_data(symbol, timeframe='1d', limit=730)
    logger.info(f"   ✓ Datos 1D: {len(df_1d)} velas ({len(df_1d)/365:.1f} años)")

    # 3. Generar features
    logger.info("\n3. Generando features...")
    fe = FeatureEngineer()

    # Features de 1H + features macro de 1D
    features_df = fe.build_full_features(
        crypto_df=df_1h,
        macro_df=None,  # Si tienes BTCDOM, pásalo aquí
        crypto_4h_df=df_1d  # Contexto macro (usa param crypto_4h_df pero con datos 1D)
    )

    logger.info(f"   ✓ Features generadas: {features_df.shape}")
    logger.info(f"   ✓ Período: {features_df.index[0]} a {features_df.index[-1]}")

    # 4. Crear targets
    logger.info("\n4. Creando targets...")
    # ESTRATEGIA: CALIDAD sobre CANTIDAD
    # Capturar MENOS señales pero REALES (no ruido)
    # - forward_window: 12 velas × 1H = 12h (tendencias significativas)
    # - trend_threshold: 2.5% (movimientos grandes y claros)
    # - volatility_threshold_low: 0.018 (1.8% - muy selectivo)
    #
    # Objetivo: 70-75% NO_TRADE, pero cuando dice LONG/SHORT que sea CONFIABLE
    labeler = RegimeLabeler(
        forward_window=12,  # 12 velas × 1H = 12 horas (tendencias claras y reales)
        volatility_threshold_low=0.018,  # 1.8% - MUY selectivo para lateral
        volatility_threshold_high=0.055,  # 5.5% - umbral para volatilidad extrema
        trend_threshold=0.025  # 2.5% - solo movimientos SIGNIFICATIVOS en 12h
    )

    # Preparar datos para labeling
    price_df = df_1h[['open', 'high', 'low', 'close']].copy()
    labeled_df = labeler.label_regime(price_df)

    # Alinear targets con features
    common_idx = features_df.index.intersection(labeled_df.index)
    features_df = features_df.loc[common_idx]
    targets = labeled_df.loc[common_idx, 'regime']

    logger.info(f"   ✓ Targets creados: {len(targets)}")
    logger.info(f"   ✓ Distribución de clases:")
    for cls in sorted(targets.unique()):
        count = (targets == cls).sum()
        pct = count / len(targets) * 100
        logger.info(f"      Clase {int(cls)}: {count:4d} ({pct:5.1f}%)")

    # 5. Calcular pesos de muestras
    logger.info("\n5. Calculando pesos de muestras...")
    try:
        # Usar TemporalWeighting para calcular pesos
        weighting = TemporalWeighting(
            decay_rate=0.001,
            min_weight=0.1,
            max_weight=1.0,
            recent_days=7
        )
        sample_weights = weighting.calculate_weights(features_df)
    except Exception as e:
        logger.warning(f"Error calculando pesos: {e}")
        # Fallback simple
        sample_weights = np.ones(len(features_df))
        decay_factor = np.linspace(0.1, 1.0, len(sample_weights))
        sample_weights = sample_weights * decay_factor

    logger.info(f"   ✓ Pesos calculados: {len(sample_weights)}")
    logger.info(f"   ✓ Peso promedio: {sample_weights.mean():.4f}")
    logger.info(f"   ✓ Peso min/max: {sample_weights.min():.4f} / {sample_weights.max():.4f}")

    # 6. Preparar datos
    logger.info("\n6. Preparando datos...")

    # Remover NaNs
    valid_mask = ~(features_df.isna().any(axis=1) | targets.isna())
    X = features_df[valid_mask]
    y = targets[valid_mask]
    weights = sample_weights[valid_mask]

    logger.info(f"   ✓ Muestras válidas: {len(X)} / {len(features_df)}")
    logger.info(f"   ✓ Features finales: {X.shape[1]}")

    # Split temporal
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]
    w_train, w_val = weights[:split_idx], weights[split_idx:]

    logger.info(f"   ✓ Train: {len(X_train)} muestras")
    logger.info(f"   ✓ Val:   {len(X_val)} muestras")

    # 7. Entrenar modelo
    logger.info("\n7. Entrenando modelo...")
    model = XGBoostRegimeModel(
        n_classes=n_classes,
        optuna_trials=optuna_trials
    )

    try:
        model.train(X_train, y_train, w_train, X_val, y_val, optimize=True)
        logger.info("   ✓ Modelo entrenado exitosamente")
    except Exception as e:
        logger.error(f"   ✗ Error entrenando modelo: {e}")
        import traceback
        traceback.print_exc()
        return

    # 8. Guardar modelo
    logger.info("\n8. Guardando modelo...")
    model.save_model("xgboost_model.json")
    logger.info("   ✓ Modelo guardado en: models/xgboost_model.json")

    # Resumen final
    logger.info("\n" + "=" * 80)
    logger.info("ENTRENAMIENTO COMPLETADO")
    logger.info("=" * 80)
    logger.info(f"✓ Timeframe: {timeframe}")
    logger.info(f"✓ Features: {X.shape[1]}")
    logger.info(f"✓ Muestras train: {len(X_train)}")
    logger.info(f"✓ Muestras val: {len(X_val)}")
    logger.info(f"✓ Modelo guardado: models/xgboost_model.json")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
