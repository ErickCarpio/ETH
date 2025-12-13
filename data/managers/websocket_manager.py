# data/managers/websocket_manager.py
import asyncio
import websockets
import json
import logging
from typing import Callable, List, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebSocketManager")

class WebSocketManager:
    def __init__(self, base_url: str = "wss://fstream.binance.com/ws"):
        self.base_url = base_url
        self.ws = None
        self.callbacks = {}
        self.is_running = False
        self.active_streams = []

    async def connect(self):
        self.is_running = True
        while self.is_running:
            try:
                url = self.base_url
                if self.active_streams:
                    url = f"{self.base_url}/stream?streams={'/'.join(self.active_streams)}"
                
                logger.info(f"🔌 Conectando a {url}...")
                async with websockets.connect(url) as ws:
                    self.ws = ws
                    logger.info("✅ Conexión establecida")
                    while self.is_running:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if 'stream' in data:
                            await self._distribute(data['stream'], data['data'])
            except Exception as e:
                logger.warning(f"⚠️ Re-conectando... ({e})")
                await asyncio.sleep(2)

    async def subscribe(self, stream, callback):
        if stream not in self.callbacks: self.callbacks[stream] = []
        self.callbacks[stream].append(callback)
        if stream not in self.active_streams:
            self.active_streams.append(stream)
            if self.ws: await self.ws.close() # Forzar reconexión para añadir stream

    async def _distribute(self, stream, data):
        if stream in self.callbacks:
            for cb in self.callbacks[stream]:
                if asyncio.iscoroutinefunction(cb): await cb(data)
                else: cb(data)

    async def stop(self):
        self.is_running = False
        if self.ws: await self.ws.close()