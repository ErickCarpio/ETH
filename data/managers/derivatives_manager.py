"""
Derivatives Data Manager - Phase 2
Real-time derivatives data streaming: Funding Rates, Liquidations, Open Interest

Features calculadas:
1. Funding Rate (real-time)
2. Funding Rate Delta (cambios)
3. Liquidations (volumen, dirección)
4. Open Interest (OI)
5. Open Interest Delta (cambios intra-minuto)
6. OI/Volume ratio
7. Liquidation clusters
"""

import asyncio
import logging
import websockets
import json
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from collections import deque
import statistics

logger = logging.getLogger(__name__)


class DerivativesDataManager:
    """
    Manager para datos de derivados en tiempo real

    Streams:
    1. Funding Rate (Binance Futures)
    2. Mark Price (para calcular deltas)
    3. Liquidation Orders (via forceOrder stream)
    4. Open Interest (polling cada 30s)
    """

    def __init__(self, symbol: str = "ETHUSDT"):
        self.symbol = symbol.upper().replace("/", "")
        self.base_url_futures = "wss://fstream.binance.com/ws"

        # State
        self.funding_rate_history: deque = deque(maxlen=100)  # Últimos 100 funding rates
        self.liquidations: deque = deque(maxlen=1000)  # Últimas 1000 liquidaciones
        self.oi_history: deque = deque(maxlen=100)  # Open Interest history

        # Current values
        self.current_funding_rate: float = 0.0
        self.current_mark_price: float = 0.0
        self.current_oi: float = 0.0
        self.last_oi_update: Optional[datetime] = None

        # WebSocket connections
        self.ws_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.running = False

        # Callbacks
        self.on_funding_update: Optional[Callable] = None
        self.on_liquidation: Optional[Callable] = None
        self.on_oi_update: Optional[Callable] = None

    async def start(self):
        """Inicia todos los streams de derivados"""
        self.running = True
        logger.info(f"🚀 Iniciando DerivativesDataManager para {self.symbol}")

        # Start streams in parallel
        await asyncio.gather(
            self._stream_mark_price(),
            self._stream_liquidations(),
            self._poll_open_interest(),
            return_exceptions=True
        )

    async def stop(self):
        """Detiene todos los streams"""
        self.running = False

        # Close all WebSocket connections
        for name, ws in self.ws_connections.items():
            try:
                await ws.close()
                logger.info(f"✅ Cerrado stream: {name}")
            except Exception as e:
                logger.error(f"Error cerrando {name}: {e}")

        logger.info("✅ DerivativesDataManager detenido")

    async def _stream_mark_price(self):
        """
        Stream de Mark Price

        El mark price viene con el funding rate incluido.
        Stream: <symbol>@markPrice@1s
        """
        stream = f"{self.symbol.lower()}@markPrice@1s"
        url = f"{self.base_url_futures}/{stream}"

        logger.info(f"🔌 Conectando a mark price stream: {stream}")

        while self.running:
            try:
                async with websockets.connect(url) as ws:
                    self.ws_connections['mark_price'] = ws
                    logger.info(f"✅ Conectado a mark price stream")

                    async for message in ws:
                        if not self.running:
                            break

                        try:
                            data = json.loads(message)

                            # Binance futures markPrice stream format:
                            # {
                            #   "e": "markPriceUpdate",
                            #   "E": event_time,
                            #   "s": "ETHUSDT",
                            #   "p": "3800.12345678",  # mark price
                            #   "i": "3800.11111111",  # index price
                            #   "P": "3800.13456789",  # estimated Settle Price (funding time)
                            #   "r": "0.00010000",     # funding rate
                            #   "T": 1640995200000     # next funding time
                            # }

                            if data.get('e') == 'markPriceUpdate':
                                self.current_mark_price = float(data.get('p', 0))
                                new_funding_rate = float(data.get('r', 0))

                                # Track funding rate changes
                                if new_funding_rate != self.current_funding_rate:
                                    old_rate = self.current_funding_rate
                                    self.current_funding_rate = new_funding_rate

                                    self.funding_rate_history.append({
                                        'timestamp': datetime.now(),
                                        'funding_rate': new_funding_rate,
                                        'mark_price': self.current_mark_price,
                                        'next_funding_time': datetime.fromtimestamp(data.get('T', 0) / 1000)
                                    })

                                    # Callback
                                    if self.on_funding_update:
                                        await self.on_funding_update({
                                            'funding_rate': new_funding_rate,
                                            'funding_rate_delta': new_funding_rate - old_rate,
                                            'mark_price': self.current_mark_price
                                        })

                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            logger.error(f"Error procesando mark price: {e}")

            except Exception as e:
                logger.error(f"❌ Error en mark price stream: {e}")
                if self.running:
                    logger.info("🔄 Reconectando en 5 segundos...")
                    await asyncio.sleep(5)

    async def _stream_liquidations(self):
        """
        Stream de liquidaciones

        Stream: <symbol>@forceOrder

        Nota: Este stream solo está disponible en Binance Futures
        """
        stream = f"{self.symbol.lower()}@forceOrder"
        url = f"{self.base_url_futures}/{stream}"

        logger.info(f"🔌 Conectando a liquidation stream: {stream}")

        while self.running:
            try:
                async with websockets.connect(url) as ws:
                    self.ws_connections['liquidations'] = ws
                    logger.info(f"✅ Conectado a liquidation stream")

                    async for message in ws:
                        if not self.running:
                            break

                        try:
                            data = json.loads(message)

                            # Binance forceOrder format:
                            # {
                            #   "e":"forceOrder",
                            #   "E": event_time,
                            #   "o":{
                            #     "s": "ETHUSDT",
                            #     "S": "SELL",        # Side
                            #     "o": "LIMIT",       # Order Type
                            #     "f": "IOC",         # Time in Force
                            #     "q": "0.014",       # Original Quantity
                            #     "p": "3800",        # Price
                            #     "ap": "3800.5",     # Average Price
                            #     "X": "FILLED",      # Order Status
                            #     "l": "0.014",       # Last Filled Quantity
                            #     "z": "0.014",       # Cumulative Filled Quantity
                            #     "T": 1568014460893  # Trade Time
                            #   }
                            # }

                            if data.get('e') == 'forceOrder':
                                order = data.get('o', {})

                                liquidation = {
                                    'timestamp': datetime.now(),
                                    'side': order.get('S'),  # 'BUY' = long liquidated, 'SELL' = short liquidated
                                    'quantity': float(order.get('q', 0)),
                                    'price': float(order.get('p', 0)),
                                    'avg_price': float(order.get('ap', 0)),
                                    'notional': float(order.get('q', 0)) * float(order.get('ap', 0))
                                }

                                self.liquidations.append(liquidation)

                                # Callback
                                if self.on_liquidation:
                                    await self.on_liquidation(liquidation)

                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            logger.error(f"Error procesando liquidation: {e}")

            except Exception as e:
                logger.error(f"❌ Error en liquidation stream: {e}")
                if self.running:
                    logger.info("🔄 Reconectando en 5 segundos...")
                    await asyncio.sleep(5)

    async def _poll_open_interest(self):
        """
        Polling de Open Interest

        Binance no tiene OI via WebSocket, así que hacemos polling cada 30s
        Endpoint: GET /fapi/v1/openInterest
        """
        import aiohttp

        url = f"https://fapi.binance.com/fapi/v1/openInterest"

        logger.info(f"🔄 Iniciando polling de Open Interest (cada 30s)")

        async with aiohttp.ClientSession() as session:
            while self.running:
                try:
                    async with session.get(url, params={'symbol': self.symbol}) as resp:
                        if resp.status == 200:
                            data = await resp.json()

                            # Response format:
                            # {
                            #   "openInterest": "10659.509",
                            #   "symbol": "ETHUSDT",
                            #   "time": 1640995200000
                            # }

                            new_oi = float(data.get('openInterest', 0))
                            old_oi = self.current_oi

                            self.current_oi = new_oi
                            self.last_oi_update = datetime.now()

                            self.oi_history.append({
                                'timestamp': self.last_oi_update,
                                'oi': new_oi,
                                'oi_delta': new_oi - old_oi if old_oi > 0 else 0
                            })

                            # Callback
                            if self.on_oi_update:
                                await self.on_oi_update({
                                    'oi': new_oi,
                                    'oi_delta': new_oi - old_oi if old_oi > 0 else 0,
                                    'oi_delta_pct': ((new_oi - old_oi) / old_oi * 100) if old_oi > 0 else 0
                                })
                        else:
                            logger.error(f"❌ Error polling OI: status {resp.status}")

                except Exception as e:
                    logger.error(f"❌ Error polling OI: {e}")

                # Wait 30 seconds before next poll
                await asyncio.sleep(30)

    def get_funding_rate_features(self) -> Dict:
        """
        Calcula features basadas en funding rate

        Returns:
            Dict con features de funding rate
        """
        if len(self.funding_rate_history) < 2:
            return {
                'funding_rate': self.current_funding_rate,
                'funding_rate_ma_10': 0.0,
                'funding_rate_std_10': 0.0,
                'funding_rate_delta': 0.0,
                'funding_rate_trend': 'neutral'
            }

        recent_rates = [x['funding_rate'] for x in list(self.funding_rate_history)[-10:]]

        ma_10 = statistics.mean(recent_rates) if len(recent_rates) >= 2 else self.current_funding_rate
        std_10 = statistics.stdev(recent_rates) if len(recent_rates) >= 2 else 0.0

        # Delta (last - previous)
        delta = recent_rates[-1] - recent_rates[-2] if len(recent_rates) >= 2 else 0.0

        # Trend
        if ma_10 > 0.0001:
            trend = 'bullish'
        elif ma_10 < -0.0001:
            trend = 'bearish'
        else:
            trend = 'neutral'

        return {
            'funding_rate': self.current_funding_rate,
            'funding_rate_ma_10': ma_10,
            'funding_rate_std_10': std_10,
            'funding_rate_delta': delta,
            'funding_rate_trend': trend
        }

    def get_liquidation_features(self, window_minutes: int = 5) -> Dict:
        """
        Calcula features basadas en liquidaciones

        Args:
            window_minutes: Ventana de tiempo para calcular features

        Returns:
            Dict con features de liquidaciones
        """
        if not self.liquidations:
            return {
                'liq_count_5m': 0,
                'liq_volume_5m': 0.0,
                'liq_notional_5m': 0.0,
                'liq_long_pct': 0.0,
                'liq_short_pct': 0.0,
                'liq_imbalance': 0.0
            }

        # Filter by time window
        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        recent_liqs = [liq for liq in self.liquidations if liq['timestamp'] >= cutoff]

        if not recent_liqs:
            return {
                'liq_count_5m': 0,
                'liq_volume_5m': 0.0,
                'liq_notional_5m': 0.0,
                'liq_long_pct': 0.0,
                'liq_short_pct': 0.0,
                'liq_imbalance': 0.0
            }

        # Calculate metrics
        total_count = len(recent_liqs)
        total_volume = sum(liq['quantity'] for liq in recent_liqs)
        total_notional = sum(liq['notional'] for liq in recent_liqs)

        # Long vs Short
        long_liqs = [liq for liq in recent_liqs if liq['side'] == 'SELL']  # Long liquidated = SELL
        short_liqs = [liq for liq in recent_liqs if liq['side'] == 'BUY']  # Short liquidated = BUY

        long_count = len(long_liqs)
        short_count = len(short_liqs)

        long_pct = (long_count / total_count * 100) if total_count > 0 else 0
        short_pct = (short_count / total_count * 100) if total_count > 0 else 0

        # Imbalance: positive = más longs liquidados (bearish), negative = más shorts liquidados (bullish)
        imbalance = (long_count - short_count) / total_count if total_count > 0 else 0

        return {
            'liq_count_5m': total_count,
            'liq_volume_5m': total_volume,
            'liq_notional_5m': total_notional,
            'liq_long_pct': long_pct,
            'liq_short_pct': short_pct,
            'liq_imbalance': imbalance
        }

    def get_oi_features(self) -> Dict:
        """
        Calcula features basadas en Open Interest

        Returns:
            Dict con features de OI
        """
        if len(self.oi_history) < 2:
            return {
                'oi': self.current_oi,
                'oi_delta': 0.0,
                'oi_delta_pct': 0.0,
                'oi_trend': 'neutral'
            }

        recent_oi = list(self.oi_history)[-10:]

        deltas = [x['oi_delta'] for x in recent_oi]
        avg_delta = statistics.mean(deltas) if deltas else 0.0

        # Trend
        if avg_delta > 0:
            trend = 'increasing'
        elif avg_delta < 0:
            trend = 'decreasing'
        else:
            trend = 'stable'

        last_delta = deltas[-1] if deltas else 0.0
        last_delta_pct = (last_delta / self.current_oi * 100) if self.current_oi > 0 else 0.0

        return {
            'oi': self.current_oi,
            'oi_delta': last_delta,
            'oi_delta_pct': last_delta_pct,
            'oi_trend': trend,
            'oi_avg_delta_10': avg_delta
        }

    def get_all_features(self) -> Dict:
        """
        Retorna todas las features de derivados combinadas
        """
        features = {
            'timestamp': datetime.now(),
            **self.get_funding_rate_features(),
            **self.get_liquidation_features(window_minutes=5),
            **self.get_oi_features()
        }

        return features


# Example usage
async def demo():
    """Demo del DerivativesDataManager"""

    manager = DerivativesDataManager("ETHUSDT")

    # Callbacks para monitorear
    async def on_funding(data):
        print(f"💰 Funding Rate: {data['funding_rate']:.6f} (delta: {data['funding_rate_delta']:.6f})")

    async def on_liq(data):
        side_emoji = "🔴" if data['side'] == 'SELL' else "🟢"
        print(f"{side_emoji} Liquidation: {data['side']} {data['quantity']:.4f} @ ${data['avg_price']:.2f}")

    async def on_oi(data):
        print(f"📊 OI: {data['oi']:.2f} (delta: {data['oi_delta']:+.2f}, {data['oi_delta_pct']:+.2f}%)")

    manager.on_funding_update = on_funding
    manager.on_liquidation = on_liq
    manager.on_oi_update = on_oi

    # Start
    print("🚀 Iniciando Derivatives Manager...")
    print("⏹️  Presiona Ctrl+C para detener\n")

    try:
        # Start streams
        await manager.start()
    except KeyboardInterrupt:
        print("\n\n⏹️  Deteniendo...")
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(demo())
