"""
Order Book Manager - Reconstrucción L2 Local
Mantiene una copia exacta del Order Book de Binance en memoria.
Crucial para calcular OBI, Spread y Micro-Precio.
"""

import asyncio
import logging
import time
import aiohttp
from typing import Dict, List, Optional
import numpy as np

import sys
import os

# --- PARCHE DE RUTAS ---
# Esto permite que el archivo encuentre a sus "vecinos" sin importar cómo lo ejecutes
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)
# -----------------------

try:
    from websocket_manager import WebSocketManager
except ImportError:
    # Intento alternativo por si se ejecuta como módulo
    from data.managers.websocket_manager import WebSocketManager

logger = logging.getLogger("OrderBookManager")

class OrderBookManager:
    def __init__(self, symbol: str = "ETHUSDT", ws_manager: WebSocketManager = None):
        self.symbol = symbol.lower()
        self.ws_manager = ws_manager
        
        # El Libro Local: {price (float): quantity (float)}
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        
        self.last_update_id = 0
        self.is_ready = False
        self.buffer = []  # Buffer para eventos mientras se descarga el snapshot
        
    async def start(self):
        """Inicia el proceso de sincronización"""
        logger.info(f"📘 Iniciando Order Book local para {self.symbol}...")
        
        # 1. Suscribirse al WebSocket (Diff Depth)
        # depth@100ms es la actualización más rápida gratuita
        stream_name = f"{self.symbol}@depth@100ms"
        await self.ws_manager.subscribe(stream_name, self._handle_ws_message)
        
        # 2. Esperar un poco para llenar el buffer
        await asyncio.sleep(2)
        
        # 3. Descargar Snapshot REST para tener la base
        await self._fetch_snapshot()
        
    async def _fetch_snapshot(self):
        """Descarga el estado inicial del libro vía REST API"""
        logger.info("📸 Descargando snapshot inicial...")
        url = f"https://fapi.binance.com/fapi/v1/depth?symbol={self.symbol.upper()}&limit=1000"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error("❌ Error descargando snapshot")
                    return
                
                snapshot = await response.json()
                
        # Procesar snapshot
        self.last_update_id = snapshot['lastUpdateId']
        
        # Llenar diccionarios
        self.bids = {float(p): float(q) for p, q in snapshot['bids']}
        self.asks = {float(p): float(q) for p, q in snapshot['asks']}
        
        logger.info(f"✅ Snapshot cargado. LastUpdateId: {self.last_update_id}")
        
        # 4. Procesar el buffer (Replay)
        self._process_buffer()
        self.is_ready = True

    def _handle_ws_message(self, msg: dict):
        """Maneja cada actualización del WebSocket"""
        if not self.is_ready:
            self.buffer.append(msg)
            return

        # Validar secuencia (U = FirstUpdateId, u = FinalUpdateId)
        U = msg['U']
        u = msg['u']
        pu = msg['pu'] # Previous Final Update Id
        
        # Lógica de sincronización estricta de Binance
        if u <= self.last_update_id:
            return # Evento viejo, ignorar
            
        # Aplicar cambios
        self._apply_updates(msg['b'], self.bids)
        self._apply_updates(msg['a'], self.asks)
        
        self.last_update_id = u

    def _process_buffer(self):
        """Procesa eventos acumulados durante la carga del snapshot"""
        logger.info(f"🔄 Procesando buffer ({len(self.buffer)} eventos)...")
        for msg in self.buffer:
            U = msg['U']
            u = msg['u']
            
            # Solo aplicar si el evento es posterior al snapshot
            if u > self.last_update_id:
                self._apply_updates(msg['b'], self.bids)
                self._apply_updates(msg['a'], self.asks)
                self.last_update_id = u
        
        self.buffer = [] # Limpiar

    def _apply_updates(self, updates: List[List[str]], book_side: Dict[float, float]):
        """
        Actualiza el diccionario del libro.
        Si qty == 0, se elimina el nivel de precio.
        """
        for price_str, qty_str in updates:
            price = float(price_str)
            qty = float(qty_str)
            
            if qty == 0:
                if price in book_side:
                    del book_side[price]
            else:
                book_side[price] = qty

    def get_l2_snapshot(self, limit: int = 10):
        """
        Retorna el estado actual del libro ordenado (Top N niveles).
        Útil para features de ML.
        """
        # Ordenar Bids (Descendente: Mayor precio primero)
        sorted_bids = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)[:limit]
        
        # Ordenar Asks (Ascendente: Menor precio primero)
        sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])[:limit]
        
        return {
            'timestamp': time.time(),
            'bids': sorted_bids,
            'asks': sorted_asks
        }
    
    def get_obi(self, depth: int = 5) -> float:
        """
        Calcula el Order Book Imbalance (OBI) simple.
        Rango: [-1, 1]. Positivo = Presión de Compra.
        """
        bids = self.get_l2_snapshot(depth)['bids']
        asks = self.get_l2_snapshot(depth)['asks']
        
        vol_bid = sum(q for p, q in bids)
        vol_ask = sum(q for p, q in asks)
        
        if (vol_bid + vol_ask) == 0: return 0
        
        return (vol_bid - vol_ask) / (vol_bid + vol_ask)

# --- BLOQUE DE PRUEBA ---
if __name__ == "__main__":
    async def test():
        # 1. Instanciar WS Manager
        ws = WebSocketManager()
        
        # 2. Instanciar Book Manager
        book = OrderBookManager("ETHUSDT", ws)
        
        # 3. Iniciar conexión WS en background
        asyncio.create_task(ws.connect())
        
        # 4. Iniciar Book Manager
        await book.start()
        
        # 5. Monitorizar OBI en tiempo real por 10s
        for _ in range(10):
            await asyncio.sleep(1)
            if book.is_ready:
                snapshot = book.get_l2_snapshot(1)
                best_bid = snapshot['bids'][0][0]
                best_ask = snapshot['asks'][0][0]
                obi = book.get_obi(10)
                
                print(f"⚡ Precio: {best_bid:.2f} / {best_ask:.2f} | 📊 OBI (10): {obi:.4f}")
                
        await ws.stop()

    asyncio.run(test())