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
    Clasifica régimen de mercado en 4 categorías:
    - Clase 0: Rango/Lateral (Low Volatility)
    - Clase 1: Tendencia Alcista
    - Clase 2: Tendencia Bajista
    - Clase 3: Peligro (Volatilidad extrema)
    """
    
    def __init__(self, 
                 forward_window: int = 3,  # 3 velas de 4h = 12h forward
                 volatility_threshold_low: float = 0.015,
                 volatility_threshold_high: float = 0.05,
                 trend_threshold: float = 0.02):
        """
        Args:
            forward_window: Ventanas hacia adelante para calcular target
            volatility_threshold_low: Umbral para mercado lateral
            volatility_threshold_high: Umbral para mercado peligroso
            trend_threshold: Mínimo cambio % para considerar tendencia
        """
        self.forward_window = forward_window
        self.vol_low = volatility_threshold_low
        self.vol_high = volatility_threshold_high
        self.trend_threshold = trend_threshold
    
    def label_regime(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Asigna etiquetas de régimen basadas en comportamiento futuro
        
        Args:
            df: DataFrame con columnas 'close', 'high', 'low'
        
        Returns:
            DataFrame con columna 'regime' agregada
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
        
        # Inicializar regime
        df['regime'] = -1  # Default: no clasificado
        
        # Clase 3: PELIGRO (Volatilidad Extrema)
        danger_mask = (
            (df['forward_volatility'] > self.vol_high) |
            (df['forward_hl_range'] > self.vol_high * 2)
        )
        df.loc[danger_mask, 'regime'] = 3
        
        # Clase 0: LATERAL (Baja Volatilidad)
        lateral_mask = (
            (df['regime'] == -1) &
            (df['forward_volatility'] < self.vol_low) &
            (np.abs(df['forward_return']) < self.trend_threshold)
        )
        df.loc[lateral_mask, 'regime'] = 0
        
        # Clase 1: TENDENCIA ALCISTA
        bullish_mask = (
            (df['regime'] == -1) &
            (df['forward_return'] > self.trend_threshold) &
            (df['forward_volatility'] < self.vol_high)
        )
        df.loc[bullish_mask, 'regime'] = 1
        
        # Clase 2: TENDENCIA BAJISTA
        bearish_mask = (
            (df['regime'] == -1) &
            (df['forward_return'] < -self.trend_threshold) &
            (df['forward_volatility'] < self.vol_high)
        )
        df.loc[bearish_mask, 'regime'] = 2
        
        # Cualquier registro sin clasificar -> Asignar como Lateral (clase 0)
        df.loc[df['regime'] == -1, 'regime'] = 0
        
        # Eliminar filas sin target (últimas N filas)
        df.dropna(subset=['forward_return'], inplace=True)
        
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
    dates = pd.date_range(end=pd.Timestamp.now(), periods=2000, freq='4H')
    
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
        forward_window=3,
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


# ============================================================================
# WRAPPER FUNCTION FOR COMPATIBILITY
# ============================================================================

def label_regime_targets(df: pd.DataFrame,
                        n_classes: int = 4,
                        method: str = 'static',
                        forward_window: int = 3,
                        **kwargs) -> pd.Series:
    """
    Wrapper function to create regime targets compatible with model_pipeline.py

    Args:
        df: DataFrame with OHLC data (must have 'close', 'high', 'low')
        n_classes: Number of classes (default 4)
        method: 'static' or 'adaptive' or 'volatility_quantiles'
        forward_window: Forward window for target calculation
        **kwargs: Additional parameters for RegimeLabeler

    Returns:
        Series with regime labels (0, 1, 2, 3)
    """
    logger.info(f"Creating regime targets using method: {method}")

    # Validate required columns
    required_cols = ['close', 'high', 'low']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Initialize labeler
    labeler = RegimeLabeler(
        forward_window=forward_window,
        volatility_threshold_low=kwargs.get('volatility_threshold_low', 0.015),
        volatility_threshold_high=kwargs.get('volatility_threshold_high', 0.05),
        trend_threshold=kwargs.get('trend_threshold', 0.02)
    )

    # Apply labeling based on method
    if method == 'adaptive':
        df_labeled = labeler.create_adaptive_labels(
            df,
            lookback_period=kwargs.get('lookback_period', 168)
        )
        targets = df_labeled['regime_adaptive']
    elif method == 'volatility_quantiles':
        # Use adaptive method with quantiles (same as adaptive)
        df_labeled = labeler.create_adaptive_labels(
            df,
            lookback_period=kwargs.get('lookback_period', 168)
        )
        targets = df_labeled['regime_adaptive']
    else:  # static
        df_labeled = labeler.label_regime(df)
        targets = df_labeled['regime']

    # Align targets with original dataframe index
    targets = targets.reindex(df.index)

    logger.info(f"✓ Targets created: {len(targets)} samples")
    logger.info(f"✓ NaN values: {targets.isna().sum()}")

    return targets