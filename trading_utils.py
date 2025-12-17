"""
Trading Utilities - Cálculo de TP/SL en Tiempo Real
====================================================

Funciones para calcular Take Profit y Stop Loss DESPUÉS de la predicción,
sin mirar hacia el futuro (sin look-ahead bias).
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Calcula Average True Range actual (última vela)

    Args:
        df: DataFrame con 'high', 'low', 'close'
        period: Período para ATR

    Returns:
        ATR actual (float)
    """
    if len(df) < period:
        logger.warning(f"Not enough data for ATR calculation (need {period}, got {len(df)})")
        return df['close'].iloc[-1] * 0.02  # Fallback: 2% del precio

    high = df['high']
    low = df['low']
    close = df['close']

    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]

    return float(atr)


def calculate_tp_sl_realtime(
    signal: int,
    current_price: float,
    df_history: pd.DataFrame,
    atr_multiplier_sl: float = 2.0,
    atr_multiplier_tp: float = 4.0,
    min_rr: float = 2.0
) -> Tuple[Optional[float], Optional[float], float]:
    """
    Calcula TP y SL en tiempo real DESPUÉS de la predicción.

    NO usa datos futuros - solo ATR y precio actual.

    Args:
        signal: 0=LONG, 1=SHORT, 2=NO_TRADE
        current_price: Precio actual
        df_history: DataFrame histórico con 'high', 'low', 'close'
        atr_multiplier_sl: Multiplicador de ATR para stop loss
        atr_multiplier_tp: Multiplicador de ATR para take profit
        min_rr: Ratio mínimo reward:risk

    Returns:
        (tp_price, sl_price, reward_risk)
        - Si signal=2 (NO_TRADE): (None, None, 0.0)
    """
    # NO_TRADE → Sin TP/SL
    if signal == 2:
        return None, None, 0.0

    # Calcular ATR actual
    atr = calculate_atr(df_history)
    atr_pct = atr / current_price

    # === LONG ===
    if signal == 0:
        # SL: Precio actual - (ATR * multiplicador)
        sl_pct = -atr_multiplier_sl * atr_pct
        sl_price = current_price * (1 + sl_pct)

        # TP: Precio actual + (ATR * multiplicador)
        tp_pct = atr_multiplier_tp * atr_pct
        tp_price = current_price * (1 + tp_pct)

        # Verificar R:R
        reward = tp_price - current_price
        risk = current_price - sl_price
        rr = reward / risk if risk > 0 else 0

        # Si R:R es muy bajo, ajustar TP hacia arriba
        if rr < min_rr and risk > 0:
            tp_price = current_price + (risk * min_rr)
            rr = min_rr

        logger.info(f"LONG @ {current_price:.2f} | TP: {tp_price:.2f} (+{tp_pct*100:.2f}%) | "
                   f"SL: {sl_price:.2f} ({sl_pct*100:.2f}%) | R:R: {rr:.2f}")

        return tp_price, sl_price, rr

    # === SHORT ===
    elif signal == 1:
        # SL: Precio actual + (ATR * multiplicador)
        sl_pct = atr_multiplier_sl * atr_pct
        sl_price = current_price * (1 + sl_pct)

        # TP: Precio actual - (ATR * multiplicador)
        tp_pct = -atr_multiplier_tp * atr_pct
        tp_price = current_price * (1 + tp_pct)

        # Verificar R:R
        reward = current_price - tp_price
        risk = sl_price - current_price
        rr = reward / risk if risk > 0 else 0

        # Si R:R es muy bajo, ajustar TP hacia abajo
        if rr < min_rr and risk > 0:
            tp_price = current_price - (risk * min_rr)
            rr = min_rr

        logger.info(f"SHORT @ {current_price:.2f} | TP: {tp_price:.2f} ({tp_pct*100:.2f}%) | "
                   f"SL: {sl_price:.2f} (+{sl_pct*100:.2f}%) | R:R: {rr:.2f}")

        return tp_price, sl_price, rr

    # Señal desconocida
    return None, None, 0.0


def calculate_position_size(
    signal: int,
    capital: float,
    current_price: float,
    sl_price: float,
    risk_per_trade: float = 0.02,
    max_position_pct: float = 0.10
) -> float:
    """
    Calcula tamaño de posición basado en riesgo por trade.

    Args:
        signal: 0=LONG, 1=SHORT, 2=NO_TRADE
        capital: Capital total disponible
        current_price: Precio de entrada
        sl_price: Precio de stop loss
        risk_per_trade: % de capital a arriesgar por trade (default 2%)
        max_position_pct: % máximo de capital en una posición (default 10%)

    Returns:
        Tamaño de posición en unidades del activo
    """
    if signal == 2 or sl_price is None:
        return 0.0

    # Calcular riesgo por unidad
    if signal == 0:  # LONG
        risk_per_unit = current_price - sl_price
    else:  # SHORT
        risk_per_unit = sl_price - current_price

    if risk_per_unit <= 0:
        logger.warning("Invalid risk calculation - risk_per_unit <= 0")
        return 0.0

    # Capital a arriesgar
    risk_amount = capital * risk_per_trade

    # Posición basada en riesgo
    position_size = risk_amount / risk_per_unit

    # Limitar por % máximo de capital
    max_position_size = (capital * max_position_pct) / current_price
    position_size = min(position_size, max_position_size)

    logger.info(f"Position sizing: ${capital:.2f} capital, {risk_per_trade*100:.1f}% risk "
               f"→ {position_size:.4f} units (${position_size * current_price:.2f})")

    return position_size


# ============================================================================
# EJEMPLO DE USO EN PRODUCCIÓN
# ============================================================================

if __name__ == "__main__":
    # Simulación de uso en producción

    # 1. El modelo predice una señal
    predicted_signal = 0  # LONG

    # 2. Precio actual del mercado
    current_price = 3500.0

    # 3. Datos históricos (últimas N velas)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='4H')
    prices = np.random.randn(100).cumsum() + 3500
    df_history = pd.DataFrame({
        'close': prices,
        'high': prices * 1.01,
        'low': prices * 0.99
    }, index=dates)

    # 4. Calcular TP/SL en tiempo real (SIN mirar futuro)
    tp, sl, rr = calculate_tp_sl_realtime(
        signal=predicted_signal,
        current_price=current_price,
        df_history=df_history,
        atr_multiplier_sl=2.0,
        atr_multiplier_tp=4.0,
        min_rr=2.0
    )

    print(f"\n{'='*60}")
    print(f"SEÑAL: {'LONG' if predicted_signal == 0 else 'SHORT'}")
    print(f"Precio entrada: ${current_price:.2f}")
    print(f"Take Profit: ${tp:.2f}")
    print(f"Stop Loss: ${sl:.2f}")
    print(f"Reward:Risk: {rr:.2f}:1")
    print(f"{'='*60}")

    # 5. Calcular tamaño de posición
    capital = 10000.0
    position_size = calculate_position_size(
        signal=predicted_signal,
        capital=capital,
        current_price=current_price,
        sl_price=sl,
        risk_per_trade=0.02,  # Arriesgar 2% del capital
        max_position_pct=0.10  # Máximo 10% del capital en la posición
    )

    print(f"\nCapital: ${capital:.2f}")
    print(f"Posición: {position_size:.4f} ETH (${position_size * current_price:.2f})")
    print(f"Riesgo: ${abs(position_size * (current_price - sl)):.2f} ({abs(position_size * (current_price - sl)) / capital * 100:.2f}% del capital)")
