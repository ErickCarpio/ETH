"""
Micro-Price Calculator - Estimación del Precio Justo
Calcula el precio teórico ajustado por la microestructura del libro de órdenes.
Basado en la fórmula de Weighted Mid-Price (Stoikov approximation).
"""

import numpy as np

class MicroPriceCalculator:
    def __init__(self):
        pass

    def calculate_micro_price(self, bids: list, asks: list) -> float:
        """
        Calcula el Micro-Precio usando el desequilibrio de volumen en el tope del libro.
        Fórmula: P_micro = (P_ask * V_bid + P_bid * V_ask) / (V_bid + V_ask)
        """
        if not bids or not asks:
            return 0.0

        # Mejor Bid y Ask (Tope del libro)
        best_bid_price, best_bid_vol = bids[0]
        best_ask_price, best_ask_vol = asks[0]
        
        total_vol = best_bid_vol + best_ask_vol
        
        if total_vol == 0:
            return (best_bid_price + best_ask_price) / 2
            
        # El precio se inclina hacia donde hay MENOS volumen (camino de menor resistencia)
        # Si hay mucho Bid, el precio sube hacia el Ask.
        micro_price = (best_ask_price * best_bid_vol + best_bid_price * best_ask_vol) / total_vol
        
        return micro_price

    def calculate_effective_spread(self, bids: list, asks: list) -> float:
        """
        Calcula el spread efectivo (costo real de cruzar el spread).
        """
        if not bids or not asks:
            return 0.0
        return asks[0][0] - bids[0][0]

if __name__ == "__main__":
    # Prueba rápida
    calc = MicroPriceCalculator()
    
    # Caso: Mucha presión de COMPRA (100 vs 10)
    # Precio actual: 100.0 - 101.0 (Mid: 100.5)
    mock_bids = [(100.0, 100.0)] 
    mock_asks = [(101.0, 10.0)]
    
    mp = calc.calculate_micro_price(mock_bids, mock_asks)
    print(f"Mid Price: 100.5")
    print(f"Micro Price: {mp:.4f}")
    print("Interpretación: El precio real está casi en 101.0 porque la presión de compra es masiva.")