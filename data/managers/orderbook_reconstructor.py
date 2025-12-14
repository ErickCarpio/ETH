"""
Order Book L2 Reconstructor
Fase 1.2: Reconstrucción de Order Book desde WebSocket

Características:
- Reconstruye order book completo desde depth snapshots
- Mantiene estado sincronizado con depth updates (@100ms)
- Calcula microstructure features en tiempo real
- Almacena snapshots históricos
- Detecta anomalías y desincronización

Protocolo de sincronización Binance:
1. Conectar a wss://stream.binance.com:9443/ws/ethusdt@depth@100ms
2. Buffer events hasta recibir lastUpdateId (U)
3. Fetch snapshot vía GET /api/v3/depth?symbol=ETHUSDT&limit=1000
4. Descartar eventos donde u <= lastUpdateId del snapshot
5. El primer evento procesado debe tener U <= lastUpdateId+1 Y u >= lastUpdateId+1
6. Aplicar deltas: u = último u procesado + 1
"""

import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Tuple
from collections import OrderedDict
from datetime import datetime
import time
from decimal import Decimal

logger = logging.getLogger(__name__)


class OrderBookL2:
    """
    Representa un order book L2 (Level 2 - price aggregated)

    Estructura:
    - bids: OrderedDict{price: quantity} (ordenado desc)
    - asks: OrderedDict{price: quantity} (ordenado asc)
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids: OrderedDict = OrderedDict()  # price -> qty (desc order)
        self.asks: OrderedDict = OrderedDict()  # price -> qty (asc order)
        self.last_update_id: int = 0
        self.last_update_time: float = 0
        self.snapshot_time: float = 0
        self.is_synchronized = False

        # Métricas
        self.total_updates = 0
        self.total_snapshots = 0
        self.desync_count = 0

    def apply_snapshot(self, bids: List[List[str]], asks: List[List[str]], last_update_id: int):
        """
        Aplica un snapshot completo del order book

        Args:
            bids: [[price, qty], ...] ordenado por precio descendente
            asks: [[price, qty], ...] ordenado por precio ascendente
            last_update_id: lastUpdateId del snapshot
        """
        self.bids.clear()
        self.asks.clear()

        # Cargar bids (ya vienen ordenados desc de Binance)
        for price_str, qty_str in bids:
            price = float(price_str)
            qty = float(qty_str)
            if qty > 0:
                self.bids[price] = qty

        # Cargar asks (ya vienen ordenados asc de Binance)
        for price_str, qty_str in asks:
            price = float(price_str)
            qty = float(qty_str)
            if qty > 0:
                self.asks[price] = qty

        self.last_update_id = last_update_id
        self.snapshot_time = time.time()
        self.total_snapshots += 1
        self.is_synchronized = True

        logger.info(f"📸 Snapshot aplicado - {self.symbol} - Bids: {len(self.bids)}, Asks: {len(self.asks)}, UpdateID: {last_update_id}")

    def apply_update(self, bids: List[List[str]], asks: List[List[str]], update_id: int, event_time: int):
        """
        Aplica un delta update al order book

        Args:
            bids: [[price, qty], ...] cambios en bids
            asks: [[price, qty], ...] cambios en asks
            update_id: Final update ID (u field)
            event_time: Event time (E field)
        """
        # Aplicar cambios a bids
        for price_str, qty_str in bids:
            price = float(price_str)
            qty = float(qty_str)

            if qty == 0:
                # Eliminar este nivel de precio
                self.bids.pop(price, None)
            else:
                # Actualizar cantidad
                self.bids[price] = qty

        # Aplicar cambios a asks
        for price_str, qty_str in asks:
            price = float(price_str)
            qty = float(qty_str)

            if qty == 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = qty

        # Re-ordenar (importante para mantener orden correcto)
        self.bids = OrderedDict(sorted(self.bids.items(), key=lambda x: x[0], reverse=True))
        self.asks = OrderedDict(sorted(self.asks.items(), key=lambda x: x[0]))

        self.last_update_id = update_id
        self.last_update_time = event_time / 1000.0  # Convertir a segundos
        self.total_updates += 1

    def get_best_bid(self) -> Optional[Tuple[float, float]]:
        """Retorna (price, qty) del mejor bid, o None"""
        if not self.bids:
            return None
        price = next(iter(self.bids))
        return (price, self.bids[price])

    def get_best_ask(self) -> Optional[Tuple[float, float]]:
        """Retorna (price, qty) del mejor ask, o None"""
        if not self.asks:
            return None
        price = next(iter(self.asks))
        return (price, self.asks[price])

    def get_spread(self) -> Optional[float]:
        """Retorna el spread (best_ask - best_bid)"""
        bid = self.get_best_bid()
        ask = self.get_best_ask()

        if bid and ask:
            return ask[0] - bid[0]
        return None

    def get_mid_price(self) -> Optional[float]:
        """Retorna el mid price (promedio entre best bid y best ask)"""
        bid = self.get_best_bid()
        ask = self.get_best_ask()

        if bid and ask:
            return (bid[0] + ask[0]) / 2.0
        return None

    def get_micro_price(self) -> Optional[float]:
        """
        Calcula micro-price (precio ponderado por volumen en L1)

        micro_price = (bid_price * ask_qty + ask_price * bid_qty) / (bid_qty + ask_qty)

        Más preciso que mid-price para detectar dirección de presión
        """
        bid = self.get_best_bid()
        ask = self.get_best_ask()

        if bid and ask:
            bid_price, bid_qty = bid
            ask_price, ask_qty = ask

            total_qty = bid_qty + ask_qty
            if total_qty > 0:
                return (bid_price * ask_qty + ask_price * bid_qty) / total_qty

        return None

    def get_depth_imbalance(self, levels: int = 5) -> Optional[float]:
        """
        Calcula Order Book Imbalance (OBI) en los primeros N niveles

        OBI = (bid_volume - ask_volume) / (bid_volume + ask_volume)

        Valores:
        - OBI > 0: Presión compradora (más volumen en bids)
        - OBI < 0: Presión vendedora (más volumen en asks)
        - OBI ≈ 0: Equilibrio
        """
        bid_volume = sum(qty for _, qty in list(self.bids.items())[:levels])
        ask_volume = sum(qty for _, qty in list(self.asks.items())[:levels])

        total_volume = bid_volume + ask_volume
        if total_volume > 0:
            return (bid_volume - ask_volume) / total_volume

        return None

    def get_weighted_mid_price(self, levels: int = 5) -> Optional[float]:
        """
        Calcula mid-price ponderado por volumen en los primeros N niveles
        """
        bid_levels = list(self.bids.items())[:levels]
        ask_levels = list(self.asks.items())[:levels]

        bid_weighted_sum = sum(price * qty for price, qty in bid_levels)
        ask_weighted_sum = sum(price * qty for price, qty in ask_levels)

        bid_total_qty = sum(qty for _, qty in bid_levels)
        ask_total_qty = sum(qty for _, qty in ask_levels)

        total_qty = bid_total_qty + ask_total_qty

        if total_qty > 0:
            return (bid_weighted_sum + ask_weighted_sum) / total_qty

        return None

    def get_level_stats(self, levels: int = 10) -> Dict:
        """
        Retorna estadísticas de los primeros N niveles
        """
        bid_levels = list(self.bids.items())[:levels]
        ask_levels = list(self.asks.items())[:levels]

        return {
            "bid_volume": sum(qty for _, qty in bid_levels),
            "ask_volume": sum(qty for _, qty in ask_levels),
            "bid_levels": len(bid_levels),
            "ask_levels": len(ask_levels),
            "bid_value": sum(price * qty for price, qty in bid_levels),
            "ask_value": sum(price * qty for price, qty in ask_levels),
        }

    def to_dict(self, levels: int = 20) -> Dict:
        """
        Serializa el order book a dict (útil para storage)
        """
        return {
            "symbol": self.symbol,
            "timestamp": self.last_update_time,
            "last_update_id": self.last_update_id,
            "bids": [[p, q] for p, q in list(self.bids.items())[:levels]],
            "asks": [[p, q] for p, q in list(self.asks.items())[:levels]],
            "best_bid": self.get_best_bid(),
            "best_ask": self.get_best_ask(),
            "spread": self.get_spread(),
            "mid_price": self.get_mid_price(),
            "micro_price": self.get_micro_price(),
            "obi_5": self.get_depth_imbalance(5),
            "obi_10": self.get_depth_imbalance(10),
        }


class OrderBookReconstructor:
    """
    Reconstruye y mantiene order books L2 sincronizados con Binance WebSocket

    Maneja el protocolo de sincronización completo:
    1. Buffer de eventos
    2. Fetch de snapshot
    3. Validación de secuencia
    4. Aplicación de deltas
    """

    def __init__(self, symbol: str, rest_api_url: str = "https://api.binance.com"):
        self.symbol = symbol.upper()
        self.rest_api_url = rest_api_url
        self.orderbook = OrderBookL2(symbol)

        # Buffer para eventos recibidos antes del snapshot
        self.event_buffer: List[Dict] = []
        self.snapshot_fetched = False

        # Control de sincronización
        self.sync_lock = asyncio.Lock()
        self.last_sync_check = 0
        self.sync_check_interval = 30  # Verificar sincronización cada 30s

    async def initialize(self):
        """
        Inicializa el order book con un snapshot
        """
        await self._fetch_snapshot()

    async def _fetch_snapshot(self):
        """
        Obtiene snapshot del order book vía REST API
        """
        url = f"{self.rest_api_url}/api/v3/depth"
        params = {"symbol": self.symbol, "limit": 1000}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    bids = data["bids"]
                    asks = data["asks"]
                    last_update_id = data["lastUpdateId"]

                    self.orderbook.apply_snapshot(bids, asks, last_update_id)
                    self.snapshot_fetched = True

                    logger.info(f"✅ Snapshot obtenido - {self.symbol} - UpdateID: {last_update_id}")

                    # Procesar eventos bufferados
                    await self._process_buffered_events()
                else:
                    logger.error(f"❌ Error fetching snapshot: {response.status}")

    async def _process_buffered_events(self):
        """
        Procesa eventos que fueron bufferados antes del snapshot
        """
        if not self.event_buffer:
            return

        logger.info(f"📦 Procesando {len(self.event_buffer)} eventos bufferados")

        processed = 0
        for event in self.event_buffer:
            if self._should_process_event(event):
                await self.process_depth_update(event)
                processed += 1

        self.event_buffer.clear()
        logger.info(f"✅ Procesados {processed} eventos del buffer")

    def _should_process_event(self, event: Dict) -> bool:
        """
        Verifica si un evento debe ser procesado según el protocolo de Binance
        """
        U = event.get("U")  # First update ID
        u = event.get("u")  # Final update ID

        last_id = self.orderbook.last_update_id

        # Descartar eventos viejos
        if u <= last_id:
            return False

        # Para el primer evento después del snapshot:
        # U <= lastUpdateId+1 AND u >= lastUpdateId+1
        if not self.orderbook.is_synchronized:
            if U <= last_id + 1 and u >= last_id + 1:
                return True
            else:
                return False

        # Para eventos posteriores: u debe ser consecutivo
        if U != last_id + 1:
            logger.warning(f"⚠️  Posible desincronización - Expected U={last_id+1}, got U={U}")
            self.orderbook.desync_count += 1

            # Si hay muchas desincronizaciones, re-fetch snapshot
            if self.orderbook.desync_count >= 3:
                logger.error(f"❌ Desincronización detectada - Re-fetching snapshot")
                asyncio.create_task(self._fetch_snapshot())
                return False

        return True

    async def process_depth_update(self, event: Dict):
        """
        Procesa un depth update del WebSocket

        Args:
            event: Depth update event de Binance
        """
        async with self.sync_lock:
            # Si no tenemos snapshot, buffear el evento
            if not self.snapshot_fetched:
                self.event_buffer.append(event)
                return

            # Validar si debemos procesar este evento
            if not self._should_process_event(event):
                return

            # Aplicar update
            bids = event.get("b", [])
            asks = event.get("a", [])
            u = event.get("u")
            E = event.get("E")

            self.orderbook.apply_update(bids, asks, u, E)

            # Reset contador de desync
            self.orderbook.desync_count = 0

    async def check_synchronization(self):
        """
        Verifica periódicamente la sincronización del order book
        """
        current_time = time.time()

        if current_time - self.last_sync_check < self.sync_check_interval:
            return

        self.last_sync_check = current_time

        # Verificar que estamos recibiendo updates recientes
        time_since_update = current_time - self.orderbook.last_update_time

        if time_since_update > 5:  # Más de 5 segundos sin updates
            logger.warning(f"⚠️  {self.symbol}: Sin updates por {time_since_update:.1f}s - posible desconexión")

        # Verificar que el spread es razonable (< 0.5%)
        spread = self.orderbook.get_spread()
        mid_price = self.orderbook.get_mid_price()

        if spread and mid_price:
            spread_pct = (spread / mid_price) * 100
            if spread_pct > 0.5:
                logger.warning(f"⚠️  {self.symbol}: Spread anormalmente alto: {spread_pct:.4f}%")

    def get_orderbook(self) -> OrderBookL2:
        """
        Retorna el order book actual
        """
        return self.orderbook

    def get_stats(self) -> Dict:
        """
        Retorna estadísticas del reconstructor
        """
        return {
            "symbol": self.symbol,
            "is_synchronized": self.orderbook.is_synchronized,
            "total_updates": self.orderbook.total_updates,
            "total_snapshots": self.orderbook.total_snapshots,
            "desync_count": self.orderbook.desync_count,
            "buffer_size": len(self.event_buffer),
            "last_update_id": self.orderbook.last_update_id,
            "time_since_update": time.time() - self.orderbook.last_update_time if self.orderbook.last_update_time > 0 else None,
        }


# Ejemplo de uso
if __name__ == "__main__":
    from data.managers.websocket_manager import DepthStreamManager

    async def main():
        symbol = "ethusdt"

        # Crear reconstructor
        reconstructor = OrderBookReconstructor(symbol)

        # Inicializar con snapshot
        await reconstructor.initialize()

        # Callback para WebSocket updates
        async def on_depth_update(data):
            await reconstructor.process_depth_update(data)

            # Cada 100 updates, mostrar estado
            if reconstructor.orderbook.total_updates % 100 == 0:
                ob = reconstructor.get_orderbook()
                print(f"\n📊 Order Book Update #{ob.total_updates}")
                print(f"   Best Bid: {ob.get_best_bid()}")
                print(f"   Best Ask: {ob.get_best_ask()}")
                print(f"   Spread: ${ob.get_spread():.2f}")
                print(f"   Mid Price: ${ob.get_mid_price():.2f}")
                print(f"   Micro Price: ${ob.get_micro_price():.2f}")
                print(f"   OBI (5): {ob.get_depth_imbalance(5):.4f}")

        # Conectar WebSocket
        ws_manager = DepthStreamManager()
        await ws_manager.connect_depth(symbol, on_depth_update, update_speed="100ms")

        # Monitorear por 60 segundos
        for _ in range(60):
            await asyncio.sleep(1)
            await reconstructor.check_synchronization()

        # Mostrar stats finales
        print(f"\n📈 Stats Finales:")
        print(reconstructor.get_stats())

        await ws_manager.disconnect_all()

    asyncio.run(main())
