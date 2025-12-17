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


class TradingSignalLabeler:
    """
    Genera señales de trading enfocadas en oportunidades reales:
    - Clase 0: LONG (oportunidad alcista con buen R:R)
    - Clase 1: SHORT (oportunidad bajista con buen R:R)
    - Clase 2: NO_TRADE (sin señal clara o alta volatilidad)

    Además calcula TP y SL óptimos para cada señal
    """

    def __init__(self,
                 forward_window: int = 6,  # 6 velas = 24h forward
                 min_reward_risk: float = 2.0,  # R:R mínimo 2:1
                 min_move_pct: float = 0.025,  # Mínimo 2.5% de movimiento
                 atr_multiplier_sl: float = 2.0,  # SL = ATR * 2
                 atr_multiplier_tp: float = 4.0):  # TP objetivo = ATR * 4
        """
        Args:
            forward_window: Ventanas hacia adelante para calcular target (6 = 24h)
            min_reward_risk: Ratio mínimo reward:risk para considerar trade
            min_move_pct: Movimiento mínimo % para considerar señal
            atr_multiplier_sl: Multiplicador de ATR para stop loss
            atr_multiplier_tp: Multiplicador de ATR para take profit objetivo
        """
        self.forward_window = forward_window
        self.min_rr = min_reward_risk
        self.min_move = min_move_pct
        self.atr_sl = atr_multiplier_sl
        self.atr_tp = atr_multiplier_tp

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calcula Average True Range"""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()

        return atr

    def label_trading_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Genera señales de trading con TP/SL

        Args:
            df: DataFrame con columnas 'close', 'high', 'low'

        Returns:
            DataFrame con columnas agregadas:
            - 'signal': 0=LONG, 1=SHORT, 2=NO_TRADE
            - 'tp_price': Precio de take profit
            - 'sl_price': Precio de stop loss
            - 'tp_pct': TP en porcentaje
            - 'sl_pct': SL en porcentaje
            - 'reward_risk': Ratio R:R de la señal
        """
        df = df.copy()

        # Calcular ATR para stop loss
        df['atr'] = self.calculate_atr(df)

        # Calcular métricas forward
        df['forward_return'] = (
            df['close'].shift(-self.forward_window) / df['close'] - 1
        )

        # Máximo y mínimo alcanzado en ventana forward
        df['forward_max'] = (
            df['high'].rolling(self.forward_window).max().shift(-self.forward_window)
        )
        df['forward_min'] = (
            df['low'].rolling(self.forward_window).min().shift(-self.forward_window)
        )

        # Calcular upside y downside potencial
        df['upside_pct'] = (df['forward_max'] / df['close'] - 1)
        df['downside_pct'] = (df['forward_min'] / df['close'] - 1)

        # Volatilidad forward
        df['forward_volatility'] = (
            df['close']
            .pct_change()
            .rolling(self.forward_window)
            .std()
            .shift(-self.forward_window)
        )

        # Calcular TP y SL basados en ATR
        df['atr_pct'] = df['atr'] / df['close']  # ATR normalizado

        # Stop Loss y Take Profit default (basado en ATR)
        df['sl_pct_default'] = -self.atr_sl * df['atr_pct']  # Negativo (pérdida)
        df['tp_pct_default'] = self.atr_tp * df['atr_pct']   # Positivo (ganancia)

        # Inicializar señales
        df['signal'] = 2  # Default: NO_TRADE
        df['tp_pct'] = 0.0
        df['sl_pct'] = 0.0
        df['reward_risk'] = 0.0

        # === SEÑAL LONG ===
        # Condiciones:
        # 1. Upside potencial > min_move
        # 2. Forward return positivo
        # 3. Volatilidad no extrema
        # 4. Reward:Risk > min_rr

        long_candidates = (
            (df['upside_pct'] > self.min_move) &
            (df['forward_return'] > 0) &
            (df['forward_volatility'] < 0.08)  # Volatilidad < 8%
        )

        # Calcular R:R para LONG
        df.loc[long_candidates, 'tp_pct'] = df.loc[long_candidates, 'upside_pct']
        df.loc[long_candidates, 'sl_pct'] = df.loc[long_candidates, 'sl_pct_default']
        df.loc[long_candidates, 'reward_risk'] = (
            df.loc[long_candidates, 'tp_pct'] /
            abs(df.loc[long_candidates, 'sl_pct'])
        )

        # Filtrar por R:R mínimo
        long_mask = long_candidates & (df['reward_risk'] >= self.min_rr)
        df.loc[long_mask, 'signal'] = 0

        # === SEÑAL SHORT ===
        # Condiciones similares pero invertidas

        short_candidates = (
            (df['downside_pct'] < -self.min_move) &
            (df['forward_return'] < 0) &
            (df['forward_volatility'] < 0.08)
        )

        # Calcular R:R para SHORT
        df.loc[short_candidates, 'tp_pct'] = df.loc[short_candidates, 'downside_pct']
        df.loc[short_candidates, 'sl_pct'] = -df.loc[short_candidates, 'sl_pct_default']
        df.loc[short_candidates, 'reward_risk'] = (
            abs(df.loc[short_candidates, 'tp_pct']) /
            abs(df.loc[short_candidates, 'sl_pct'])
        )

        # Filtrar por R:R mínimo
        short_mask = short_candidates & (df['reward_risk'] >= self.min_rr)
        df.loc[short_mask, 'signal'] = 1

        # === CALCULAR PRECIOS ===
        df['tp_price'] = df['close'] * (1 + df['tp_pct'])
        df['sl_price'] = df['close'] * (1 + df['sl_pct'])

        # Limpiar registros sin datos forward
        df.dropna(subset=['forward_return'], inplace=True)

        # Log distribución
        self._log_signal_distribution(df)

        return df

    def _log_signal_distribution(self, df: pd.DataFrame):
        """Log de distribución de señales"""
        counts = df['signal'].value_counts().sort_index()
        percentages = (counts / len(df) * 100).round(2)

        signal_names = {
            0: 'LONG',
            1: 'SHORT',
            2: 'NO_TRADE'
        }

        logger.info("=" * 50)
        logger.info("DISTRIBUCIÓN DE SEÑALES DE TRADING:")
        for signal_id, count in counts.items():
            name = signal_names.get(signal_id, f'Unknown-{signal_id}')
            logger.info(f"  Señal {signal_id} ({name}): {count} ({percentages[signal_id]}%)")

        # Estadísticas de R:R
        for signal_id in [0, 1]:  # LONG y SHORT
            if signal_id in counts.index:
                signal_data = df[df['signal'] == signal_id]
                avg_rr = signal_data['reward_risk'].mean()
                avg_tp = signal_data['tp_pct'].mean() * 100
                avg_sl = signal_data['sl_pct'].mean() * 100
                logger.info(f"  {signal_names[signal_id]} - Avg R:R: {avg_rr:.2f}, "
                          f"Avg TP: {avg_tp:.2f}%, Avg SL: {avg_sl:.2f}%")

        logger.info("=" * 50)


