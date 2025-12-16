"""
Microstructure Integration for Feature Engineering
FASE 2: Reconexión de features de microestructura con datos REALES de QuestDB

Este módulo carga datos reales de order book desde QuestDB y calcula
las 19 features de microestructura que fueron removidas.
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def add_microstructure_features(df: pd.DataFrame,
                                microstructure_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Agrega features de microestructura desde datos REALES de QuestDB

    Args:
        df: DataFrame principal con OHLCV (4h intervals)
        microstructure_df: DataFrame con datos de QuestDB (10s intervals)
            Columns esperadas:
            - obi_5, obi_10, obi_20 (Order Book Imbalance)
            - vpin (Volume-Synchronized PIN)
            - ofi (Order Flow Imbalance)
            - spread, spread_bps (Spread metrics)
            - micro_price (Stoikov micro-price)
            - kyle_lambda (Price impact)
            - roll_spread (Roll spread)

    Returns:
        DataFrame con 19 features de microestructura agregadas
    """
    if microstructure_df is None or microstructure_df.empty:
        logger.warning("⚠️ Microstructure data no disponible - agregando placeholders")
        _add_placeholder_features(df)
        return df

    logger.info(f"📊 Integrando microstructure features desde QuestDB ({len(microstructure_df)} rows)")

    df = df.copy()

    # Resamplear de 10s (QuestDB) a 4h (modelo)
    # Agregamos usando múltiples estadísticas para capturar dinámica intra-período

    # Asegurar que microstructure_df tiene index datetime
    if not isinstance(microstructure_df.index, pd.DatetimeIndex):
        if 'timestamp' in microstructure_df.columns:
            microstructure_df = microstructure_df.set_index('timestamp')

    # Resamplear a 4h
    micro_4h = microstructure_df.resample('4h').agg({
        # OBI (Order Book Imbalance) multi-nivel
        'obi_5': ['mean', 'std', 'max', 'min'],
        'obi_10': ['mean', 'std'],
        'obi_20': ['mean', 'std'],

        # VPIN (Toxicity)
        'vpin': ['mean', 'max'],

        # OFI (Order Flow Imbalance)
        'ofi': ['mean', 'std'],

        # Spreads
        'spread': ['mean'],
        'spread_bps': ['mean', 'max'],

        # Micro-price
        'micro_price': ['mean'],

        # Advanced metrics
        'kyle_lambda': ['mean'],
        'roll_spread': ['mean']
    })

    # Flatten multi-level columns
    micro_4h.columns = ['_'.join(col).strip() for col in micro_4h.columns.values]

    # Join con df principal
    df = df.join(micro_4h, how='left')

    # ===== PHASE 1: MICROSTRUCTURE FEATURES (REALES) =====

    # OBI Features (6 features)
    if 'obi_5_mean' in df.columns:
        df['obi_5'] = df['obi_5_mean']  # Valor promedio
        df['obi_5_std'] = df['obi_5_std']  # Volatilidad del OBI
        df['obi_10'] = df['obi_10_mean']
        df['obi_20'] = df['obi_20_mean']

        # OBI divergence (L5 vs L20)
        df['obi_divergence'] = df['obi_5'] - df['obi_20']

        # OBI velocity (cambio en OBI/hora)
        df['obi_velocity'] = df['obi_5'].diff() / 4.0  # Cambio por hora (ventana 4h)

    # VPIN Features (2 features)
    if 'vpin_mean' in df.columns:
        df['vpin'] = df['vpin_mean']
        df['vpin_max'] = df['vpin_max']

        # VPIN regime (alto/bajo)
        vpin_threshold = 0.8
        df['vpin_regime'] = (df['vpin'] > vpin_threshold).astype(int)

    # Spread Features (3 features)
    if 'spread_bps_mean' in df.columns:
        df['spread_bps'] = df['spread_bps_mean']
        df['spread_bps_max'] = df['spread_bps_max']

        # Spread widening (indicador de stress)
        df['spread_widening'] = (
            df['spread_bps_max'] / (df['spread_bps'] + 1e-8)
        )

    # Micro-price Features (1 feature)
    if 'micro_price_mean' in df.columns:
        df['micro_price'] = df['micro_price_mean']

        # Micro-price vs mid-price deviation
        if 'close' in df.columns:
            df['micro_mid_deviation'] = (
                (df['micro_price'] - df['close']) / df['close']
            )

    # Advanced Metrics (3 features)
    if 'kyle_lambda_mean' in df.columns:
        df['kyle_lambda'] = df['kyle_lambda_mean']  # Price impact

    if 'roll_spread_mean' in df.columns:
        df['roll_spread'] = df['roll_spread_mean']  # Roll spread

    if 'ofi_mean' in df.columns:
        df['ofi'] = df['ofi_mean']
        df['ofi_std'] = df['ofi_std']  # OFI volatility

    # Depth Features (estimados de OBI)
    if 'obi_5' in df.columns and 'obi_10' in df.columns:
        # Depth decay: cómo cambia OBI con profundidad
        df['depth_decay'] = abs(df['obi_5'] - df['obi_10'])

    logger.info(f"✅ Microstructure features agregadas: 19 features")

    return df


