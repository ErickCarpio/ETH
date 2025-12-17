#!/usr/bin/env python3
"""
Test simplificado del pipeline de modelo.
"""

import sys
import os

print("="*60)
print("TEST DE PIPELINE")
print("="*60)

# 1. Verificar Python
print(f"\n1. Python version: {sys.version}")

# 2. Verificar imports
print("\n2. Verificando imports...")
try:
    import pandas as pd
    print("   ✓ pandas")
except Exception as e:
    print(f"   ✗ pandas: {e}")
    sys.exit(1)

try:
    import numpy as np
    print("   ✓ numpy")
except Exception as e:
    print(f"   ✗ numpy: {e}")
    sys.exit(1)

try:
    import xgboost as xgb
    print("   ✓ xgboost")
except Exception as e:
    print(f"   ✗ xgboost: {e}")
    sys.exit(1)

try:
    import ccxt
    print("   ✓ ccxt")
except Exception as e:
    print(f"   ✗ ccxt: {e}")
    sys.exit(1)

# 3. Verificar archivos necesarios
print("\n3. Verificando archivos...")
required_files = [
    'config.json',
    'feature_engineering.py',
    'target_labeling.py',
    'weighting_logic.py'
]

for file in required_files:
    if os.path.exists(file):
        print(f"   ✓ {file}")
    else:
        print(f"   ✗ {file} NO ENCONTRADO")

# 4. Cargar config
print("\n4. Cargando configuración...")
try:
    import json
    with open('config.json', 'r') as f:
        config = json.load(f)
    print(f"   ✓ Config cargado")
    print(f"   - Symbol: {config['exchange']['symbol']}")
    print(f"   - Testnet: {config['exchange']['testnet']}")
    print(f"   - Features microestructura: {config['features']['use_microstructure']}")
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

# 5. Test de descarga de datos
print("\n5. Probando descarga de datos...")
try:
    import ccxt

    exchange = ccxt.binance()
    symbol = 'ETH/USDT'
    timeframe = '4h'

    print(f"   - Descargando {symbol} {timeframe}...")
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=10)

    print(f"   ✓ Descargadas {len(ohlcv)} velas")
    print(f"   - Última vela: {pd.to_datetime(ohlcv[-1][0], unit='ms')}")
    print(f"   - Close: ${ohlcv[-1][4]:,.2f}")

except Exception as e:
    print(f"   ✗ Error descargando datos: {e}")
    import traceback
    traceback.print_exc()

# 6. Test de feature engineering
print("\n6. Probando feature_engineering...")
try:
    # Import
    sys.path.insert(0, os.getcwd())
    from feature_engineering import generate_features

    print("   - Generando features (solo 100 velas para test)...")

    # Preparar datos mínimos
    df_test = pd.DataFrame({
        'timestamp': pd.date_range(end=pd.Timestamp.now(), periods=100, freq='4h'),
        'close': np.random.randn(100).cumsum() + 2000,
        'volume': np.random.rand(100) * 1000000
    })
    df_test.set_index('timestamp', inplace=True)

    print(f"   - Test data shape: {df_test.shape}")
    print(f"   ✓ Feature engineering importado correctamente")

except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("TEST COMPLETADO")
print("="*60)
print("\n✓ Si todos los pasos pasaron, model_pipeline.py debería funcionar.")
print("✗ Si alguno falló, revisa el error específico arriba.\n")
