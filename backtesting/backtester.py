"""
Backtester - Simulación de Trading con TP/SL

Simula trades reales usando predicciones del modelo:
- Aplica Stop Loss y Take Profit
- Calcula P&L por trade
- Genera estadísticas de trading
- Optimiza TP/SL
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Tuple, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Backtester")


class Trade:
    """Representa un trade individual"""

    def __init__(self, entry_time, entry_price, direction, stop_loss_pct, take_profit_pct, position_size=100):
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.direction = direction  # 1 = LONG, 0 = SHORT
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.position_size = position_size

        # Calcular niveles de TP/SL
        if direction == 1:  # LONG
            self.stop_loss = entry_price * (1 - stop_loss_pct)
            self.take_profit = entry_price * (1 + take_profit_pct)
        else:  # SHORT
            self.stop_loss = entry_price * (1 + stop_loss_pct)
            self.take_profit = entry_price * (1 - take_profit_pct)

        self.exit_time = None
        self.exit_price = None
        self.exit_reason = None
        self.pnl = 0.0
        self.pnl_pct = 0.0
        self.bars_held = 0

    def check_exit(self, current_time, high, low, close):
        """
        Verifica si el trade debe cerrarse (TP o SL).

        Returns:
            (should_exit, exit_price, exit_reason)
        """
        if self.direction == 1:  # LONG
            # Check SL primero (prioridad)
            if low <= self.stop_loss:
                return True, self.stop_loss, 'SL'
            # Check TP
            if high >= self.take_profit:
                return True, self.take_profit, 'TP'
        else:  # SHORT
            # Check SL primero
            if high >= self.stop_loss:
                return True, self.stop_loss, 'SL'
            # Check TP
            if low <= self.take_profit:
                return True, self.take_profit, 'TP'

        return False, None, None

    def close(self, exit_time, exit_price, exit_reason):
        """Cierra el trade y calcula P&L"""
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = exit_reason

        # Calcular P&L
        if self.direction == 1:  # LONG
            self.pnl_pct = (exit_price - self.entry_price) / self.entry_price
        else:  # SHORT
            self.pnl_pct = (self.entry_price - exit_price) / self.entry_price

        self.pnl = self.pnl_pct * self.position_size

        # Calcular barras mantenidas
        self.bars_held = (exit_time - self.entry_time).total_seconds() / 3600  # En horas


class Backtester:
    """
    Backtester que simula trading con TP/SL.
    """

    def __init__(self, stop_loss_pct=0.02, take_profit_pct=0.05, position_size=100, max_positions=1):
        """
        Args:
            stop_loss_pct: Stop loss en % (ej: 0.02 = 2%)
            take_profit_pct: Take profit en % (ej: 0.05 = 5%)
            position_size: Tamaño de posición en USD
            max_positions: Máximo de posiciones simultáneas
        """
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.position_size = position_size
        self.max_positions = max_positions

        self.trades: List[Trade] = []
        self.current_position: Optional[Trade] = None

    def run(self, df: pd.DataFrame, predictions: np.ndarray, probabilities: np.ndarray = None, prediction_threshold=0.65) -> Dict:
        """
        Ejecuta backtesting en un DataFrame.

        Args:
            df: DataFrame con OHLCV data (debe tener: open, high, low, close)
            predictions: Array con predicciones del modelo (0=SHORT, 1=LONG)
            probabilities: Array opcional con probabilidades [prob_class_0, prob_class_1]
            prediction_threshold: Umbral de confianza mínimo (0.5-1.0). Solo opera si probability >= threshold

        Returns:
            Diccionario con resultados del backtesting
        """
        logger.info("🔄 Ejecutando backtesting...")
        if probabilities is not None:
            logger.info(f"   🎯 Threshold de confianza: {prediction_threshold:.2%}")

        self.trades = []
        self.current_position = None

        for i in range(len(df)):
            current_time = df.index[i]
            current_open = df.iloc[i]['open']
            current_high = df.iloc[i]['high']
            current_low = df.iloc[i]['low']
            current_close = df.iloc[i]['close']

            # 1. Check si hay posición abierta y debe cerrarse
            if self.current_position is not None:
                should_exit, exit_price, exit_reason = self.current_position.check_exit(
                    current_time, current_high, current_low, current_close
                )

                if should_exit:
                    self.current_position.close(current_time, exit_price, exit_reason)
                    self.trades.append(self.current_position)
                    self.current_position = None

            # 2. Check si debe abrir nueva posición
            if self.current_position is None and i < len(predictions):
                signal = predictions[i]

                # Verificar confianza si se proporcionaron probabilidades
                should_trade = True
                if probabilities is not None:
                    # probabilities shape: (n_samples, 2) -> [prob_class_0, prob_class_1]
                    max_prob = probabilities[i].max()
                    should_trade = max_prob >= prediction_threshold

                # Abrir posición si hay señal clara Y confianza suficiente
                if signal in [0, 1] and should_trade:
                    self.current_position = Trade(
                        entry_time=current_time,
                        entry_price=current_close,  # Asumimos entrada al cierre
                        direction=signal,
                        stop_loss_pct=self.stop_loss_pct,
                        take_profit_pct=self.take_profit_pct,
                        position_size=self.position_size
                    )

        # Cerrar posición final si quedó abierta
        if self.current_position is not None:
            self.current_position.close(
                df.index[-1],
                df.iloc[-1]['close'],
                'END'
            )
            self.trades.append(self.current_position)

        # Calcular estadísticas
        stats = self.calculate_statistics()

        logger.info(f"✅ Backtesting completado: {len(self.trades)} trades")

        return stats

    def calculate_statistics(self) -> Dict:
        """Calcula estadísticas de trading"""
        if not self.trades:
            return {
                'total_trades': 0,
                'total_pnl': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'max_win': 0,
                'max_loss': 0,
                'avg_bars_held': 0
            }

        # Separar wins y losses
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]

        # Separar por TP y SL
        tp_trades = [t for t in self.trades if t.exit_reason == 'TP']
        sl_trades = [t for t in self.trades if t.exit_reason == 'SL']

        # Calcular estadísticas
        stats = {
            'total_trades': len(self.trades),
            'total_pnl': sum(t.pnl for t in self.trades),
            'total_pnl_pct': sum(t.pnl_pct for t in self.trades) * 100,

            'win_trades': len(wins),
            'loss_trades': len(losses),
            'win_rate': len(wins) / len(self.trades) * 100 if self.trades else 0,

            'avg_win': np.mean([t.pnl for t in wins]) if wins else 0,
            'avg_loss': np.mean([t.pnl for t in losses]) if losses else 0,
            'avg_win_pct': np.mean([t.pnl_pct for t in wins]) * 100 if wins else 0,
            'avg_loss_pct': np.mean([t.pnl_pct for t in losses]) * 100 if losses else 0,

            'max_win': max([t.pnl for t in wins]) if wins else 0,
            'max_loss': min([t.pnl for t in losses]) if losses else 0,
            'max_win_pct': max([t.pnl_pct for t in wins]) * 100 if wins else 0,
            'max_loss_pct': min([t.pnl_pct for t in losses]) * 100 if losses else 0,

            'tp_trades': len(tp_trades),
            'sl_trades': len(sl_trades),
            'tp_rate': len(tp_trades) / len(self.trades) * 100 if self.trades else 0,
            'sl_rate': len(sl_trades) / len(self.trades) * 100 if self.trades else 0,

            'avg_bars_held': np.mean([t.bars_held for t in self.trades]) if self.trades else 0,

            'profit_factor': abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)) if losses and sum(t.pnl for t in losses) != 0 else 0,
        }

        return stats

    def get_trade_history(self) -> pd.DataFrame:
        """Retorna historial de trades como DataFrame"""
        if not self.trades:
            return pd.DataFrame()

        data = []
        for t in self.trades:
            data.append({
                'entry_time': t.entry_time,
                'exit_time': t.exit_time,
                'direction': 'LONG' if t.direction == 1 else 'SHORT',
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'exit_reason': t.exit_reason,
                'pnl': t.pnl,
                'pnl_pct': t.pnl_pct * 100,
                'bars_held': t.bars_held
            })

        return pd.DataFrame(data)

    def print_summary(self, stats: Dict):
        """Imprime resumen de backtesting"""
        print("\n" + "="*70)
        print("📊 BACKTESTING RESULTS")
        print("="*70)

        print(f"\n💼 TRADES:")
        print(f"   Total Trades: {stats['total_trades']}")
        print(f"   Wins: {stats['win_trades']} ({stats['win_rate']:.1f}%)")
        print(f"   Losses: {stats['loss_trades']} ({100-stats['win_rate']:.1f}%)")

        print(f"\n💰 P&L:")
        print(f"   Total P&L: ${stats['total_pnl']:.2f} ({stats['total_pnl_pct']:.2f}%)")
        print(f"   Avg Win: ${stats['avg_win']:.2f} ({stats['avg_win_pct']:.2f}%)")
        print(f"   Avg Loss: ${stats['avg_loss']:.2f} ({stats['avg_loss_pct']:.2f}%)")
        print(f"   Max Win: ${stats['max_win']:.2f} ({stats['max_win_pct']:.2f}%)")
        print(f"   Max Loss: ${stats['max_loss']:.2f} ({stats['max_loss_pct']:.2f}%)")

        print(f"\n🎯 TP/SL:")
        print(f"   TP Hits: {stats['tp_trades']} ({stats['tp_rate']:.1f}%)")
        print(f"   SL Hits: {stats['sl_trades']} ({stats['sl_rate']:.1f}%)")

        print(f"\n📈 METRICS:")
        print(f"   Profit Factor: {stats['profit_factor']:.2f}")
        print(f"   Avg Bars Held: {stats['avg_bars_held']:.1f} horas")

        print("="*70 + "\n")


def optimize_tp_sl(df: pd.DataFrame, predictions: np.ndarray,
                   sl_range=(0.01, 0.05), tp_range=(0.02, 0.10),
                   step=0.005, position_size=100) -> Dict:
    """
    Optimiza TP y SL mediante grid search.

    Args:
        df: DataFrame con OHLCV
        predictions: Predicciones del modelo
        sl_range: Rango de SL a probar (min, max)
        tp_range: Rango de TP a probar (min, max)
        step: Paso para grid search
        position_size: Tamaño de posición

    Returns:
        Mejores parámetros y resultados
    """
    logger.info("🔍 Optimizando TP/SL...")

    best_pnl = -float('inf')
    best_params = None
    best_stats = None

    results = []

    # Grid search
    sl_values = np.arange(sl_range[0], sl_range[1] + step, step)
    tp_values = np.arange(tp_range[0], tp_range[1] + step, step)

    total_combinations = len(sl_values) * len(tp_values)
    logger.info(f"   Probando {total_combinations} combinaciones...")

    for sl in sl_values:
        for tp in tp_values:
            # Validar que TP > SL (risk/reward positivo)
            if tp <= sl:
                continue

            backtester = Backtester(
                stop_loss_pct=sl,
                take_profit_pct=tp,
                position_size=position_size
            )

            stats = backtester.run(df, predictions)

            results.append({
                'sl': sl,
                'tp': tp,
                'total_pnl': stats['total_pnl'],
                'win_rate': stats['win_rate'],
                'total_trades': stats['total_trades'],
                'profit_factor': stats['profit_factor']
            })

            # Actualizar mejor
            if stats['total_pnl'] > best_pnl:
                best_pnl = stats['total_pnl']
                best_params = {'sl': sl, 'tp': tp}
                best_stats = stats

    logger.info(f"✅ Optimización completada")
    logger.info(f"   Mejor SL: {best_params['sl']*100:.1f}%")
    logger.info(f"   Mejor TP: {best_params['tp']*100:.1f}%")
    logger.info(f"   P&L: ${best_pnl:.2f}")

    return {
        'best_params': best_params,
        'best_stats': best_stats,
        'all_results': pd.DataFrame(results)
    }


def optimize_threshold_and_tpsl(df: pd.DataFrame, predictions: np.ndarray, probabilities: np.ndarray,
                                 threshold_range=(0.55, 0.85), sl_range=(0.015, 0.03), tp_range=(0.03, 0.08),
                                 threshold_step=0.05, tpsl_step=0.005, position_size=100) -> Dict:
    """
    Optimiza threshold de confianza + TP/SL mediante grid search.

    Args:
        df: DataFrame con OHLCV
        predictions: Predicciones del modelo (0=SHORT, 1=LONG)
        probabilities: Probabilidades del modelo shape (n_samples, 2)
        threshold_range: Rango de thresholds a probar (min, max)
        sl_range: Rango de SL a probar (min, max)
        tp_range: Rango de TP a probar (min, max)
        threshold_step: Paso para threshold
        tpsl_step: Paso para TP/SL
        position_size: Tamaño de posición

    Returns:
        Mejores parámetros y resultados (threshold, sl, tp)
    """
    logger.info("🔍 Optimizando Threshold + TP/SL...")

    best_win_rate = 0.0
    best_params = None
    best_stats = None
    best_pnl = -float('inf')

    results = []

    # Grid search
    threshold_values = np.arange(threshold_range[0], threshold_range[1] + threshold_step, threshold_step)
    sl_values = np.arange(sl_range[0], sl_range[1] + tpsl_step, tpsl_step)
    tp_values = np.arange(tp_range[0], tp_range[1] + tpsl_step, tpsl_step)

    total_combinations = len(threshold_values) * len(sl_values) * len(tp_values)
    logger.info(f"   Probando {total_combinations} combinaciones...")

    for threshold in threshold_values:
        for sl in sl_values:
            for tp in tp_values:
                # Validar que TP > SL (risk/reward positivo)
                if tp <= sl:
                    continue

                backtester = Backtester(
                    stop_loss_pct=sl,
                    take_profit_pct=tp,
                    position_size=position_size
                )

                stats = backtester.run(df, predictions, probabilities=probabilities, prediction_threshold=threshold)

                # Solo considerar si hay trades suficientes
                if stats['total_trades'] >= 10:
                    results.append({
                        'threshold': threshold,
                        'sl': sl,
                        'tp': tp,
                        'total_pnl': stats['total_pnl'],
                        'win_rate': stats['win_rate'],
                        'total_trades': stats['total_trades'],
                        'profit_factor': stats['profit_factor']
                    })

                    # Criterio: Maximizar win_rate, luego P&L
                    if stats['win_rate'] > best_win_rate or (stats['win_rate'] == best_win_rate and stats['total_pnl'] > best_pnl):
                        best_win_rate = stats['win_rate']
                        best_pnl = stats['total_pnl']
                        best_params = {'threshold': threshold, 'sl': sl, 'tp': tp}
                        best_stats = stats

    if best_params is None:
        logger.warning("⚠️ No se encontraron combinaciones válidas")
        return None

    logger.info(f"✅ Optimización completada")
    logger.info(f"   Mejor Threshold: {best_params['threshold']:.2%}")
    logger.info(f"   Mejor SL: {best_params['sl']*100:.1f}%")
    logger.info(f"   Mejor TP: {best_params['tp']*100:.1f}%")
    logger.info(f"   Win Rate: {best_win_rate:.2%}")
    logger.info(f"   P&L: ${best_pnl:.2f}")

    return {
        'best_params': best_params,
        'best_stats': best_stats,
        'all_results': pd.DataFrame(results)
    }


# --- PRUEBA UNITARIA ---
if __name__ == "__main__":
    logger.info("🧪 Probando Backtester...")

    # Generar datos de prueba
    np.random.seed(42)
    n = 1000

    dates = pd.date_range('2024-01-01', periods=n, freq='1h')

    # Simular precios con tendencia
    trend = np.cumsum(np.random.randn(n) * 10) + 2000

    df_test = pd.DataFrame({
        'open': trend + np.random.randn(n) * 5,
        'high': trend + np.random.randn(n) * 5 + 10,
        'low': trend + np.random.randn(n) * 5 - 10,
        'close': trend + np.random.randn(n) * 5,
    }, index=dates)

    # Generar predicciones aleatorias
    predictions = np.random.choice([0, 1], size=n, p=[0.4, 0.6])

    # Ejecutar backtest
    backtester = Backtester(stop_loss_pct=0.02, take_profit_pct=0.05, position_size=100)
    stats = backtester.run(df_test, predictions)

    # Mostrar resultados
    backtester.print_summary(stats)

    # Mostrar primeros 5 trades
    trade_history = backtester.get_trade_history()
    print("\n📋 Primeros 5 trades:")
    print(trade_history.head())

    print("\n✅ Prueba completada!")
