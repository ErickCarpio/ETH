"""
Microstructure Manager - INTEGRACIÓN FINAL
Coordina WebSockets, OrderBook, VPIN y Feature Engine.
Guarda una "foto" completa del mercado en QuestDB cada 100ms.
"""
import asyncio
import logging
import time
import sys
import os
import numpy as np

# Parche de rutas
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path: sys.path.append(project_root)

# Imports de TODOS tus componentes
from data.managers.websocket_manager import WebSocketManager
from data.managers.orderbook_manager import OrderBookManager
from features.microstructure.vpin_calculator import VPINCalculator
from features.microstructure.order_book_features import OrderBookFeatureEngine
from data.storage.questdb_connector import QuestDBConnector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MicroStructure")

class MicrostructureManager:
    def __init__(self, symbol: str = "ETHUSDT"):
        self.symbol = symbol.lower()
        
        # 1. Componentes de Infraestructura
        self.ws_manager = WebSocketManager()
        self.db_connector = QuestDBConnector()
        
        # 2. Componentes de Datos (Estado)
        self.book_manager = OrderBookManager(self.symbol, self.ws_manager)
        
        # 3. Componentes de Matemáticas (Lógica)
        self.vpin_calc = VPINCalculator(bucket_volume=1000.0, window_buckets=50)
        self.feature_engine = OrderBookFeatureEngine()
        
        # Estado auxiliar para VPIN
        self.last_trade_price = None
        self.price_history = []

    async def start(self):
        logger.info(f"🧠 Iniciando Cerebro de Microestructura para {self.symbol}...")
        
        # Conectar DB
        self.db_connector.connect()
        
        # Iniciar WebSocket
        asyncio.create_task(self.ws_manager.connect())
        
        # Iniciar OrderBook (ya se suscribe a depth@100ms internamente)
        await self.book_manager.start()
        
        # Suscribirse a Trades (para VPIN)
        await self.ws_manager.subscribe(f"{self.symbol}@aggTrade", self._handle_trade)
        
        # Iniciar Bucle de Grabación (Sampling Loop)
        asyncio.create_task(self._sampling_loop())

    async def _handle_trade(self, msg: dict):
        """Procesa trades reales para el VPIN"""
        try:
            price = float(msg['p'])
            qty = float(msg['q'])
            
            if self.last_trade_price is None:
                self.last_trade_price = price
                return

            price_change = price - self.last_trade_price
            self.last_trade_price = price
            
            # Sigma dinámico
            self.price_history.append(price_change)
            if len(self.price_history) > 100: self.price_history.pop(0)
            sigma = np.std(self.price_history) if len(self.price_history) > 10 else 1.0
            if sigma == 0: sigma = 0.01

            self.vpin_calc.process_trade(price, qty, price_change, sigma)
        except Exception:
            pass

    async def _sampling_loop(self):
        """
        Bucle Principal: Cada 1s toma una 'foto' de todo y guarda en DB.
        """
        logger.info("📸 Iniciando grabación de features en QuestDB...")
        while True:
            await asyncio.sleep(1) # Frecuencia de muestreo (1Hz)
            
            if not self.book_manager.is_ready:
                continue
                
            try:
                # 1. Obtener datos crudos
                snapshot = self.book_manager.get_l2_snapshot(limit=20)
                current_vpin = self.vpin_calc.get_current_vpin()
                mid_price = (snapshot['bids'][0][0] + snapshot['asks'][0][0]) / 2
                
                # 2. Calcular Features Avanzadas (OBI, Spoofing, etc)
                features = self.feature_engine.compute_all_features(snapshot)
                
                # 3. Agregar VPIN y Precio al diccionario
                features['vpin'] = current_vpin
                features['mid_price'] = mid_price
                features['spread'] = features['spread_absolute'] # Alias
                
                # 4. Guardar en QuestDB
                self.db_connector.insert('features_microstructure', self.symbol.upper(), features)
                
                # Log visual minimalista
                spoof_signal = "⚠️" if abs(features['spoofing_divergence']) > 0.5 else "  "
                print(f"\r💾 DB Saved: Price {mid_price:.2f} | VPIN {current_vpin:.4f} | OBI {features['obi_weighted_strong']:.4f} {spoof_signal}    ", end="")
                
            except Exception as e:
                logger.error(f"Error en sampling loop: {e}")

# --- EJECUCIÓN ---
if __name__ == "__main__":
    manager = MicrostructureManager("ETHUSDT")
    loop = asyncio.get_event_loop()
    loop.create_task(manager.start())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("\n🛑 Deteniendo sistema...")