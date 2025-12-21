#!/usr/bin/env python3
"""
Script de Verificación del Sistema ETH Trading Bot
Verifica el estado del sistema y da instrucciones de qué hacer
"""

import os
from pathlib import Path
import json

def verificar_directorios():
    """Verifica y crea directorios necesarios"""
    print("=" * 60)
    print("🗂️  VERIFICANDO DIRECTORIOS")
    print("=" * 60)

    directorios = [
        'logs',
        'models',
        'data/cache',
        'data/cache/data',
        'data/cache/features'
    ]

    for dir_path in directorios:
        path = Path(dir_path)
        if path.exists():
            print(f"✅ {dir_path} - Existe")
        else:
            print(f"❌ {dir_path} - No existe, creando...")
            path.mkdir(parents=True, exist_ok=True)
            print(f"   ✓ {dir_path} creado")

    print()

def verificar_cache():
    """Verifica si hay datos en cache"""
    print("=" * 60)
    print("💾 VERIFICANDO CACHE DE DATOS")
    print("=" * 60)

    cache_dir = Path('data/cache/data')

    if not cache_dir.exists():
        print("❌ No existe directorio de cache")
        return False

    files = list(cache_dir.glob('*.pkl'))

    if len(files) == 0:
        print("❌ Cache vacío - No hay datos descargados")
        print("   Necesitas ejecutar: python model_pipeline_complete.py")
        return False

    print(f"✅ Cache tiene {len(files)} archivos")

    # Buscar archivo de datos de 1H
    eth_files = [f for f in files if 'ETH' in f.name and '1h' in f.name]
    if eth_files:
        print(f"   ✓ Datos de ETHUSDT encontrados:")
        for f in eth_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"     - {f.name} ({size_mb:.2f} MB)")

    print()
    return True

def verificar_modelo():
    """Verifica si existe modelo entrenado"""
    print("=" * 60)
    print("🧠 VERIFICANDO MODELO")
    print("=" * 60)

    model_path = Path('models/xgboost_model.json')
    metadata_path = Path('models/xgboost_model_metadata.pkl')

    if not model_path.exists():
        print("❌ Modelo no encontrado en: models/xgboost_model.json")
        print("   Necesitas entrenar el modelo primero")
        print("   Ejecuta: python model_pipeline_complete.py")
        return False

    size_mb = model_path.stat().st_size / (1024 * 1024)
    print(f"✅ Modelo encontrado ({size_mb:.2f} MB)")

    # Verificar fecha de última modificación
    import datetime
    mod_time = datetime.datetime.fromtimestamp(model_path.stat().st_mtime)
    age = datetime.datetime.now() - mod_time

    print(f"   Última actualización: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Antigüedad: {age.days} días, {age.seconds // 3600} horas")

    if age.days > 7:
        print("   ⚠️  Modelo tiene más de 7 días - Considera re-entrenar")

    if metadata_path.exists():
        print("   ✓ Metadata encontrada")

    print()
    return True

def verificar_configuracion():
    """Verifica archivo de configuración"""
    print("=" * 60)
    print("⚙️  VERIFICANDO CONFIGURACIÓN")
    print("=" * 60)

    config_path = Path('config_15min.json')

    if not config_path.exists():
        print("❌ Archivo config_15min.json no encontrado")
        return False

    print("✅ Archivo de configuración encontrado")

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Verificar API keys
        exchange_config = config.get('exchange', {})

        testnet_key = exchange_config.get('testnet_api_key', '')
        testnet_secret = exchange_config.get('testnet_api_secret', '')

        if testnet_key and testnet_secret:
            print("   ✓ API keys de Testnet configuradas")
        else:
            print("   ⚠️  API keys de Testnet no configuradas")
            print("      El bot no podrá operar sin API keys")
            print("      Obtén keys en: https://testnet.binancefuture.com")

        # Verificar parámetros clave
        trading = config.get('trading', {})
        print(f"   Threshold: {trading.get('prediction_threshold', 'N/A')}")
        print(f"   Stop Loss: {trading.get('stop_loss_pct', 'N/A') * 100:.1f}%")
        print(f"   Take Profit: {trading.get('take_profit_pct', 'N/A') * 100:.1f}%")

    except Exception as e:
        print(f"   ❌ Error leyendo configuración: {e}")
        return False

    print()
    return True

