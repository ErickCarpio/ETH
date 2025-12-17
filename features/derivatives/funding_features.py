"""
Funding Rate Features - FASE 3.2
=================================

Procesa funding rates y calcula features para el modelo.

Funding Rate:
- Tasa que longs pagan a shorts (o viceversa) cada 8h en futuros perpetuos
- Funding positivo = más longs → pagan a shorts → mercado alcista sobrecalentado
- Funding negativo = más shorts → pagan a longs → mercado bajista sobrecalentado

Extremos de funding:
- Funding muy alto (>0.1%) → Posible squeeze de longs
- Funding muy bajo (<-0.1%) → Posible squeeze de shorts

Features calculadas (~18 features):
1. Funding rate actual
2. Funding rate smoothed (MA)
3. Funding rate velocity (cambio por hora)
4. Funding rate percentile histórico
5. Funding rate divergence vs precio
6. Funding rate extremes (spikes)
7. Funding bias (predominio de positivo/negativo)
8. Funding volatility
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class FundingFeatures:
    """
    Calculador de features basadas en funding rates.

    Workflow:
    1. Recibir serie temporal de funding rates
    2. Calcular métricas derivadas (MA, velocity, percentile)
    3. Detectar extremos y divergencias
    4. Generar features para modelo
    """

    def __init__(self):
        """Initialize Funding Features calculator."""
        pass

    def calculate_funding_ma(self,
                            funding_series: pd.Series,
                            windows: list = [3, 7, 14, 30]) -> pd.DataFrame:
        """
        Calcula moving averages del funding rate.

        Args:
            funding_series: Serie de funding rates
            windows: Ventanas para MA (en períodos de 8h)

        Returns:
            DataFrame con MAs
        """
        result = pd.DataFrame(index=funding_series.index)

        for window in windows:
            col_name = f'funding_ma_{window * 8}h'
            result[col_name] = funding_series.rolling(window, min_periods=1).mean()

        return result

    def calculate_funding_velocity(self,
                                  funding_series: pd.Series,
                                  window_periods: int = 1) -> pd.Series:
        """
        Calcula velocidad de cambio del funding rate.

        Args:
            funding_series: Serie de funding rates
            window_periods: Ventana en períodos (1 período = 8h)

        Returns:
            Serie con velocidad
        """
        velocity = funding_series.diff(window_periods) / window_periods
        return velocity

    def calculate_funding_percentile(self,
                                    funding_series: pd.Series,
                                    window_days: int = 90) -> pd.Series:
        """
        Calcula percentil del funding rate vs histórico.

        Args:
            funding_series: Serie de funding rates
            window_days: Ventana histórica (días)

        Returns:
            Serie con percentiles (0-1)
        """
        # Convert days to periods (3 períodos de 8h por día)
        window_periods = window_days * 3

        def rolling_percentile(x):
            if len(x) < 2:
                return 0.5
            return (x.iloc[-1] > x.iloc[:-1]).sum() / (len(x) - 1)

        percentile = funding_series.rolling(window=window_periods, min_periods=2).apply(
            rolling_percentile, raw=False
        )
        return percentile

    def detect_funding_extremes(self,
                               funding_series: pd.Series,
                               high_threshold: float = 0.001,  # 0.1%
                               low_threshold: float = -0.001) -> pd.DataFrame:
        """
        Detecta extremos en funding rate.

        Args:
            funding_series: Serie de funding rates
            high_threshold: Umbral alto (default 0.1%)
            low_threshold: Umbral bajo (default -0.1%)

        Returns:
            DataFrame con flags de extremos
        """
        result = pd.DataFrame(index=funding_series.index)

        result['funding_extreme_high'] = (funding_series > high_threshold).astype(int)
        result['funding_extreme_low'] = (funding_series < low_threshold).astype(int)
        result['funding_extreme_any'] = (result['funding_extreme_high'] | result['funding_extreme_low']).astype(int)

        return result

    def calculate_funding_bias(self,
                              funding_series: pd.Series,
                              window_days: int = 30) -> pd.Series:
        """
        Calcula bias del funding (predominio de positivo/negativo).

        Args:
            funding_series: Serie de funding rates
            window_days: Ventana para cálculo

        Returns:
            Serie con bias (-1 a 1)
        """
        window_periods = window_days * 3

        def calc_bias(x):
            if len(x) == 0:
                return 0
            positive_count = (x > 0).sum()
            negative_count = (x < 0).sum()
            total = len(x)

            if total == 0:
                return 0

            return (positive_count - negative_count) / total

        bias = funding_series.rolling(window=window_periods, min_periods=1).apply(
            calc_bias, raw=False
        )
        return bias

    def calculate_funding_volatility(self,
                                    funding_series: pd.Series,
                                    window_days: int = 30) -> pd.Series:
        """
        Calcula volatilidad del funding rate.

        Args:
            funding_series: Serie de funding rates
            window_days: Ventana para std dev

        Returns:
            Serie con volatilidad
        """
        window_periods = window_days * 3
        volatility = funding_series.rolling(window=window_periods, min_periods=1).std()
        return volatility

    def detect_funding_divergence(self,
                                 funding_series: pd.Series,
                                 price_series: pd.Series,
                                 window: int = 24) -> pd.Series:
        """
        Detecta divergencia entre funding y precio.

        Lógica:
        - Funding up, Price down = Bearish divergence (longs acumulándose en caída)
        - Funding down, Price up = Bullish divergence (shorts acumulándose en subida)

        Args:
            funding_series: Serie de funding rates
            price_series: Serie de precios
            window: Ventana para tendencia

        Returns:
            Serie con divergencia (-1, 0, 1)
        """
        # Alinear índices
        aligned_price = price_series.reindex(funding_series.index, method='ffill')

        # Calcular tendencias
        funding_trend = funding_series.rolling(window).apply(
            lambda x: 1 if x.iloc[-1] > x.iloc[0] else -1, raw=False
        )
        price_trend = aligned_price.rolling(window).apply(
            lambda x: 1 if x.iloc[-1] > x.iloc[0] else -1, raw=False
        )

        # Detectar divergencias
        divergence = pd.Series(0, index=funding_series.index)

        # Bearish: Funding up, price down
        divergence[(funding_trend == 1) & (price_trend == -1)] = -1

        # Bullish: Funding down, price up
        divergence[(funding_trend == -1) & (price_trend == 1)] = 1

        return divergence

    def calculate_all_features(self,
                              funding_series: pd.Series,
                              price_series: Optional[pd.Series] = None) -> pd.DataFrame:
        """
        Calcula todas las features de funding.

        Args:
            funding_series: Serie de funding rates
            price_series: Serie de precios (opcional, para divergencias)

        Returns:
            DataFrame con ~18 features
        """
        if funding_series.empty:
            return self._get_empty_features()

        result = pd.DataFrame(index=funding_series.index)

        # 1. Funding rate actual
        result['funding_rate'] = funding_series

        # 2. Moving averages (4 features)
        ma_df = self.calculate_funding_ma(funding_series, windows=[3, 7, 14, 30])
        result = result.join(ma_df)

        # 3. Velocity (1 feature)
        result['funding_velocity'] = self.calculate_funding_velocity(funding_series)

        # 4. Percentile (1 feature)
        result['funding_percentile_90d'] = self.calculate_funding_percentile(funding_series, window_days=90)

        # 5. Extremes (3 features)
        extremes_df = self.detect_funding_extremes(funding_series)
        result = result.join(extremes_df)

        # 6. Bias (1 feature)
        result['funding_bias_30d'] = self.calculate_funding_bias(funding_series, window_days=30)

        # 7. Volatility (1 feature)
        result['funding_volatility_30d'] = self.calculate_funding_volatility(funding_series, window_days=30)

        # 8. Divergence con precio (si disponible) (1 feature)
        if price_series is not None and not price_series.empty:
            result['funding_price_divergence'] = self.detect_funding_divergence(
                funding_series, price_series, window=24
            )
        else:
            result['funding_price_divergence'] = 0

        # 9. Derivadas adicionales
        # Funding rate vs MA (spread)
        result['funding_vs_ma7'] = funding_series - result['funding_ma_56h']

        # Funding percentile cambio
        result['funding_percentile_change'] = result['funding_percentile_90d'].diff()

        # Z-score del funding (últimos 90d)
        def calc_zscore(x):
            if len(x) < 2:
                return 0
            mean = x.mean()
            std = x.std()
            if std == 0:
                return 0
            return (x.iloc[-1] - mean) / std

        window_90d = 90 * 3  # 90 días en períodos de 8h
        result['funding_zscore_90d'] = funding_series.rolling(window=window_90d, min_periods=2).apply(
            calc_zscore, raw=False
        )

        # Fill NaNs
        result = result.fillna(0)

        logger.debug(f"Calculated {len(result.columns)} funding features")

        return result

    def _get_empty_features(self) -> pd.DataFrame:
        """Retorna DataFrame vacío con columnas correctas."""
        columns = [
            'funding_rate',
            'funding_ma_24h',
            'funding_ma_56h',
            'funding_ma_112h',
            'funding_ma_240h',
            'funding_velocity',
            'funding_percentile_90d',
            'funding_extreme_high',
            'funding_extreme_low',
            'funding_extreme_any',
            'funding_bias_30d',
            'funding_volatility_30d',
            'funding_price_divergence',
            'funding_vs_ma7',
            'funding_percentile_change',
            'funding_zscore_90d'
        ]

        return pd.DataFrame(columns=columns)

    def get_current_funding_state(self,
                                 funding_series: pd.Series) -> Dict:
        """
        Obtiene estado actual del funding para análisis.

        Args:
            funding_series: Serie de funding rates

        Returns:
            Dict con estado actual
        """
        if funding_series.empty:
            return {}

        current_funding = funding_series.iloc[-1]

        # Percentile
        percentile_90d = self.calculate_funding_percentile(funding_series, window_days=90).iloc[-1]

        # Bias
        bias_30d = self.calculate_funding_bias(funding_series, window_days=30).iloc[-1]

        # Volatility
        vol_30d = self.calculate_funding_volatility(funding_series, window_days=30).iloc[-1]

        # Classification
        if current_funding > 0.001:
            state = "EXTREME_BULLISH"
            risk = "HIGH"
        elif current_funding > 0.0005:
            state = "BULLISH"
            risk = "MEDIUM"
        elif current_funding < -0.001:
            state = "EXTREME_BEARISH"
            risk = "HIGH"
        elif current_funding < -0.0005:
            state = "BEARISH"
            risk = "MEDIUM"
        else:
            state = "NEUTRAL"
            risk = "LOW"

        return {
            'current_funding_rate': current_funding,
            'current_funding_pct': current_funding * 100,
            'percentile_90d': percentile_90d,
            'bias_30d': bias_30d,
            'volatility_30d': vol_30d,
            'state': state,
            'risk_level': risk
        }


if __name__ == "__main__":
    # Ejemplo de uso
    logging.basicConfig(level=logging.INFO)

    # Simular funding rates
    dates = pd.date_range(end=pd.Timestamp.now(), periods=1000, freq='8H')
    np.random.seed(42)

    # Generar funding rates realistas
    funding_rates = np.random.normal(0.0001, 0.0003, 1000)  # Mean 0.01%, std 0.03%
    funding_rates += np.sin(np.linspace(0, 10, 1000)) * 0.0002  # Add cyclical pattern

    funding_series = pd.Series(funding_rates, index=dates)

    # Simular precios
    prices = 1950 + np.cumsum(np.random.normal(0, 10, 1000))
    price_series = pd.Series(prices, index=dates)

    # Calcular features
    calc = FundingFeatures()
    features = calc.calculate_all_features(funding_series, price_series)

    print("\n" + "="*60)
    print("FUNDING FEATURES")
    print("="*60)
    print(f"\nShape: {features.shape}")
    print(f"\nColumns: {list(features.columns)}")
    print(f"\nLast 5 rows:")
    print(features.tail())

    # Estado actual
    state = calc.get_current_funding_state(funding_series)
    print("\n" + "="*60)
    print("CURRENT FUNDING STATE")
    print("="*60)
    for key, value in state.items():
        print(f"{key}: {value}")