# ============================================================================
# WRAPPER FUNCTION FOR COMPATIBILITY
# ============================================================================

def label_regime_targets(df: pd.DataFrame,
                        n_classes: int = 3,
                        method: str = 'trading_signals',
                        forward_window: int = 6,
                        **kwargs) -> pd.Series:
    """
    Wrapper function to create targets compatible with model_pipeline.py

    Args:
        df: DataFrame with OHLC data (must have 'close', 'high', 'low')
        n_classes: Number of classes (3 for trading_signals, 4 for regime)
        method: 'trading_signals' (default) or 'static' or 'adaptive' or 'volatility_quantiles'
        forward_window: Forward window for target calculation (6 = 24h for 4h candles)
        **kwargs: Additional parameters

    Returns:
        Series with labels:
        - trading_signals: 0=LONG, 1=SHORT, 2=NO_TRADE
        - regime methods: 0=Lateral, 1=Alcista, 2=Bajista, 3=Peligro
    """
    logger.info(f"Creating targets using method: {method}")

    # Validate required columns
    required_cols = ['close', 'high', 'low']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # === NUEVO: TRADING SIGNALS (LONG/SHORT/NO_TRADE) ===
    if method == 'trading_signals':
        signal_labeler = TradingSignalLabeler(
            forward_window=forward_window,
            min_reward_risk=kwargs.get('min_reward_risk', 2.0),
            min_move_pct=kwargs.get('min_move_pct', 0.025),
            atr_multiplier_sl=kwargs.get('atr_multiplier_sl', 2.0),
            atr_multiplier_tp=kwargs.get('atr_multiplier_tp', 4.0)
        )

        df_labeled = signal_labeler.label_trading_signals(df)
        targets = df_labeled['signal']

        # IMPORTANTE: NO copiar tp_pct, sl_pct, reward_risk al DataFrame original
        # Estos valores son calculados con datos futuros (forward-looking)
        # y causarían look-ahead bias si se usan como features del modelo.
        #
        # El flujo correcto es:
        # 1. Usar estos valores SOLO para etiquetar (LONG/SHORT/NO_TRADE)
        # 2. Entrenar modelo SIN estas columnas
        # 3. En producción: Predecir señal → Luego calcular TP/SL con ATR actual

    # === REGIME LABELING (LEGACY) ===
    else:
        labeler = RegimeLabeler(
            forward_window=forward_window,
            volatility_threshold_low=kwargs.get('volatility_threshold_low', 0.015),
            volatility_threshold_high=kwargs.get('volatility_threshold_high', 0.05),
            trend_threshold=kwargs.get('trend_threshold', 0.02)
        )

        if method == 'adaptive':
            df_labeled = labeler.create_adaptive_labels(
                df,
                lookback_period=kwargs.get('lookback_period', 168)
            )
            targets = df_labeled['regime_adaptive']
        elif method == 'volatility_quantiles':
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