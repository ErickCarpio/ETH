"""
Order Book Reconstructor - FASE 1.2
====================================

Reconstrucción de Order Book L2 local en memoria usando:
1. Snapshot inicial (REST API)
2. Diff updates en tiempo real (WebSocket)

Algoritmo de sincronización según documentación Binance:
https://binance-docs.github.io/apidocs/spot/en/#how-to-manage-a-local-order-book-correctly

Features:
- Reconstrucción book L2 completo
- Validación de secuencia (lastUpdateId)
- Snapshot periódico para rollback
- Detección de gaps y auto-recuperación
"""

import aiohttp
import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Tuple
from collections import OrderedDict
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


class OrderBookReconstructor:
    """
    Reconstruye y mantiene Order Book L2 local.

    Workflow:
    1. Buffer eventos del WebSocket
    2. GET snapshot inicial vía REST
    3. Descartar eventos antiguos (u <= lastUpdateId)
    4. Aplicar eventos donde U <= lastUpdateId+1 AND u >= lastUpdateId+1
    5. Mantener book local actualizado
    6. Validar secuencia continuamente
    """

    def __init__(self,
                 symbol: str = "ETHUSDT",
                 limit: int = 5000,
                 snapshot_interval: int = 300):
        """
        Initialize Order Book Reconstructor.

        Args:
            symbol: Par de trading (ETHUSDT, BTCUSDT, etc.)
            limit: Profundidad del snapshot (5, 10, 20, 50, 100, 500, 1000, 5000)
            snapshot_interval: Intervalo para snapshots periódicos (segundos)
        """
        self.symbol = symbol.upper()
        self.limit = limit
        self.snapshot_interval = snapshot_interval

        # Order book state
        self.bids: OrderedDict = OrderedDict()  # {price: quantity}
        self.asks: OrderedDict = OrderedDict()  # {price: quantity}
        self.last_update_id = 0

        # Buffer para eventos WebSocket
        self.event_buffer: List[Dict] = []
        self.initialized = False

        # Validation
        self.updates_processed = 0
        self.updates_dropped = 0
        self.gaps_detected = 0
        self.last_snapshot_time = 0

        # Binance REST endpoint
        self.rest_url = "https://api.binance.com/api/v3/depth"

    async def initialize(self) -> bool:
        """
        Inicializa el order book con snapshot inicial.

        Returns:
            True si inicialización exitosa
        """
        try:
            logger.info(f"Initializing order book for {self.symbol}...")

            # 1. Obtener snapshot inicial
            snapshot = await self._fetch_snapshot()

            if not snapshot:
                logger.error("Failed to fetch initial snapshot")
                return False

            # 2. Aplicar snapshot
            self._apply_snapshot(snapshot)

            # 3. Procesar eventos bufferados
            self._process_buffered_events()

            self.initialized = True
            self.last_snapshot_time = time.time()

            logger.info(f"✓ Order book initialized - lastUpdateId: {self.last_update_id}")
            logger.info(f"  Bids: {len(self.bids)} levels, Asks: {len(self.asks)} levels")

            return True

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    async def _fetch_snapshot(self) -> Optional[Dict]:
        """
        Obtiene snapshot del order book vía REST API.

        Returns:
            Dict con snapshot data
        """
        params = {
            'symbol': self.symbol,
            'limit': self.limit
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.rest_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(f"Snapshot fetched - lastUpdateId: {data.get('lastUpdateId')}")
                        return data
                    else:
                        logger.error(f"Snapshot request failed: {response.status}")
                        return None

        except Exception as e:
            logger.error(f"Error fetching snapshot: {e}")
            return None

    def _apply_snapshot(self, snapshot: Dict) -> None:
        """
        Aplica snapshot inicial al order book.

        Args:
            snapshot: Data del snapshot con bids, asks, lastUpdateId
        """
        # Clear existing book
        self.bids.clear()
        self.asks.clear()

        # Update lastUpdateId
        self.last_update_id = snapshot['lastUpdateId']

        # Apply bids
        for price_str, qty_str in snapshot['bids']:
            price = float(price_str)
            qty = float(qty_str)
            if qty > 0:
                self.bids[price] = qty

        # Apply asks
        for price_str, qty_str in snapshot['asks']:
            price = float(price_str)
            qty = float(qty_str)
            if qty > 0:
                self.asks[price] = qty

        # Sort bids descending, asks ascending
        self.bids = OrderedDict(sorted(self.bids.items(), reverse=True))
        self.asks = OrderedDict(sorted(self.asks.items()))

        logger.debug(f"Snapshot applied - Bids: {len(self.bids)}, Asks: {len(self.asks)}")

    def apply_diff(self, event: Dict) -> bool:
        """
        Aplica diff update del WebSocket.

        Args:
            event: Evento de depth update

        Returns:
            True si update aplicado, False si descartado
        """
        # Si no inicializado, buffear evento
        if not self.initialized:
            self.event_buffer.append(event)
            return False

        # Extraer campos
        U = event.get('U')  # First update ID in event
        u = event.get('u')  # Final update ID in event
        b = event.get('b', [])  # Bid updates [[price, qty], ...]
        a = event.get('a', [])  # Ask updates [[price, qty], ...]

        # Validar secuencia según documentación Binance:
        # The first processed event should have U <= lastUpdateId+1 AND u >= lastUpdateId+1
        if self.updates_processed == 0:
            if U <= self.last_update_id + 1 and u >= self.last_update_id + 1:
                # OK - primer evento válido
                pass
            else:
                # Descartar evento fuera de secuencia
                self.updates_dropped += 1
                return False
        else:
            # Eventos posteriores: u debe ser last_update_id + 1
            if U != self.last_update_id + 1:
                # Gap detectado
                logger.warning(f"Gap detected: expected U={self.last_update_id + 1}, got U={U}")
                self.gaps_detected += 1

                # Reinicializar book
                asyncio.create_task(self.initialize())
                return False

        # Aplicar updates de bids
        for price_str, qty_str in b:
            price = float(price_str)
            qty = float(qty_str)

            if qty == 0:
                # Eliminar nivel
                self.bids.pop(price, None)
            else:
                # Actualizar nivel
                self.bids[price] = qty

        # Aplicar updates de asks
        for price_str, qty_str in a:
            price = float(price_str)
            qty = float(qty_str)

            if qty == 0:
                # Eliminar nivel
                self.asks.pop(price, None)
            else:
                # Actualizar nivel
                self.asks[price] = qty

        # Ordenar de nuevo (solo si añadimos niveles nuevos)
        self.bids = OrderedDict(sorted(self.bids.items(), reverse=True))
        self.asks = OrderedDict(sorted(self.asks.items()))

        # Actualizar lastUpdateId
        self.last_update_id = u
        self.updates_processed += 1

        return True

    def _process_buffered_events(self) -> None:
        """
        Procesa eventos que llegaron antes de la inicialización.
        """
        logger.info(f"Processing {len(self.event_buffer)} buffered events...")

        applied = 0
        for event in self.event_buffer:
            if self.apply_diff(event):
                applied += 1

        self.event_buffer.clear()

        logger.info(f"✓ Processed buffer - Applied: {applied}/{len(self.event_buffer)} events")

    def get_book(self, depth: int = 10) -> Dict:
        """
        Obtiene top N niveles del order book.

        Args:
            depth: Número de niveles (default 10)

        Returns:
            Dict con bids, asks, mid_price, spread
        """
        # Top N bids (mejores precios = más altos)
        top_bids = list(self.bids.items())[:depth]

        # Top N asks (mejores precios = más bajos)
        top_asks = list(self.asks.items())[:depth]

        # Calculate mid price and spread
        if top_bids and top_asks:
            best_bid = top_bids[0][0]
            best_ask = top_asks[0][0]
            mid_price = (best_bid + best_ask) / 2
            spread = best_ask - best_bid
            spread_bps = (spread / mid_price) * 10000
        else:
            mid_price = None
            spread = None
            spread_bps = None

        return {
            'symbol': self.symbol,
            'timestamp': time.time(),
            'lastUpdateId': self.last_update_id,
            'bids': top_bids,  # [(price, qty), ...]
            'asks': top_asks,  # [(price, qty), ...]
            'mid_price': mid_price,
            'spread': spread,
            'spread_bps': spread_bps,
            'total_bid_levels': len(self.bids),
            'total_ask_levels': len(self.asks)
        }

    def validate_sequence(self) -> bool:
        """
        Valida integridad del order book.

        Returns:
            True si book válido
        """
        # Check que tenemos bids y asks
        if not self.bids or not self.asks:
            logger.warning("Empty book detected")
            return False

        # Check que best bid < best ask (no crossed book)
        best_bid = list(self.bids.keys())[0]
        best_ask = list(self.asks.keys())[0]

        if best_bid >= best_ask:
            logger.error(f"Crossed book detected: bid={best_bid}, ask={best_ask}")
            return False

        return True

    async def periodic_snapshot(self) -> None:
        """
        Toma snapshot periódico para validación y rollback.
        """
        while True:
            await asyncio.sleep(self.snapshot_interval)

            # Fetch new snapshot
            snapshot = await self._fetch_snapshot()

            if not snapshot:
                continue

            # Comparar con book local
            snapshot_last_id = snapshot['lastUpdateId']

            if abs(snapshot_last_id - self.last_update_id) > 100:
                logger.warning(f"Local book drift detected: local={self.last_update_id}, snapshot={snapshot_last_id}")

                # Reinicializar
                await self.initialize()

            self.last_snapshot_time = time.time()

    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas del reconstructor.

        Returns:
            Dict con métricas
        """
        return {
            'symbol': self.symbol,
            'initialized': self.initialized,
            'last_update_id': self.last_update_id,
            'updates_processed': self.updates_processed,
            'updates_dropped': self.updates_dropped,
            'gaps_detected': self.gaps_detected,
            'bid_levels': len(self.bids),
            'ask_levels': len(self.asks),
            'book_valid': self.validate_sequence(),
            'seconds_since_snapshot': time.time() - self.last_snapshot_time,
            'buffer_size': len(self.event_buffer)
        }


async def main():
    """
    Ejemplo de uso del OrderBookReconstructor.
    """
    # Crear reconstructor
    reconstructor = OrderBookReconstructor(symbol='ETHUSDT', limit=1000)

    # Inicializar con snapshot
    success = await reconstructor.initialize()

    if not success:
        logger.error("Failed to initialize")
        return

    # Simular algunos eventos (en producción vienen del WebSocket)
    # ...

    # Obtener book
    book = reconstructor.get_book(depth=10)

    print("\n" + "="*60)
    print("ORDER BOOK SNAPSHOT")
    print("="*60)
    print(f"Symbol: {book['symbol']}")
    print(f"Mid Price: ${book['mid_price']:.2f}")
    print(f"Spread: ${book['spread']:.4f} ({book['spread_bps']:.2f} bps)")
    print(f"\nTop 10 Bids:")
    for price, qty in book['bids']:
        print(f"  ${price:.2f} x {qty:.4f} ETH")

    print(f"\nTop 10 Asks:")
    for price, qty in book['asks']:
        print(f"  ${price:.2f} x {qty:.4f} ETH")

    # Stats
    stats = reconstructor.get_stats()
    print(f"\nStats:")
    print(f"  Updates processed: {stats['updates_processed']}")
    print(f"  Gaps detected: {stats['gaps_detected']}")
    print(f"  Book valid: {stats['book_valid']}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(main())
