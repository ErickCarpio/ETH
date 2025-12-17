#!/usr/bin/env python3
"""
Verifica que config.json se carga correctamente y muestra configuración actual.
"""

import json
import os
from pathlib import Path


def load_config(config_path: str = "config.json") -> dict:
    """
    Carga configuración desde JSON.

    Args:
        config_path: Ruta al archivo config.json

    Returns:
        Dict con configuración
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"❌ No se encontró {config_path}")

    with open(config_path, 'r') as f:
        config = json.load(f)

    return config


def verify_config(config: dict) -> None:
    """
    Verifica que configuración tenga campos requeridos.

    Args:
        config: Dict de configuración
    """
    print("\n" + "="*60)
    print("🔍 VERIFICACIÓN DE CONFIGURACIÓN")
    print("="*60)

    # Exchange
    print("\n📊 EXCHANGE:")
    exchange = config.get('exchange', {})
    testnet = exchange.get('testnet', False)
    print(f"  Symbol: {exchange.get('symbol', 'N/A')}")
    print(f"  Testnet: {'✅ SÍ (modo seguro)' if testnet else '⚠️ NO (PRODUCCIÓN)'}")

    if testnet:
        api_key = exchange.get('testnet_api_key', '')
        print(f"  API Key (testnet): {api_key[:10]}...{api_key[-10:] if len(api_key) > 20 else ''}")
    else:
        api_key = exchange.get('api_key', '')
        print(f"  API Key (prod): {api_key[:10]}...{api_key[-10:] if len(api_key) > 20 else ''}")

    # Trading
    print("\n💰 TRADING:")
    trading = config.get('trading', {})
    print(f"  Capital: ${trading.get('total_capital', 0):,.2f}")
    print(f"  Grid Allocation: {trading.get('grid_allocation', 0)*100:.0f}%")
    print(f"  Min Order: ${trading.get('min_order_value', 0):.2f}")
    print(f"  Prediction Threshold: {trading.get('prediction_threshold', 0)*100:.0f}%")
    print(f"  Stop Loss: {trading.get('stop_loss_pct', 0)*100:.1f}%")
    print(f"  Take Profit: {trading.get('take_profit_pct', 0)*100:.1f}%")

    # APIs Externas
    print("\n🌐 APIS EXTERNAS:")
    apis = config.get('external_apis', {})

    if apis.get('cryptopanic', {}).get('enabled'):
        print("  ✅ CryptoPanic")
    else:
        print("  ❌ CryptoPanic (deshabilitado)")

    if apis.get('newsapi', {}).get('enabled'):
        print("  ✅ NewsAPI")
    else:
        print("  ❌ NewsAPI (deshabilitado)")

    if apis.get('coinglass', {}).get('enabled'):
        print("  ✅ Coinglass (OI, Funding)")
    else:
        print("  ❌ Coinglass (deshabilitado)")

    if apis.get('deribit', {}).get('enabled'):
        print("  ✅ Deribit (GEX)")
    else:
        print("  ❌ Deribit (deshabilitado)")

    if apis.get('defillama', {}).get('enabled'):
        print("  ✅ DefiLlama (TVL)")
    else:
        print("  ❌ DefiLlama (deshabilitado)")

    # Features
    print("\n🧬 FEATURES (FASES 1-6):")
    features = config.get('features', {})
    print(f"  Microestructura (FASE 2): {'✅' if features.get('use_microstructure') else '❌'} (~150 features)")
    print(f"  Derivados (FASE 3): {'✅' if features.get('use_derivatives') else '❌'} (~80 features)")
    print(f"  Estadísticos (FASE 4): {'✅' if features.get('use_statistical') else '❌'} (~100 features)")
    print(f"  tsfresh (FASE 5): {'✅' if features.get('use_tsfresh') else '❌'} (~{features.get('tsfresh_top_n', 100)} features)")

    total_features = 30  # Base
    if features.get('use_microstructure'):
        total_features += 150
    if features.get('use_derivatives'):
        total_features += 80
    if features.get('use_statistical'):
        total_features += 100
    if features.get('use_tsfresh'):
        total_features += features.get('tsfresh_top_n', 100)

    print(f"\n  📈 TOTAL ESTIMADO: ~{total_features} features")

    # Data
    print("\n📊 DATA:")
    data = config.get('data', {})
    print(f"  QuestDB: {data.get('questdb_host', 'localhost')}:{data.get('questdb_http_port', 9000)}")
    print(f"  Cache: {'✅ Habilitado' if data.get('use_cache') else '❌ Deshabilitado'}")
    print(f"  Timeframe: {data.get('timeframe', '4h')}")
    print(f"  Window: {data.get('window_years', 2)} años")

    # Model
    print("\n🤖 MODEL:")
    model = config.get('model', {})
    print(f"  Tipo: {model.get('type', 'xgboost').upper()}")
    print(f"  Optuna Trials: {model.get('optuna_trials', 1000):,}")
    print(f"  Re-entrenar cada: {model.get('retrain_every_days', 7)} días")
    print(f"  Target: {model.get('target_method', 'fixed_horizon')}")
    print(f"  Modelo guardado en: {model.get('model_path', './models/xgboost_model.pkl')}")

    # Dev
    print("\n🔧 DESARROLLO:")
    dev = config.get('dev', {})
    print(f"  Paper Trading: {'✅ SÍ (sin dinero real)' if dev.get('paper_trading') else '⚠️ NO (REAL)'}")
    print(f"  Debug Mode: {'✅' if dev.get('debug_mode') else '❌'}")
    print(f"  Guardar Predicciones: {'✅' if dev.get('save_predictions') else '❌'}")

    # Warnings
    print("\n⚠️ ADVERTENCIAS:")
    warnings = []

    if not testnet and not dev.get('paper_trading'):
        warnings.append("  🔴 MODO PRODUCCIÓN - Usará dinero REAL")

    if not features.get('use_microstructure'):
        warnings.append("  ⚠️ Microestructura deshabilitada (perdiendo ~150 features)")

    if not features.get('use_tsfresh'):
        warnings.append("  ⚠️ tsfresh deshabilitado (perdiendo ~100 features)")

    if model.get('optuna_trials', 0) < 500:
        warnings.append("  ⚠️ Pocos Optuna trials (<500) - modelo puede no optimizar bien")

    if trading.get('total_capital', 0) < 100:
        warnings.append("  ⚠️ Capital muy bajo (<$100)")

    if warnings:
        for warning in warnings:
            print(warning)
    else:
        print("  ✅ Sin advertencias")

    print("\n" + "="*60)
    print("✅ Configuración cargada correctamente")
    print("="*60 + "\n")


def main():
    """Main function."""
    try:
        config = load_config("config.json")
        verify_config(config)

        print("💡 SIGUIENTE PASO:")
        print("   python start_system.py")
        print()

    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 SOLUCIÓN:")
        print("   El archivo config.json ya debería existir.")
        print("   Si no existe, verifica que estés en el directorio correcto:")
        print("   cd /home/user/ETH")
        print()
    except json.JSONDecodeError as e:
        print(f"\n❌ Error al parsear JSON: {e}")
        print("\n💡 SOLUCIÓN:")
        print("   El archivo config.json tiene un error de sintaxis.")
        print("   Verifica que no falten comas, corchetes o llaves.")
        print()
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        print()


if __name__ == "__main__":
    main()
