"""
Unified Storage Manager
Combina lo mejor de ambos conectores:
- ILP (port 9009) para inserts de alta frecuencia (tu implementación)
- PostgreSQL (port 8812) para queries analíticos (mi implementación)
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Import condicional de ambos conectores
try:
    from data.storage.questdb_connector import QuestDBConnector
    ILP_AVAILABLE = True
except Exception as e:
    ILP_AVAILABLE = False
    logger.warning(f"ILP connector no disponible: {e}")

try:
    from data.storage.questdb_storage import QuestDBStorage
    PSQL_AVAILABLE = True
except Exception as e:
    PSQL_AVAILABLE = False
    logger.warning(f"PostgreSQL connector no disponible: {e}")


class UnifiedQuestDBStorage:
    """
    Storage unificado que usa:
    - ILP para inserts rápidos (10x más rápido)
    - PostgreSQL para queries complejos

    Si solo uno está disponible, usa ese.
    """

    def __init__(
        self,
        host: str = "localhost",
        ilp_port: int = 9009,
        psql_port: int = 8812,
        prefer_ilp: bool = True
    ):
        self.host = host
        self.prefer_ilp = prefer_ilp

        # Connector ILP (para inserts rápidos)
        self.ilp: Optional[QuestDBConnector] = None
        if ILP_AVAILABLE:
            try:
                self.ilp = QuestDBConnector(host=host, port=ilp_port)
                self.ilp.connect()
                logger.info("✅ ILP connector habilitado (port 9009)")
            except Exception as e:
                logger.warning(f"⚠️  ILP connector falló: {e}")

        # Connector PostgreSQL (para queries)
        self.psql: Optional[QuestDBStorage] = None
        if PSQL_AVAILABLE:
            try:
                self.psql = QuestDBStorage(host=host, port=psql_port)
                logger.info("✅ PostgreSQL connector habilitado (port 8812)")
            except Exception as e:
                logger.warning(f"⚠️  PostgreSQL connector falló: {e}")

    def initialize_tables(self):
        """
        Crea tablas usando el connector PostgreSQL
        (ILP no necesita crear tablas, lo hace automáticamente)
        """
        if self.psql:
            self.psql.initialize_tables()
            logger.info("✅ Tablas inicializadas vía PostgreSQL")
        else:
            logger.warning("⚠️  No se pueden crear tablas (PostgreSQL no disponible)")

    def insert_fast(self, table_name: str, symbol: str, data: Dict):
        """
        Insert rápido usando ILP

        Usa esto para alta frecuencia (>10 inserts/segundo)
        """
        if self.ilp:
            self.ilp.insert(table_name, symbol, data)
        elif self.psql:
            # Fallback a PostgreSQL si ILP no disponible
            logger.debug("Usando PostgreSQL para insert (más lento)")
            self._insert_via_psql(table_name, symbol, data)
        else:
            logger.error("❌ No hay storage disponible")

    def insert_batch(self, snapshots: List[Dict]):
        """
        Insert batch usando PostgreSQL (optimizado para batches)

        Usa esto para batches grandes (<10 inserts/segundo)
        """
        if self.psql:
            for snapshot in snapshots:
                self.psql.insert_orderbook_snapshot(snapshot)
            self.psql.flush_all_batches()
        elif self.ilp:
            # Fallback a ILP individual
            for snapshot in snapshots:
                self.ilp.insert("orderbook_snapshots", snapshot["symbol"], snapshot)
        else:
            logger.error("❌ No hay storage disponible")

    def _insert_via_psql(self, table_name: str, symbol: str, data: Dict):
        """Helper para insertar vía PostgreSQL"""
        if not self.psql:
            return

        # Mapear a los métodos correctos
        data["symbol"] = symbol
        data["timestamp"] = datetime.now()

        if table_name == "orderbook_snapshots":
            self.psql.insert_orderbook_snapshot(data)
        elif table_name == "microstructure_features" or table_name == "features_microstructure":
            self.psql.insert_microstructure_features(data)
        elif table_name == "trades":
            self.psql.insert_trade(data)

    def query(self, sql: str, params: Optional[tuple] = None) -> List[Dict]:
        """
        Ejecuta query SQL (solo PostgreSQL)
        """
        if self.psql:
            return self.psql.query(sql, params)
        else:
            logger.error("❌ Queries no disponibles (PostgreSQL no habilitado)")
            return []

    def get_latest_orderbook_snapshot(self, symbol: str) -> Optional[Dict]:
        """Obtiene último snapshot"""
        if self.psql:
            return self.psql.get_latest_orderbook_snapshot(symbol)
        return None

    def flush(self):
        """Flush todos los batches pendientes"""
        if self.psql:
            self.psql.flush_all_batches()

        # ILP no tiene batching, todo es inmediato

    def close(self):
        """Cierra conexiones"""
        if self.ilp:
            self.ilp.close()

        if self.psql:
            self.psql.flush_all_batches()

    @property
    def is_available(self) -> bool:
        """Retorna True si hay al menos un storage disponible"""
        return self.ilp is not None or self.psql is not None

    def get_status(self) -> Dict:
        """Retorna estado de ambos conectores"""
        return {
            "ilp_available": self.ilp is not None and self.ilp.is_connected,
            "psql_available": self.psql is not None,
            "can_insert": self.ilp is not None or self.psql is not None,
            "can_query": self.psql is not None,
            "preferred_method": "ILP" if self.prefer_ilp and self.ilp else "PostgreSQL"
        }


# Ejemplo de uso
if __name__ == "__main__":
    storage = UnifiedQuestDBStorage()

    print("📊 Storage Status:")
    print(storage.get_status())

    if storage.is_available:
        # Test insert rápido
        data = {
            "mid_price": 2000.50,
            "spread": 0.05,
            "obi_5": 0.15,
            "vpin": 0.25
        }

        storage.insert_fast("features_microstructure", "ETHUSDT", data)
        print("✅ Insert test completado")
    else:
        print("⚠️  No hay storage disponible")
