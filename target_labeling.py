"""
Target Labeling - Clasificación de Régimen de Mercado
Define targets multi-clase para las próximas 4-12 horas
"""

import pandas as pd
import numpy as np
from typing import Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RegimeLabeler:
    """
    Clasificación BINARIA de OPORTUNIDADES de trading:
    - Clase 0: SHORT (Tendencia Bajista CLARA)
    - Clase 1: LONG (Tendencia Alcista CLARA)

    IMPORTANTE: Solo etiqueta cuando hay oportunidad REAL.
    Descarta velas laterales/inciertas del training.

    El modelo aprende a distinguir LONG vs SHORT,
    y solo da señal cuando encuentra patrón similar.
    """

    def __init__(self,
                 forward_window: int = 12,  # 12 velas de 1H = 12h forward
                 volatility_threshold_low: float = 0.015,
                 volatility_threshold_high: float = 0.05,
                 trend_threshold: float = 0.025):
        """
        Args:
            forward_window: Ventanas hacia adelante para calcular target
                           - 1H: 12 velas = 12h, 24 velas = 1 día
            volatility_threshold_low: Mínimo de volatilidad para considerar (no usado en binario)
            volatility_threshold_high: Máximo de volatilidad (descarta extremos)
            trend_threshold: Mínimo cambio % para considerar tendencia CLARA
        """
        self.forward_window = forward_window
        self.vol_low = volatility_threshold_low
        self.vol_high = volatility_threshold_high
        self.trend_threshold = trend_threshold
    
    def label_regime(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Etiqueta SOLO oportunidades CLARAS de trading (LONG o SHORT)
        Descarta velas laterales/inciertas

        Args:
            df: DataFrame con columnas 'close', 'high', 'low'

        Returns:
            DataFrame con columna 'regime' (solo velas con oportunidad clara)
            - regime=1: LONG (oportunidad alcista)
            - regime=0: SHORT (oportunidad bajista)
        """
        df = df.copy()

        # Calcular forward returns y volatilidad
        df['forward_return'] = (
            df['close'].shift(-self.forward_window) / df['close'] - 1
        )

        # Volatilidad forward (desviación std de returns en ventana)
        df['forward_volatility'] = (
            df['close']
            .pct_change()
            .shift(-self.forward_window)
            .rolling(self.forward_window)
            .std()
        )

        # Rango High-Low normalizado (forward)
        df['forward_hl_range'] = (
            (df['high'].shift(-self.forward_window) -
             df['low'].shift(-self.forward_window)) /
            df['close']
        )

        # Inicializar regime como NaN (no clasificado)
        df['regime'] = np.nan

        # CLASE 1: LONG (Tendencia Alcista CLARA)
        # Condiciones:
        # - Return positivo significativo (> trend_threshold)
        # - Volatilidad controlada (< vol_high)
        bullish_mask = (
            (df['forward_return'] > self.trend_threshold) &
            (df['forward_volatility'] < self.vol_high) &
            (df['forward_volatility'].notna())
        )
        df.loc[bullish_mask, 'regime'] = 1

        # CLASE 0: SHORT (Tendencia Bajista CLARA)
        # Condiciones:
        # - Return negativo significativo (< -trend_threshold)
        # - Volatilidad controlada (< vol_high)
        bearish_mask = (
            (df['forward_return'] < -self.trend_threshold) &
            (df['forward_volatility'] < self.vol_high) &
            (df['forward_volatility'].notna())
        )
        df.loc[bearish_mask, 'regime'] = 0

        # CRÍTICO: Eliminar velas sin oportunidad clara (laterales, extremas, etc.)
        # Solo mantenemos velas con regime=0 o regime=1
        df_original_len = len(df)
        df = df.dropna(subset=['regime'])
        df_filtered_len = len(df)

        logger.info(f"✂️ Filtrado: {df_original_len} velas → {df_filtered_len} oportunidades claras")
        if df_original_len > 0:
            logger.info(f"   Descartadas: {df_original_len - df_filtered_len} velas laterales/inciertas ({(df_original_len - df_filtered_len)/df_original_len*100:.1f}%)")

        # Verificar que haya datos
        if df_filtered_len == 0:
            logger.error("❌ No hay datos después del filtrado. Verifica que el cache tenga datos históricos.")
            logger.error("   Ejecuta: python model_pipeline_complete.py primero para generar datos.")
            raise ValueError("No hay datos para entrenar. Cache vacío.")

        # Convertir regime a int
        df['regime'] = df['regime'].astype(int)

        # Eliminar filas sin forward_return (últimas N velas)
        df = df.dropna(subset=['forward_return'])

        # Estadísticas de distribución
        self._log_regime_distribution(df)

        return df
    
    def create_adaptive_labels(self, df: pd.DataFrame, 
                              lookback_period: int = 168) -> pd.DataFrame:
        """
        Versión ADAPTATIVA de labels basada en percentiles históricos
        Los umbrales se ajustan según la volatilidad reciente del mercado
        
        Args:
            df: DataFrame con datos
            lookback_period: Ventana para calcular percentiles (168 = 28 días)
        
        Returns:
            DataFrame con 'regime_adaptive'
        """
        df = df.copy()
        
        # Calcular forward metrics
        df['forward_return'] = (
            df['close'].shift(-self.forward_window) / df['close'] - 1
        )
        
        df['forward_volatility'] = (
            df['close']
            .pct_change()
            .shift(-self.forward_window)
            .rolling(self.forward_window)
            .std()
        )
        
        # Umbrales adaptativos basados en rolling percentiles
        df['vol_p20'] = df['forward_volatility'].rolling(lookback_period).quantile(0.20)
        df['vol_p80'] = df['forward_volatility'].rolling(lookback_period).quantile(0.80)
        
        df['return_p20'] = df['forward_return'].rolling(lookback_period).quantile(0.20)
        df['return_p80'] = df['forward_return'].rolling(lookback_period).quantile(0.80)
        
        # Clasificación adaptativa
        df['regime_adaptive'] = 0  # Default: Lateral
        
        # Peligro: volatilidad en percentil 80+
        df.loc[df['forward_volatility'] > df['vol_p80'], 'regime_adaptive'] = 3
        
        # Alcista: return alto + volatilidad controlada
        df.loc[
            (df['forward_return'] > df['return_p80']) &
            (df['forward_volatility'] < df['vol_p80']),
            'regime_adaptive'
        ] = 1
        
        # Bajista: return bajo + volatilidad controlada
        df.loc[
            (df['forward_return'] < df['return_p20']) &
            (df['forward_volatility'] < df['vol_p80']),
            'regime_adaptive'
        ] = 2
        
        # Lateral: todo lo demás queda en 0
        
        df.dropna(subset=['forward_return'], inplace=True)
        
        self._log_regime_distribution(df, column='regime_adaptive')
        
        return df
    
    def _log_regime_distribution(self, df: pd.DataFrame, 
                                 column: str = 'regime'):
        """Log de distribución de clases"""
        counts = df[column].value_counts().sort_index()
        percentages = (counts / len(df) * 100).round(2)
        
        regime_names = {
            0: 'Lateral',
            1: 'Alcista',
            2: 'Bajista',
            3: 'Peligro'
        }
        
        logger.info("=" * 50)
        logger.info(f"DISTRIBUCIÓN DE RÉGIMEN ({column}):")
        for regime_id, count in counts.items():
            name = regime_names.get(regime_id, f'Unknown-{regime_id}')
            logger.info(f"  Clase {regime_id} ({name}): {count} ({percentages[regime_id]}%)")
        logger.info("=" * 50)
    
    def get_regime_summary_stats(self, df: pd.DataFrame, 
                                 regime_column: str = 'regime') -> pd.DataFrame:
        """
        Estadísticas de cada régimen para validación
        
        Returns:
            DataFrame con métricas por régimen
        """
        stats = []
        
        for regime_id in sorted(df[regime_column].unique()):
            regime_data = df[df[regime_column] == regime_id]
            
            stats.append({
                'regime': regime_id,
                'count': len(regime_data),
                'avg_forward_return': regime_data['forward_return'].mean(),
                'avg_volatility': regime_data['forward_volatility'].mean(),
                'max_drawdown': regime_data['forward_return'].min(),
                'max_upside': regime_data['forward_return'].max()
            })
        
        return pd.DataFrame(stats)


# Testing y visualización
if __name__ == "__main__":
    # Crear datos sintéticos de mercado
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=2000, freq='15min')
    
    # Simular diferentes regímenes
    price = 2000
    prices = [price]
    
    for i in range(1, len(dates)):
        # Cambiar régimen cada ~200 velas
        if i % 200 < 50:  # Lateral
            change = np.random.randn() * 5
        elif i % 200 < 100:  # Alcista
            change = np.random.randn() * 10 + 15
        elif i % 200 < 150:  # Bajista
            change = np.random.randn() * 10 - 15
        else:  # Volátil
            change = np.random.randn() * 30
        
        price += change
        prices.append(price)
    
    df = pd.DataFrame({
        'close': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices]
    }, index=dates)
    
    # Etiquetar regímenes
    labeler = RegimeLabeler(
        forward_window=16,  # 16 velas de 15min = 4 horas
        volatility_threshold_low=0.015,
        volatility_threshold_high=0.05,
        trend_threshold=0.02
    )
    
    # Método estático
    df_static = labeler.label_regime(df.copy())
    
    # Método adaptativo
    df_adaptive = labeler.create_adaptive_labels(df.copy())
    
    # Comparar distribuciones
    print("\n" + "=" * 60)
    print("MÉTODO ESTÁTICO:")
    print(df_static['regime'].value_counts().sort_index())
    
    print("\n" + "=" * 60)
    print("MÉTODO ADAPTATIVO:")
    print(df_adaptive['regime_adaptive'].value_counts().sort_index())
    
    # Estadísticas por régimen
    print("\n" + "=" * 60)
    print("ESTADÍSTICAS POR RÉGIMEN (Método Estático):")
    stats = labeler.get_regime_summary_stats(df_static)
    print(stats.to_string(index=False))