"""
VPIN Calculator - Toxicidad del Flujo de Órdenes
Mide la probabilidad de trading informado (Informed Trading).
Un VPIN alto (>0.8) predice alta volatilidad o caídas inminentes.
"""

import pandas as pd
import numpy as np
from scipy.stats import norm
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VPIN")

class VPINCalculator:
    def __init__(self, bucket_volume: float = 1000.0, window_buckets: int = 50):
        """
        Args:
            bucket_volume: Cantidad de ETH por "barra" de volumen (Volume Bar)
            window_buckets: Cuántos buckets usar para calcular el VPIN móvil
        """
        self.bucket_vol = bucket_volume
        self.window = window_buckets
        
        # Estado acumulado
        self.current_bucket_vol = 0.0
        self.current_buy_vol = 0.0
        self.current_sell_vol = 0.0
        
        # Historial de desequilibrios (OI = |Buy - Sell|)
        self.oi_history = [] 
        
    def process_trade(self, price: float, qty: float, price_change: float = 0.0, sigma_p: float = 1.0):
        """
        Procesa un trade individual y actualiza el VPIN en tiempo real.
        Usa Bulk Volume Classification (BVC) probabilístico.
        """
        # 1. Clasificar Volumen (Buy vs Sell) usando BVC
        # Si el precio subió, es más probable que sea compra.
        # Usamos la distribución normal (CDF) del cambio de precio estandarizado.
        
        if sigma_p == 0: sigma_p = 1.0 # Evitar división por cero
        
        z_score = price_change / sigma_p
        buy_prob = norm.cdf(z_score)
        
        buy_vol = qty * buy_prob
        sell_vol = qty * (1 - buy_prob)
        
        # 2. Llenar el Bucket actual
        remaining_qty = qty
        
        while remaining_qty > 0:
            space_in_bucket = self.bucket_vol - self.current_bucket_vol
            
            if remaining_qty >= space_in_bucket:
                # Llenar lo que falta y cerrar bucket
                fraction = space_in_bucket / qty
                
                self.current_buy_vol += buy_vol * fraction
                self.current_sell_vol += sell_vol * fraction
                self.current_bucket_vol += space_in_bucket
                
                self._close_bucket()
                
                remaining_qty -= space_in_bucket
            else:
                # Solo acumular
                fraction = remaining_qty / qty
                self.current_buy_vol += buy_vol * fraction
                self.current_sell_vol += sell_vol * fraction
                self.current_bucket_vol += remaining_qty
                remaining_qty = 0

    def _close_bucket(self):
        """Se llama cuando un bucket de volumen se llena"""
        # Calcular Order Imbalance del bucket
        oi = abs(self.current_buy_vol - self.current_sell_vol)
        self.oi_history.append(oi)
        
        # Mantener ventana deslizante
        if len(self.oi_history) > self.window:
            self.oi_history.pop(0)
            
        # Resetear acumuladores para el siguiente bucket
        self.current_bucket_vol = 0.0
        self.current_buy_vol = 0.0
        self.current_sell_vol = 0.0
        
        # Loguear si el VPIN es peligroso (opcional)
        current_vpin = self.get_current_vpin()
        if current_vpin > 0.8:
            logger.warning(f"⚠️ ALERTA DE TOXICIDAD: VPIN {current_vpin:.2f} (Posible Crash/Volatilidad)")

    def get_current_vpin(self) -> float:
        """Retorna el valor VPIN actual"""
        if len(self.oi_history) < self.window:
            return 0.5 # Valor neutral si falta historia
            
        # Fórmula VPIN: Promedio de OI / Volumen del Bucket
        sum_oi = sum(self.oi_history)
        total_vol = len(self.oi_history) * self.bucket_vol
        
        return sum_oi / total_vol

# --- PRUEBA UNITARIA ---
if __name__ == "__main__":
    # Simular un ataque de ventas (Crash)
    calc = VPINCalculator(bucket_volume=100, window_buckets=10)
    
    print("Simulando mercado normal...")
    for _ in range(500):
        # Trades aleatorios con poco cambio de precio
        change = np.random.normal(0, 0.5)
        calc.process_trade(price=3000, qty=10, price_change=change)
        
    print(f"VPIN Normal: {calc.get_current_vpin():.4f}")
    
    print("\nSimulando Pánico (Ventas masivas con precio cayendo)...")
    for _ in range(500):
        # Ventas agresivas (cambio negativo fuerte)
        change = np.random.normal(-5, 2.0) 
        calc.process_trade(price=2900, qty=20, price_change=change, sigma_p=2.0)
        
    print(f"VPIN Pánico: {calc.get_current_vpin():.4f}")