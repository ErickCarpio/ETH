"""
Derivatives Data Collector - Phase 2
Recolecta datos de derivados en tiempo real y los guarda en QuestDB

Features recolectadas:
- Funding Rate (actualizado cada cambio)
- Liquidaciones (streaming en tiempo real)
- Open Interest (polling cada 30s)
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

# Import opcional de QuestDB
try:
    from data.storage.questdb_storage import QuestDBStorage
    QUESTDB_AVAILABLE = True
except ImportError:
    QUESTDB_AVAILABLE = False
    logging.warning("QuestDB no disponible - datos se guardarán solo en memoria")

from data.managers.derivatives_manager import DerivativesDataManager

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


class DerivativesCollector:
    """
    Collector que integra DerivativesDataManager con QuestDB storage
    """

    def __init__(self, symbol: str = "ETHUSDT"):
        self.symbol = symbol
        self.manager = DerivativesDataManager(symbol)

        # Storage
        self.storage = None
        if QUESTDB_AVAILABLE:
            try:
                self.storage = QuestDBStorage()
                self.storage.create_derivatives_tables()
                logger.info("✅ QuestDB storage habilitado")
            except Exception as e:
                logger.warning(f"⚠️  No se pudo conectar a QuestDB: {e}")
                self.storage = None

        # Stats
        self.funding_updates = 0
        self.liquidations_count = 0
        self.oi_updates = 0

        # Callbacks
        self.manager.on_funding_update = self._on_funding_update
        self.manager.on_liquidation = self._on_liquidation
        self.manager.on_oi_update = self._on_oi_update

    async def _on_funding_update(self, data: dict):
        """Callback cuando se actualiza funding rate"""
        self.funding_updates += 1

        if self.storage:
            try:
                self.storage.insert_funding_rate({
                    'timestamp': datetime.now(),
                    'symbol': self.symbol,
                    'funding_rate': data['funding_rate'],
                    'funding_rate_delta': data['funding_rate_delta'],
                    'mark_price': data['mark_price']
                })
            except Exception as e:
                logger.error(f"Error guardando funding rate: {e}")

    async def _on_liquidation(self, data: dict):
        """Callback cuando ocurre una liquidación"""
        self.liquidations_count += 1

        if self.storage:
            try:
                self.storage.insert_liquidation({
                    'timestamp': data['timestamp'],
                    'symbol': self.symbol,
                    'side': data['side'],
                    'quantity': data['quantity'],
                    'price': data['price'],
                    'avg_price': data['avg_price'],
                    'notional': data['notional']
                })
            except Exception as e:
                logger.error(f"Error guardando liquidation: {e}")

    async def _on_oi_update(self, data: dict):
        """Callback cuando se actualiza Open Interest"""
        self.oi_updates += 1

        if self.storage:
            try:
                self.storage.insert_open_interest({
                    'timestamp': datetime.now(),
                    'symbol': self.symbol,
                    'oi': data['oi'],
                    'oi_delta': data['oi_delta'],
                    'oi_delta_pct': data['oi_delta_pct']
                })
            except Exception as e:
                logger.error(f"Error guardando OI: {e}")

    async def start(self):
        """Inicia la recolección de datos"""
        logger.info(f"🚀 Iniciando recolección de derivados para {self.symbol}...")

        # Start manager
        await self.manager.start()

    async def stop(self):
        """Detiene la recolección"""
        await self.manager.stop()

        if self.storage:
            self.storage.flush_all_batches()

        logger.info(f"\n📊 Estadísticas:")
        logger.info(f"   Funding updates: {self.funding_updates}")
        logger.info(f"   Liquidaciones: {self.liquidations_count}")
        logger.info(f"   OI updates: {self.oi_updates}")

    async def print_stats_loop(self):
        """Loop que imprime estadísticas cada 10 segundos"""
        import time
        start_time = time.time()

        while True:
            await asyncio.sleep(10)

            uptime_hours = (time.time() - start_time) / 3600.0

            # Get current features
            features = self.manager.get_all_features()

            print(f"\n⏱️  Uptime: {uptime_hours:.1f} horas")
            print(f"   Funding Updates: {self.funding_updates}")
            print(f"   Liquidaciones: {self.liquidations_count}")
            print(f"   OI Updates: {self.oi_updates}")
            print(f"\n💰 Funding Rate: {features.get('funding_rate', 0):.6f}")
            print(f"   MA(10): {features.get('funding_rate_ma_10', 0):.6f}")
            print(f"   Trend: {features.get('funding_rate_trend', 'N/A')}")
            print(f"\n📊 Open Interest: {features.get('oi', 0):,.2f}")
            print(f"   Delta: {features.get('oi_delta', 0):+,.2f}")
            print(f"   Trend: {features.get('oi_trend', 'N/A')}")
            print(f"\n💥 Liquidaciones (5min):")
            print(f"   Count: {features.get('liq_count_5m', 0)}")
            print(f"   Volume: {features.get('liq_volume_5m', 0):.2f} ETH")
            print(f"   Long %: {features.get('liq_long_pct', 0):.1f}%")
            print(f"   Short %: {features.get('liq_short_pct', 0):.1f}%")

            # Flush storage
            if self.storage:
                self.storage.flush_all_batches()


async def main():
    """Main function"""
    print("🔄 Iniciando recolección de datos de derivados...")
    print("📊 Guardando en QuestDB" if QUESTDB_AVAILABLE else "⚠️  Sin QuestDB - solo modo monitor")
    print("⏱️  Déjalo corriendo al menos 1 hora (ideal: 24 horas)")
    print("⏹️  Presiona Ctrl+C para detener\n")

    collector = DerivativesCollector("ETHUSDT")

    try:
        # Start collector and stats loop
        await asyncio.gather(
            collector.start(),
            collector.print_stats_loop()
        )
    except KeyboardInterrupt:
        print("\n\n⏹️  Deteniendo recolección...")
        await collector.stop()
        print("\n✅ Recolección detenida")


if __name__ == "__main__":
    asyncio.run(main())
