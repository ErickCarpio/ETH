"""
Order Book Features - Ingeniería de Características de L2
Calcula desequilibrios (OBI) simples, ponderados y detección de Spoofing.
"""

import numpy as np
import logging
from typing import Dict, List, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("L2_Features")

class OrderBookProcessor:
    def __init__(self):
        pass

    def calculate_obi(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]], depth: int = 5) -> float:
        """
        Calcula el Order Book Imbalance (OBI) estándar.
        Fórmula: (Vol_Bid - Vol_Ask) / (Vol_Bid + Vol_Ask)
        Rango: [-1, 1]. Positivo = Presión de Compra.
        """
        # Tomar solo los primeros 'depth' niveles
        relevant_bids = bids[:depth]
        relevant_asks = asks[:depth]
        
        vol_bid = sum(q for p, q in relevant_bids)
        vol_ask = sum(q for p, q in relevant_asks)
        
        total_vol = vol_bid + vol_ask
        if total_vol == 0:
            return 0.0
            
        return (vol_bid - vol_ask) / total_vol

    def calculate_weighted_obi(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]], decay_rate: float = 0.5) -> float:
        """
        OBI Ponderado por Distancia (Weighted OBI).
        Las órdenes cercanas al precio medio valen más que las lejanas.
        Peso = exp(-decay_rate * nivel)
        """
        mid_price = (bids[0][0] + asks[0][0]) / 2
        
        w_vol_bid = 0.0
        w_vol_ask = 0.0
        
        # Calcular peso para Bids
        for i, (price, qty) in enumerate(bids):
            # Nivel 0 (tope) tiene peso 1.0, Nivel 1 tiene peso menor...
            weight = np.exp(-decay_rate * i)
            w_vol_bid += qty * weight
            
        # Calcular peso para Asks
        for i, (price, qty) in enumerate(asks):
            weight = np.exp(-decay_rate * i)
            w_vol_ask += qty * weight
            
        total_w_vol = w_vol_bid + w_vol_ask
        if total_w_vol == 0:
            return 0.0
            
        return (w_vol_bid - w_vol_ask) / total_w_vol

    def detect_spoofing_pressure(self, obi_l1: float, obi_l20: float) -> float:
        """
        Detecta divergencia entre la intención inmediata (L1) y la profunda (L20).
        Si L1 es muy positivo (compra) pero L20 es muy negativo (muro de venta oculto),
        puede ser señal de Spoofing o absorción.
        
        Retorna: Grado de divergencia [-1, 1]
        """
        # Si tienen signos opuestos, la multiplicación es negativa -> Divergencia alta
        return obi_l1 - obi_l20

    def compute_all_features(self, snapshot: dict) -> dict:
        """
        Genera el vector completo de features de microestructura para un snapshot dado.
        """
        bids = snapshot['bids']
        asks = snapshot['asks']
        
        # Validar datos mínimos
        if not bids or not asks:
            return {}

        features = {
            # 1. OBI por niveles (La "forma" del libro)
            "obi_L1": self.calculate_obi(bids, asks, depth=1),
            "obi_L5": self.calculate_obi(bids, asks, depth=5),
            "obi_L10": self.calculate_obi(bids, asks, depth=10),
            "obi_L20": self.calculate_obi(bids, asks, depth=20),
            
            # 2. OBI Inteligente (Matemático)
            "obi_weighted_strong": self.calculate_weighted_obi(bids, asks, decay_rate=0.8), # Muy enfocado en el precio
            "obi_weighted_weak": self.calculate_weighted_obi(bids, asks, decay_rate=0.1),   # Mira la profundidad
            
            # 3. Métricas de Spread
            "spread_absolute": asks[0][0] - bids[0][0],
            "spread_relative": (asks[0][0] - bids[0][0]) / asks[0][0],
        }
        
        # 4. Señal de Spoofing
        features["spoofing_divergence"] = self.detect_spoofing_pressure(features["obi_L1"], features["obi_L20"])
        
        return features

# --- PRUEBA UNITARIA ---
if __name__ == "__main__":
    engine = OrderBookProcessor()
    
    # Simular un libro donde:
    # - Tope del libro (L1): Mucha COMPRA (100 vs 10)
    # - Profundidad (L5): Muro de VENTA oculto (100 vs 5000)
    print("🧪 Simulando escenario de 'Fake Bull' (Posible Spoofing)...")
    
    mock_bids = [(3000.0, 100.0), (2999.0, 10.0), (2998.0, 10.0), (2997.0, 10.0), (2996.0, 10.0)]
    mock_asks = [(3001.0, 10.0), (3002.0, 1000.0), (3003.0, 1000.0), (3004.0, 1000.0), (3005.0, 1000.0)]
    
    snapshot = {'bids': mock_bids, 'asks': mock_asks}
    feats = engine.compute_all_features(snapshot)
    
    print(f"🔹 OBI L1 (Inmediato): {feats['obi_L1']:.4f} (¡Muy Alcista!)")
    print(f"🔹 OBI L5 (Profundo):  {feats['obi_L5']:.4f} (¡Muy Bajista!)")
    print(f"⚠️ Divergencia Spoofing: {feats['spoofing_divergence']:.4f}")
    
    print("\n✅ Cálculo de features L2 completado.")