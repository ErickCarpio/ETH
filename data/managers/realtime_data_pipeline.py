"""
Real-Time Data Pipeline - Integración FASE 1+2+3
=================================================

Conecta todos los componentes para ingesta de datos en tiempo real:
1. WebSocket Manager → Order Book Depth
2. Order Book Reconstructor → Book L2 local
3. Microstructure Features → OBI, VPIN, OFI, Microprice
4. QuestDB Storage → Almacenamiento series temporales
5. Deribit GEX → Opciones y gamma exposure

Workflow:
- WebSocket recibe depth updates @100ms
- Order Book Reconstructor mantiene book L2
- Cada 1s: calcular features de microestructura
- Cada 1s: guardar snapshot en QuestDB
- Cada 5min: fetch GEX de Deribit
- Cada 4h: agregar features para modelo
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
import pandas as pd
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from data.managers.websocket_manager import DepthStreamManager
from data.fetchers.orderbook_fetcher import OrderBookReconstructor
from data.fetchers.deribit_fetcher import DeribOptions
from data.storage.questdb_connector import QuestDBConnector

# Microstructure calculators
try:
    from features.microstructure.order_book_processor import OrderBookProcessor
    from features.microstructure.vpin_calculator import VPINCalculator
    from features.microstructure.ofi_calculator import OFICalculator
    from features.microstructure.microprice_calculator import MicropriceCalculator
    MICROSTRUCTURE_AVAILABLE = True
except ImportError:
    MICROSTRUCTURE_AVAILABLE = False
    logging.warning("Microstructure features not available")

logger = logging.getLogger(__name__)


class RealtimeDataPipeline:
    """
    Pipeline principal para ingesta de datos en tiempo real.

    Componentes:
    - WebSocket Manager (Binance depth stream)
    - Order Book Reconstructor (L2 local)
    - Microstructure Calculators (OBI, VPIN, OFI, Microprice)
    - QuestDB Storage
    - Deribit GEX (opciones)
    """

    def __init__(self,
                 symbol: str = "ETHUSDT",
                 snapshot_interval: int = 1,      # segundos
                 gex_interval: int = 300):         # 5 minutos
        """
        Initialize Real-Time Data Pipeline.

        Args:
            symbol: Par de trading
            snapshot_interval: Intervalo para snapshots (segundos)
            gex_interval: Intervalo para GEX fetch (segundos)
        """
        self.symbol = symbol.upper()
        self.snapshot_interval = snapshot_interval
        self.gex_interval = gex_interval

        # Components
        self.ws_manager = DepthStreamManager()
        self.orderbook = OrderBookReconstructor(symbol=symbol, limit=1000)
        self.questdb = QuestDBConnector()
        self.deribit = DeribOptions(currency=symbol.replace('USDT', ''))

        # Microstructure calculators
        if MICROSTRUCTURE_AVAILABLE:
            self.obi_calc = OrderBookProcessor()
            self.vpin_calc = VPINCalculator()
            self.ofi_calc = OFICalculator()
            self.micro_calc = MicropriceCalculator()
        else:
            logger.warning("Microstructure calculators not available")

        # State
        self.running = False
        self.prev_book = None
        self.trade_buffer = []

        # Stats
        self.snapshots_saved = 0
        self.features_calculated = 0
        self.gex_updates = 0

    async def start(self) -> None:
        """
        Inicia el pipeline completo.
        """
        logger.info(f"Starting Real-Time Data Pipeline for {self.symbol}")

        self.running = True

        # 1. Inicializar Order Book con snapshot
        logger.info("Initializing Order Book...")
        success = await self.orderbook.initialize()

        if not success:
            logger.error("Failed to initialize Order Book")
            return

        # 2. Conectar WebSocket para depth updates
        logger.info("Connecting WebSocket...")
        stream_id = await self.ws_manager.connect_depth(
            symbol=self.symbol,
            callback=self._on_depth_update,
            update_speed='100ms'
        )

        # 3. Start background tasks
        tasks = [
            asyncio.create_task(self._snapshot_loop()),
            asyncio.create_task(self._gex_loop()),
            asyncio.create_task(self.orderbook.periodic_snapshot())
        ]

        logger.info("✅ Pipeline started successfully")
        logger.info(f"  WebSocket: {stream_id}")
        logger.info(f"  Order Book: {len(self.orderbook.bids)} bids, {len(self.orderbook.asks)} asks")
        logger.info(f"  Snapshot interval: {self.snapshot_interval}s")
        logger.info(f"  GEX interval: {self.gex_interval}s")

        # 4. Wait for tasks
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            await self.stop()

    async def stop(self) -> None:
        """
        Detiene el pipeline.
        """
        logger.info("Stopping pipeline...")

        self.running = False

        # Disconnect WebSocket
        await self.ws_manager.disconnect_all()

        # Close QuestDB
        # self.questdb.close()  # Si tiene método close

        logger.info("✅ Pipeline stopped")

    async def _on_depth_update(self, data: Dict) -> None:
        """
        Callback para depth updates del WebSocket.

        Args:
            data: Depth update event
        """
        # Aplicar diff al order book local
        self.orderbook.apply_diff(data)

    async def _snapshot_loop(self) -> None:
        """
        Loop que toma snapshots periódicos y calcula features.
        """
        while self.running:
            await asyncio.sleep(self.snapshot_interval)

            try:
                # 1. Get current order book
                book = self.orderbook.get_book(depth=20)

                # 2. Calculate microstructure features
                if MICROSTRUCTURE_AVAILABLE:
                    features = self._calculate_features(book)
                else:
                    features = {}

                # 3. Save to QuestDB
                await self._save_snapshot(book, features)

                self.snapshots_saved += 1
                self.features_calculated += 1

                # Log every 60 snapshots (~1 minute)
                if self.snapshots_saved % 60 == 0:
                    logger.info(f"Stats: {self.snapshots_saved} snapshots, {self.features_calculated} features, {self.gex_updates} GEX updates")

            except Exception as e:
                logger.error(f"Error in snapshot loop: {e}")

    def _calculate_features(self, book: Dict) -> Dict:
        """
        Calcula features de microestructura.

        Args:
            book: Order book snapshot

        Returns:
            Dict con features
        """
        features = {}

        try:
            # Convertir book a formato esperado por calculators
            book_data = {
                'bids': book['bids'],
                'asks': book['asks'],
                'mid_price': book['mid_price']
            }

            # OBI (Order Book Imbalance)
            if hasattr(self, 'obi_calc'):
                obi_features = self.obi_calc.calculate_obi(book_data, levels=[1, 5, 10, 20])
                features.update(obi_features)

            # OFI (Order Flow Imbalance)
            if hasattr(self, 'ofi_calc') and self.prev_book:
                ofi_features = self.ofi_calc.calculate_ofi(self.prev_book, book_data)
                features.update(ofi_features)

            # Microprice
            if hasattr(self, 'micro_calc'):
                micro_features = self.micro_calc.calculate_microprice(book_data)
                features.update(micro_features)

            # VPIN (requiere trades, que vienen de otro stream)
            # Por ahora skip si no tenemos trades
            # if hasattr(self, 'vpin_calc') and self.trade_buffer:
            #     vpin_features = self.vpin_calc.calculate_vpin(self.trade_buffer)
            #     features.update(vpin_features)

            # Save prev book for OFI
            self.prev_book = book_data.copy()

        except Exception as e:
            logger.error(f"Error calculating features: {e}")

        return features

    async def _save_snapshot(self, book: Dict, features: Dict) -> None:
        """
        Guarda snapshot en QuestDB.

        Args:
            book: Order book data
            features: Microstructure features
        """
        try:
            # Preparar data para QuestDB
            timestamp = datetime.now()

            # Extract top 10 bids/asks
            bids_prices = [b[0] for b in book['bids'][:10]]
            bids_vols = [b[1] for b in book['bids'][:10]]
            asks_prices = [a[0] for a in book['asks'][:10]]
            asks_vols = [a[1] for a in book['asks'][:10]]

            # Pad to 10 levels if needed
            while len(bids_prices) < 10:
                bids_prices.append(0.0)
                bids_vols.append(0.0)
            while len(asks_prices) < 10:
                asks_prices.append(0.0)
                asks_vols.append(0.0)

            # Insert to QuestDB
            # self.questdb.insert_orderbook_snapshot(
            #     timestamp=timestamp,
            #     symbol=self.symbol,
            #     bid_prices=bids_prices,
            #     bid_vols=bids_vols,
            #     ask_prices=asks_prices,
            #     ask_vols=asks_vols,
            #     **features
            # )

            # For now just log (descomenta arriba cuando QuestDB esté listo)
            logger.debug(f"Snapshot: mid=${book['mid_price']:.2f}, spread={book['spread_bps']:.2f}bps, features={len(features)}")

        except Exception as e:
            logger.error(f"Error saving snapshot: {e}")

    async def _gex_loop(self) -> None:
        """
        Loop que fetch GEX de Deribit periódicamente.
        """
        while self.running:
            await asyncio.sleep(self.gex_interval)

            try:
                logger.info("Fetching GEX from Deribit...")

                # Fetch GEX
                df, gex_by_strike = await self.deribit.calculate_gex()

                if not gex_by_strike.empty:
                    # Get spot price
                    spot = await self.deribit.get_current_price()

                    # Get levels
                    levels = self.deribit.get_gex_levels(gex_by_strike, spot)

                    # Log summary
                    logger.info(f"✓ GEX Update:")
                    logger.info(f"  Total GEX: ${levels['total_gex']:,.0f}")
                    logger.info(f"  Nearest Support: ${levels.get('nearest_support', {}).get('strike', 'N/A')}")
                    logger.info(f"  Nearest Resistance: ${levels.get('nearest_resistance', {}).get('strike', 'N/A')}")

                    # Save to QuestDB (implementar)
                    # self.questdb.insert_gex(timestamp, levels)

                    self.gex_updates += 1

            except Exception as e:
                logger.error(f"Error in GEX loop: {e}")

    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas del pipeline.

        Returns:
            Dict con stats
        """
        return {
            'running': self.running,
            'symbol': self.symbol,
            'snapshots_saved': self.snapshots_saved,
            'features_calculated': self.features_calculated,
            'gex_updates': self.gex_updates,
            'orderbook_stats': self.orderbook.get_stats(),
            'websocket_health': self.ws_manager.get_health_status(f"{self.symbol.lower()}@depth@100ms")
        }


async def main():
    """
    Ejemplo de uso del Real-Time Data Pipeline.
    """
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Crear pipeline
    pipeline = RealtimeDataPipeline(
        symbol='ETHUSDT',
        snapshot_interval=1,    # 1 snapshot/segundo
        gex_interval=300        # GEX cada 5 minutos
    )

    # Iniciar pipeline
    try:
        await pipeline.start()
    except KeyboardInterrupt:
        await pipeline.stop()

    # Show final stats
    stats = pipeline.get_stats()
    print("\n" + "="*60)
    print("PIPELINE STATS")
    print("="*60)
    print(f"Snapshots saved: {stats['snapshots_saved']}")
    print(f"Features calculated: {stats['features_calculated']}")
    print(f"GEX updates: {stats['gex_updates']}")
    print(f"Order Book: {stats['orderbook_stats']['updates_processed']} updates processed")
    print(f"Gaps detected: {stats['orderbook_stats']['gaps_detected']}")


if __name__ == "__main__":
    asyncio.run(main())
