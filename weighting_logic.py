"""
Weighting Logic - Sistema de Ponderación Temporal (Fixed & Clean)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TemporalWeighting:
    
    def __init__(self, 
                 decay_rate: float = 0.001,
                 min_weight: float = 0.1,
                 max_weight: float = 1.0,
                 recent_days: int = 7):
        self.decay_rate = decay_rate
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.recent_days = recent_days
    
    def calculate_weights(self, 
                         df: pd.DataFrame,
                         date_column: Optional[str] = None) -> np.ndarray:
        """
        Calcula array de pesos.
        CORREGIDO: Conversión estricta a NumPy para evitar errores de índice inmutable.
        """
        # 1. Obtener fechas
        if date_column and date_column in df.columns:
            dates = pd.to_datetime(df[date_column])
        else:
            dates = df.index
            
        if not isinstance(dates, (pd.DatetimeIndex, pd.Series)):
            try:
                dates = pd.to_datetime(dates)
            except:
                raise ValueError("El DataFrame debe tener índice temporal válido")
        
        # 2. Calcular antigüedad
        most_recent = dates.max()
        delta = most_recent - dates
        
        # 3. Convertir a segundos (Manejo híbrido robusto)
        if hasattr(delta, 'dt'): # Es una Serie
            seconds = delta.dt.total_seconds()
        else: # Es un Index (TimedeltaIndex)
            seconds = delta.total_seconds()
            
        # --- FIX CRÍTICO: Convertir a NumPy puro INMEDIATAMENTE ---
        # Esto rompe el vínculo con el índice inmutable de Pandas
        if hasattr(seconds, 'to_numpy'):
            seconds = seconds.to_numpy(dtype=np.float64)
        else:
            seconds = np.array(seconds, dtype=np.float64)
            
        # Convertir a días
        days_ago = seconds / (24 * 3600)
        
        # 4. Calcular pesos (Ahora es seguro operar porque es numpy puro)
        raw_weights = self.max_weight * np.exp(-self.decay_rate * days_ago)
        
        # Ajustar recientes
        recent_mask = days_ago <= self.recent_days
        raw_weights[recent_mask] = self.max_weight
        
        # Aplicar suelo
        weights = np.maximum(raw_weights, self.min_weight)
        
        logger.info(f"Pesos calculados - Rango: [{weights.min():.3f}, {weights.max():.3f}]")
        
        return weights
    
    def visualize_decay_curve(self, days_range: int = 730):
        days = np.arange(0, days_range)
        weights = self.max_weight * np.exp(-self.decay_rate * days)
        weights = np.maximum(weights, self.min_weight)
        weights[days <= self.recent_days] = self.max_weight
        return pd.DataFrame({'days_ago': days, 'weight': weights})
    
    def get_weight_statistics(self, weights: np.ndarray) -> dict:
        return {
            'mean': float(np.mean(weights)),
            'min': float(np.min(weights)),
            'max': float(np.max(weights))
        }
    
    @staticmethod
    def calibrate_decay_rate(target_half_life_days: int = 180) -> float:
        return -np.log(0.5) / target_half_life_days