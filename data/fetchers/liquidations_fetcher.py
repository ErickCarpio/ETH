"""
Liquidations Fetcher - FASE 3.3
================================

Monitor de liquidaciones en tiempo real desde Binance Futures.

WebSocket Stream:
- Endpoint: wss://fstream.binance.com/ws/!forceOrder@arr
- Recibe todas las liquidaciones de todos los pares
- Formato: {"s": "ETHUSDT", "S": "BUY", "o": "LIMIT", "q": "0.001", "p": "1920.00", "T": 1234567890}

Features calculadas:
1. Volumen de liquidaciones por lado (long/short)
2. Agregación por ventanas temporales (1m, 5m, 15m)
3. Detección de clusters (>$1M en 1 minuto)
4. Liquidation ratio (longs/shorts)
5. Promedio de precio de liquidación

Uso típico:
- Clusters grandes indican zonas de liquidez barrida
- Ratio alto de long liq → mercado bajista
- Ratio alto de short liq → mercado alcista
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from collections import deque
import websockets
import pandas as pd

logger = logging.getLogger(__name__)


class LiquidationEvent:
    """
    Representa un evento de liquidación individual.
    """

    def __init__(self, data: Dict):
        """
        Initialize liquidation event.

        Args:
            data: Raw event data from WebSocket
        """
        self.symbol = data.get('s')
        self.side = data.get('S')  # BUY (long liquidation) or SELL (short liquidation)
        self.order_type = data.get('o')
        self.quantity = float(data.get('q', 0))
        self.price = float(data.get('p', 0))
        self.timestamp = data.get('T')

        # Calcular valor en USD
        self.value_usd = self.quantity * self.price

    def is_long_liquidation(self) -> bool:
        """Long liquidations tienen side=SELL (forzados a vender)."""
        return self.side == 'SELL'

    def is_short_liquidation(self) -> bool:
        """Short liquidations tienen side=BUY (forzados a comprar)."""
        return self.side == 'BUY'

    def to_dict(self) -> Dict:
        """Convert to dict."""
        return {
            'symbol': self.symbol,
            'side': self.side,
            'quantity': self.quantity,
            'price': self.price,
            'value_usd': self.value_usd,
            'timestamp': self.timestamp,
            'is_long_liq': self.is_long_liquidation(),
            'is_short_liq': self.is_short_liquidation()
        }


class LiquidationsFetcher:
    """
    Fetcher para liquidaciones en tiempo real desde Binance Futures.

    Conecta a WebSocket stream de liquidaciones y mantiene buffer
    para agregación por ventanas temporales.
    """

    FUTURES_WS_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"

    def __init__(self,
                 symbols: Optional[List[str]] = None,
                 buffer_size: int = 1000):
        """
        Initialize Liquidations Fetcher.

        Args:
            symbols: Lista de símbolos a monitorear (None = todos)
            buffer_size: Tamaño del buffer de liquidaciones
        """
        self.symbols = [s.upper() for s in symbols] if symbols else None
        self.buffer_size = buffer_size

        # Buffer de liquidaciones (deque for performance)
        self.liquidations: deque[LiquidationEvent] = deque(maxlen=buffer_size)

        # WebSocket
        self.ws = None
        self.running = False

        # Callbacks
        self.on_liquidation_callbacks: List[Callable] = []

        # Stats
        self.total_liquidations = 0
        self.total_volume_usd = 0
        self.long_liquidations = 0
        self.short_liquidations = 0

        logger.info(f"LiquidationsFetcher initialized - symbols: {symbols or 'ALL'}")

    async def connect(self) -> None:
        """
        Conecta al WebSocket de liquidaciones.
        """
        logger.info("Connecting to Binance Futures liquidations stream...")

        self.running = True

        while self.running:
            try:
                async with websockets.connect(self.FUTURES_WS_URL) as ws:
                    self.ws = ws
                    logger.info("✓ Connected to liquidations stream")

                    # Receive messages
                    async for message in ws:
                        if not self.running:
                            break

                        await self._on_message(message)

            except websockets.exceptions.ConnectionClosed:
                if self.running:
                    logger.warning("Connection closed - reconnecting in 5s...")
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self.running:
                    await asyncio.sleep(5)

    async def disconnect(self) -> None:
        """
        Desconecta del WebSocket.
        """
        logger.info("Disconnecting from liquidations stream...")
        self.running = False

        if self.ws:
            await self.ws.close()

    async def _on_message(self, message: str) -> None:
        """
        Procesa mensaje del WebSocket.

        Args:
            message: Raw WebSocket message
        """
        try:
            data = json.loads(message)

            # El mensaje puede contener 'o' (order data)
            if 'o' not in data:
                return

            order_data = data['o']
            event = LiquidationEvent(order_data)

            # Filtrar por símbolos si especificado
            if self.symbols and event.symbol not in self.symbols:
                return

            # Añadir a buffer
            self.liquidations.append(event)

            # Update stats
            self.total_liquidations += 1
            self.total_volume_usd += event.value_usd

            if event.is_long_liquidation():
                self.long_liquidations += 1
            else:
                self.short_liquidations += 1

            # Trigger callbacks
            for callback in self.on_liquidation_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

            logger.debug(f"Liquidation: {event.symbol} {event.side} ${event.value_usd:,.0f}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def register_callback(self, callback: Callable) -> None:
        """
        Registra callback para liquidaciones.

        Args:
            callback: Función a llamar en cada liquidación
        """
        self.on_liquidation_callbacks.append(callback)

    def get_liquidations(self,
                        symbol: Optional[str] = None,
                        window: Optional[timedelta] = None) -> List[LiquidationEvent]:
        """
        Obtiene liquidaciones del buffer.

        Args:
            symbol: Filtrar por símbolo (None = todos)
            window: Ventana temporal (None = todas)

        Returns:
            Lista de liquidation events
        """
        result = list(self.liquidations)

        # Filter by symbol
        if symbol:
            symbol = symbol.upper()
            result = [liq for liq in result if liq.symbol == symbol]

        # Filter by time window
        if window:
            cutoff_time = datetime.now().timestamp() * 1000 - window.total_seconds() * 1000
            result = [liq for liq in result if liq.timestamp >= cutoff_time]

        return result

    def aggregate_liquidations(self,
                              symbol: Optional[str] = None,
                              window: timedelta = timedelta(minutes=1)) -> Dict:
        """
        Agrega liquidaciones por ventana temporal.

        Args:
            symbol: Símbolo a agregar (None = todos)
            window: Ventana temporal

        Returns:
            Dict con métricas agregadas
        """
        liquidations = self.get_liquidations(symbol, window)

        if not liquidations:
            return {
                'symbol': symbol,
                'window_seconds': window.total_seconds(),
                'count': 0,
                'total_volume_usd': 0,
                'long_liquidations': 0,
                'short_liquidations': 0,
                'long_volume_usd': 0,
                'short_volume_usd': 0,
                'liquidation_ratio': 0,
                'avg_price': 0
            }

        # Aggregate
        long_liqs = [liq for liq in liquidations if liq.is_long_liquidation()]
        short_liqs = [liq for liq in liquidations if liq.is_short_liquidation()]

        long_volume = sum(liq.value_usd for liq in long_liqs)
        short_volume = sum(liq.value_usd for liq in short_liqs)
        total_volume = long_volume + short_volume

        # Liquidation ratio (long/short)
        liq_ratio = long_volume / short_volume if short_volume > 0 else float('inf')

        # Average liquidation price
        avg_price = sum(liq.price for liq in liquidations) / len(liquidations)

        return {
            'symbol': symbol,
            'window_seconds': window.total_seconds(),
            'count': len(liquidations),
            'total_volume_usd': total_volume,
            'long_liquidations': len(long_liqs),
            'short_liquidations': len(short_liqs),
            'long_volume_usd': long_volume,
            'short_volume_usd': short_volume,
            'liquidation_ratio': liq_ratio,
            'avg_price': avg_price
        }

    def detect_cluster(self,
                      symbol: Optional[str] = None,
                      threshold_usd: float = 1_000_000,
                      window: timedelta = timedelta(minutes=1)) -> Optional[Dict]:
        """
        Detecta clusters de liquidaciones (>$1M en ventana).

        Args:
            symbol: Símbolo (None = cualquiera)
            threshold_usd: Umbral en USD
            window: Ventana temporal

        Returns:
            Dict con info del cluster o None
        """
        agg = self.aggregate_liquidations(symbol, window)

        if agg['total_volume_usd'] >= threshold_usd:
            logger.warning(f"Liquidation cluster detected: {agg['symbol']} ${agg['total_volume_usd']:,.0f}")
            return agg

        return None

    def calculate_liquidation_ratio(self,
                                   symbol: str,
                                   window: timedelta = timedelta(minutes=5)) -> float:
        """
        Calcula ratio de liquidaciones long/short.

        Args:
            symbol: Símbolo
            window: Ventana temporal

        Returns:
            Ratio (>1 = más longs liquidados, <1 = más shorts liquidados)
        """
        agg = self.aggregate_liquidations(symbol, window)
        return agg['liquidation_ratio']

    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas globales.

        Returns:
            Dict con stats
        """
        liq_ratio = (self.long_liquidations / self.short_liquidations
                    if self.short_liquidations > 0 else float('inf'))

        return {
            'total_liquidations': self.total_liquidations,
            'total_volume_usd': self.total_volume_usd,
            'long_liquidations': self.long_liquidations,
            'short_liquidations': self.short_liquidations,
            'liquidation_ratio': liq_ratio,
            'buffer_size': len(self.liquidations),
            'running': self.running
        }

    def to_dataframe(self,
                    symbol: Optional[str] = None,
                    window: Optional[timedelta] = None) -> pd.DataFrame:
        """
        Convierte liquidaciones a DataFrame.

        Args:
            symbol: Filtrar por símbolo
            window: Ventana temporal

        Returns:
            DataFrame con liquidaciones
        """
        liquidations = self.get_liquidations(symbol, window)

        if not liquidations:
            return pd.DataFrame()

        data = [liq.to_dict() for liq in liquidations]
        df = pd.DataFrame(data)

        # Convert timestamp to datetime
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')

        return df


