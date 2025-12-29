#!/usr/bin/env python3
"""
Entrenamiento Multi-Par - 20 Modelos Especializados
====================================================

Script que entrena 20 modelos XGBoost separados (uno por cada par)
reutilizando todo el pipeline existente:
- FeatureEngineer (96 features completas)
- RegimeLabeler (labels binarios: LONG/SHORT)
- XGBoostRegimeModel (optimización + entrenamiento)

IMPORTANTE:
- Respeta límites de API (NewsAPI: 5 noticias/par)
- Excluye BTC del análisis
- Guarda modelos separados: model_ETHUSDT.pkl, model_SOLUSDT.pkl, etc.
"""

import asyncio
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import sys

# Imports del proyecto
from feature_engineering import FeatureEngineer
from target_labeling import RegimeLabeler
from model_pipeline_complete import XGBoostRegimeModel, download_binance_data
from weighting_logic import TemporalWeighting
from data.managers.data_manager import DataManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =====================================================================
# CONFIGURACIÓN DE PARES (Top 20 por volumen, SIN BTC)
# =====================================================================

PAIRS = [
    'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT',
    'DOGEUSDT', 'MATICUSDT', 'DOTUSDT', 'LINKUSDT', 'UNIUSDT',
    'ATOMUSDT', 'AVAXUSDT', 'LTCUSDT', 'ETCUSDT', 'FILUSDT',
    'APTUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT', 'SUIUSDT'
]

# Configuración de descarga
TRAINING_CONFIG = {
    'days_historical': 730,  # 2 años
    'timeframe_1h': '1h',
    'timeframe_4h': '4h',
    'candles_1h': 5000,  # ~208 días de 1h
    'candles_4h': 2000,  # ~333 días de 4h

    # Límites de API
    'news_per_pair': 5,  # NewsAPI: 100/día total → 5 por par

    # Configuración de modelo
    'forward_window': 12,  # 12h forward (para 1h timeframe)
    'trend_threshold': 0.025,  # 2.5% mínimo para considerar tendencia (legacy)
    'optuna_trials': 30,  # Trials de optimización (reducido para velocidad)

    # NUEVO: ATR-based labeling
    'use_atr_labels': True,  # Usar ATR en lugar de threshold fijo
    'atr_multiplier_tp': 2.5,  # Multiplicador para TP (2.5x ATR)
    'atr_multiplier_sl': 1.0,  # Multiplicador para SL (1.0x ATR)
}


# =====================================================================
# FUNCIONES DE DESCARGA Y PREPARACIÓN DE DATOS
# =====================================================================