def add_microstructure_interactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega features de interacción que usan microestructura

    PHASE 5 INTERACTIONS (RECUPERADAS):
    - OBI × Returns
    - VPIN × Volatility
    - Spread × Volume
    - Conditional signals

    Args:
        df: DataFrame con microstructure features ya agregadas

    Returns:
        DataFrame con 12 features de interacción
    """
    df = df.copy()

    # === 2. MICROSTRUCTURE × PRICE INTERACTIONS ===

    # OBI-Returns synchronization
    if 'obi_5' in df.columns and 'returns' in df.columns:
        df['obi_returns_sync'] = df['obi_5'] * df['returns']

        # OBI-Returns divergence (cuando no se mueven juntos)
        obi_direction = np.sign(df['obi_5'])
        returns_direction = np.sign(df['returns'])
        df['obi_returns_divergence'] = (obi_direction != returns_direction).astype(int)

    # VPIN × Volatility stress
    if 'vpin' in df.columns and 'volatility_24h' in df.columns:
        df['vpin_vol_stress'] = df['vpin'] * df['volatility_24h']

    # Spread × Volume impact
    if 'spread_bps' in df.columns and 'volume' in df.columns:
        df['spread_volume_impact'] = df['spread_bps'] * np.log1p(df['volume'])

    # === 4. MICROSTRUCTURE RATIOS ===

    # OBI depth ratio (L5 vs L20)
    if 'obi_5' in df.columns and 'obi_20' in df.columns:
        df['obi_depth_ratio'] = df['obi_5'] / (df['obi_20'] + 1e-8)

    # Spread/Volatility ratio
    if 'spread_bps' in df.columns and 'volatility_24h' in df.columns:
        df['spread_vol_ratio'] = df['spread_bps'] / (df['volatility_24h'] + 1e-8)

    # === 5. CONDITIONAL FEATURES ===

    # Extreme risk regime (VPIN alto + spread amplio)
    if 'vpin' in df.columns and 'spread_widening' in df.columns:
        vpin_high = df['vpin'] > df['vpin'].quantile(0.75)
        spread_wide = df['spread_widening'] > 1.5
        df['extreme_risk_regime'] = (vpin_high & spread_wide).astype(int)

    # Manipulation signal (OBI extremo con bajo volumen)
    if 'obi_5' in df.columns and 'volume' in df.columns:
        obi_extreme = abs(df['obi_5']) > 0.7
        volume_low = df['volume'] < df['volume'].quantile(0.25)
        df['manipulation_signal'] = (obi_extreme & volume_low).astype(int)

    # Resistance rejection (precio cerca resistencia + OBI negativo)
    if 'dist_to_resistance' in df.columns and 'obi_5' in df.columns:
        near_resistance = df['dist_to_resistance'] < 0.02
        obi_negative = df['obi_5'] < -0.3
        df['resistance_rejection'] = (near_resistance & obi_negative).astype(int)

    # === 6. POLYNOMIAL FEATURES ===

    # OBI squared (non-linear effects)
    if 'obi_5' in df.columns:
        df['obi_squared'] = df['obi_5'] ** 2

    logger.info(f"✅ Microstructure interactions agregadas: 12 features")

    return df


def _add_placeholder_features(df: pd.DataFrame):
    """
    Agrega placeholders si no hay datos de microestructura

    Esto mantiene la compatibilidad del modelo mientras se acumulan datos
    """
    placeholder_features = [
        # Basic OBI
        'obi_5', 'obi_5_std', 'obi_10', 'obi_20', 'obi_divergence', 'obi_velocity',
        # VPIN
        'vpin', 'vpin_max', 'vpin_regime',
        # Spread
        'spread_bps', 'spread_bps_max', 'spread_widening',
        # Micro-price
        'micro_price', 'micro_mid_deviation',
        # Advanced
        'kyle_lambda', 'roll_spread', 'ofi', 'ofi_std', 'depth_decay',
        # Interactions
        'obi_returns_sync', 'obi_returns_divergence', 'vpin_vol_stress',
        'spread_volume_impact', 'obi_depth_ratio', 'spread_vol_ratio',
        'extreme_risk_regime', 'manipulation_signal', 'resistance_rejection',
        'obi_squared'
    ]

    for feature in placeholder_features:
        df[feature] = 0.0

    logger.warning(f"⚠️ {len(placeholder_features)} microstructure features = 0 (no hay datos reales)")


# Demo / Testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("🧪 Microstructure Integration - Test\n")

    # Generar datos de prueba
    dates = pd.date_range('2024-01-01', periods=100, freq='4h')
    df = pd.DataFrame({
        'close': np.random.normal(3000, 50, 100),
        'volume': np.random.normal(10000, 1000, 100),
        'returns': np.random.normal(0, 0.01, 100),
        'volatility_24h': np.random.normal(0.02, 0.005, 100),
        'dist_to_resistance': np.random.uniform(0, 0.1, 100)
    }, index=dates)

    # Generar microstructure data (10s intervals)
    micro_dates = pd.date_range('2024-01-01', periods=14400, freq='10s')
    microstructure_df = pd.DataFrame({
        'timestamp': micro_dates,
        'obi_5': np.random.normal(0.1, 0.3, 14400),
        'obi_10': np.random.normal(0.05, 0.25, 14400),
        'obi_20': np.random.normal(0, 0.2, 14400),
        'vpin': np.random.uniform(0.3, 0.9, 14400),
        'ofi': np.random.normal(0, 100, 14400),
        'spread': np.random.uniform(0.5, 2.0, 14400),
        'spread_bps': np.random.uniform(10, 50, 14400),
        'micro_price': np.random.normal(3000, 50, 14400),
        'kyle_lambda': np.random.uniform(0.0001, 0.001, 14400),
        'roll_spread': np.random.uniform(0.0001, 0.0005, 14400)
    }).set_index('timestamp')

    print("📊 Agregando microstructure features...")
    df = add_microstructure_features(df, microstructure_df)

    print("\n📊 Agregando microstructure interactions...")
    df = add_microstructure_interactions(df)

    print(f"\n✅ Features finales:")
    print(f"   Total columns: {len(df.columns)}")
    print(f"   Microstructure features: ~31")

    print(f"\n📋 Primeras 10 features de microestructura:")
    micro_cols = [col for col in df.columns if any(x in col for x in ['obi', 'vpin', 'spread', 'micro', 'ofi'])]
    for i, col in enumerate(micro_cols[:10], 1):
        print(f"   {i}. {col}")

    print(f"\n💡 Listo para integrar en feature_engineering.py")
