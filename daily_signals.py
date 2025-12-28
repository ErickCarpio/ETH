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
        self.models = {}  # Cache de modelos por par (multi-model approach)
        self.exchange = None
        self.feature_engineer = None

    def _load_config(self, config_path):
        """Carga configuración"""
        with open(config_path, 'r') as f:
            return json.load(f)

    async def initialize(self):
        """Inicializa exchange y feature engineer (modelos se cargan por demanda)"""
        logger.info("🚀 Inicializando generador de señales...")

        # Inicializar FeatureEngineer
        self.feature_engineer = FeatureEngineer(self.config)
        logger.info("✓ FeatureEngineer inicializado")

        # Inicializar exchange (SPOT para datos)
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        logger.info("✓ Exchange inicializado (SPOT)")
        logger.info("✓ Modelos se cargarán bajo demanda (uno por par)")

    def load_model_for_pair(self, symbol):
        """
        Carga el modelo específico para un par (con caching)

        Args:
            symbol: Símbolo del par (ej: 'ETH/USDT')

        Returns:
            Modelo cargado (o None si no existe)
        """
        # Normalizar símbolo (ETH/USDT → ETHUSDT)
        symbol_clean = symbol.replace('/', '')

        # Si ya está cargado, retornar del cache
        if symbol_clean in self.models:
            return self.models[symbol_clean]

        # Cargar modelo del disco
        model_path = Path(f'models/model_{symbol_clean}.json')

        if not model_path.exists():
            logger.warning(f"⚠️ Modelo no encontrado para {symbol}: {model_path}")
            logger.warning(f"   Entrena el modelo primero con: python train_multiple_pairs.py")
            return None

        try:
            import xgboost as xgb
            model = xgb.XGBClassifier()
            model.load_model(model_path)

            # Guardar en cache
            self.models[symbol_clean] = model

            logger.info(f"✓ Modelo cargado para {symbol}: {model_path}")
            return model

        except Exception as e:
            logger.error(f"❌ Error cargando modelo para {symbol}: {e}")
            return None

    async def get_top_pairs(self, limit=20):
        """Obtiene los pares con modelos entrenados"""
        logger.info(f"📊 Usando pares con modelos entrenados...")

        # Lista de pares que fueron entrenados
        trained_pairs = [
            'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT',
            'DOGE/USDT', 'DOT/USDT', 'LINK/USDT', 'UNI/USDT', 'ATOM/USDT',
            'AVAX/USDT', 'LTC/USDT', 'ETC/USDT', 'FIL/USDT', 'APT/USDT',
            'ARB/USDT', 'OP/USDT', 'INJ/USDT', 'SUI/USDT'
        ]

        # Limitar a los primeros N pares
        selected_pairs = trained_pairs[:limit]

        logger.info(f"✓ {len(selected_pairs)} pares seleccionados: {', '.join(selected_pairs[:5])}...")
        return selected_pairs

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

    def calculate_support_resistance(self, df, lookback=100):
        """
        Identifica niveles de soporte y resistencia basados en:
        - Swing highs/lows
        - Niveles psicológicos (números redondos)
        - Volumen en precio
        """
        try:
            # Tomar últimas N velas
            recent = df.tail(lookback).copy()

            # Identificar swing highs (máximos locales)
            swing_highs = []
            swing_lows = []

            for i in range(2, len(recent) - 2):
                # Swing high: high[i] > high[i-1,i-2,i+1,i+2]
                if (recent['high'].iloc[i] > recent['high'].iloc[i-1] and
                    recent['high'].iloc[i] > recent['high'].iloc[i-2] and
                    recent['high'].iloc[i] > recent['high'].iloc[i+1] and
                    recent['high'].iloc[i] > recent['high'].iloc[i+2]):
                    swing_highs.append(recent['high'].iloc[i])

                # Swing low: low[i] < low[i-1,i-2,i+1,i+2]
                if (recent['low'].iloc[i] < recent['low'].iloc[i-1] and
                    recent['low'].iloc[i] < recent['low'].iloc[i-2] and
                    recent['low'].iloc[i] < recent['low'].iloc[i+1] and
                    recent['low'].iloc[i] < recent['low'].iloc[i+2]):
                    swing_lows.append(recent['low'].iloc[i])

            # Agrupar niveles similares (±0.5%)
            def cluster_levels(levels, tolerance=0.005):
                if not levels:
                    return []
                levels = sorted(levels)
                clusters = []
                current_cluster = [levels[0]]

                for level in levels[1:]:
                    if (level - current_cluster[0]) / current_cluster[0] < tolerance:
                        current_cluster.append(level)
                    else:
                        clusters.append(np.mean(current_cluster))
                        current_cluster = [level]

                clusters.append(np.mean(current_cluster))
                return clusters

            resistance_levels = cluster_levels(swing_highs)
            support_levels = cluster_levels(swing_lows)

            return {
                'resistance': resistance_levels,
                'support': support_levels
            }

        except Exception as e:
            logger.error(f"Error calculando S/R: {e}")
            return {'resistance': [], 'support': []}

    def calculate_entry_levels(self, df, direction, current_price, confidence):
        """
        Calcula niveles de entrada, TP y SL usando PORCENTAJES FIJOS del config.

        IMPORTANTE: Esto es CONSISTENTE con el entrenamiento del modelo.
        El modelo aprendió a predecir movimientos de >2.5% en 12h,
        NO aprendió sobre niveles óptimos de entrada.

        Por lo tanto, usamos:
        - Entrada = precio actual
        - TP = ±take_profit_pct (5%)
        - SL = ∓stop_loss_pct (2%)
        """
        try:
            sl_pct = self.config['trading']['stop_loss_pct']
            tp_pct = self.config['trading']['take_profit_pct']

            entry_options = []

            if direction == 'LONG':
                # SIMPLE: Entry = precio actual, TP/SL = porcentajes fijos
                entry = current_price
                take_profit = current_price * (1 + tp_pct)
                stop_loss = current_price * (1 - sl_pct)

                # Risk:Reward
                potential_gain = take_profit - entry
                potential_loss = entry - stop_loss
                risk_reward = potential_gain / potential_loss

                entry_options.append({
                    'entry': entry,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'probability': confidence,
                    'risk_reward': risk_reward,
                    'expected_value': confidence * risk_reward,
                    'distance_pct': 0.0,  # Entrada inmediata
                    'gain_pct': tp_pct,
                    'loss_pct': sl_pct
                })

            else:  # SHORT
                # SIMPLE: Entry = precio actual, TP/SL = porcentajes fijos
                entry = current_price
                take_profit = current_price * (1 - tp_pct)
                stop_loss = current_price * (1 + sl_pct)

                # Risk:Reward
                potential_gain = entry - take_profit
                potential_loss = stop_loss - entry
                risk_reward = potential_gain / potential_loss

                entry_options.append({
                    'entry': entry,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'probability': confidence,
                    'risk_reward': risk_reward,
                    'expected_value': confidence * risk_reward,
                    'distance_pct': 0.0,  # Entrada inmediata
                    'gain_pct': tp_pct,
                    'loss_pct': sl_pct
                })

            # Ordenar por expected value (mayor a menor)
            entry_options.sort(key=lambda x: x['expected_value'], reverse=True)

            return entry_options

        except Exception as e:
            logger.error(f"Error calculando entry levels: {e}")
            # Fallback a entrada inmediata con TP/SL porcentuales
            if direction == 'LONG':
                entry = current_price
                sl = current_price * (1 - sl_pct)
                tp = current_price * (1 + tp_pct)
                return [{
                    'entry': entry,
                    'stop_loss': sl,
                    'take_profit': tp,
                    'probability': confidence,
                    'risk_reward': tp_pct / sl_pct,
                    'expected_value': confidence * (tp_pct / sl_pct),
                    'distance_pct': 0.0,
                    'gain_pct': tp_pct,
                    'loss_pct': sl_pct
                }]
            else:
                entry = current_price
                sl = current_price * (1 + sl_pct)
                tp = current_price * (1 - tp_pct)
                return [{
                    'entry': entry,
                    'stop_loss': sl,
                    'take_profit': tp,
                    'probability': confidence,
                    'risk_reward': tp_pct / sl_pct,
                    'expected_value': confidence * (tp_pct / sl_pct),
                    'distance_pct': 0.0,
                    'gain_pct': tp_pct,
                    'loss_pct': sl_pct
                }]

    def make_prediction(self, df, current_price, symbol):
        """
        Hace predicción y calcula múltiples opciones de entrada óptimas.
        Retorna la MEJOR opción basada en Expected Value.

        Args:
            df: DataFrame con features
            current_price: Precio actual
            symbol: Símbolo del par (para cargar modelo específico)
        """
        try:
            # Cargar modelo específico del par
            model = self.load_model_for_pair(symbol)

            if model is None:
                logger.error(f"❌ No se pudo cargar modelo para {symbol}")
                return None

            # Tomar última fila
            latest = df.iloc[-1:].copy()

            # Reordenar columnas según modelo
            if hasattr(model, 'feature_names_in_'):
                expected_features = model.feature_names_in_
                missing_cols = [col for col in expected_features if col not in latest.columns]
                if missing_cols:
                    for col in missing_cols:
                        latest[col] = 0.0
                X = latest[expected_features]
            else:
                X = latest

            # Predicción
            pred_class = model.predict(X)[0]
            pred_proba = model.predict_proba(X)[0]

            confidence = pred_proba[pred_class]
            direction = 'LONG' if pred_class == 1 else 'SHORT'

            # Calcular niveles de entrada óptimos (múltiples opciones)
            entry_levels = self.calculate_entry_levels(df, direction, current_price, confidence)

            if not entry_levels:
                return None

            # Tomar la MEJOR opción (mayor expected value)
            best_entry = entry_levels[0]

            # Preparar todas las opciones para guardar
            all_options = []
            for i, option in enumerate(entry_levels[:3], 1):  # Top 3 opciones
                all_options.append({
                    'option': i,
                    'entry': option['entry'],
                    'stop_loss': option['stop_loss'],
                    'take_profit': option['take_profit'],
                    'probability': option['probability'],
                    'expected_value': option['expected_value'],
                    'distance_pct': option['distance_pct']
                })

            return {
                'direction': direction,
                'confidence': confidence,
                'current_price': current_price,
                # Mejor opción (la recomendada)
                'entry': best_entry['entry'],
                'stop_loss': best_entry['stop_loss'],
                'take_profit': best_entry['take_profit'],
                'probability': best_entry['probability'],
                'expected_value': best_entry['expected_value'],
                'distance_pct': best_entry['distance_pct'],
                'risk_reward': best_entry['risk_reward'],
                # Todas las opciones (para CSV)
                'all_entry_options': all_options
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

                # Predicción (con modelo específico del par)
                signal = self.make_prediction(df, current_price, symbol)

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
        """Guarda señales en CSV con múltiples opciones de entrada"""
        if not signals:
            logger.warning("⚠️ No hay señales para guardar")
            return

        if filename is None:
            filename = f"signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        # Guardar CSV principal (mejor opción por señal)
        df_main = pd.DataFrame(signals)

        # Reordenar columnas principales
        main_cols = ['timestamp', 'symbol', 'direction', 'confidence', 'current_price',
                     'entry', 'stop_loss', 'take_profit', 'probability', 'expected_value',
                     'distance_pct', 'risk_reward']
        df_main = df_main[main_cols]

        # Guardar
        output_dir = Path('signals')
        output_dir.mkdir(exist_ok=True)
        filepath = output_dir / filename

        df_main.to_csv(filepath, index=False)
        logger.info(f"✅ Señales guardadas: {filepath}")

        # Guardar CSV con TODAS las opciones de entrada (para análisis detallado)
        all_options = []
        for signal in signals:
            if 'all_entry_options' in signal:
                for option in signal['all_entry_options']:
                    all_options.append({
                        'timestamp': signal['timestamp'],
                        'symbol': signal['symbol'],
                        'direction': signal['direction'],
                        'confidence': signal['confidence'],
                        'current_price': signal['current_price'],
                        'option': option['option'],
                        'entry': option['entry'],
                        'stop_loss': option['stop_loss'],
                        'take_profit': option['take_profit'],
                        'probability': option['probability'],
                        'expected_value': option['expected_value'],
                        'distance_pct': option['distance_pct']
                    })

        if all_options:
            df_all = pd.DataFrame(all_options)
            filepath_all = output_dir / filename.replace('.csv', '_all_options.csv')
            df_all.to_csv(filepath_all, index=False)
            logger.info(f"✅ Todas las opciones guardadas: {filepath_all}")

        # Mostrar resumen
        print("\n" + "="*100)
        print(f"📊 SEÑALES DIARIAS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*100)

        # Filtrar por confianza mínima
        threshold = self.config['trading']['prediction_threshold']
        high_conf = df_main[df_main['confidence'] >= threshold]

        if not high_conf.empty:
            print(f"\n🎯 SEÑALES DE ALTA CONFIANZA (>={threshold:.0%}):\n")
            # Mostrar solo columnas más importantes
            display_cols = ['symbol', 'direction', 'confidence', 'current_price', 'entry',
                           'probability', 'expected_value', 'distance_pct']
            print(high_conf[display_cols].to_string(index=False))

            print("\n📝 NOTA: Usa 'distance_pct' para ver cuánto debe bajar/subir el precio para entrada óptima")
            print("📝 'probability' = probabilidad de que llegue a ese precio")
            print("📝 'expected_value' = Probability × Risk:Reward (mayor es mejor)")
        else:
            print(f"\n⚠️ No hay señales con confianza >= {threshold:.0%}")

        print(f"\n📈 RESUMEN DE TODAS LAS SEÑALES ({len(df_main)}):")
        summary_cols = ['symbol', 'direction', 'confidence', 'expected_value']
        print(df_main[summary_cols].to_string(index=False))

        print("\n" + "="*100)
        print(f"📁 Archivos guardados:")
        print(f"  - Mejores entradas: {filepath}")
        if all_options:
            print(f"  - Todas las opciones: {filepath_all}")
        print("="*100 + "\n")

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
