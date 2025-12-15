"""
Quick verification script for QuestDB data collection status
FASE 0: Validación de infraestructura existente
"""

from data.storage.questdb_storage import QuestDBStorage
from datetime import datetime, timedelta
import sys

def verify_questdb():
    """Verify QuestDB connection and data availability"""

    print("🔍 VERIFICACIÓN DE QUESTDB - FASE 0")
    print("=" * 60)

    try:
        storage = QuestDBStorage()
        print("✅ Conexión a QuestDB establecida")
    except Exception as e:
        print(f"❌ ERROR: No se pudo conectar a QuestDB")
        print(f"   Detalle: {e}")
        print(f"\n💡 Solución:")
        print(f"   1. Verificar que QuestDB está corriendo")
        print(f"   2. Instalar psycopg2: pip install psycopg2-binary")
        return False

    # Verificar datos en cada tabla
    symbol = 'ETHUSDT'
    end_time = datetime.now()
    start_time = end_time - timedelta(days=1)  # Últimas 24 horas

    print(f"\n📊 Verificando datos para {symbol}")
    print(f"   Período: últimas 24 horas")
    print("-" * 60)

    # Check microstructure_features
    try:
        sql = """
        SELECT COUNT(*) as count,
               MIN(timestamp) as first_ts,
               MAX(timestamp) as last_ts
        FROM microstructure_features
        WHERE symbol = %s
          AND timestamp >= %s
        """
        results = storage.query(sql, (symbol, start_time))

        if results and results[0]['count'] > 0:
            count = results[0]['count']
            first_ts = results[0]['first_ts']
            last_ts = results[0]['last_ts']
            print(f"✅ microstructure_features: {count} rows")
            print(f"   Primera entrada: {first_ts}")
            print(f"   Última entrada: {last_ts}")

            # Criterio de éxito: >100 rows
            if count >= 100:
                print(f"   ✅ CRITERIO CUMPLIDO (>100 rows)")
            else:
                print(f"   ⚠️  INSUFICIENTE (necesita >100 rows)")
        else:
            print(f"❌ microstructure_features: SIN DATOS")
            print(f"   Acción: Ejecutar collect_microstructure.py")
    except Exception as e:
        print(f"❌ microstructure_features: Error al consultar")
        print(f"   Detalle: {e}")
        print(f"   Probablemente la tabla no existe aún")

    # Check funding_rates
    try:
        sql = """
        SELECT COUNT(*) as count,
               MIN(timestamp) as first_ts,
               MAX(timestamp) as last_ts
        FROM funding_rates
        WHERE symbol = %s
          AND timestamp >= %s
        """
        results = storage.query(sql, (symbol, start_time))

        if results and results[0]['count'] > 0:
            count = results[0]['count']
            first_ts = results[0]['first_ts']
            last_ts = results[0]['last_ts']
            print(f"\n✅ funding_rates: {count} rows")
            print(f"   Primera entrada: {first_ts}")
            print(f"   Última entrada: {last_ts}")

            # Criterio de éxito: >1000 rows
            if count >= 1000:
                print(f"   ✅ CRITERIO CUMPLIDO (>1000 rows)")
            else:
                print(f"   ⚠️  INSUFICIENTE (necesita >1000 rows)")
        else:
            print(f"\n❌ funding_rates: SIN DATOS")
            print(f"   Acción: Ejecutar collect_derivatives.py")
    except Exception as e:
        print(f"\n❌ funding_rates: Error al consultar")
        print(f"   Detalle: {e}")

    # Check liquidations
    try:
        sql = """
        SELECT COUNT(*) as count,
               MIN(timestamp) as first_ts,
               MAX(timestamp) as last_ts
        FROM liquidations
        WHERE symbol = %s
          AND timestamp >= %s
        """
        results = storage.query(sql, (symbol, start_time))

        if results and results[0]['count'] > 0:
            count = results[0]['count']
            first_ts = results[0]['first_ts']
            last_ts = results[0]['last_ts']
            print(f"\n✅ liquidations: {count} rows")
            print(f"   Primera entrada: {first_ts}")
            print(f"   Última entrada: {last_ts}")

            # Criterio de éxito: >50 rows
            if count >= 50:
                print(f"   ✅ CRITERIO CUMPLIDO (>50 rows)")
            else:
                print(f"   ⚠️  INSUFICIENTE (necesita >50 rows)")
        else:
            print(f"\n❌ liquidations: SIN DATOS")
            print(f"   Acción: Ejecutar collect_derivatives.py")
    except Exception as e:
        print(f"\n❌ liquidations: Error al consultar")
        print(f"   Detalle: {e}")

    # Check open_interest
    try:
        sql = """
        SELECT COUNT(*) as count,
               MIN(timestamp) as first_ts,
               MAX(timestamp) as last_ts
        FROM open_interest
        WHERE symbol = %s
          AND timestamp >= %s
        """
        results = storage.query(sql, (symbol, start_time))

        if results and results[0]['count'] > 0:
            count = results[0]['count']
            first_ts = results[0]['first_ts']
            last_ts = results[0]['last_ts']
            print(f"\n✅ open_interest: {count} rows")
            print(f"   Primera entrada: {first_ts}")
            print(f"   Última entrada: {last_ts}")
        else:
            print(f"\n❌ open_interest: SIN DATOS")
    except Exception as e:
        print(f"\n❌ open_interest: Error al consultar")
        print(f"   Detalle: {e}")

    print("\n" + "=" * 60)
    print("📋 RESUMEN:")
    print("   Si todas las tablas tienen ✅ CRITERIO CUMPLIDO:")
    print("      → Proceder con FASE 0.2: Conectar feature_engineering.py")
    print("\n   Si alguna tabla tiene ❌ SIN DATOS:")
    print("      → Ejecutar collectors correspondientes:")
    print("         Terminal 1: python collect_microstructure.py")
    print("         Terminal 2: python collect_derivatives.py")
    print("      → Esperar al menos 1 hora")
    print("      → Volver a ejecutar este script")
    print("=" * 60)

    return True

if __name__ == "__main__":
    verify_questdb()