async def main():
    """
    Ejemplo de uso del Liquidations Fetcher.
    """
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Crear fetcher (monitorear solo ETH y BTC)
    fetcher = LiquidationsFetcher(symbols=['ETHUSDT', 'BTCUSDT'])

    # Registrar callback
    def on_liquidation(event: LiquidationEvent):
        if event.value_usd > 50000:  # Solo mostrar liquidaciones >$50k
            side_name = "LONG" if event.is_long_liquidation() else "SHORT"
            print(f"🔥 {event.symbol} {side_name} liquidation: ${event.value_usd:,.0f} @ ${event.price:,.2f}")

    fetcher.register_callback(on_liquidation)

    # Crear tarea para monitorear clusters
    async def monitor_clusters():
        while True:
            await asyncio.sleep(60)  # Check cada minuto

            # Check clusters para ETH
            cluster = fetcher.detect_cluster('ETHUSDT', threshold_usd=1_000_000)
            if cluster:
                print(f"\n⚠️  CLUSTER DETECTED:")
                print(f"   Symbol: {cluster['symbol']}")
                print(f"   Volume: ${cluster['total_volume_usd']:,.0f}")
                print(f"   Long/Short Ratio: {cluster['liquidation_ratio']:.2f}")
                print(f"   Avg Price: ${cluster['avg_price']:,.2f}\n")

            # Stats
            stats = fetcher.get_stats()
            print(f"\n📊 Liquidations Stats (last minute):")
            print(f"   Total: {stats['total_liquidations']}")
            print(f"   Volume: ${stats['total_volume_usd']:,.0f}")
            print(f"   Ratio (L/S): {stats['liquidation_ratio']:.2f}\n")

    # Iniciar fetcher y monitor
    try:
        await asyncio.gather(
            fetcher.connect(),
            monitor_clusters()
        )
    except KeyboardInterrupt:
        print("\nStopping...")
        await fetcher.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
