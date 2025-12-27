#!/usr/bin/env python3
"""
Daily Trading Signals Generator
Genera señales diarias para múltiples pares de criptomonedas
"""

import asyncio
import pandas as pd
import numpy as np
import json
import logging
from datetime import datetime
from pathlib import Path
import ccxt.async_support as ccxt
import joblib

from feature_engineering import FeatureEngineer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DailySignalsGenerator:
    """Genera señales de trading diarias para múltiples pares"""

    def __init__(self, config_path='config_15min.json'):
        self.config = self._load_config(config_path)
        self.model = None
        self.exchange = None
        self.feature_engineer = None

    def _load_config(self, config_path):
        """Carga configuración"""
        with open(config_path, 'r') as f:
            return json.load(f)

    async def initialize(self):
        """Inicializa exchange, modelo y feature engineer"""
        logger.info("🚀 Inicializando generador de señales...")

        # Cargar modelo
        model_path = self.config.get('model_path', 'models/xgboost_model.pkl')
        self.model = joblib.load(model_path)
        logger.info(f"✓ Modelo cargado: {model_path}")

        # Inicializar FeatureEngineer
        self.feature_engineer = FeatureEngineer(self.config)
        logger.info("✓ FeatureEngineer inicializado")

        # Inicializar exchange (demo para obtener datos)
        self.exchange = ccxt.binanceusdm({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        logger.info("✓ Exchange inicializado")

    async def get_top_pairs(self, limit=20):
        """Obtiene los top N pares por volumen de Binance Futures"""
        logger.info(f"📊 Obteniendo top {limit} pares por volumen...")

        try:
            markets = await self.exchange.load_markets()
            futures_markets = [
                market for market in markets.values()
                if market['type'] == 'future' and market['quote'] == 'USDT' and market['active']
            ]

            # Obtener tickers para volumen
            tickers = await self.exchange.fetch_tickers()

            # Filtrar y ordenar por volumen
            pairs_with_volume = []
            for market in futures_markets:
                symbol = market['symbol']
                if symbol in tickers and tickers[symbol].get('quoteVolume'):
                    pairs_with_volume.append({
                        'symbol': symbol,
                        'volume': tickers[symbol]['quoteVolume']
                    })

            # Ordenar por volumen descendente
            pairs_with_volume.sort(key=lambda x: x['volume'], reverse=True)

            # Tomar top N
            top_pairs = [p['symbol'] for p in pairs_with_volume[:limit]]

            logger.info(f"✓ Top {len(top_pairs)} pares: {', '.join(top_pairs[:5])}...")
            return top_pairs

        except Exception as e:
            logger.error(f"Error obteniendo pares: {e}")
            # Fallback a pares conocidos
            return [
                'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
                'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT', 'MATIC/USDT', 'DOT/USDT',
                'UNI/USDT', 'LINK/USDT', 'ATOM/USDT', 'LTC/USDT', 'BCH/USDT',
                'NEAR/USDT', 'APT/USDT', 'ARB/USDT', 'OP/USDT', 'FIL/USDT'
            ]

    async def fetch_pair_data(self, symbol, timeframe='1h', limit=350):
        """Descarga datos históricos para un par"""
        try:
            # Datos de 1h
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            # Datos de 4h para macro features
            ohlcv_4h = await self.exchange.fetch_ohlcv(symbol, '4h', limit=200)
            df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms')
            df_4h.set_index('timestamp', inplace=True)

            return df, df_4h

        except Exception as e:
            logger.error(f"Error descargando datos para {symbol}: {e}")
            return pd.DataFrame(), pd.DataFrame()

    def calculate_features(self, df, df_4h):
        """Calcula features usando el FeatureEngineer"""
        try:
            # Technical features
            df = self.feature_engineer.create_technical_features(df, timeframe='15m')

            # Macro features de 4h
            if df_4h is not None and not df_4h.empty:
                df = self.feature_engineer.add_4h_macro_features(df, df_4h)

            # Statistical features
            if hasattr(self.feature_engineer, 'statistical_engine') and self.feature_engineer.statistical_engine:
                df = self.feature_engineer.statistical_engine.compute_all_features(df, price_col='close')

            # Features externas (fallback a 0 si no existen)
            required_external_features = [
                'funding_rate', 'open_interest_norm', 'oi_change',
                'Net_Flow_Z', 'BTCDOM_ROC', 'FinBERT_Score',
                'stablecoin_mcap', 'stablecoin_flow_7d', 'stablecoin_trend'
            ]

            for feature in required_external_features:
                if feature not in df.columns:
                    df[feature] = 0.0

            # Forward fill
            df = df.ffill()

            return df.dropna()

        except Exception as e:
            logger.error(f"Error calculando features: {e}")
            return pd.DataFrame()

    def make_prediction(self, df, current_price):
        """Hace predicción y calcula entrada, TP, SL"""
        try:
            # Tomar última fila
            latest = df.iloc[-1:].copy()

            # Reordenar columnas según modelo
            if hasattr(self.model, 'feature_names_in_'):
                expected_features = self.model.feature_names_in_
                missing_cols = [col for col in expected_features if col not in latest.columns]
                if missing_cols:
                    for col in missing_cols:
                        latest[col] = 0.0
                X = latest[expected_features]
            else:
                X = latest

            # Predicción
            pred_class = self.model.predict(X)[0]
            pred_proba = self.model.predict_proba(X)[0]

            confidence = pred_proba[pred_class]
            direction = 'LONG' if pred_class == 1 else 'SHORT'

            # Calcular TP y SL
            sl_pct = self.config['trading']['stop_loss_pct']
            tp_pct = self.config['trading']['take_profit_pct']

            if direction == 'LONG':
                entry = current_price
                stop_loss = entry * (1 - sl_pct)
                take_profit = entry * (1 + tp_pct)
            else:  # SHORT
                entry = current_price
                stop_loss = entry * (1 + sl_pct)
                take_profit = entry * (1 - tp_pct)

            return {
                'direction': direction,
                'confidence': confidence,
                'entry': entry,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk_reward': tp_pct / sl_pct
            }

        except Exception as e:
            logger.error(f"Error en predicción: {e}")
            return None

    async def generate_signals(self, pairs):
        """Genera señales para todos los pares"""
        signals = []

        logger.info(f"📊 Generando señales para {len(pairs)} pares...")

        for i, symbol in enumerate(pairs, 1):
            try:
                logger.info(f"[{i}/{len(pairs)}] Analizando {symbol}...")

                # Descargar datos
                df, df_4h = await self.fetch_pair_data(symbol)

                if df.empty:
                    logger.warning(f"⚠️ Sin datos para {symbol}, saltando...")
                    continue

                # Calcular features
                df = self.calculate_features(df, df_4h)

                if df.empty:
                    logger.warning(f"⚠️ Features vacías para {symbol}, saltando...")
                    continue

                # Precio actual
                current_price = df['close'].iloc[-1]

                # Predicción
                signal = self.make_prediction(df, current_price)

                if signal:
                    signal['symbol'] = symbol
                    signal['current_price'] = current_price
                    signal['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    signals.append(signal)

                    logger.info(
                        f"  ✓ {symbol}: {signal['direction']} "
                        f"(Confianza: {signal['confidence']:.1%}, "
                        f"Precio: ${current_price:.2f})"
                    )

                # Rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error procesando {symbol}: {e}")
                continue

        return signals

    def save_signals(self, signals, filename=None):
        """Guarda señales en CSV"""
        if not signals:
            logger.warning("⚠️ No hay señales para guardar")
            return

        if filename is None:
            filename = f"signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        df = pd.DataFrame(signals)

        # Reordenar columnas
        cols = ['timestamp', 'symbol', 'direction', 'confidence', 'current_price',
                'entry', 'stop_loss', 'take_profit', 'risk_reward']
        df = df[cols]

        # Guardar
        output_dir = Path('signals')
        output_dir.mkdir(exist_ok=True)
        filepath = output_dir / filename

        df.to_csv(filepath, index=False)
        logger.info(f"✅ Señales guardadas: {filepath}")

        # Mostrar resumen
        print("\n" + "="*80)
        print(f"📊 SEÑALES DIARIAS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)

        # Filtrar por confianza mínima
        threshold = self.config['trading']['prediction_threshold']
        high_conf = df[df['confidence'] >= threshold]

        if not high_conf.empty:
            print(f"\n🎯 SEÑALES DE ALTA CONFIANZA (>={threshold:.0%}):")
            print(high_conf.to_string(index=False))
        else:
            print(f"\n⚠️ No hay señales con confianza >= {threshold:.0%}")

        print(f"\n📈 TODAS LAS SEÑALES ({len(df)}):")
        print(df.to_string(index=False))

        print("\n" + "="*80)
        print(f"📁 Archivo guardado: {filepath}")
        print("="*80 + "\n")

    async def run(self, num_pairs=20):
        """Ejecuta el generador de señales"""
        try:
            await self.initialize()

            # Obtener top pares
            pairs = await self.get_top_pairs(limit=num_pairs)

            # Generar señales
            signals = await self.generate_signals(pairs)

            # Guardar y mostrar
            self.save_signals(signals)

        except Exception as e:
            logger.error(f"Error en ejecución: {e}")
            import traceback
            traceback.print_exc()

        finally:
            if self.exchange:
                await self.exchange.close()


async def main():
    """Función principal"""
    import argparse

    parser = argparse.ArgumentParser(description='Generador de señales diarias de trading')
    parser.add_argument('--pairs', type=int, default=20, help='Número de pares a analizar (default: 20)')
    parser.add_argument('--config', type=str, default='config_15min.json', help='Archivo de configuración')

    args = parser.parse_args()

    generator = DailySignalsGenerator(config_path=args.config)
    await generator.run(num_pairs=args.pairs)


if __name__ == "__main__":
    asyncio.run(main())
