"""
Main execution script for model training pipeline.
Loads data, generates features, trains XGBoost model.
"""

import json
import logging
import numpy as np
import pandas as pd
from model_pipeline import XGBoostRegimeModel
from feature_engineering import generate_features
from target_labeling import label_regime_targets
from weighting_logic import calculate_sample_weights

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
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
        raise

    # 3. Crear targets
    logger.info("\n3. Creando targets...")

    try:
        # Necesitamos el precio para crear targets
        # Si no está en df_features, descargarlo
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

            # Alinear con features
            df_features['close'] = prices['close'].reindex(df_features.index)

        # Crear targets
        targets = label_regime_targets(
            df_features,
            n_classes=n_classes,
            method='volatility_quantiles'
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

    # Alinear features, targets y weights
    valid_idx = (~df_features.isna().any(axis=1)) & (~targets.isna())

    X = df_features[valid_idx].copy()
    y = targets[valid_idx].copy()
    w = sample_weights[valid_idx]

    logger.info(f"   ✓ Muestras válidas: {len(X)} / {len(df_features)}")

    # Eliminar columna 'close' si existe (no es feature)
    if 'close' in X.columns:
        X = X.drop(columns=['close'])

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


if __name__ == "__main__":
    main()
