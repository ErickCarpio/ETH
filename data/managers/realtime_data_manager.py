"""
Real-Time Data Manager
Integración completa de Fase 1

Orquesta todos los componentes:
- WebSocket Manager (conexiones persistentes)
- Order Book Reconstructor (sincronización L2)
- Microstructure Features Calculator (OBI, VPIN, OFI, etc.)
- QuestDB Storage (persistencia time-series)
- Rate Limiter (control de APIs)

Provee interfaz unificada para:
- Streaming de datos en tiempo real
- Cálculo de features microestructurales
- Almacenamiento histórico
- Queries analíticos
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime
import time

from data.managers.websocket_manager import DepthStreamManager, TradeStreamManager
from data.managers.orderbook_reconstructor import OrderBookReconstructor
from data.managers.rate_limiter import MultiSourceRateLimiter, create_binance_limiter
from microstructure.features import MicrostructureFeatures

# Import opcional de QuestDB
try:
    from data.storage.questdb_storage import QuestDBStorage
    QUESTDB_AVAILABLE = True
except ImportError:
    QUESTDB_AVAILABLE = False
    logging.warning("QuestDB storage no disponible (falta psycopg2)")
    QuestDBStorage = None

logger = logging.getLogger(__name__)


class RealtimeDataManager:
    """
    Manager principal para datos en tiempo real

    Uso:
        manager = RealtimeDataManager(symbol="ETHUSDT")
        await manager.start()

        # Obtener features actuales
        features = manager.get_current_features()

        # Obtener order book
        orderbook = manager.get_orderbook()
    """

    def __init__(
        self,
        symbol: str,
        enable_storage: bool = True,
        storage_batch_interval: int = 10,  # Guardar cada 10 segundos
        enable_trades: bool = True,
        questdb_host: str = "localhost",
        questdb_port: int = 8812
    ):
        self.symbol = symbol.upper()
        self.enable_storage = enable_storage
        self.storage_batch_interval = storage_batch_interval
        self.enable_trades = enable_trades

        # Componentes principales
        self.depth_manager = DepthStreamManager()
        self.trade_manager = TradeStreamManager() if enable_trades else None
        self.orderbook_reconstructor = OrderBookReconstructor(symbol)
        self.rate_limiter = MultiSourceRateLimiter()
        self.microstructure_calc = MicrostructureFeatures(symbol)

        # Storage (opcional)
        self.storage: Optional[QuestDBStorage] = None
        if enable_storage:
            if not QUESTDB_AVAILABLE:
                logger.warning("⚠️  QuestDB no disponible - instala: pip install psycopg2-binary")
                self.enable_storage = False
            else:
                try:
                    self.storage = QuestDBStorage(host=questdb_host, port=questdb_port)
                    self.storage.initialize_tables()
                    logger.info("✅ QuestDB storage habilitado")
                except Exception as e:
                    logger.warning(f"⚠️  No se pudo conectar a QuestDB: {e}")
                    self.enable_storage = False

        # Control de ejecución
        self.is_running = False
        self.tasks: List[asyncio.Task] = []

        # Callbacks externos
        self.feature_callbacks: List[Callable] = []

        # Métricas
        self.total_depth_updates = 0
        self.total_trades = 0
        self.total_features_calculated = 0
        self.start_time = 0.0

        # Cache de features actuales
        self.current_features: Dict = {}
        self.last_feature_update = 0.0

        # Configurar rate limiters
        self.rate_limiter.add_source("binance", create_binance_limiter().limits)

    async def start(self):
        """
        Inicia el streaming de datos en tiempo real
        """
        if self.is_running:
            logger.warning("⚠️  Manager ya está corriendo")
            return

        self.is_running = True
        self.start_time = time.time()

        logger.info(f"🚀 Iniciando RealtimeDataManager para {self.symbol}...")

        # 1. Inicializar order book con snapshot
        await self.orderbook_reconstructor.initialize()

        # 2. Conectar depth stream
        depth_stream = await self.depth_manager.connect_depth(
            self.symbol.lower(),
            self._on_depth_update,
            update_speed="100ms"
        )
        logger.info(f"✅ Depth stream conectado: {depth_stream}")

        # 3. Conectar trade stream (opcional)
        if self.enable_trades and self.trade_manager:
            trade_stream = await self.trade_manager.connect_agg_trades(
                self.symbol.lower(),
                self._on_trade
            )
            logger.info(f"✅ Trade stream conectado: {trade_stream}")

        # 4. Iniciar task de sincronización periódica
        sync_task = asyncio.create_task(self._periodic_sync_check())
        self.tasks.append(sync_task)

        # 5. Iniciar task de storage periódico
        if self.enable_storage:
            storage_task = asyncio.create_task(self._periodic_storage())
            self.tasks.append(storage_task)

        logger.info(f"✅ RealtimeDataManager iniciado para {self.symbol}")

    async def stop(self):
        """
        Detiene el streaming y limpia recursos
        """
        if not self.is_running:
            return

        logger.info(f"🛑 Deteniendo RealtimeDataManager...")

        self.is_running = False

        # Cancelar tasks
        for task in self.tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Desconectar streams
        await self.depth_manager.disconnect_all()
        if self.trade_manager:
            await self.trade_manager.disconnect_all()

        # Flush storage final
        if self.storage:
            self.storage.flush_all_batches()

        logger.info(f"✅ RealtimeDataManager detenido")

    async def _on_depth_update(self, data: Dict):
        """
        Callback para depth updates del WebSocket

        Args:
            data: Depth update event
        """
        try:
            # Aplicar rate limiting (por si acaso, aunque WebSocket no tiene límite)
            # await self.rate_limiter.acquire("binance", priority=1)

            # Procesar depth update
            await self.orderbook_reconstructor.process_depth_update(data)
            self.total_depth_updates += 1

            # Calcular features cada N updates (para no saturar)
            if self.total_depth_updates % 10 == 0:  # Cada 10 updates (aprox 1 segundo)
                await self._calculate_and_update_features()

        except Exception as e:
            logger.error(f"❌ Error procesando depth update: {e}")

    async def _on_trade(self, data: Dict):
        """
        Callback para trades del WebSocket

        Args:
            data: Trade event
        """
        try:
            # Extraer datos del trade
            trade = {
                "timestamp": datetime.fromtimestamp(data.get("T", 0) / 1000.0),
                "symbol": self.symbol,
                "trade_id": data.get("a"),
                "price": float(data.get("p", 0)),
                "quantity": float(data.get("q", 0)),
                "is_buyer_maker": data.get("m", False),  # m=True -> sell, m=False -> buy
                "quote_qty": float(data.get("p", 0)) * float(data.get("q", 0))
            }

            # Agregar a microstructure calculator
            self.microstructure_calc.add_trade({
                "price": trade["price"],
                "quantity": trade["quantity"],
                "is_buy": not trade["is_buyer_maker"],  # Invertir porque m=maker side
                "timestamp": trade["timestamp"]
            })

            self.total_trades += 1

            # Guardar en storage
            if self.storage:
                self.storage.insert_trade(trade)

        except Exception as e:
            logger.error(f"❌ Error procesando trade: {e}")

    async def _calculate_and_update_features(self):
        """
        Calcula features microestructurales y las almacena
        """
        try:
            # Obtener order book actual
            orderbook = self.orderbook_reconstructor.get_orderbook()
            orderbook_dict = orderbook.to_dict()

            # Agregar al historial del calculator
            self.microstructure_calc.add_orderbook_snapshot(orderbook_dict)

            # Calcular todas las features microestructurales
            micro_features = self.microstructure_calc.get_all_features(orderbook_dict)

            # Combinar con features básicas del order book
            all_features = {
                **orderbook_dict,
                **micro_features,
                "timestamp": datetime.fromtimestamp(orderbook.last_update_time)
            }

            # Actualizar cache
            self.current_features = all_features
            self.last_feature_update = time.time()
            self.total_features_calculated += 1

            # Llamar callbacks externos
            for callback in self.feature_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(all_features)
                    else:
                        callback(all_features)
                except Exception as e:
                    logger.error(f"❌ Error en callback: {e}")

        except Exception as e:
            logger.error(f"❌ Error calculando features: {e}")

    async def _periodic_sync_check(self):
        """
        Verifica periódicamente la sincronización del order book
        """
        while self.is_running:
            try:
                await asyncio.sleep(30)  # Cada 30 segundos
                await self.orderbook_reconstructor.check_synchronization()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error en sync check: {e}")

    async def _periodic_storage(self):
        """
        Guarda snapshots periódicamente en QuestDB
        """
        while self.is_running:
            try:
                await asyncio.sleep(self.storage_batch_interval)

                if self.storage and self.current_features:
                    # Guardar snapshot del order book
                    orderbook = self.orderbook_reconstructor.get_orderbook()
                    snapshot_dict = orderbook.to_dict()

                    # Agregar features calculadas
                    snapshot_dict["spread_bps"] = (
                        (snapshot_dict["spread"] / snapshot_dict["mid_price"]) * 10000
                        if snapshot_dict.get("spread") and snapshot_dict.get("mid_price")
                        else None
                    )

                    # Calcular volúmenes agregados
                    level_stats = orderbook.get_level_stats(5)
                    snapshot_dict["bid_volume_5"] = level_stats["bid_volume"]
                    snapshot_dict["ask_volume_5"] = level_stats["ask_volume"]

                    level_stats_10 = orderbook.get_level_stats(10)
                    snapshot_dict["bid_volume_10"] = level_stats_10["bid_volume"]
                    snapshot_dict["ask_volume_10"] = level_stats_10["ask_volume"]

                    snapshot_dict["weighted_mid_5"] = orderbook.get_weighted_mid_price(5)

                    # Insertar en storage
                    self.storage.insert_orderbook_snapshot(snapshot_dict)

                    # Guardar features microestructurales
                    if "vpin" in self.current_features:
                        micro_features = {
                            "timestamp": snapshot_dict["timestamp"],
                            "symbol": self.symbol,
                            "vpin": self.current_features.get("vpin"),
                            "vpin_window": 50,  # Del config
                            "ofi": self.current_features.get("ofi"),
                            "trade_flow_toxicity": None,  # Calcular en Fase 2
                            "effective_spread": self.current_features.get("effective_spread"),
                            "realized_spread": None,  # Calcular en Fase 2
                            "price_impact": None,  # Calcular en Fase 2
                            "kyle_lambda": self.current_features.get("kyle_lambda"),
                            "roll_spread": self.current_features.get("roll_spread"),
                            "volume_imbalance": self.current_features.get("obi_5"),
                            "trade_intensity": None  # Calcular en Fase 2
                        }

                        self.storage.insert_microstructure_features(micro_features)

                    # Flush batches si es necesario
                    if self.total_features_calculated % 100 == 0:
                        self.storage.flush_all_batches()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error en periodic storage: {e}")

    def register_feature_callback(self, callback: Callable):
        """
        Registra un callback para recibir features calculadas

        Args:
            callback: Función async(features: Dict) o sync(features: Dict)
        """
        self.feature_callbacks.append(callback)
        logger.info(f"✅ Callback registrado")

    def get_orderbook(self):
        """
        Retorna el order book actual
        """
        return self.orderbook_reconstructor.get_orderbook()

    def get_current_features(self) -> Dict:
        """
        Retorna las features más recientes calculadas
        """
        return self.current_features.copy()

    def get_stats(self) -> Dict:
        """
        Retorna estadísticas del manager
        """
        uptime = time.time() - self.start_time if self.start_time > 0 else 0

        return {
            "symbol": self.symbol,
            "is_running": self.is_running,
            "uptime_seconds": uptime,
            "total_depth_updates": self.total_depth_updates,
            "total_trades": self.total_trades,
            "total_features_calculated": self.total_features_calculated,
            "depth_updates_per_sec": self.total_depth_updates / max(1, uptime),
            "trades_per_sec": self.total_trades / max(1, uptime),
            "storage_enabled": self.enable_storage,
            "orderbook_stats": self.orderbook_reconstructor.get_stats(),
            "last_feature_update": self.last_feature_update,
            "features_age_seconds": time.time() - self.last_feature_update if self.last_feature_update > 0 else None
        }


# Ejemplo de uso
if __name__ == "__main__":
    async def on_features_update(features: Dict):
        """Callback de ejemplo"""
        print(f"\n📊 Features Update:")
        print(f"   Mid Price: ${features.get('mid_price', 0):.2f}")
        print(f"   Micro Price: ${features.get('micro_price', 0):.2f}")
        print(f"   OBI(5): {features.get('obi_5', 0):.4f}")
        print(f"   OFI: {features.get('ofi', 0):.4f}")
        print(f"   VPIN: {features.get('vpin', 0):.4f}")

    async def main():
        # Crear manager
        manager = RealtimeDataManager(
            symbol="ETHUSDT",
            enable_storage=False,  # Deshabilitar si no tienes QuestDB corriendo
            enable_trades=True
        )

        # Registrar callback
        manager.register_feature_callback(on_features_update)

        # Iniciar
        await manager.start()

        # Correr por 60 segundos
        for i in range(60):
            await asyncio.sleep(1)

            if i % 10 == 0:
                stats = manager.get_stats()
                print(f"\n📈 Stats (t={i}s):")
                print(f"   Depth updates: {stats['total_depth_updates']}")
                print(f"   Trades: {stats['total_trades']}")
                print(f"   Updates/sec: {stats['depth_updates_per_sec']:.1f}")

        # Detener
        await manager.stop()

        # Stats finales
        print(f"\n✅ Test completado")
        print(f"📊 Stats Finales:")
        final_stats = manager.get_stats()
        for key, value in final_stats.items():
            if not isinstance(value, dict):
                print(f"   {key}: {value}")

    asyncio.run(main())