async def download_pair_data(symbol: str, config: dict) -> dict:
    """
    Descarga datos completos para un par CON CACHÉ:
    - OHLCV (1h y 4h) - usa caché si < 4 horas
    - BTCDOM para macro

    Args:
        symbol: 'ETHUSDT', 'SOLUSDT', etc. (sin barra)
        config: Configuración de descarga

    Returns:
        dict con 'df_1h', 'df_4h', 'macro'
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"📥 DESCARGANDO DATOS PARA {symbol}")
    logger.info(f"{'='*80}")

    # Convertir ETHUSDT → ETH/USDT para DataManager
    # Insertar '/' antes de 'USDT'
    symbol_with_slash = symbol.replace('USDT', '/USDT')

    # Usar DataManager con caché (4 horas)
    from data.managers.data_manager import DataManager

    # 1. OHLCV 1H (para trading y features técnicas)
    logger.info(f"⬇️  Obteniendo OHLCV 1h (con caché)...")
    dm_1h = DataManager(symbol=symbol_with_slash, window_years=2)

    # Cargar de caché o descargar
    df_1h = dm_1h._load_from_cache("prices_1h", max_age_hours=4)
    if df_1h.empty:
        logger.info(f"   ⬇️  Cache miss, descargando...")
        await dm_1h.initialize_exchange(testnet=False)
        df_1h = await dm_1h._fetch_symbol_data(
            symbol_with_slash,
            timeframe=config['timeframe_1h'],
            max_candles=config['candles_1h']
        )
        dm_1h._save_to_cache(df_1h, "prices_1h")
        await dm_1h.close_exchange()

    if df_1h.empty:
        logger.error(f"❌ No se pudo descargar datos de {symbol}")
        return None

    # 2. OHLCV 4H (para macro features)
    logger.info(f"⬇️  Obteniendo OHLCV 4h (con caché)...")
    dm_4h = DataManager(symbol=symbol_with_slash, window_years=2)

    df_4h = dm_4h._load_from_cache("prices_4h", max_age_hours=4)
    if df_4h.empty:
        logger.info(f"   ⬇️  Cache miss, descargando...")
        await dm_4h.initialize_exchange(testnet=False)
        df_4h = await dm_4h._fetch_symbol_data(
            symbol_with_slash,
            timeframe=config['timeframe_4h'],
            max_candles=config['candles_4h']
        )
        dm_4h._save_to_cache(df_4h, "prices_4h")
        await dm_4h.close_exchange()

    # 3. BTCDOM para macro sentiment (compartido entre pares)
    logger.info(f"⬇️  Obteniendo BTCDOM (con caché)...")
    dm_btc = DataManager(symbol='BTCDOM/USDT', window_years=2)

    btcdom_df = dm_btc._load_from_cache("prices_4h", max_age_hours=4)
    if btcdom_df.empty:
        logger.info(f"   ⬇️  Cache miss, descargando...")
        await dm_btc.initialize_exchange(testnet=False)
        btcdom_df = await dm_btc._fetch_symbol_data(
            'BTCDOM/USDT',
            timeframe=config['timeframe_4h'],
            max_candles=config['candles_4h']
        )
        dm_btc._save_to_cache(btcdom_df, "prices_4h")
        await dm_btc.close_exchange()

    macro = pd.DataFrame()
    if not btcdom_df.empty:
        macro = pd.DataFrame({'BTCDOM': btcdom_df['close']})

    logger.info(f"✅ Datos obtenidos:")
    logger.info(f"   - 1h: {len(df_1h)} velas")
    logger.info(f"   - 4h: {len(df_4h)} velas")
    logger.info(f"   - Macro: {len(macro)} registros")

    return {
        'df_1h': df_1h,
        'df_4h': df_4h,
        'macro': macro
    }


def generate_features(data: dict, symbol: str, config_path: str = 'config_15min.json') -> pd.DataFrame:
    """
    Genera 96 features usando FeatureEngineer existente

    Args:
        data: Dict con df_1h, df_4h, macro
        symbol: Símbolo del par
        config_path: Path al config (usamos config_15min.json como base)

    Returns:
        DataFrame con todas las features
    """
    logger.info(f"\n🔧 GENERANDO FEATURES PARA {symbol}")
    logger.info(f"{'='*80}")

    # Cargar config (para paths de API keys, etc.)
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Inicializar FeatureEngineer
    feature_engineer = FeatureEngineer(config)

    df = data['df_1h'].copy()
    df_4h = data['df_4h'].copy()
    macro_df = data['macro'].copy()

    # 1. Features técnicas (1h)
    logger.info("📊 Generando features técnicas 1h...")
    df = feature_engineer.create_technical_features(df, timeframe='1h')

    # 2. Features macro (4h)
    if not df_4h.empty:
        logger.info("📈 Generando features macro 4h...")
        df = feature_engineer.add_4h_macro_features(df, df_4h)

    # 3. Features estadísticas (Hurst, Wavelet, FFT, etc.)
    if hasattr(feature_engineer, 'statistical_engine') and feature_engineer.statistical_engine:
        logger.info("🔬 Generando statistical features...")
        try:
            df = feature_engineer.statistical_engine.compute_all_features(df, price_col='close')
            logger.info(f"   ✓ Statistical features: {len(df.columns)} columnas totales")
        except Exception as e:
            logger.warning(f"⚠️  Error generando statistical features: {e}")

    # 4. Macro features (BTCDOM)
    if not macro_df.empty:
        logger.info("📊 Agregando BTCDOM features...")
        df = feature_engineer.merge_macro_features(df, macro_df)

    # 5. Agregar features faltantes con valor 0 (para compatibilidad)
    # Estas features normalmente vendrían de APIs externas
    required_external_features = [
        'funding_rate', 'open_interest_norm', 'oi_change',
        'Net_Flow_Z', 'BTCDOM_ROC', 'FinBERT_Score',
        'stablecoin_mcap', 'stablecoin_flow_7d', 'stablecoin_trend'
    ]

    missing_features = [f for f in required_external_features if f not in df.columns]
    if missing_features:
        logger.info(f"⚠️  Agregando {len(missing_features)} features externas con valor 0 (placeholder)")
        for feature in missing_features:
            df[feature] = 0.0

    # 6. Eliminar filas con NaN (warmup de indicadores)
    initial_len = len(df)
    df = df.dropna()
    final_len = len(df)

    logger.info(f"✅ Features generadas: {len(df.columns)} columnas")
    logger.info(f"   Filas válidas: {final_len} / {initial_len} (descartadas: {initial_len - final_len})")

    return df


def create_labels(df: pd.DataFrame, config: dict,
                 use_atr: bool = False,
                 atr_multiplier_tp: float = 2.5,
                 atr_multiplier_sl: float = 1.0) -> pd.DataFrame:
    """
    Crea labels binarios (LONG=1, SHORT=0) usando RegimeLabeler

    NUEVO: Soporta ATR con multiplicadores personalizados

    Args:
        df: DataFrame con features
        config: Configuración de entrenamiento
        use_atr: Si True, usa ATR en lugar de threshold fijo
        atr_multiplier_tp: Multiplicador de ATR para TP
        atr_multiplier_sl: Multiplicador de ATR para SL

    Returns:
        DataFrame con columna 'regime' (solo oportunidades claras)
    """
    logger.info(f"\n🎯 CREANDO LABELS")
    logger.info(f"{'='*80}")

    if use_atr:
        logger.info(f"📊 Usando ATR con multiplicadores: TP={atr_multiplier_tp:.2f}x, SL={atr_multiplier_sl:.2f}x")
        labeler = RegimeLabeler(
            forward_window=config['forward_window'],
            use_atr=True,
            atr_multiplier_tp=atr_multiplier_tp,
            atr_multiplier_sl=atr_multiplier_sl
        )
    else:
        logger.info(f"📊 Usando threshold fijo: {config['trend_threshold']:.1%}")
        labeler = RegimeLabeler(
            forward_window=config['forward_window'],
            trend_threshold=config['trend_threshold']
        )

    labeled_df = labeler.label_regime(df)

    return labeled_df


def train_model_for_pair(features_df: pd.DataFrame, symbol: str, config: dict) -> XGBoostRegimeModel:
    """
    Entrena modelo XGBoost para un par específico

    NUEVO: Optuna optimiza MULTIPLICADORES ATR + hiperparámetros XGBoost juntos

    Args:
        features_df: DataFrame con features (SIN labels aún)
        symbol: Símbolo del par
        config: Configuración de entrenamiento

    Returns:
        Tupla (modelo entrenado, métricas con multiplicadores óptimos)
    """
    logger.info(f"\n🤖 ENTRENANDO MODELO PARA {symbol}")
    logger.info(f"{'='*80}")

    import optuna
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import f1_score, accuracy_score, precision_recall_fscore_support
    import xgboost as xgb

    # Configuración de Optuna
    use_atr = config.get('use_atr_labels', False)
    n_trials = config.get('optuna_trials', 30)

    # Variables para guardar el mejor modelo y sus multiplicadores
    best_model = None
    best_multipliers = {'atr_multiplier_tp': 2.5, 'atr_multiplier_sl': 1.0}
    best_metrics = {}

    def objective(trial):
        """Función objetivo de Optuna que optimiza ATR + XGBoost juntos"""
        nonlocal best_model, best_multipliers, best_metrics

        # 1. OPTIMIZAR MULTIPLICADORES ATR (si está habilitado)
        if use_atr:
            atr_mult_tp = trial.suggest_float('atr_multiplier_tp', 1.5, 4.0)
            atr_mult_sl = trial.suggest_float('atr_multiplier_sl', 0.5, 2.0)
        else:
            atr_mult_tp = config.get('atr_multiplier_tp', 2.5)
            atr_mult_sl = config.get('atr_multiplier_sl', 1.0)

        # 2. CREAR LABELS con los multiplicadores de este trial
        labeled_df = create_labels(
            features_df.copy(),
            config,
            use_atr=use_atr,
            atr_multiplier_tp=atr_mult_tp,
            atr_multiplier_sl=atr_mult_sl
        )

        # Si no hay suficientes datos, penalizar
        if labeled_df.empty or len(labeled_df) < 100:
            return 0.0

        # 3. SEPARAR FEATURES Y TARGET
        feature_cols = [col for col in labeled_df.columns
                       if col not in ['regime', 'forward_return', 'forward_volatility',
                                     'forward_hl_range', 'atr_pct', 'tp_threshold']]

        X = labeled_df[feature_cols]
        y = labeled_df['regime']

        # Verificar que tengamos ambas clases
        if len(y.value_counts()) < 2:
            return 0.0

        # 4. TEMPORAL WEIGHTING
        temporal_weighter = TemporalWeighting(
            decay_rate=0.001,
            min_weight=0.1,
            max_weight=1.0,
            recent_days=7
        )
        all_weights = temporal_weighter.calculate_weights(labeled_df)

        # 5. TIME SERIES SPLIT
        split_idx = int(len(X) * 0.8)
        X_train = X.iloc[:split_idx]
        y_train = y.iloc[:split_idx]
        sample_weights = all_weights[:split_idx]

        # 6. OPTIMIZAR HIPERPARÁMETROS XGBOOST
        params = {
            'objective': 'binary:logistic',
            'eval_metric': 'logloss',
            'tree_method': 'hist',
            'device': 'cpu',
            'max_depth': trial.suggest_int('max_depth', 3, 10),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
            'n_estimators': trial.suggest_int('n_estimators', 100, 500),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'gamma': trial.suggest_float('gamma', 0, 5),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-5, 10.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-5, 10.0, log=True),
            'random_state': 42
        }

        # 7. CROSS-VALIDATION con TimeSeriesSplit
        tscv = TimeSeriesSplit(n_splits=3)
        scores = []

        for train_idx, val_idx in tscv.split(X_train):
            X_fold_train = X_train.iloc[train_idx]
            y_fold_train = y_train.iloc[train_idx]
            w_fold_train = sample_weights[train_idx]

            X_fold_val = X_train.iloc[val_idx]
            y_fold_val = y_train.iloc[val_idx]

            model = xgb.XGBClassifier(**params)
            model.fit(X_fold_train, y_fold_train, sample_weight=w_fold_train, verbose=False)

            y_pred = model.predict(X_fold_val)
            score = f1_score(y_fold_val, y_pred, average='weighted')
            scores.append(score)

        mean_score = np.mean(scores)

        # 8. SI ES EL MEJOR, entrenar modelo completo y guardarlo
        if trial.number == 0 or mean_score > trial.study.best_value:
            # Entrenar en TODO el train set
            final_model = xgb.XGBClassifier(**params)
            final_model.fit(X_train, y_train, sample_weight=sample_weights, verbose=False)

            # Evaluar en test set
            X_test = X.iloc[split_idx:]
            y_test = y.iloc[split_idx:]
            y_pred_test = final_model.predict(X_test)

            # Métricas finales
            accuracy = accuracy_score(y_test, y_pred_test)
            precision, recall, f1, support = precision_recall_fscore_support(
                y_test, y_pred_test, average=None, labels=[0, 1]
            )

            # Guardar modelo y métricas
            best_model = final_model
            best_multipliers = {
                'atr_multiplier_tp': atr_mult_tp,
                'atr_multiplier_sl': atr_mult_sl
            }
            best_metrics = {
                'accuracy': float(accuracy),
                'precision_short': float(precision[0]) if len(precision) > 0 else 0.0,
                'precision_long': float(precision[1]) if len(precision) > 1 else 0.0,
                'recall_short': float(recall[0]) if len(recall) > 0 else 0.0,
                'recall_long': float(recall[1]) if len(recall) > 1 else 0.0,
                'f1_short': float(f1[0]) if len(f1) > 0 else 0.0,
                'f1_long': float(f1[1]) if len(f1) > 1 else 0.0,
                'support_short': int(support[0]) if len(support) > 0 else 0,
                'support_long': int(support[1]) if len(support) > 1 else 0,
                'test_samples': int(len(y_test)),
                'train_samples': int(len(y_train)),
                'f1_weighted': float(mean_score)
            }

        return mean_score

    # EJECUTAR OPTIMIZACIÓN
    logger.info(f"🔍 Optimizando multiplicadores ATR + hiperparámetros XGBoost...")
    logger.info(f"   Trials: {n_trials}")

    study = optuna.create_study(
        direction='maximize',
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=5)
    )

    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    # RESULTADOS
    logger.info(f"\n📊 RESULTADOS DE OPTIMIZACIÓN:")
    logger.info(f"   Best F1-weighted: {study.best_value:.4f}")

    if use_atr:
        logger.info(f"   🎯 Multiplicadores óptimos:")
        logger.info(f"      TP: {best_multipliers['atr_multiplier_tp']:.2f}x ATR")
        logger.info(f"      SL: {best_multipliers['atr_multiplier_sl']:.2f}x ATR")

    logger.info(f"\n📊 MÉTRICAS EN TEST SET:")
    logger.info(f"   Accuracy: {best_metrics.get('accuracy', 0):.1%}")
    logger.info(f"   Precision LONG: {best_metrics.get('precision_long', 0):.1%}")
    logger.info(f"   Recall LONG: {best_metrics.get('recall_long', 0):.1%}")

    # Agregar multiplicadores a las métricas
    best_metrics.update(best_multipliers)

    # Crear objeto compatible con el flujo existente
    class ModelWrapper:
        def __init__(self, xgb_model):
            self.model = xgb_model

        def save_model(self, filename):
            self.model.save_model(filename)

    wrapped_model = ModelWrapper(best_model)

    return wrapped_model, best_metrics


# =====================================================================
# FUNCIÓN PRINCIPAL
# =====================================================================

async def train_all_pairs():
    """
    Loop principal: entrena 20 modelos separados (uno por par)
    """
    logger.info("\n" + "="*80)
    logger.info("🚀 INICIANDO ENTRENAMIENTO MULTI-PAR")
    logger.info("="*80)
    logger.info(f"Pares a entrenar: {len(PAIRS)}")
    logger.info(f"Total de modelos: {len(PAIRS)}")
    logger.info(f"Configuración:")
    logger.info(f"   - Datos históricos: {TRAINING_CONFIG['days_historical']} días")
    logger.info(f"   - Timeframe principal: {TRAINING_CONFIG['timeframe_1h']}")
    logger.info(f"   - Forward window: {TRAINING_CONFIG['forward_window']}h")
    logger.info(f"   - Optuna trials: {TRAINING_CONFIG['optuna_trials']}")
    logger.info(f"   - News por par: {TRAINING_CONFIG['news_per_pair']} (NewsAPI)")
    logger.info("="*80 + "\n")

    # Crear directorio de modelos
    models_dir = Path('./models')
    models_dir.mkdir(exist_ok=True)

    # Resultados del entrenamiento
    training_results = []

    for i, symbol in enumerate(PAIRS, 1):
        try:
            logger.info(f"\n{'#'*80}")
            logger.info(f"# PAR {i}/{len(PAIRS)}: {symbol}")
            logger.info(f"{'#'*80}\n")

            # 1. Descargar datos
            data = await download_pair_data(symbol, TRAINING_CONFIG)
            if data is None:
                logger.error(f"❌ Fallo en descarga de {symbol}. Saltando...")
                training_results.append({
                    'symbol': symbol,
                    'status': 'FAILED',
                    'error': 'Data download failed'
                })
                continue

            # 2. Generar features
            features_df = generate_features(data, symbol)

            if features_df.empty:
                logger.error(f"❌ No hay features para {symbol}. Saltando...")
                training_results.append({
                    'symbol': symbol,
                    'status': 'FAILED',
                    'error': 'Feature generation failed'
                })
                continue

            # 3. Crear labels (con ATR si está configurado)
            labeled_df = create_labels(
                features_df,
                TRAINING_CONFIG,
                use_atr=TRAINING_CONFIG.get('use_atr_labels', False),
                atr_multiplier_tp=TRAINING_CONFIG.get('atr_multiplier_tp', 2.5),
                atr_multiplier_sl=TRAINING_CONFIG.get('atr_multiplier_sl', 1.0)
            )

            if labeled_df.empty or len(labeled_df) < 100:
                logger.error(f"❌ Insuficientes datos etiquetados para {symbol}. Saltando...")
                training_results.append({
                    'symbol': symbol,
                    'status': 'FAILED',
                    'error': 'Insufficient labeled data'
                })
                continue

            # 4. Entrenar modelo
            result = train_model_for_pair(labeled_df, symbol, TRAINING_CONFIG)

            if result is None or (isinstance(result, tuple) and result[0] is None):
                logger.error(f"❌ Fallo en entrenamiento de {symbol}. Saltando...")
                training_results.append({
                    'symbol': symbol,
                    'status': 'FAILED',
                    'error': 'Training failed'
                })
                continue

            # Desempaquetar resultado
            if isinstance(result, tuple):
                model, metrics = result
            else:
                model = result
                metrics = {}

            # 5. Guardar modelo con nombre del par
            model_filename = f"model_{symbol}.json"
            model.save_model(model_filename)

            # 6. Guardar métricas en JSON (incluir multiplicadores ATR)
            metrics_filename = models_dir / f"model_{symbol}_metadata.json"

            # Agregar multiplicadores ATR al metadata
            metrics['use_atr'] = TRAINING_CONFIG.get('use_atr_labels', False)
            if metrics['use_atr']:
                metrics['atr_multiplier_tp'] = TRAINING_CONFIG.get('atr_multiplier_tp', 2.5)
                metrics['atr_multiplier_sl'] = TRAINING_CONFIG.get('atr_multiplier_sl', 1.0)

            with open(metrics_filename, 'w') as f:
                json.dump(metrics, f, indent=2)

            logger.info(f"✅ Modelo guardado: {models_dir / model_filename}")
            logger.info(f"✅ Métricas guardadas: {metrics_filename}")

            training_results.append({
                'symbol': symbol,
                'status': 'SUCCESS',
                'model_file': model_filename,
                'samples': len(labeled_df),
                'features': len(labeled_df.columns) - 4,  # Excluir regime y forward_*
                'accuracy': metrics.get('accuracy', 0),
                'test_samples': metrics.get('test_samples', 0)
            })

            # Rate limiting entre pares (respetar APIs)
            if i < len(PAIRS):
                logger.info(f"\n⏳ Esperando 3s antes del siguiente par...")
                await asyncio.sleep(3)

        except Exception as e:
            logger.error(f"❌ Error inesperado en {symbol}: {e}")
            import traceback
            traceback.print_exc()
            training_results.append({
                'symbol': symbol,
                'status': 'FAILED',
                'error': str(e)
            })
            continue

    # Resumen final
    logger.info("\n" + "="*80)
    logger.info("📊 RESUMEN DE ENTRENAMIENTO")
    logger.info("="*80)

    successful = sum(1 for r in training_results if r['status'] == 'SUCCESS')
    failed = sum(1 for r in training_results if r['status'] == 'FAILED')

    logger.info(f"Total de pares: {len(PAIRS)}")
    logger.info(f"✅ Exitosos: {successful}")
    logger.info(f"❌ Fallidos: {failed}")

    if successful > 0:
        logger.info(f"\n✅ Modelos guardados en: {models_dir}/")
        logger.info(f"   Archivos:")
        for result in training_results:
            if result['status'] == 'SUCCESS':
                logger.info(f"   - {result['model_file']}")

    # Guardar resumen en JSON
    summary_file = models_dir / 'training_summary.json'
    with open(summary_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_pairs': len(PAIRS),
            'successful': successful,
            'failed': failed,
            'results': training_results,
            'config': TRAINING_CONFIG
        }, f, indent=2)

    logger.info(f"\n📄 Resumen guardado en: {summary_file}")

    return training_results


# =====================================================================
# ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    import sys

    # Verificar que existan los módulos necesarios
    try:
        from feature_engineering import FeatureEngineer
        from target_labeling import RegimeLabeler
        from model_pipeline_complete import XGBoostRegimeModel
    except ImportError as e:
        logger.error(f"❌ Error importando módulos: {e}")
        logger.error("   Asegúrate de que todos los módulos estén en el directorio.")
        sys.exit(1)

    # Ejecutar entrenamiento
    results = asyncio.run(train_all_pairs())

    # Exit code basado en resultados
    successful = sum(1 for r in results if r['status'] == 'SUCCESS')
    if successful == 0:
        logger.error("\n❌ Ningún modelo se entrenó exitosamente")
        sys.exit(1)
    elif successful < len(PAIRS):
        logger.warning(f"\n⚠️  Solo {successful}/{len(PAIRS)} modelos se entrenaron exitosamente")
        sys.exit(0)
    else:
        logger.info(f"\n✅ Todos los modelos ({successful}) se entrenaron exitosamente!")
        sys.exit(0)
