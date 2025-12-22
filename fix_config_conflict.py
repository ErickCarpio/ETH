"""
Script para resolver conflictos de merge en config_15min.json
"""
import json
import sys
from pathlib import Path

def fix_config_conflict():
    config_path = Path('config_15min.json')

    # Leer el archivo
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error al leer el archivo: {e}")
        return False

    # Verificar si hay marcadores de conflicto
    has_conflict = any(marker in content for marker in ['<<<<<<<', '=======', '>>>>>>>'])

    if not has_conflict:
        # Intentar parsear como JSON
        try:
            config = json.loads(content)
            print("✅ El archivo JSON está bien formado")

            # Verificar campos importantes
            testnet_key = config.get('exchange', {}).get('testnet_api_key', '')
            testnet_secret = config.get('exchange', {}).get('testnet_api_secret', '')

            if not testnet_key or not testnet_secret:
                print("\n⚠️  ADVERTENCIA: Las API keys de testnet están vacías")
                print("   Necesitas agregarlas manualmente en:")
                print("   - Línea 15: testnet_api_key")
                print("   - Línea 16: testnet_api_secret")
            else:
                print(f"\n✅ API keys configuradas:")
                print(f"   testnet_api_key: {testnet_key[:10]}...{testnet_key[-10:]}")
                print(f"   testnet_api_secret: {testnet_secret[:10]}...{testnet_secret[-10:]}")

            return True

        except json.JSONDecodeError as e:
            print(f"❌ Error de sintaxis JSON: {e}")
            print(f"   Línea {e.lineno}, Columna {e.colno}")
            print(f"\n💡 Busca en el archivo caracteres extraños o comillas faltantes")
            return False

    else:
        print("❌ El archivo contiene marcadores de conflicto de Git:")
        print("   - <<<<<<<")
        print("   - =======")
        print("   - >>>>>>>")
        print("\n💡 SOLUCIÓN:")
        print("   1. Abre config_15min.json en un editor")
        print("   2. Busca esas líneas y elimínalas")
        print("   3. Mantén solo el contenido correcto")
        print("   4. Guarda el archivo")
        return False

if __name__ == '__main__':
    success = fix_config_conflict()
    sys.exit(0 if success else 1)
