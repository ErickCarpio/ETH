"""
Script de Verificación de Conexión a Binance Demo Trading
Diagnostica problemas con API keys usando ccxt.binanceusdm + sandbox mode
"""

import ccxt
import asyncio
import json
from pathlib import Path


async def verificar_conexion_testnet():
    """Verifica conexión a Binance Testnet con diagnóstico detallado"""

    print("=" * 70)
    print("🔍 VERIFICADOR DE CONEXIÓN BINANCE DEMO TRADING")
    print("=" * 70)
    print()

    # Cargar config
    config_path = Path('config_15min.json')
    with open(config_path, 'r') as f:
        config = json.load(f)

    exchange_config = config['exchange']

    # Mostrar configuración
    print("📋 CONFIGURACIÓN ACTUAL:")
    print(f"   testnet: {exchange_config.get('testnet', False)}")
    print(f"   paper_trading: {exchange_config.get('paper_trading', False)}")
    print()

    testnet_api_key = exchange_config.get('testnet_api_key', '').strip()
    testnet_api_secret = exchange_config.get('testnet_api_secret', '').strip()

    # Verificar que las keys no estén vacías
    print("🔑 VERIFICACIÓN DE API KEYS:")
    if not testnet_api_key or not testnet_api_secret:
        print("   ❌ API keys de testnet están VACÍAS")
        print("   → Configúralas en config_15min.json")
        return

    print(f"   ✓ testnet_api_key: {testnet_api_key[:10]}...{testnet_api_key[-10:]}")
    print(f"   ✓ testnet_secret: {testnet_api_secret[:10]}...{testnet_api_secret[-10:]}")
    print()

    # PRUEBA 1: Conexión a demo.binance.com usando binanceusdm
    print("🧪 PRUEBA 1: Conexión a demo.binance.com (USDT-Margined Futures)")
    print("-" * 70)
    exchange = None
    try:
        # Usar binanceusdm con sandbox mode
        exchange = ccxt.binanceusdm({
            'apiKey': testnet_api_key,
            'secret': testnet_api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,  # Sincroniza reloj local con servidor
            }
        })

        # Activar modo sandbox/demo
        exchange.set_sandbox_mode(True)

        # CRÍTICO: Sobrescribir URLs explícitamente
        # Las versiones de CCXT pueden tener URLs obsoletas del antiguo testnet
        # Forzamos el enrutamiento a demo-fapi.binance.com según doc oficial:
        # https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
        new_testnet_urls = {
            'fapiPublic': 'https://demo-fapi.binance.com/fapi/v1',
            'fapiPrivate': 'https://demo-fapi.binance.com/fapi/v1',
            'fapiPublicV2': 'https://demo-fapi.binance.com/fapi/v2',
            'fapiPrivateV2': 'https://demo-fapi.binance.com/fapi/v2',
            'fapiPublicV3': 'https://demo-fapi.binance.com/fapi/v3',
            'fapiPrivateV3': 'https://demo-fapi.binance.com/fapi/v3',
            'public': 'https://demo-fapi.binance.com/fapi/v1',
            'private': 'https://demo-fapi.binance.com/fapi/v1',
        }
        exchange.urls['api'] = new_testnet_urls

        print("   URLs configuradas: demo-fapi.binance.com")
        print("   Conectando y obteniendo balance...")
        balance = await exchange.fetch_balance()

        usdt_balance = balance.get('USDT', {})
        free = usdt_balance.get('free', 0)

        print()
        print("   ✅ CONEXIÓN EXITOSA a demo.binance.com")
        print(f"   💰 Balance USDT: ${free:.2f}")
        print()

        if exchange:
            await exchange.close()
        return True

    except Exception as e:
        error_str = str(e)
        print(f"   ❌ ERROR: {error_str}")
        print()

        # Diagnóstico del error
        if "-2008" in error_str or "Invalid Api-Key ID" in error_str:
            print("   📊 DIAGNÓSTICO:")
            print("   Este error significa que Binance no reconoce tu API Key.")
            print()
            print("   ⚠️ POSIBLES CAUSAS:")
            print("   1. Las keys son de PRODUCCIÓN (binance.com) y NO de DEMO")
            print("   2. Las keys fueron creadas en demo pero revocadas/eliminadas")
            print("   3. Las keys no existen en el sistema de demo")
            print()
            print("   ✅ SOLUCIÓN:")
            print("   1. Ve a: https://demo.binance.com")
            print("   2. Login con tu cuenta")
            print("   3. API Management → REVOCA las keys antiguas")
            print("   4. API Management → CREA NUEVAS keys")
            print("   5. Copia las NUEVAS keys a config_15min.json")
            print()

        elif "-2015" in error_str or "permissions" in error_str.lower():
            print("   📊 DIAGNÓSTICO:")
            print("   Las keys existen pero no tienen permisos correctos.")
            print()
            print("   ✅ SOLUCIÓN:")
            print("   1. Ve a: https://demo.binance.com")
            print("   2. API Management → Edit API")
            print("   3. Habilita: 'Enable Futures' o 'Enable Trading'")
            print("   4. Guarda cambios")
            print()

        if exchange:
            try:
                await exchange.close()
            except:
                pass

    print()
    print("=" * 70)
    print("📝 RESUMEN:")
    print("-" * 70)
    print("Si la prueba falló con error -2008 'Invalid Api-Key ID',")
    print("significa que tus API keys NO son de Binance Demo Trading.")
    print()
    print("VERIFICA:")
    print("1. ¿Creaste las keys en https://demo.binance.com?")
    print("2. ¿O las creaste en https://binance.com? (esas son de PRODUCCIÓN)")
    print()
    print("Si creaste las keys en binance.com → NO FUNCIONARÁN en demo")
    print("Si creaste las keys en demo.binance.com → Deberían funcionar")
    print()
    print("SOLUCIÓN: Crea NUEVAS keys en https://demo.binance.com")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(verificar_conexion_testnet())
