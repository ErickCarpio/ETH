"""
Advanced Derivatives Features - FASE 3.2, 3.3, 3.4
Features avanzados de funding rates, liquidaciones y open interest

Features implementadas:
- Funding: velocity, cross-exchange, predicted_next
- Liquidations: cluster detection, cascade risk
- OI: velocity, percentiles, divergence
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class AdvancedDerivativesFeatures:
    """
    Calculador de features avanzados de derivados

    Expande las features básicas de derivatives_manager.py con:
    - Análisis de velocidad y tendencias
    - Detección de anomalías
    - Cross-exchange comparisons
    - Risk metrics
    """

    def __init__(self):
        self.funding_history = []
        self.oi_history = []
        self.liq_history = []

    # ===== FUNDING RATE ADVANCED =====

    def calculate_funding_velocity(self,
                                   funding_history: pd.Series,
                                   window_hours: int = 8) -> float:
        """
        Calcula la velocidad de cambio del funding rate

        Funding velocity = (current - funding_8h_ago) / 8h

        Args:
            funding_history: Serie temporal de funding rates
            window_hours: Window para calcular velocidad (default: 8h)

        Returns:
            Funding velocity (cambio por hora)
        """
        if len(funding_history) < window_hours:
            return 0.0

        current = funding_history.iloc[-1]
        past = funding_history.iloc[-window_hours]

        velocity = (current - past) / window_hours

        return velocity

    def calculate_funding_cross_exchange(self,
                                        binance_funding: float,
                                        bybit_funding: float) -> Dict[str, float]:
        """
        Calcula divergencia de funding entre exchanges

        Funding arbitrage opportunities cuando diverge mucho

        Args:
            binance_funding: Funding rate de Binance
            bybit_funding: Funding rate de Bybit

        Returns:
            Dict con spread y ratio
        """
        spread = binance_funding - bybit_funding
        avg = (abs(binance_funding) + abs(bybit_funding)) / 2

        if avg == 0:
            ratio = 0.0
        else:
            ratio = spread / avg

        return {
            'funding_spread': spread,
            'funding_ratio': ratio,
            'funding_arbitrage_signal': abs(ratio) > 0.5  # >50% divergence
        }

    def predict_next_funding(self,
                            funding_history: pd.Series,
                            method: str = 'linear') -> float:
        """
        Predice el próximo funding rate usando extrapolación

        Args:
            funding_history: Serie histórica
            method: 'linear', 'ema', o 'momentum'

        Returns:
            Funding rate predicho
        """
        if len(funding_history) < 3:
            return funding_history.iloc[-1] if len(funding_history) > 0 else 0.0

        if method == 'linear':
            # Extrapolación lineal simple
            x = np.arange(len(funding_history))
            y = funding_history.values

            # Linear regression
            A = np.vstack([x, np.ones(len(x))]).T
            m, c = np.linalg.lstsq(A, y, rcond=None)[0]

            # Predict next point
            next_val = m * len(x) + c
            return next_val

        elif method == 'ema':
            # Exponential moving average
            ema = funding_history.ewm(span=10).mean().iloc[-1]
            return ema

        elif method == 'momentum':
            # Momentum-based: current + velocity
            velocity = self.calculate_funding_velocity(funding_history, window_hours=8)
            predicted = funding_history.iloc[-1] + velocity
            return predicted

        return funding_history.iloc[-1]

    # ===== LIQUIDATIONS ADVANCED =====

    def detect_liquidation_cluster(self,
                                   liquidations: pd.DataFrame,
                                   window_minutes: int = 1,
                                   threshold_usd: float = 1_000_000) -> Dict:
        """
        Detecta clusters de liquidaciones (cascadas)

        Cluster = >$1M liquidado en <1 minuto

        Args:
            liquidations: DataFrame con columnas [timestamp, notional]
            window_minutes: Ventana para agrupar
            threshold_usd: Threshold en USD

        Returns:
            Dict con detección y métricas
        """
        if liquidations.empty:
            return {
                'cluster_detected': False,
                'cluster_notional': 0.0,
                'cluster_count': 0
            }

        # Agrupar por ventana de tiempo
        liquidations = liquidations.set_index('timestamp')
        window = f'{window_minutes}min'

        agg = liquidations.resample(window).agg({
            'notional': 'sum',
            'quantity': 'count'
        })

        # Detectar clusters
        max_notional = agg['notional'].max()
        cluster_detected = max_notional > threshold_usd

        if cluster_detected:
            cluster_time = agg['notional'].idxmax()
            cluster_count = agg.loc[cluster_time, 'quantity']
        else:
            cluster_count = 0

        return {
            'cluster_detected': cluster_detected,
            'cluster_notional': max_notional,
            'cluster_count': int(cluster_count),
            'cluster_intensity': max_notional / threshold_usd  # Múltiplo del threshold
        }

    def calculate_cascade_risk(self,
                              liquidations: pd.DataFrame,
                              oi_current: float,
                              price_current: float) -> float:
        """
        Calcula riesgo de cascada de liquidaciones

        Risk = (liquidations_recent / OI) × price_velocity

        Args:
            liquidations: DataFrame con liquidaciones recientes
            oi_current: Open Interest actual
            price_current: Precio actual

        Returns:
            Cascade risk score (0-1)
        """
        if liquidations.empty or oi_current == 0:
            return 0.0

        # Liquidaciones últimos 15 minutos
        recent_liqs = liquidations[liquidations['timestamp'] > (pd.Timestamp.now() - pd.Timedelta(minutes=15))]

        if recent_liqs.empty:
            return 0.0

        # Total liquidado
        total_liquidated = recent_liqs['notional'].sum()

        # Ratio vs OI
        liq_ratio = total_liquidated / (oi_current * price_current + 1e-8)

        # Price velocity (simplificado: número de liquidaciones)
        velocity_proxy = len(recent_liqs) / 15  # liqs por minuto

        # Risk score
        risk = min(liq_ratio * velocity_proxy * 10, 1.0)

        return risk

    def aggregate_liquidations_by_windows(self,
                                         liquidations: pd.DataFrame,
                                         windows: List[str] = ['1min', '5min', '15min']) -> Dict:
        """
        Agrega liquidaciones en múltiples ventanas de tiempo.

        Args:
            liquidations: DataFrame con liquidaciones [timestamp, notional, side]
            windows: Lista de ventanas (ej: ['1min', '5min', '15min'])

        Returns:
            Dict con agregaciones por ventana
        """
        features = {}

        if liquidations.empty or 'timestamp' not in liquidations.columns:
            for window in windows:
                features[f'liq_total_{window}'] = 0.0
                features[f'liq_count_{window}'] = 0
                features[f'liq_avg_{window}'] = 0.0
            return features

        # Set timestamp as index
        liq_df = liquidations.set_index('timestamp')

        for window in windows:
            # Aggregate by window
            agg = liq_df.resample(window).agg({
                'notional': ['sum', 'count', 'mean'],
            })

            # Get most recent window
            if not agg.empty:
                latest = agg.iloc[-1]
                features[f'liq_total_{window}'] = latest[('notional', 'sum')]
                features[f'liq_count_{window}'] = int(latest[('notional', 'count')])
                features[f'liq_avg_{window}'] = latest[('notional', 'mean')]
            else:
                features[f'liq_total_{window}'] = 0.0
                features[f'liq_count_{window}'] = 0
                features[f'liq_avg_{window}'] = 0.0

        return features

    def calculate_liquidation_ratio(self,
                                   liquidations: pd.DataFrame) -> Dict:
        """
        Calcula ratio de liquidaciones long vs short.

        Args:
            liquidations: DataFrame con columna 'side' ('long' o 'short')

        Returns:
            Dict con ratios y métricas
        """
        features = {}

        if liquidations.empty or 'side' not in liquidations.columns:
            return {
                'liq_long_ratio': 0.5,
                'liq_short_ratio': 0.5,
                'liq_long_short_ratio': 1.0,
                'liq_long_total': 0.0,
                'liq_short_total': 0.0
            }

        # Separate by side
        long_liqs = liquidations[liquidations['side'] == 'long']
        short_liqs = liquidations[liquidations['side'] == 'short']

        # Calculate totals
        long_total = long_liqs['notional'].sum() if not long_liqs.empty else 0.0
        short_total = short_liqs['notional'].sum() if not short_liqs.empty else 0.0
        total = long_total + short_total

        # Calculate ratios
        if total > 0:
            long_ratio = long_total / total
            short_ratio = short_total / total
        else:
            long_ratio = 0.5
            short_ratio = 0.5

        # Long/Short ratio
        if short_total > 0:
            ls_ratio = long_total / short_total
        else:
            ls_ratio = 1.0 if long_total == 0 else float('inf')

        features['liq_long_ratio'] = long_ratio
        features['liq_short_ratio'] = short_ratio
        features['liq_long_short_ratio'] = min(ls_ratio, 100.0)  # Cap at 100
        features['liq_long_total'] = long_total
        features['liq_short_total'] = short_total

        return features

    # ===== OPEN INTEREST ADVANCED =====

    def calculate_oi_velocity(self,
                             oi_history: pd.Series,
                             window_hours: int = 1) -> float:
        """
        Calcula velocidad de cambio del OI

        OI velocity = (current - oi_1h_ago) / 1h

        Args:
            oi_history: Serie temporal de OI
            window_hours: Window para calcular velocidad

        Returns:
            OI velocity (cambio por hora)
        """
        if len(oi_history) < window_hours:
            return 0.0

        current = oi_history.iloc[-1]
        past = oi_history.iloc[-window_hours]

        velocity = (current - past) / window_hours

        return velocity

    def calculate_oi_percentile(self,
                               oi_current: float,
                               oi_history: pd.Series,
                               window_days: int = 90) -> float:
        """
        Calcula percentil del OI actual vs histórico

        Percentile = 0.95 → OI en top 5% de los últimos 90d

        Args:
            oi_current: OI actual
            oi_history: Serie histórica (últimos 90 días)
            window_days: Ventana para calcular percentil

        Returns:
            Percentil (0-1)
        """
        if len(oi_history) < 10:
            return 0.5  # Neutral si no hay historia

        # Limitar a últimos N días
        if len(oi_history) > window_days * 24:  # Asumiendo hourly data
            oi_history = oi_history.iloc[-window_days * 24:]

        percentile = (oi_history < oi_current).sum() / len(oi_history)

        return percentile

    def detect_oi_divergence(self,
                            oi_history: pd.Series,
                            price_history: pd.Series,
                            window: int = 24) -> Dict:
        """
        Detecta divergencia entre OI y precio

        Divergencia alcista: OI sube pero precio no (preparación rally)
        Divergencia bajista: OI baja pero precio aguanta (distribución)

        Args:
            oi_history: Serie de OI
            price_history: Serie de precio
            window: Ventana en horas

        Returns:
            Dict con señales de divergencia
        """
        if len(oi_history) < window or len(price_history) < window:
            return {
                'divergence_detected': False,
                'divergence_type': 'none',
                'divergence_strength': 0.0
            }

        # Cambios porcentuales
        oi_change = (oi_history.iloc[-1] - oi_history.iloc[-window]) / oi_history.iloc[-window]
        price_change = (price_history.iloc[-1] - price_history.iloc[-window]) / price_history.iloc[-window]

        # Detectar divergencias
        divergence_threshold = 0.05  # 5%

        # Divergencia alcista: OI sube >5% pero precio plano o baja
        bullish_divergence = (oi_change > divergence_threshold) and (price_change < divergence_threshold)

        # Divergencia bajista: OI baja >5% pero precio plano o sube
        bearish_divergence = (oi_change < -divergence_threshold) and (price_change > -divergence_threshold)

        if bullish_divergence:
            div_type = 'bullish'
            strength = oi_change / (abs(price_change) + 0.01)
        elif bearish_divergence:
            div_type = 'bearish'
            strength = abs(oi_change) / (price_change + 0.01)
        else:
            div_type = 'none'
            strength = 0.0

        return {
            'divergence_detected': bullish_divergence or bearish_divergence,
            'divergence_type': div_type,
            'divergence_strength': min(abs(strength), 10.0),  # Cap at 10x
            'oi_change_pct': oi_change,
            'price_change_pct': price_change
        }

    # ===== AGGREGATE FEATURES =====

    def calculate_all_advanced_features(self,
                                       funding_df: pd.DataFrame,
                                       liquidations_df: pd.DataFrame,
                                       oi_df: pd.DataFrame,
                                       price_df: pd.DataFrame,
                                       bybit_funding: Optional[float] = None) -> Dict:
        """
        Calcula todas las features avanzadas de derivados

        Args:
            funding_df: DataFrame con funding rates
            liquidations_df: DataFrame con liquidaciones
            oi_df: DataFrame con open interest
            price_df: DataFrame con precios
            bybit_funding: Funding rate de Bybit (opcional)

        Returns:
            Dict con todas las features
        """
        features = {}

        # === FUNDING FEATURES ===
        if not funding_df.empty and 'funding_rate' in funding_df.columns:
            funding_series = funding_df['funding_rate']

            features['funding_velocity_8h'] = self.calculate_funding_velocity(funding_series, window_hours=8)
            features['funding_predicted_next'] = self.predict_next_funding(funding_series, method='momentum')

            # Cross-exchange (si disponible)
            if bybit_funding is not None:
                current_binance = funding_series.iloc[-1]
                cross_ex = self.calculate_funding_cross_exchange(current_binance, bybit_funding)
                features.update(cross_ex)
            else:
                features['funding_spread'] = 0.0
                features['funding_ratio'] = 0.0
                features['funding_arbitrage_signal'] = False

        # === LIQUIDATION FEATURES ===
        if not liquidations_df.empty:
            cluster = self.detect_liquidation_cluster(liquidations_df, window_minutes=1, threshold_usd=1_000_000)
            features.update({f'liq_{k}': v for k, v in cluster.items()})

            # Cascade risk
            if not oi_df.empty and not price_df.empty:
                oi_current = oi_df['oi'].iloc[-1]
                price_current = price_df['close'].iloc[-1]
                features['liq_cascade_risk'] = self.calculate_cascade_risk(liquidations_df, oi_current, price_current)
            else:
                features['liq_cascade_risk'] = 0.0

            # Aggregations by windows (1m, 5m, 15m)
            window_features = self.aggregate_liquidations_by_windows(liquidations_df)
            features.update(window_features)

            # Long/Short ratio
            ratio_features = self.calculate_liquidation_ratio(liquidations_df)
            features.update(ratio_features)
        else:
            # Placeholder if no liquidation data
            features.update({
                'liq_total_1min': 0.0,
                'liq_count_1min': 0,
                'liq_avg_1min': 0.0,
                'liq_total_5min': 0.0,
                'liq_count_5min': 0,
                'liq_avg_5min': 0.0,
                'liq_total_15min': 0.0,
                'liq_count_15min': 0,
                'liq_avg_15min': 0.0,
                'liq_long_ratio': 0.5,
                'liq_short_ratio': 0.5,
                'liq_long_short_ratio': 1.0
            })

        # === OI FEATURES ===
        if not oi_df.empty and 'oi' in oi_df.columns:
            oi_series = oi_df['oi']

            features['oi_velocity_1h'] = self.calculate_oi_velocity(oi_series, window_hours=1)
            features['oi_percentile_90d'] = self.calculate_oi_percentile(oi_series.iloc[-1], oi_series, window_days=90)

            # OI-Price divergence
            if not price_df.empty and 'close' in price_df.columns:
                divergence = self.detect_oi_divergence(oi_series, price_df['close'], window=24)
                features.update({f'oi_div_{k}': v for k, v in divergence.items()})

        return features


# Demo / Testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("🧪 Advanced Derivatives Features - Test\n")

    calc = AdvancedDerivativesFeatures()

    # Generar datos de prueba
    dates = pd.date_range('2024-01-01', periods=200, freq='1h')

    funding_df = pd.DataFrame({
        'timestamp': dates,
        'funding_rate': np.random.normal(0.0001, 0.00005, 200).cumsum()
    })

    liquidations_df = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=50, freq='30s'),
        'notional': np.random.exponential(100000, 50),
        'quantity': np.random.randint(1, 100, 50)
    })

    oi_df = pd.DataFrame({
        'timestamp': dates,
        'oi': np.random.normal(1000000, 50000, 200).cumsum()
    })

    price_df = pd.DataFrame({
        'timestamp': dates,
        'close': np.random.normal(3000, 50, 200).cumsum()
    })

    # Calcular features
    features = calc.calculate_all_advanced_features(
        funding_df=funding_df,
        liquidations_df=liquidations_df,
        oi_df=oi_df,
        price_df=price_df,
        bybit_funding=0.00012
    )

    print("✅ Features calculadas:\n")
    for key, value in features.items():
        if isinstance(value, float):
            print(f"   {key}: {value:.6f}")
        else:
            print(f"   {key}: {value}")

    print(f"\n💡 Total features: {len(features)}")
