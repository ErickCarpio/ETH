"""
QuestDB Storage Manager
Fase 1.3: Almacenamiento de Time-Series

QuestDB es una base de datos time-series optimizada para:
- Alto throughput de inserts (>1M rows/sec)
- Queries analíticas rápidas
- Almacenamiento eficiente con compresión columnar
- Interfaz SQL estándar

Características:
- Batch inserts para máxima performance
- Auto-creación de tablas
- Particionamiento automático por tiempo
- Queries optimizadas para agregaciones
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import contextmanager

# Lazy import de psycopg2 (opcional si no tienes QuestDB)
try:
    import psycopg2
    from psycopg2.extras import execute_batch
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logging.warning("psycopg2 no disponible - QuestDB storage deshabilitado")

logger = logging.getLogger(__name__)


class QuestDBStorage:
    """
    Manager para almacenamiento en QuestDB

    Usa psycopg2 para conectar vía PostgreSQL wire protocol
    QuestDB es compatible con psycopg2 en el puerto 8812
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8812,
        database: str = "qdb",
        user: str = "admin",
        password: str = "quest"
    ):
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 no está instalado. Instala con: pip install psycopg2-binary"
            )

        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password

        # Batch configuration
        self.batch_size = 1000
        self.batches: Dict[str, List] = {}  # table_name -> [rows]

        # Connection pool (simple implementation)
        self._connection = None

    @contextmanager
    def get_connection(self):
        """
        Context manager para obtener conexión a QuestDB
        """
        conn = None
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            yield conn
        except Exception as e:
            logger.error(f"❌ Error conectando a QuestDB: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def create_orderbook_table(self):
        """
        Crea tabla para snapshots de order book

        Estructura:
        - timestamp: TIMESTAMP (designated timestamp column)
        - symbol: SYMBOL (indexado automáticamente)
        - Métricas de L1 (best bid/ask)
        - Métricas microestructurales (OBI, spread, etc.)
        """
        sql = """
        CREATE TABLE IF NOT EXISTS orderbook_snapshots (
            timestamp TIMESTAMP,
            symbol SYMBOL,
            best_bid_price DOUBLE,
            best_bid_qty DOUBLE,
            best_ask_price DOUBLE,
            best_ask_qty DOUBLE,
            spread DOUBLE,
            spread_bps DOUBLE,
            mid_price DOUBLE,
            micro_price DOUBLE,
            obi_5 DOUBLE,
            obi_10 DOUBLE,
            obi_20 DOUBLE,
            bid_volume_5 DOUBLE,
            ask_volume_5 DOUBLE,
            bid_volume_10 DOUBLE,
            ask_volume_10 DOUBLE,
            weighted_mid_5 DOUBLE,
            last_update_id LONG
        ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    conn.commit()
            logger.info("✅ Tabla orderbook_snapshots creada/verificada")
        except Exception as e:
            logger.error(f"❌ Error creando tabla orderbook_snapshots: {e}")

    def create_microstructure_features_table(self):
        """
        Crea tabla para features microestructurales calculadas

        Incluye:
        - VPIN (Volume-Synchronized Probability of Informed Trading)
        - OFI (Order Flow Imbalance)
        - Trade flow toxicity
        - Price impact measures
        """
        sql = """
        CREATE TABLE IF NOT EXISTS microstructure_features (
            timestamp TIMESTAMP,
            symbol SYMBOL,
            vpin DOUBLE,
            vpin_window INT,
            ofi DOUBLE,
            trade_flow_toxicity DOUBLE,
            effective_spread DOUBLE,
            realized_spread DOUBLE,
            price_impact DOUBLE,
            kyle_lambda DOUBLE,
            roll_spread DOUBLE,
            volume_imbalance DOUBLE,
            trade_intensity DOUBLE
        ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    conn.commit()
            logger.info("✅ Tabla microstructure_features creada/verificada")
        except Exception as e:
            logger.error(f"❌ Error creando tabla microstructure_features: {e}")

    def create_trades_table(self):
        """
        Crea tabla para trades individuales
        """
        sql = """
        CREATE TABLE IF NOT EXISTS trades (
            timestamp TIMESTAMP,
            symbol SYMBOL,
            trade_id LONG,
            price DOUBLE,
            quantity DOUBLE,
            is_buyer_maker BOOLEAN,
            quote_qty DOUBLE
        ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    conn.commit()
            logger.info("✅ Tabla trades creada/verificada")
        except Exception as e:
            logger.error(f"❌ Error creando tabla trades: {e}")

    def create_funding_rate_table(self):
        """
        Crea tabla para funding rates
        """
        sql = """
        CREATE TABLE IF NOT EXISTS funding_rates (
            timestamp TIMESTAMP,
            symbol SYMBOL,
            funding_rate DOUBLE,
            funding_rate_delta DOUBLE,
            mark_price DOUBLE
        ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    conn.commit()
            logger.info("✅ Tabla funding_rates creada/verificada")
        except Exception as e:
            logger.error(f"❌ Error creando tabla funding_rates: {e}")

    def create_liquidations_table(self):
        """
        Crea tabla para liquidaciones
        """
        sql = """
        CREATE TABLE IF NOT EXISTS liquidations (
            timestamp TIMESTAMP,
            symbol SYMBOL,
            side SYMBOL,
            quantity DOUBLE,
            price DOUBLE,
            avg_price DOUBLE,
            notional DOUBLE
        ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    conn.commit()
            logger.info("✅ Tabla liquidations creada/verificada")
        except Exception as e:
            logger.error(f"❌ Error creando tabla liquidations: {e}")

    def create_open_interest_table(self):
        """
        Crea tabla para Open Interest
        """
        sql = """
        CREATE TABLE IF NOT EXISTS open_interest (
            timestamp TIMESTAMP,
            symbol SYMBOL,
            oi DOUBLE,
            oi_delta DOUBLE,
            oi_delta_pct DOUBLE
        ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    conn.commit()
            logger.info("✅ Tabla open_interest creada/verificada")
        except Exception as e:
            logger.error(f"❌ Error creando tabla open_interest: {e}")

    def create_derivatives_tables(self):
        """
        Inicializa todas las tablas de derivados
        """
        self.create_funding_rate_table()
        self.create_liquidations_table()
        self.create_open_interest_table()

    def initialize_tables(self):
        """
        Inicializa todas las tablas necesarias
        """
        self.create_orderbook_table()
        self.create_microstructure_features_table()
        self.create_trades_table()
        self.create_derivatives_tables()

    def insert_orderbook_snapshot(self, snapshot: Dict):
        """
        Inserta un snapshot del order book

        Args:
            snapshot: Dict con estructura del order book
        """
        table = "orderbook_snapshots"

        # Preparar fila
        row = (
            snapshot.get("timestamp"),
            snapshot.get("symbol"),
            snapshot.get("best_bid", [None, None])[0],
            snapshot.get("best_bid", [None, None])[1],
            snapshot.get("best_ask", [None, None])[0],
            snapshot.get("best_ask", [None, None])[1],
            snapshot.get("spread"),
            snapshot.get("spread_bps"),
            snapshot.get("mid_price"),
            snapshot.get("micro_price"),
            snapshot.get("obi_5"),
            snapshot.get("obi_10"),
            snapshot.get("obi_20"),
            snapshot.get("bid_volume_5"),
            snapshot.get("ask_volume_5"),
            snapshot.get("bid_volume_10"),
            snapshot.get("ask_volume_10"),
            snapshot.get("weighted_mid_5"),
            snapshot.get("last_update_id")
        )

        # Agregar a batch
        if table not in self.batches:
            self.batches[table] = []

        self.batches[table].append(row)

        # Si el batch está lleno, flush
        if len(self.batches[table]) >= self.batch_size:
            self.flush_batch(table)

    def insert_microstructure_features(self, features: Dict):
        """
        Inserta features microestructurales
        """
        table = "microstructure_features"

        row = (
            features.get("timestamp"),
            features.get("symbol"),
            features.get("vpin"),
            features.get("vpin_window"),
            features.get("ofi"),
            features.get("trade_flow_toxicity"),
            features.get("effective_spread"),
            features.get("realized_spread"),
            features.get("price_impact"),
            features.get("kyle_lambda"),
            features.get("roll_spread"),
            features.get("volume_imbalance"),
            features.get("trade_intensity")
        )

        if table not in self.batches:
            self.batches[table] = []

        self.batches[table].append(row)

        if len(self.batches[table]) >= self.batch_size:
            self.flush_batch(table)

    def insert_trade(self, trade: Dict):
        """
        Inserta un trade individual
        """
        table = "trades"

        row = (
            trade.get("timestamp"),
            trade.get("symbol"),
            trade.get("trade_id"),
            trade.get("price"),
            trade.get("quantity"),
            trade.get("is_buyer_maker"),
            trade.get("quote_qty")
        )

        if table not in self.batches:
            self.batches[table] = []

        self.batches[table].append(row)

        if len(self.batches[table]) >= self.batch_size:
            self.flush_batch(table)

    def insert_funding_rate(self, data: Dict):
        """
        Inserta funding rate
        """
        table = "funding_rates"

        row = (
            data.get("timestamp"),
            data.get("symbol"),
            data.get("funding_rate"),
            data.get("funding_rate_delta"),
            data.get("mark_price")
        )

        if table not in self.batches:
            self.batches[table] = []

        self.batches[table].append(row)

        if len(self.batches[table]) >= self.batch_size:
            self.flush_batch(table)

    def insert_liquidation(self, data: Dict):
        """
        Inserta liquidación
        """
        table = "liquidations"

        row = (
            data.get("timestamp"),
            data.get("symbol"),
            data.get("side"),
            data.get("quantity"),
            data.get("price"),
            data.get("avg_price"),
            data.get("notional")
        )

        if table not in self.batches:
            self.batches[table] = []

        self.batches[table].append(row)

        if len(self.batches[table]) >= self.batch_size:
            self.flush_batch(table)

    def insert_open_interest(self, data: Dict):
        """
        Inserta Open Interest
        """
        table = "open_interest"

        row = (
            data.get("timestamp"),
            data.get("symbol"),
            data.get("oi"),
            data.get("oi_delta"),
            data.get("oi_delta_pct")
        )

        if table not in self.batches:
            self.batches[table] = []

        self.batches[table].append(row)

        if len(self.batches[table]) >= self.batch_size:
            self.flush_batch(table)

    def flush_batch(self, table: str):
        """
        Escribe un batch completo a QuestDB
        """
        if table not in self.batches or not self.batches[table]:
            return

        rows = self.batches[table]

        # Construir SQL según la tabla
        if table == "orderbook_snapshots":
            sql = """
            INSERT INTO orderbook_snapshots VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
        elif table == "microstructure_features":
            sql = """
            INSERT INTO microstructure_features VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
        elif table == "trades":
            sql = """
            INSERT INTO trades VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
        elif table == "funding_rates":
            sql = """
            INSERT INTO funding_rates VALUES (%s, %s, %s, %s, %s)
            """
        elif table == "liquidations":
            sql = """
            INSERT INTO liquidations VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
        elif table == "open_interest":
            sql = """
            INSERT INTO open_interest VALUES (%s, %s, %s, %s, %s)
            """
        else:
            logger.error(f"❌ Tabla desconocida: {table}")
            return

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    execute_batch(cursor, sql, rows, page_size=self.batch_size)
                    conn.commit()

            logger.info(f"✅ Batch insertado - {table}: {len(rows)} rows")
            self.batches[table] = []

        except Exception as e:
            logger.error(f"❌ Error insertando batch en {table}: {e}")

    def flush_all_batches(self):
        """
        Escribe todos los batches pendientes
        """
        for table in list(self.batches.keys()):
            self.flush_batch(table)

    def query(self, sql: str, params: Optional[tuple] = None) -> List[Dict]:
        """
        Ejecuta un query SQL y retorna resultados

        Args:
            sql: Query SQL
            params: Parámetros para el query (optional)

        Returns:
            Lista de dicts con los resultados
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    if params:
                        cursor.execute(sql, params)
                    else:
                        cursor.execute(sql)

                    # Obtener nombres de columnas
                    columns = [desc[0] for desc in cursor.description]

                    # Convertir a lista de dicts
                    results = []
                    for row in cursor.fetchall():
                        results.append(dict(zip(columns, row)))

                    return results

        except Exception as e:
            logger.error(f"❌ Error ejecutando query: {e}")
            return []

    def get_latest_orderbook_snapshot(self, symbol: str) -> Optional[Dict]:
        """
        Obtiene el snapshot más reciente del order book para un símbolo
        """
        sql = """
        SELECT * FROM orderbook_snapshots
        WHERE symbol = %s
        ORDER BY timestamp DESC
        LIMIT 1
        """

        results = self.query(sql, (symbol,))
        return results[0] if results else None

    def get_orderbook_snapshots_range(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """
        Obtiene snapshots en un rango de tiempo
        """
        sql = """
        SELECT * FROM orderbook_snapshots
        WHERE symbol = %s
          AND timestamp >= %s
          AND timestamp < %s
        ORDER BY timestamp ASC
        """

        return self.query(sql, (symbol, start_time, end_time))

    def get_microstructure_stats(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict:
        """
        Calcula estadísticas agregadas de features microestructurales
        """
        sql = """
        SELECT
            avg(vpin) as avg_vpin,
            max(vpin) as max_vpin,
            avg(ofi) as avg_ofi,
            stddev(ofi) as std_ofi,
            avg(trade_flow_toxicity) as avg_toxicity,
            avg(effective_spread) as avg_eff_spread
        FROM microstructure_features
        WHERE symbol = %s
          AND timestamp >= %s
          AND timestamp < %s
        """

        results = self.query(sql, (symbol, start_time, end_time))
        return results[0] if results else {}


# Ejemplo de uso
if __name__ == "__main__":
    import time

    # Crear storage
    storage = QuestDBStorage()

    # Inicializar tablas
    storage.initialize_tables()

    # Insertar snapshots de prueba
    for i in range(10):
        snapshot = {
            "timestamp": datetime.now(),
            "symbol": "ETHUSDT",
            "best_bid": [2000.0 + i, 10.5],
            "best_ask": [2001.0 + i, 8.3],
            "spread": 1.0,
            "spread_bps": 5.0,
            "mid_price": 2000.5 + i,
            "micro_price": 2000.45 + i,
            "obi_5": 0.15,
            "obi_10": 0.12,
            "obi_20": 0.08,
            "bid_volume_5": 150.0,
            "ask_volume_5": 130.0,
            "bid_volume_10": 300.0,
            "ask_volume_10": 280.0,
            "weighted_mid_5": 2000.48 + i,
            "last_update_id": 123456 + i
        }

        storage.insert_orderbook_snapshot(snapshot)
        time.sleep(0.1)

    # Flush batches
    storage.flush_all_batches()

    # Query latest snapshot
    latest = storage.get_latest_orderbook_snapshot("ETHUSDT")
    print(f"\n📊 Latest Snapshot:")
    print(f"   Timestamp: {latest.get('timestamp')}")
    print(f"   Mid Price: ${latest.get('mid_price'):.2f}")
    print(f"   OBI_5: {latest.get('obi_5'):.4f}")

    print("\n✅ QuestDB Storage test completado")
