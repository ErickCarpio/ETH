"""
Paper Trading Bot - Opera en modo simulado con datos en vivo
Guarda trades en logs/trades_history.csv para visualización en dashboard
"""

import pandas as pd
import numpy as np
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Importar componentes del sistema
sys.path.append(str(Path(__file__).parent))
from data.cache.cache_manager import CacheManager
from data.fetchers.binance_fetcher import fetch_ohlcv_binance
from feature_engineering.feature_engineering import FeatureEngineering
from xgboost import XGBClassifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PaperTradingBot:
    """Bot de trading simulado en tiempo real"""

    def __init__(self, config_path='config_15min.json'):
        """Inicializar bot"""
        logger.info("🤖 Inicializando Paper Trading Bot...")

        # Cargar config
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.symbol = self.config['data']['symbol']
        self.timeframe = self.config['data']['timeframe']
        self.position_size = self.config['trading']['position_size_usd']
        self.threshold = self.config['trading']['prediction_threshold']
        self.sl_pct = self.config['trading']['stop_loss_pct']
        self.tp_pct = self.config['trading']['take_profit_pct']

        # Estado
        self.cache_mgr = CacheManager()
        self.model = None
        self.feature_eng = FeatureEngineering()
        self.current_position = None
        self.trades_history = []
        self.balance = 10000  # Balance inicial simulado
        self.equity_curve = [self.balance]

        # Cargar modelo
        self.load_model()

        logger.info(f"✓ Symbol: {self.symbol}")
        logger.info(f"✓ Timeframe: {self.timeframe}")
        logger.info(f"✓ Threshold: {self.threshold:.0%}")
        logger.info(f"✓ SL: {self.sl_pct:.1%} | TP: {self.tp_pct:.1%}")
        logger.info(f"✓ Balance inicial: ${self.balance:.2f}")

    def load_model(self):
        """Cargar modelo entrenado"""
        model_path = Path('models/xgboost_model.json')
        if not model_path.exists():
            logger.error("❌ Modelo no encontrado. Ejecuta model_pipeline_complete.py primero.")
            sys.exit(1)

        self.model = XGBClassifier()
        self.model.load_model(str(model_path))
        logger.info("✓ Modelo cargado exitosamente")

    def fetch_latest_data(self, lookback_bars=200):
        """Descargar últimos datos de Binance"""
        try:
            df = fetch_ohlcv_binance(
                self.symbol,
                self.timeframe,
                limit=lookback_bars
            )
            return df
        except Exception as e:
            logger.error(f"Error descargando datos: {e}")
            return None

    def generate_features(self, df):
        """Generar features para predicción"""
        try:
            df_features = self.feature_eng.build_features(df)
            return df_features
        except Exception as e:
            logger.error(f"Error generando features: {e}")
            return None

    def check_position_exit(self, current_price):
        """Verificar si la posición debe cerrarse"""
        if self.current_position is None:
            return False

        direction = self.current_position['direction']
        entry_price = self.current_position['entry_price']

        if direction == 'LONG':
            pnl_pct = (current_price - entry_price) / entry_price
            # Check TP
            if pnl_pct >= self.tp_pct:
                self.close_position(current_price, 'TP')
                return True
            # Check SL
            if pnl_pct <= -self.sl_pct:
                self.close_position(current_price, 'SL')
                return True
        else:  # SHORT
            pnl_pct = (entry_price - current_price) / entry_price
            # Check TP
            if pnl_pct >= self.tp_pct:
                self.close_position(current_price, 'TP')
                return True
            # Check SL
            if pnl_pct <= -self.sl_pct:
                self.close_position(current_price, 'SL')
                return True

        return False

    def open_position(self, direction, price, confidence):
        """Abrir nueva posición"""
        self.current_position = {
            'direction': direction,
            'entry_price': price,
            'entry_time': datetime.now(),
            'confidence': confidence,
            'size': self.position_size
        }
        logger.info(f"📈 {direction} abierto @ ${price:.2f} (confianza: {confidence:.1%})")

    def close_position(self, price, reason):
        """Cerrar posición actual"""
        if self.current_position is None:
            return

        direction = self.current_position['direction']
        entry_price = self.current_position['entry_price']
        entry_time = self.current_position['entry_time']

        # Calcular P&L
        if direction == 'LONG':
            pnl_pct = (price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - price) / entry_price

        pnl_usd = self.position_size * pnl_pct
        self.balance += pnl_usd
        self.equity_curve.append(self.balance)

        # Registrar trade
        trade = {
            'entry_time': entry_time,
            'exit_time': datetime.now(),
            'direction': direction,
            'entry_price': entry_price,
            'exit_price': price,
            'pnl_pct': pnl_pct * 100,
            'exit_reason': reason
        }
        self.trades_history.append(trade)

        logger.info(f"📉 {direction} cerrado @ ${price:.2f} | {reason} | P&L: {pnl_pct:+.2%} (${pnl_usd:+.2f})")
        logger.info(f"💰 Balance: ${self.balance:.2f}")

        # Guardar en CSV
        self.save_trades_to_csv()

        self.current_position = None

    def save_trades_to_csv(self):
        """Guardar historial de trades en CSV"""
        if not self.trades_history:
            return

        df = pd.DataFrame(self.trades_history)
        Path('logs').mkdir(exist_ok=True)
        df.to_csv('logs/trades_history.csv', index=False)

    def run(self, interval_seconds=60):
        """
        Ejecutar bot en loop continuo

        Args:
            interval_seconds: Segundos entre cada iteración
        """
        logger.info("🚀 Paper Trading Bot iniciado")
        logger.info(f"⏱️ Comprobando mercado cada {interval_seconds}s")
        logger.info("Presiona Ctrl+C para detener\n")

        iteration = 0

        try:
            while True:
                iteration += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"🔄 Iteración #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"{'='*60}")

                # 1. Descargar datos
                df = self.fetch_latest_data()
                if df is None or df.empty:
                    logger.warning("⚠️ No se pudieron obtener datos. Reintentando...")
                    time.sleep(interval_seconds)
                    continue

                current_price = df.iloc[-1]['close']
                logger.info(f"📊 Precio actual: ${current_price:.2f}")

                # 2. Verificar si debe cerrar posición existente
                if self.current_position is not None:
                    logger.info(f"📍 Posición activa: {self.current_position['direction']} @ ${self.current_position['entry_price']:.2f}")
                    self.check_position_exit(current_price)

                # 3. Si no hay posición, buscar señal
                if self.current_position is None:
                    # Generar features
                    df_features = self.generate_features(df)
                    if df_features is None or df_features.empty:
                        logger.warning("⚠️ Error generando features")
                        time.sleep(interval_seconds)
                        continue

                    # Obtener última fila de features
                    X = df_features.iloc[-1:].select_dtypes(include=[np.number])

                    # Hacer predicción
                    prediction = self.model.predict(X)[0]
                    probabilities = self.model.predict_proba(X)[0]
                    confidence = probabilities.max()

                    logger.info(f"🔮 Señal: {prediction} (confianza: {confidence:.1%})")

                    # Abrir posición si confianza > threshold
                    if confidence >= self.threshold:
                        direction = 'LONG' if prediction == 1 else 'SHORT'
                        self.open_position(direction, current_price, confidence)
                    else:
                        logger.info("⏸️ Sin señal clara (confianza insuficiente)")
                else:
                    logger.info("⏸️ Esperando salida de posición actual")

                # Estadísticas
                if self.trades_history:
                    wins = sum(1 for t in self.trades_history if t['pnl_pct'] > 0)
                    total = len(self.trades_history)
                    win_rate = wins / total * 100
                    total_pnl = sum(t['pnl_pct'] for t in self.trades_history)

                    logger.info(f"\n📊 Estadísticas:")
                    logger.info(f"   Trades: {total} | Win Rate: {win_rate:.1f}% ({wins}W/{total-wins}L)")
                    logger.info(f"   P&L Total: {total_pnl:+.2f}%")
                    logger.info(f"   Balance: ${self.balance:.2f}")

                # Esperar hasta próxima iteración
                logger.info(f"\n⏳ Esperando {interval_seconds}s hasta próxima comprobación...")
                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("\n\n⏹️ Bot detenido por el usuario")
            if self.current_position is not None:
                logger.info("⚠️ Cerrando posición abierta...")
                self.close_position(current_price, 'MANUAL')

            # Resumen final
            if self.trades_history:
                logger.info(f"\n{'='*60}")
                logger.info("📊 RESUMEN FINAL")
                logger.info(f"{'='*60}")
                logger.info(f"Total trades: {len(self.trades_history)}")
                wins = sum(1 for t in self.trades_history if t['pnl_pct'] > 0)
                logger.info(f"Win rate: {wins/len(self.trades_history)*100:.1f}%")
                logger.info(f"Balance final: ${self.balance:.2f}")
                logger.info(f"P&L total: ${self.balance - 10000:+.2f}")

        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}", exc_info=True)


if __name__ == '__main__':
    # Crear y ejecutar bot
    bot = PaperTradingBot()

    # Ejecutar con comprobación cada 60 segundos
    # Para 1h timeframe, puedes aumentar a 300s (5 min) o 600s (10 min)
    bot.run(interval_seconds=60)
