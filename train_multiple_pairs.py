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
    'trend_threshold': 0.025,  # 2.5% mínimo para considerar tendencia
    'optuna_trials': 30,  # Trials de optimización (reducido para velocidad)
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


def create_labels(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Crea labels binarios (LONG=1, SHORT=0) usando RegimeLabeler

    Args:
        df: DataFrame con features
        config: Configuración de entrenamiento

    Returns:
        DataFrame con columna 'regime' (solo oportunidades claras)
    """
    logger.info(f"\n🎯 CREANDO LABELS")
    logger.info(f"{'='*80}")

    labeler = RegimeLabeler(
        forward_window=config['forward_window'],
        trend_threshold=config['trend_threshold']
    )

    labeled_df = labeler.label_regime(df)

    return labeled_df


def train_model_for_pair(features_df: pd.DataFrame, symbol: str, config: dict) -> XGBoostRegimeModel:
    """
    Entrena modelo XGBoost para un par específico

    Args:
        features_df: DataFrame con features y labels
        symbol: Símbolo del par
        config: Configuración de entrenamiento

    Returns:
        Modelo entrenado
    """
    logger.info(f"\n🤖 ENTRENANDO MODELO PARA {symbol}")
    logger.info(f"{'='*80}")

    # Separar features y target
    feature_cols = [col for col in features_df.columns if col not in ['regime', 'forward_return', 'forward_volatility', 'forward_hl_range']]

    X = features_df[feature_cols]
    y = features_df['regime']

    # Verificar que tengamos ambas clases
    class_counts = y.value_counts()
    logger.info(f"Distribución de clases:")
    logger.info(f"   LONG (1): {class_counts.get(1, 0)} ({class_counts.get(1, 0) / len(y) * 100:.1f}%)")
    logger.info(f"   SHORT (0): {class_counts.get(0, 0)} ({class_counts.get(0, 0) / len(y) * 100:.1f}%)")

    if len(class_counts) < 2:
        logger.error(f"❌ Solo hay una clase en los datos. No se puede entrenar.")
        return None

    # Pesos temporales (calcular ANTES del split, usando todo el DataFrame)
    temporal_weighter = TemporalWeighting(
        decay_rate=0.001,  # Decay suave
        min_weight=0.1,    # Peso mínimo 10%
        max_weight=1.0,    # Peso máximo 100%
        recent_days=7      # Últimos 7 días peso completo
    )

    # Calcular pesos con todo el DataFrame (que tiene índice temporal)
    all_weights = temporal_weighter.calculate_weights(features_df)

    # Split temporal (80% train, 20% test)
    split_idx = int(len(X) * 0.8)
    X_train = X.iloc[:split_idx]
    X_test = X.iloc[split_idx:]
    y_train = y.iloc[:split_idx]
    y_test = y.iloc[split_idx:]

    # Slice de pesos para train set
    sample_weights = all_weights[:split_idx]

    # Entrenar modelo
    model = XGBoostRegimeModel(
        n_classes=2,  # Binario: LONG vs SHORT
        optuna_trials=config['optuna_trials']
    )

    model.train(
        X_train, y_train,
        sample_weights=sample_weights,
        X_val=X_test,
        y_val=y_test,
        optimize=True
    )

    # Evaluar en test set
    logger.info(f"\n📊 EVALUACIÓN EN TEST SET:")
    y_pred = model.predict(X_test)
    from sklearn.metrics import classification_report, accuracy_score, precision_recall_fscore_support

    # Generar report completo
    report_text = classification_report(y_test, y_pred, target_names=['SHORT', 'LONG'])
    print(report_text)

    # Calcular métricas individuales
    accuracy = accuracy_score(y_test, y_pred)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_test, y_pred, average=None, labels=[0, 1]
    )

    # Crear diccionario de métricas
    metrics = {
        'accuracy': float(accuracy),
        'precision_short': float(precision[0]),
        'precision_long': float(precision[1]),
        'recall_short': float(recall[0]),
        'recall_long': float(recall[1]),
        'f1_short': float(f1[0]),
        'f1_long': float(f1[1]),
        'support_short': int(support[0]),
        'support_long': int(support[1]),
        'test_samples': int(len(y_test)),
        'train_samples': int(len(y_train))
    }

    return model, metrics


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

            # 3. Crear labels
            labeled_df = create_labels(features_df, TRAINING_CONFIG)

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

            # 6. Guardar métricas en JSON
            metrics_filename = models_dir / f"model_{symbol}_metadata.json"
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