def verificar_logs():
    """Verifica archivos de log"""
    print("=" * 60)
    print("📝 VERIFICANDO LOGS")
    print("=" * 60)

    logs_dir = Path('logs')

    if not logs_dir.exists():
        print("❌ Directorio logs/ no existe")
        return

    trades_files = list(logs_dir.glob('*trades*.csv'))
    log_files = list(logs_dir.glob('*.log'))

    if trades_files:
        print(f"✅ {len(trades_files)} archivos de trades encontrados:")
        for f in trades_files:
            size_kb = f.stat().st_size / 1024
            print(f"   - {f.name} ({size_kb:.1f} KB)")
    else:
        print("ℹ️  No hay trades registrados aún")

    if log_files:
        print(f"✅ {len(log_files)} archivos de log encontrados:")
        for f in log_files:
            size_kb = f.stat().st_size / 1024
            print(f"   - {f.name} ({size_kb:.1f} KB)")

    print()

def dar_instrucciones(tiene_cache, tiene_modelo):
    """Da instrucciones al usuario según el estado del sistema"""
    print("=" * 60)
    print("📋 INSTRUCCIONES")
    print("=" * 60)

    if not tiene_cache and not tiene_modelo:
        print("""
🚀 PRIMER USO - Sistema sin inicializar

PASO 1: Entrenar el modelo por primera vez
   python model_pipeline_complete.py

   Esto va a:
   - Descargar datos de Binance (5000 velas de 1H)
   - Calcular features técnicos y fundamentales
   - Entrenar modelo XGBoost con Optuna
   - Hacer backtesting
   - Guardar modelo en models/xgboost_model.json

   ⏱️  Tiempo estimado: 30-60 minutos (dependiendo de tu conexión y CPU)

PASO 2: Ejecutar el dashboard
   streamlit run web_dashboard.py

   - Verás el gráfico de precio y resultados del backtest
   - Podrás iniciar el bot de trading en vivo

PASO 3: Configurar API keys de Binance Testnet
   - Ve a: https://testnet.binancefuture.com
   - Crea una cuenta (gratis, dinero ficticio)
   - API Management → Create API Key
   - Copia las keys a config_15min.json
        """)

    elif tiene_cache and not tiene_modelo:
        print("""
⚠️  Tienes datos en cache pero NO tienes modelo entrenado

ACCIÓN REQUERIDA:
   python model_pipeline_complete.py

   El cache ya tiene datos, así que será más rápido.
        """)

    elif not tiene_cache and tiene_modelo:
        print("""
⚠️  Tienes modelo pero NO tienes datos en cache

Esto es extraño. Es posible que se hayan borrado los datos del cache.

ACCIÓN REQUERIDA:
   python model_pipeline_complete.py

   Esto descargará datos frescos y re-entrenará el modelo.
        """)

    else:
        print("""
✅ Sistema listo para usar

OPCIONES:

1. Ver dashboard y operar en vivo:
   streamlit run web_dashboard.py

   - Haz clic en "▶️ Iniciar" para comenzar trading
   - El bot operará automáticamente en Binance Testnet

2. Re-entrenar modelo con datos actualizados:
   python model_pipeline_complete.py

   - Útil si el modelo tiene varios días de antigüedad
   - El sistema usará cache para datos existentes
   - Solo descargará datos nuevos

3. Ejecutar desde terminal (sin interfaz gráfica):
   python start_system.py --mode daily
        """)

    print()

def main():
    print("\n")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║                                                           ║")
    print("║     ETH TRADING BOT - VERIFICACIÓN DEL SISTEMA            ║")
    print("║                                                           ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print()

    verificar_directorios()
    tiene_cache = verificar_cache()
    tiene_modelo = verificar_modelo()
    verificar_configuracion()
    verificar_logs()
    dar_instrucciones(tiene_cache, tiene_modelo)

    print("=" * 60)
    print("✅ Verificación completada")
    print("=" * 60)
    print()

if __name__ == "__main__":
    main()
