"""
Model Pipeline - XGBoost con Optuna
CORREGIDO: Balanceo de Clases Automático (Elimina la "pereza" del modelo)
"""

import xgboost as xgb
import optuna
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.utils.class_weight import compute_class_weight
from typing import Dict, Optional
import joblib
import logging
import warnings
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class XGBoostRegimeModel:
    
    def __init__(self, 
                 n_classes: int = 4,
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
        """
        Combina pesos temporales con pesos de clase para corregir desbalance
        """
        # 1. Calcular peso por clase (Inverso a su frecuencia)
        # Las clases raras (Peligro/Tendencia) tendrán peso alto
        classes = np.unique(y_train)
        class_weights = compute_class_weight(
            class_weight='balanced', 
            classes=classes, 
            y=y_train
        )
        class_weight_dict = dict(zip(classes, class_weights))
        
        # 2. Mapear pesos a cada muestra
        sample_class_weights = np.array([class_weight_dict[y] for y in y_train])
        
        # 3. Combinar: Peso Final = Peso Temporal * Peso de Clase
        # Esto asegura que el modelo valore lo reciente Y lo raro
        final_weights = temporal_weights * sample_class_weights
        
        return final_weights
        
    def optimize_hyperparameters(self, X_train, y_train, sample_weights, n_splits=3):
        logger.info(f"Iniciando optimización ({self.optuna_trials} trials)...")
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        
        # Calcular pesos balanceados una sola vez
        balanced_weights = self._calculate_balanced_weights(y_train, sample_weights)
        
        def objective(trial):
            params = {
                'objective': 'multi:softmax',
                'num_class': self.n_classes,
                'eval_metric': 'mlogloss',
                'tree_method': 'hist',
                'device': 'cpu',
                # Espacio de búsqueda ajustado para manejo de desbalance
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
                # Usar pesos balanceados en el fold
                w_f_train = balanced_weights[train_idx]
                
                X_f_val = X_train.iloc[val_idx]
                y_f_val = y_train.iloc[val_idx]
                
                model = xgb.XGBClassifier(**params, random_state=42)
                model.fit(X_f_train, y_f_train, sample_weight=w_f_train, verbose=False)
                
                y_pred = model.predict(X_f_val)
                # F1 Weighted es mejor métrica para desbalance
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
        
        # Aplicar balanceo de clases
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
            sample_weight=final_weights, # Usar pesos combinados (Tiempo + Clase)
            eval_set=eval_set,
            verbose=False
        )
        
        # Feature importance
        self.feature_importance = pd.DataFrame({
            'feature': X_train.columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        logger.info(f"\nTop Features:\n{self.feature_importance.head(5).to_string(index=False)}")
        
        if X_val is not None and y_val is not None:
            y_val_pred = self.model.predict(X_val)
            
            # Silenciar warnings para reporte limpio
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                logger.info("\nReporte de Clasificación (Validación):")
                print(classification_report(y_val, y_val_pred, zero_division=0))
        
        return self.model
    
    def predict(self, X): return self.model.predict(X)
    def predict_proba(self, X): return self.model.predict_proba(X)
    
    def save_model(self, model_name="xgboost_regime_model.json"):
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
    
    def load_model(self, model_name="xgboost_regime_model.json"):
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
    
    def retrain_daily(self, X_new, y_new, sample_weights, quick_optimization=True):
        logger.info("INICIO DE RE-ENTRENAMIENTO")
        original_trials = self.optuna_trials
        if quick_optimization: self.optuna_trials = 20

        self.train(X_new, y_new, sample_weights, optimize=True)

        self.optuna_trials = original_trials
        timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        self.save_model(f"model_retrain_{timestamp}.json")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    import json
    from feature_engineering import generate_features
    from target_labeling import label_regime_targets
    from weighting_logic import calculate_sample_weights

    logger.info("="*80)
    logger.info("INICIANDO PIPELINE DE ENTRENAMIENTO")
    logger.info("="*80)

    # 1. Cargar configuración
    logger.info("\n1. Cargando configuración...")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)

        symbol = config['exchange']['symbol']
        n_classes = config['model']['n_classes']
        optuna_trials = config['model']['optuna_trials']

        logger.info(f"   ✓ Symbol: {symbol}")
        logger.info(f"   ✓ N_classes: {n_classes}")
        logger.info(f"   ✓ Optuna trials: {optuna_trials}")
    except Exception as e:
        logger.warning(f"   ⚠️ Error cargando config: {e}")
        logger.info("   → Usando valores por defecto")
        symbol = 'ETHUSDT'
        n_classes = 4
        optuna_trials = 1000

    # 2. Generar features
    logger.info("\n2. Generando features...")
    logger.info(f"   Descargando datos de {symbol}...")

    try:
        df_features = generate_features(symbol=symbol)
        logger.info(f"   ✓ Features generadas: {df_features.shape}")
        logger.info(f"   ✓ Período: {df_features.index[0]} a {df_features.index[-1]}")
    except Exception as e:
        logger.error(f"   ✗ Error generando features: {e}")
        import traceback
        traceback.print_exc()
        raise

    # 3. Crear targets
    logger.info("\n3. Creando targets...")

    try:
        # Necesitamos el precio para crear targets
        if 'close' not in df_features.columns:
            import ccxt
            exchange = ccxt.binance()
            ohlcv = exchange.fetch_ohlcv(
                symbol.replace('USDT', '/USDT'),
                '4h',
                limit=len(df_features) + 10
            )
            prices = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            prices['timestamp'] = pd.to_datetime(prices['timestamp'], unit='ms')
            prices.set_index('timestamp', inplace=True)
            df_features['close'] = prices['close'].reindex(df_features.index)

        # Crear targets usando método del config
        target_method = config.get('model', {}).get('target_method', 'trading_signals')
        target_params = {
            'forward_window': config.get('model', {}).get('forward_window', 6),
            'min_reward_risk': config.get('model', {}).get('min_reward_risk', 2.0),
            'min_move_pct': config.get('model', {}).get('min_move_pct', 0.025),
            'atr_multiplier_sl': config.get('model', {}).get('atr_multiplier_sl', 2.0),
            'atr_multiplier_tp': config.get('model', {}).get('atr_multiplier_tp', 4.0),
        }

        targets = label_regime_targets(
            df_features,
            n_classes=n_classes,
            method=target_method,
            **target_params
        )

        logger.info(f"   ✓ Targets creados: {len(targets)}")
        logger.info(f"   ✓ Distribución de clases:")
        for i in range(n_classes):
            count = (targets == i).sum()
            pct = count / len(targets) * 100
            logger.info(f"      Clase {i}: {count:5d} ({pct:5.1f}%)")

    except Exception as e:
        logger.error(f"   ✗ Error creando targets: {e}")
        import traceback
        traceback.print_exc()
        raise

    # 4. Calcular pesos de muestras
    logger.info("\n4. Calculando pesos de muestras...")

    try:
        sample_weights = calculate_sample_weights(
            df_features,
            method='time_decay',
            half_life_days=30
        )

        logger.info(f"   ✓ Pesos calculados: {len(sample_weights)}")
        logger.info(f"   ✓ Peso promedio: {sample_weights.mean():.4f}")
        logger.info(f"   ✓ Peso min/max: {sample_weights.min():.4f} / {sample_weights.max():.4f}")

    except Exception as e:
        logger.warning(f"   ⚠️ Error calculando pesos: {e}")
        logger.info("   → Usando pesos uniformes")
        sample_weights = np.ones(len(df_features))

    # 5. Preparar datos para entrenamiento
    logger.info("\n5. Preparando datos...")

    valid_idx = (~df_features.isna().any(axis=1)) & (~targets.isna())

    X = df_features[valid_idx].copy()
    y = targets[valid_idx].copy()
    w = sample_weights[valid_idx]

    logger.info(f"   ✓ Muestras válidas: {len(X)} / {len(df_features)}")

    # Eliminar columnas que no deben usarse como features
    columns_to_drop = ['close']

    # CRÍTICO: Eliminar columnas forward-looking que causarían look-ahead bias
    forward_looking_cols = ['tp_pct', 'sl_pct', 'tp_price', 'sl_price', 'reward_risk',
                           'forward_return', 'forward_max', 'forward_min',
                           'forward_volatility', 'upside_pct', 'downside_pct']

    for col in forward_looking_cols:
        if col in X.columns:
            columns_to_drop.append(col)
            logger.info(f"   ⚠️ Eliminando columna forward-looking: {col}")

    X = X.drop(columns=[col for col in columns_to_drop if col in X.columns])

    logger.info(f"   ✓ Features finales: {X.shape[1]}")

    # Split temporal (últimas 20% para validación)
    split_idx = int(len(X) * 0.8)

    X_train = X.iloc[:split_idx]
    X_val = X.iloc[split_idx:]
    y_train = y.iloc[:split_idx]
    y_val = y.iloc[split_idx:]
    w_train = w[:split_idx]

    logger.info(f"   ✓ Train: {len(X_train)} muestras")
    logger.info(f"   ✓ Val:   {len(X_val)} muestras")

    # 6. Entrenar modelo
    logger.info("\n6. Entrenando modelo...")

    try:
        model = XGBoostRegimeModel(
            n_classes=n_classes,
            optuna_trials=optuna_trials,
            model_dir='./models'
        )

        model.train(
            X_train, y_train, w_train,
            X_val, y_val,
            optimize=True
        )

        logger.info("   ✓ Modelo entrenado exitosamente")

    except Exception as e:
        logger.error(f"   ✗ Error entrenando modelo: {e}")
        import traceback
        traceback.print_exc()
        raise

    # 7. Guardar modelo
    logger.info("\n7. Guardando modelo...")

    try:
        model.save_model("xgboost_model.json")
        logger.info("   ✓ Modelo guardado en: models/xgboost_model.json")

    except Exception as e:
        logger.warning(f"   ⚠️ Error guardando modelo: {e}")

    # 8. Resumen final
    logger.info("\n" + "="*80)
    logger.info("ENTRENAMIENTO COMPLETADO")
    logger.info("="*80)
    logger.info(f"✓ Features: {X_train.shape[1]}")
    logger.info(f"✓ Muestras train: {len(X_train)}")
    logger.info(f"✓ Muestras val: {len(X_val)}")
    logger.info(f"✓ Modelo guardado: models/xgboost_model.json")
    logger.info("="*80)