"""
Microstructure Manager - INTEGRACIÓN FINAL (Corregido)
Coordina WebSockets, OrderBook, VPIN y Feature Engine.
Guarda una "foto" (sample) del mercado en QuestDB cada 1 segundo.
"""
import asyncio
import logging
import time
import sys
import os
import numpy as np

# --- 1. Parche de Rutas (Para que funcione siempre) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

# --- 2. Importaciones de tus componentes ---
from data.managers.websocket_manager import WebSocketManager
from data.managers.orderbook_manager import OrderBookManager
from features.microstructure.vpin_calculator import VPINCalculator
from features.microstructure.order_book_features import OrderBookFeatureEngine
from features.microstructure.micro_price_calculator import MicroPriceCalculator # <--- NUEVO
from data.storage.questdb_connector import QuestDBConnector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MicroStructure")

class MicrostructureManager:
    def __init__(self, symbol: str = "ETHUSDT"):
        self.symbol = symbol.lower()
        
        # A. Infraestructura (Conexiones)
        self.ws_manager = WebSocketManager()
        self.db_connector = QuestDBConnector()
        
        # B. Datos (Estado del Libro)
        self.book_manager = OrderBookManager(self.symbol, self.ws_manager)
        
        # C. Cerebros Matemáticos
        self.vpin_calc = VPINCalculator(bucket_volume=1000.0, window_buckets=50)
        self.feature_engine = OrderBookFeatureEngine()
        self.micro_price_calc = MicroPriceCalculator() # <--- NUEVO: Micro-Precio
        
        # Variables auxiliares para VPIN
        self.last_trade_price = None
        self.price_history = []

    async def start(self):
        """Arranca todo el sistema"""
        logger.info(f"🧠 Iniciando Cerebro de Microestructura para {self.symbol}...")
        
        # 1. Conectar Base de Datos
        self.db_connector.connect()
        
        # 2. Iniciar WebSocket
        asyncio.create_task(self.ws_manager.connect())
        
        # 3. Iniciar OrderBook (ya se suscribe a depth@100ms internamente)
        await self.book_manager.start()
        
        # 4. Suscribirse a Trades Reales (necesario para VPIN)
        await self.ws_manager.subscribe(f"{self.symbol}@aggTrade", self._handle_trade)
        
        # 5. Iniciar el Bucle de Grabación (Sampling)
        # Esto corre en paralelo y guarda datos cada segundo
        asyncio.create_task(self._sampling_loop())

    async def _handle_trade(self, msg: dict):
        """
        Recibe cada trade de Binance y alimenta la calculadora VPIN.
        NO guarda en DB todavía, solo actualiza las matemáticas en memoria.
        """
        try:
            price = float(msg['p'])
            qty = float(msg['q'])
            
            if self.last_trade_price is None:
                self.last_trade_price = price
                return

            price_change = price - self.last_trade_price
            self.last_trade_price = price
            
            # Calcular volatilidad instantánea (Sigma)
            self.price_history.append(price_change)
            if len(self.price_history) > 100: self.price_history.pop(0)
            
            sigma = np.std(self.price_history) if len(self.price_history) > 10 else 1.0
            if sigma == 0: sigma = 0.01

            # Actualizar VPIN en memoria
            self.vpin_calc.process_trade(price, qty, price_change, sigma)
        except Exception:
            pass

    async def _sampling_loop(self):
        """
        ESTO ES EL SAMPLING:
        Un bucle infinito que cada 1 segundo:
        1. Toma todos los datos actuales.
        2. Calcula features finales.
        3. Guarda en QuestDB.
        """
        logger.info("📸 Iniciando grabación (Sampling) en QuestDB...")
        
        while True:
            await asyncio.sleep(1) # Esperar 1 segundo
            
            # Si el libro no está listo, esperar
            if not self.book_manager.is_ready:
                continue
                
            try:
                # 1. Obtener datos crudos del libro (AQUÍ ESTABA EL ERROR ANTES)
                # Usamos limit=20 para tener profundidad suficiente
                snapshot = self.book_manager.get_l2_snapshot(limit=20) # <--- CORREGIDO
                
                if not snapshot['bids'] or not snapshot['asks']:
                    continue

                # 2. Calcular Features L2 (OBI, Spread, Spoofing)
                features = self.feature_engine.compute_all_features(snapshot)
                
                # 3. Calcular Micro-Precio (NUEVO)
                mp = self.micro_price_calc.calculate_micro_price(snapshot['bids'], snapshot['asks'])
                mid_price = (snapshot['bids'][0][0] + snapshot['asks'][0][0]) / 2
                
                # 4. Obtener VPIN actual
                current_vpin = self.vpin_calc.get_current_vpin()
                
                # 5. Empaquetar todo en un solo diccionario
                features['vpin'] = current_vpin
                features['mid_price'] = mid_price
                features['micro_price'] = mp
                features['micro_dev'] = mp - mid_price # Desviación Micro vs Spot
                
                # 6. ENVIAR A QUESTDB
                self.db_connector.insert('features_microstructure', self.symbol.upper(), features)
                
                # Feedback Visual para ti
                spoof_signal = "⚠️" if abs(features.get('spoofing_divergence',0)) > 0.5 else "  "
                print(f"\r💾 Saved: Price {mid_price:.2f} | Micro {mp:.2f} | VPIN {current_vpin:.4f} {spoof_signal}    ", end="")
                
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