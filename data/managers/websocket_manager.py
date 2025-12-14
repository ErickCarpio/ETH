"""
WebSocket Manager para conexiones persistentes con Binance
Fase 1.1: Infraestructura de Datos en Tiempo Real

Características:
- Auto-reconexión con exponential backoff
- Buffer de eventos durante reconexión
- Heartbeat/Pong automático
- Manejo de múltiples streams simultáneos
- Callbacks para procesamiento de datos
"""

import asyncio
import websockets
import json
import logging
import time
from typing import Dict, Callable, Optional, List
from collections import deque
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Gestor de conexiones WebSocket persistentes para Binance

    Soporta:
    - Depth streams (@depth@100ms)
    - Trade streams (@trade)
    - Kline streams (@kline_1m, @kline_5m, etc.)
    - Aggr Trade streams (@aggTrade)
    """

    def __init__(self, base_url: str = "wss://stream.binance.com:9443/ws"):
        self.base_url = base_url
        self.connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.callbacks: Dict[str, Callable] = {}
        self.is_running: Dict[str, bool] = {}
        self.reconnect_delay: Dict[str, float] = {}
        self.max_reconnect_delay = 60  # 60 segundos máximo
        self.initial_reconnect_delay = 1  # 1 segundo inicial

        # Buffer para eventos durante reconexión (máximo 1000 eventos por stream)
        self.event_buffers: Dict[str, deque] = {}
        self.max_buffer_size = 1000

        # Health monitoring
        self.last_message_time: Dict[str, float] = {}
        self.message_counts: Dict[str, int] = {}
        self.error_counts: Dict[str, int] = {}

        # Control de tareas
        self.tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, stream_name: str, symbol: str, callback: Callable):
        """
        Conecta a un stream de Binance

        Args:
            stream_name: Tipo de stream (depth, trade, kline_1m, etc.)
            symbol: Par de trading (ethusdt, btcusdt, etc.)
            callback: Función async para procesar mensajes

        Ejemplo:
            await manager.connect('depth@100ms', 'ethusdt', process_depth)
        """
        stream_id = f"{symbol}@{stream_name}"
        full_url = f"{self.base_url}/{stream_id}"

        self.callbacks[stream_id] = callback
        self.is_running[stream_id] = True
        self.reconnect_delay[stream_id] = self.initial_reconnect_delay
        self.event_buffers[stream_id] = deque(maxlen=self.max_buffer_size)
        self.message_counts[stream_id] = 0
        self.error_counts[stream_id] = 0

        # Lanzar tarea de conexión
        task = asyncio.create_task(self._maintain_connection(stream_id, full_url))
        self.tasks[stream_id] = task

        logger.info(f"✅ Stream iniciado: {stream_id}")
        return stream_id

    async def _maintain_connection(self, stream_id: str, url: str):
        """
        Mantiene la conexión activa con reconexión automática
        """
        while self.is_running.get(stream_id, False):
            try:
                logger.info(f"🔌 Conectando a {stream_id}...")

                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    self.connections[stream_id] = ws
                    self.reconnect_delay[stream_id] = self.initial_reconnect_delay

                    logger.info(f"✅ Conectado a {stream_id}")

                    # Procesar mensajes
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            self.last_message_time[stream_id] = time.time()
                            self.message_counts[stream_id] += 1

                            # Ejecutar callback
                            callback = self.callbacks.get(stream_id)
                            if callback:
                                await callback(data)
                            else:
                                # Si no hay callback, bufferear el evento
                                self.event_buffers[stream_id].append(data)

                        except json.JSONDecodeError as e:
                            logger.error(f"❌ Error decodificando JSON en {stream_id}: {e}")
                            self.error_counts[stream_id] += 1
                        except Exception as e:
                            logger.error(f"❌ Error procesando mensaje en {stream_id}: {e}")
                            self.error_counts[stream_id] += 1

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️  Conexión cerrada para {stream_id}: {e}")
                await self._handle_reconnect(stream_id)

            except Exception as e:
                logger.error(f"❌ Error en conexión {stream_id}: {e}")
                self.error_counts[stream_id] += 1
                await self._handle_reconnect(stream_id)

        logger.info(f"🛑 Stream detenido: {stream_id}")

    async def _handle_reconnect(self, stream_id: str):
        """
        Maneja reconexión con exponential backoff
        """
        if not self.is_running.get(stream_id, False):
            return

        delay = self.reconnect_delay[stream_id]
        logger.info(f"🔄 Reconectando {stream_id} en {delay:.1f}s...")

        await asyncio.sleep(delay)

        # Exponential backoff: duplicar delay hasta máximo
        new_delay = min(delay * 2, self.max_reconnect_delay)
        self.reconnect_delay[stream_id] = new_delay

    async def disconnect(self, stream_id: str):
        """
        Desconecta un stream específico
        """
        self.is_running[stream_id] = False

        # Cerrar WebSocket
        ws = self.connections.get(stream_id)
        if ws:
            await ws.close()
            del self.connections[stream_id]

        # Cancelar tarea
        task = self.tasks.get(stream_id)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.tasks[stream_id]

        logger.info(f"🛑 Desconectado: {stream_id}")

    async def disconnect_all(self):
        """
        Desconecta todos los streams activos
        """
        stream_ids = list(self.is_running.keys())
        for stream_id in stream_ids:
            await self.disconnect(stream_id)

    def get_health_status(self, stream_id: str) -> Dict:
        """
        Retorna estado de salud de un stream
        """
        return {
            "stream_id": stream_id,
            "is_connected": stream_id in self.connections,
            "is_running": self.is_running.get(stream_id, False),
            "last_message_time": self.last_message_time.get(stream_id, 0),
            "seconds_since_last_message": time.time() - self.last_message_time.get(stream_id, time.time()),
            "total_messages": self.message_counts.get(stream_id, 0),
            "total_errors": self.error_counts.get(stream_id, 0),
            "buffer_size": len(self.event_buffers.get(stream_id, [])),
            "reconnect_delay": self.reconnect_delay.get(stream_id, 0)
        }

    def get_buffered_events(self, stream_id: str) -> List[Dict]:
        """
        Retorna eventos bufferados durante reconexión
        """
        buffer = self.event_buffers.get(stream_id, deque())
        events = list(buffer)
        buffer.clear()
        return events


class DepthStreamManager(WebSocketManager):
    """
    Manager especializado para Order Book Depth streams

    Uso:
        manager = DepthStreamManager()
        await manager.connect_depth('ethusdt', update_speed='100ms', callback=process_depth)
    """

    async def connect_depth(
        self,
        symbol: str,
        callback: Callable,
        update_speed: str = "100ms",  # 100ms o 1000ms
        levels: Optional[int] = None   # None (todos), 5, 10, 20
    ):
        """
        Conecta al depth stream para Order Book en tiempo real

        Args:
            symbol: Par de trading (ethusdt, btcusdt, etc.)
            callback: Función async(data) para procesar actualizaciones
            update_speed: '100ms' o '1000ms'
            levels: None (full book), 5, 10, 20 (partial depth)
        """
        if levels:
            stream_name = f"depth{levels}@{update_speed}"
        else:
            stream_name = f"depth@{update_speed}"

        return await self.connect(stream_name, symbol.lower(), callback)


class TradeStreamManager(WebSocketManager):
    """
    Manager especializado para Trade streams
    """

    async def connect_trades(self, symbol: str, callback: Callable):
        """
        Conecta al trade stream para trades individuales
        """
        return await self.connect('trade', symbol.lower(), callback)

    async def connect_agg_trades(self, symbol: str, callback: Callable):
        """
        Conecta al aggTrade stream para trades agregados
        """
        return await self.connect('aggTrade', symbol.lower(), callback)


# Ejemplo de uso
if __name__ == "__main__":
    async def process_depth(data):
        """Callback de ejemplo para depth updates"""
        print(f"📊 Depth Update - Bids: {len(data.get('b', []))}, Asks: {len(data.get('a', []))}")

    async def process_trade(data):
        """Callback de ejemplo para trades"""
        print(f"💹 Trade - Price: {data.get('p')}, Qty: {data.get('q')}")

    async def main():
        # Crear managers
        depth_mgr = DepthStreamManager()
        trade_mgr = TradeStreamManager()

        # Conectar streams
        depth_stream = await depth_mgr.connect_depth('ethusdt', process_depth, update_speed='100ms')
        trade_stream = await trade_mgr.connect_trades('ethusdt', process_trade)

        # Monitorear por 30 segundos
        await asyncio.sleep(30)

        # Ver health status
        print("\n📊 Health Status:")
        print(depth_mgr.get_health_status(depth_stream))
        print(trade_mgr.get_health_status(trade_stream))

        # Desconectar
        await depth_mgr.disconnect_all()
        await trade_mgr.disconnect_all()

    asyncio.run(main())
