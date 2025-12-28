"""
Dashboard Web para Trading Bot - Visualización en Tiempo Real
Ejecutar con: streamlit run web_dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
from pathlib import Path
import time
from datetime import datetime, timedelta
import numpy as np
import sys
import threading
import asyncio
import xgboost as xgb
import ccxt.async_support as ccxt
import logging

# Añadir path para importar CacheManager y FeatureEngineer
sys.path.append(str(Path(__file__).parent))
from data.cache.cache_manager import CacheManager
from feature_engineering import FeatureEngineer

# Inicializar CacheManager
cache_mgr = CacheManager()

# Configurar logging
from pathlib import Path
Path('logs').mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuración de página
st.set_page_config(
    page_title="ETH Trading Bot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .profit { color: #27AE60; font-weight: bold; }
    .loss { color: #E74C3C; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# =================== IMPORTAR COMPONENTES ===================

# Importar paneles de components/
try:
    from components.training_panel import render_training_panel
    from components.signals_panel import render_signals_panel
    from components.models_panel import render_models_panel
    from components.backtest_panel import render_backtest_panel
    _panels_loaded = True
    _panels_error = None
except Exception as e:
    _panels_loaded = False
    _panels_error = str(e)
    import traceback
    _panels_traceback = traceback.format_exc()

# =================== TRADING BOT CLASS ===================

class LiveTradingBot:
    """Bot de trading en vivo con ML predictions y ejecución en Binance Testnet"""

    def __init__(self, config_path='config_15min.json'):
        self.config = self._load_config(config_path)
        self.model = None
        self.exchange = None
        self.is_running = False
        self.current_position = None
        self.trades_file = Path('logs/live_trades.csv')
        self.trades_file.parent.mkdir(exist_ok=True)

        # Inicializar FeatureEngineer con config completo
        self.feature_engineer = FeatureEngineer(self.config)

    def _load_config(self, path):
        """Carga configuración"""
        with open(path, 'r') as f:
            return json.load(f)

    def load_model(self):
        """Carga modelo XGBoost"""
        try:
            model_path = Path('models/xgboost_model.json')
            if not model_path.exists():
                raise FileNotFoundError("Modelo no encontrado. Ejecuta primero: python model_pipeline_complete.py")

            self.model = xgb.XGBClassifier()
            self.model.load_model(str(model_path))
            logger.info("✓ Modelo cargado exitosamente")
            return True
        except Exception as e:
            logger.error(f"Error cargando modelo: {e}")
            return False

    async def initialize_exchange(self):
        """Inicializa conexión con Binance (Testnet, Paper Trading o Real)"""
        try:
            exchange_config = self.config['exchange']
            trading_config = self.config['trading']

            # Determinar modo de operación
            is_testnet = exchange_config.get('testnet', True)
            is_paper_trading = exchange_config.get('paper_trading', False)

            # MODO 1: PAPER TRADING (Simulación Local)
            if is_paper_trading:
                logger.info("🖥️ Modo PAPER TRADING (Simulación Local - Sin Riesgo)")
                logger.info("   Los trades se simulan localmente sin conectar a Binance")

                # Conectar solo para obtener datos de mercado (sin API keys)
                self.exchange = ccxt.binance({
                    'enableRateLimit': True,
                    'options': {'defaultType': 'future'}
                })

                await self.exchange.load_markets()
                logger.info("✓ Conectado a Binance (solo lectura de precios)")

                # Simular balance
                self.simulated_balance = 10000.0  # $10,000 simulados
                logger.info(f"✓ Balance Simulado: ${self.simulated_balance:.2f}")

            # MODO 2: DEMO BINANCE (Dinero Ficticio de Binance)
            elif is_testnet:
                logger.info("🧪 Modo DEMO BINANCE (Dinero Ficticio - Sin Riesgo)")
                logger.info("   Conectando a demo.binance.com")

                testnet_api_key = exchange_config.get('testnet_api_key', '').strip()
                testnet_api_secret = exchange_config.get('testnet_api_secret', '').strip()

                if not testnet_api_key or not testnet_api_secret:
                    raise ValueError(
                        "❌ API keys de Demo no configuradas.\n"
                        "   1. Ve a: https://demo.binance.com\n"
                        "   2. API Management → Create API Key\n"
                        "   3. Copia las keys a config_15min.json (testnet_api_key, testnet_api_secret)"
                    )

                # Usar binanceusdm para USDT-Margined Futures con modo demo/sandbox
                # Documentación: https://github.com/ccxt/ccxt/wiki/Manual#sandbox-mode
                self.exchange = ccxt.binanceusdm({
                    'apiKey': testnet_api_key,
                    'secret': testnet_api_secret,
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'future',
                        'adjustForTimeDifference': True,  # Sincroniza reloj local con servidor
                    }
                })

                # Activar modo sandbox/demo
                self.exchange.set_sandbox_mode(True)

                # CRÍTICO: Sobrescribir URLs explícitamente
                # Las versiones de CCXT pueden tener URLs obsoletas del antiguo testnet
                # Forzamos el enrutamiento a demo-fapi.binance.com según doc oficial:
                # https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
                new_testnet_urls = {
                    'fapiPublic': 'https://demo-fapi.binance.com/fapi/v1',
                    'fapiPrivate': 'https://demo-fapi.binance.com/fapi/v1',
                    'fapiPublicV2': 'https://demo-fapi.binance.com/fapi/v2',
                    'fapiPrivateV2': 'https://demo-fapi.binance.com/fapi/v2',
                    'fapiPublicV3': 'https://demo-fapi.binance.com/fapi/v3',
                    'fapiPrivateV3': 'https://demo-fapi.binance.com/fapi/v3',
                    'public': 'https://demo-fapi.binance.com/fapi/v1',
                    'private': 'https://demo-fapi.binance.com/fapi/v1',
                }
                self.exchange.urls['api'] = new_testnet_urls

                logger.info("✓ Conectado a Binance Demo Trading (demo-fapi.binance.com)")

                # Verificar balance
                try:
                    balance = await self.exchange.fetch_balance()
                    usdt_balance = balance.get('USDT', {}).get('free', 0)
                    logger.info(f"✓ Balance Demo USDT: ${usdt_balance:.2f}")
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo verificar balance: {e}")

                # Configurar LEVERAGE y MARGIN MODE
                symbol = exchange_config.get('symbol', 'ETHUSDT')
                leverage = trading_config.get('leverage', 1)
                margin_mode = trading_config.get('margin_mode', 'ISOLATED')

                try:
                    # Establecer modo de margen
                    await self.exchange.fapiPrivate_post_margintype({
                        'symbol': symbol.replace('/', ''),
                        'marginType': margin_mode
                    })
                    logger.info(f"✓ Margin Mode: {margin_mode}")
                except Exception as e:
                    logger.warning(f"⚠️ Margin mode ya configurado o error: {e}")

                try:
                    # Establecer apalancamiento
                    await self.exchange.fapiPrivate_post_leverage({
                        'symbol': symbol.replace('/', ''),
                        'leverage': leverage
                    })
                    logger.info(f"✓ Leverage configurado: {leverage}x")
                except Exception as e:
                    logger.warning(f"⚠️ Leverage ya configurado o error: {e}")

                # Verificar balance en testnet
                balance = await self.exchange.fetch_balance()
                usdt_balance = balance.get('USDT', {}).get('free', 0)
                logger.info(f"✓ Balance Testnet USDT: ${usdt_balance:.2f}")

            # MODO 3: REAL TRADING (Dinero Real)
            else:
                logger.warning("🔥 MODO REAL TRADING - DINERO REAL")
                logger.warning("⚠️ ⚠️ ⚠️  ESTÁS USANDO DINERO REAL  ⚠️ ⚠️ ⚠️")

                api_key = exchange_config.get('api_key', '').strip()
                api_secret = exchange_config.get('api_secret', '').strip()

                if not api_key or not api_secret:
                    raise ValueError("API keys de producción no configuradas en config_15min.json")

                self.exchange = ccxt.binance({
                    'apiKey': api_key,
                    'secret': api_secret,
                    'enableRateLimit': True,
                    'options': {'defaultType': 'future'}
                })

                await self.exchange.load_markets()
                logger.info("✓ Conectado a Binance PRODUCCIÓN")

                # Configurar LEVERAGE y MARGIN MODE
                symbol = exchange_config.get('symbol', 'ETHUSDT')
                leverage = trading_config.get('leverage', 1)
                margin_mode = trading_config.get('margin_mode', 'ISOLATED')

                try:
                    # Establecer modo de margen
                    await self.exchange.fapiPrivate_post_margintype({
                        'symbol': symbol.replace('/', ''),
                        'marginType': margin_mode
                    })
                    logger.info(f"✓ Margin Mode: {margin_mode}")
                except Exception as e:
                    logger.warning(f"⚠️ Margin mode: {e}")

                try:
                    # Establecer apalancamiento
                    await self.exchange.fapiPrivate_post_leverage({
                        'symbol': symbol.replace('/', ''),
                        'leverage': leverage
                    })
                    logger.info(f"✓ Leverage configurado: {leverage}x")
                except Exception as e:
                    logger.warning(f"⚠️ Leverage: {e}")

                # Verificar balance real
                balance = await self.exchange.fetch_balance()
                logger.info(f"✓ Balance REAL USDT: ${balance['USDT']['free']:.2f}")

            # Mostrar configuración de trading
            symbol = exchange_config.get('symbol', 'ETHUSDT')
            leverage = trading_config.get('leverage', 1)
            margin_mode = trading_config.get('margin_mode', 'ISOLATED')

            # Determinar modo para display
            if is_paper_trading:
                mode_display = "PAPER TRADING (Simulado Local)"
            elif is_testnet:
                mode_display = "TESTNET BINANCE (Dinero Ficticio)"
            else:
                mode_display = "🔥 REAL TRADING (DINERO REAL) 🔥"

            logger.info("=" * 60)
            logger.info("📊 CONFIGURACIÓN DE TRADING:")
            logger.info(f"   Modo: {mode_display}")
            logger.info(f"   Mercado: FUTUROS (Futures)")
            logger.info(f"   Símbolo: {symbol}")
            logger.info(f"   Leverage: {leverage}x")
            logger.info(f"   Margin Mode: {margin_mode}")
            logger.info(f"   Tamaño por posición: ${trading_config.get('position_size_usd', 100)} USD")
            logger.info(f"   Stop Loss: {trading_config.get('stop_loss_pct', 0.02) * 100:.1f}%")
            logger.info(f"   Take Profit: {trading_config.get('take_profit_pct', 0.05) * 100:.1f}%")
            logger.info(f"   Threshold: {trading_config.get('prediction_threshold', 0.70) * 100:.0f}%")
            logger.info("=" * 60)

            return True

        except Exception as e:
            logger.error(f"❌ Error conectando exchange: {e}")
            return False

    async def fetch_live_data(self, symbol='ETHUSDT', timeframe='1h', limit=350):
        """Obtiene datos en vivo de Binance (350 candles para statistical features)"""
        try:
            # Descargar datos de 1h para trading
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            # Descargar datos de 4h para macro features
            ohlcv_4h = await self.exchange.fetch_ohlcv(symbol, '4h', limit=200)
            df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms')
            df_4h.set_index('timestamp', inplace=True)

            return df, df_4h
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return pd.DataFrame(), pd.DataFrame()

    def calculate_features(self, df, df_4h=None):
        """Calcula features completos usando el FeatureEngineer"""
        try:
            # 1. Features técnicas de precio (usando FeatureEngineer)
            # IMPORTANTE: Usar '15m' para que genere nombres correctos de features
            # (volatility_1h, volatility_6h, etc.) que el modelo espera
            df = self.feature_engineer.create_technical_features(df, timeframe='15m')

            # 1a. Features de 4h (macro trend context)
            if df_4h is not None and not df_4h.empty:
                df = self.feature_engineer.add_4h_macro_features(df, df_4h)

            # 1b. Features estadísticas (Hurst, Wavelet, FFT, Entropy, etc.)
            if hasattr(self.feature_engineer, 'statistical_engine') and self.feature_engineer.statistical_engine:
                try:
                    logger.debug("📊 Generando statistical features...")
                    df = self.feature_engineer.statistical_engine.compute_all_features(df, price_col='close')
                    logger.debug(f"   ✓ Statistical features: {len(df.columns)} columnas totales")
                except Exception as e:
                    logger.warning(f"⚠️ Error generando statistical features: {e}")

            # 2. Cargar datos adicionales (derivatives, sentiment, macro)
            # Estos son datos históricos que se actualizan periódicamente
            try:
                logger.debug(f"📊 Features antes de merge: {len(df.columns)} columnas")

                # Derivatives (funding rate, OI, etc.)
                derivatives_df = pd.read_parquet('data/coinglass_ETH_USDT.parquet')
                logger.debug(f"📊 Derivatives: {len(derivatives_df)} filas")
                if not derivatives_df.empty and 'timestamp' in derivatives_df.columns:
                    derivatives_df['timestamp'] = pd.to_datetime(derivatives_df['timestamp'])
                    df = df.merge(derivatives_df, on='timestamp', how='left', suffixes=('', '_deriv'))
                    logger.debug(f"   ✓ Merge derivatives: {len(df.columns)} columnas")

                # Sentiment
                sentiment_df = pd.read_parquet('data/sentiment_ETH_USDT.parquet')
                logger.debug(f"📊 Sentiment: {len(sentiment_df)} filas")
                if not sentiment_df.empty and 'timestamp' in sentiment_df.columns:
                    sentiment_df['timestamp'] = pd.to_datetime(sentiment_df['timestamp'])
                    df = df.merge(sentiment_df, on='timestamp', how='left', suffixes=('', '_sent'))
                    logger.debug(f"   ✓ Merge sentiment: {len(df.columns)} columnas")

                # Macro (4h data)
                macro_df = pd.read_parquet('data/macro_ETH_USDT.parquet')
                logger.debug(f"📊 Macro: {len(macro_df)} filas")
                if not macro_df.empty and 'timestamp' in macro_df.columns:
                    macro_df['timestamp'] = pd.to_datetime(macro_df['timestamp'])
                    df = df.merge(macro_df, on='timestamp', how='left', suffixes=('', '_macro'))
                    logger.debug(f"   ✓ Merge macro: {len(df.columns)} columnas")

                logger.debug(f"📊 Total features después de merge: {len(df.columns)} columnas")

            except Exception as e:
                logger.warning(f"⚠️ No se pudieron cargar datos adicionales: {e}")
                logger.warning("⚠️ Usando solo features de precio")
                import traceback
                logger.debug(traceback.format_exc())

            # 3. Forward fill NaNs de merge (usar último valor disponible)
            df = df.ffill()

            # 4. CRÍTICO: Asegurar que existan TODAS las features que el modelo espera
            # Si falta alguna, agregarla con valor 0
            required_external_features = [
                'funding_rate', 'open_interest_norm', 'oi_change',  # Derivatives
                'Net_Flow_Z',  # Derivatives/On-chain
                'BTCDOM_ROC', 'FinBERT_Score',  # Sentiment
                'stablecoin_mcap', 'stablecoin_flow_7d', 'stablecoin_trend'  # Macro
            ]

            missing_features = [f for f in required_external_features if f not in df.columns]
            if missing_features:
                logger.warning(f"⚠️ Agregando {len(missing_features)} features faltantes con valor 0: {missing_features}")
                for feature in missing_features:
                    df[feature] = 0.0

            return df.dropna()

        except Exception as e:
            logger.error(f"Error calculando features: {e}")
            # Fallback a features básicas si falla
            return df

    def make_prediction(self, df):
        """Hace predicción LONG/SHORT"""
        try:
            # Tomar última fila con features
            latest = df.iloc[-1:].copy()

            # El modelo necesita TODAS las columnas en un orden específico
            # Obtener el orden correcto desde el modelo (si está disponible)
            if hasattr(self.model, 'feature_names_in_'):
                expected_features = self.model.feature_names_in_
                # Reordenar columnas según el modelo espera
                missing_cols = [col for col in expected_features if col not in latest.columns]
                if missing_cols:
                    logger.warning(f"⚠️ Faltan columnas en predicción: {missing_cols}")
                    for col in missing_cols:
                        latest[col] = 0.0

                # Reordenar columnas en el orden correcto
                X = latest[expected_features]
            else:
                # Si el modelo no tiene feature_names_in_, usar todas las columnas
                X = latest

            # Predicción
            pred_class = self.model.predict(X)[0]
            pred_proba = self.model.predict_proba(X)[0]

            confidence = pred_proba[pred_class]
            signal = 'LONG' if pred_class == 1 else 'SHORT'

            logger.info(f"📊 Predicción: {signal} (confianza: {confidence:.2%})")
            return signal, confidence

        except Exception as e:
            logger.error(f"Error en predicción: {e}")
            return None, 0.0

    async def execute_trade(self, signal, confidence, current_price):
        """Ejecuta trade (real o simulado según configuración)"""
        try:
            threshold = self.config['trading']['prediction_threshold']

            if confidence < threshold:
                logger.info(f"⏸️ Confianza {confidence:.2%} < {threshold:.0%} - No operar")
                return None

            # Tamaño de posición
            position_size_usd = self.config['trading']['position_size_usd']
            quantity = position_size_usd / current_price

            # Crear orden
            symbol = self.config['exchange']['symbol']
            side = 'buy' if signal == 'LONG' else 'sell'

            # Determinar modo de trading
            is_paper_trading = self.config['exchange'].get('paper_trading', False)
            is_testnet = self.config['exchange'].get('testnet', True)

            if is_paper_trading:
                # PAPER TRADING: Simular orden sin ejecutar en exchange
                order = {
                    'id': f"SIM_{int(datetime.now().timestamp())}",
                    'symbol': symbol,
                    'side': side,
                    'type': 'market',
                    'price': current_price,
                    'amount': quantity,
                    'filled': quantity,
                    'status': 'closed',
                    'timestamp': int(datetime.now().timestamp() * 1000)
                }
                logger.info(f"🖥️ Trade SIMULADO (Paper Trading Local)")
            elif is_testnet:
                # TESTNET: Ejecutar orden en testnet de Binance (dinero ficticio)
                order = await self.exchange.create_market_order(symbol, side, quantity)
                logger.info(f"🧪 Trade TESTNET ejecutado (Dinero Ficticio)")
            else:
                # REAL TRADING: Ejecutar orden real con dinero real
                order = await self.exchange.create_market_order(symbol, side, quantity)
                logger.warning(f"🔥 Trade REAL ejecutado (DINERO REAL)")

            # Calcular SL y TP
            sl_pct = self.config['trading']['stop_loss_pct']
            tp_pct = self.config['trading']['take_profit_pct']

            if signal == 'LONG':
                stop_loss = current_price * (1 - sl_pct)
                take_profit = current_price * (1 + tp_pct)
            else:
                stop_loss = current_price * (1 + sl_pct)
                take_profit = current_price * (1 - tp_pct)

            # Calcular valores exactos
            leverage = self.config['trading'].get('leverage', 1)
            notional_value = position_size_usd * leverage  # Valor nocional con leverage
            eth_value = quantity * current_price  # Valor en ETH

            trade_record = {
                'entry_time': datetime.now(),
                'direction': signal,
                'entry_price': current_price,
                'quantity': quantity,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'confidence': confidence,
                'order_id': order['id'],
                'status': 'open'
            }

            self.current_position = trade_record

            # Logs detallados
            logger.info("=" * 60)
            logger.info("🚀 TRADE EJECUTADO")
            logger.info(f"   Dirección: {signal}")
            logger.info(f"   Precio: ${current_price:.2f}")
            logger.info(f"   Cantidad ETH: {quantity:.4f}")
            logger.info(f"   Margen usado: ${position_size_usd:.2f}")
            logger.info(f"   Leverage: {leverage}x")
            logger.info(f"   Valor nocional: ${notional_value:.2f} (controlando ${eth_value:.2f} de ETH)")
            logger.info(f"   Stop Loss: ${stop_loss:.2f} ({sl_pct*100:.1f}%)")
            logger.info(f"   Take Profit: ${take_profit:.2f} ({tp_pct*100:.1f}%)")
            logger.info(f"   Confianza ML: {confidence:.1%}")
            logger.info(f"   Order ID: {order['id']}")
            logger.info("=" * 60)

            return trade_record

        except Exception as e:
            logger.error(f"❌ Error ejecutando trade: {e}")
            return None

    async def check_position(self, current_price):
        """Verifica si hay que cerrar posición (SL/TP)"""
        if not self.current_position or self.current_position['status'] != 'open':
            return

        pos = self.current_position
        direction = pos['direction']

        # Verificar SL/TP
        hit_tp = False
        hit_sl = False

        if direction == 'LONG':
            hit_tp = current_price >= pos['take_profit']
            hit_sl = current_price <= pos['stop_loss']
        else:
            hit_tp = current_price <= pos['take_profit']
            hit_sl = current_price >= pos['stop_loss']

        if hit_tp or hit_sl:
            # Cerrar posición
            exit_reason = 'TP' if hit_tp else 'SL'

            try:
                symbol = self.config['exchange']['symbol']
                side = 'sell' if direction == 'LONG' else 'buy'

                # Verificar si es paper trading
                is_paper_trading = self.config['exchange'].get('paper_trading', True)

                if is_paper_trading:
                    # PAPER TRADING: Simular cierre
                    logger.info(f"🧪 Cierre SIMULADO (Paper Trading)")
                else:
                    # REAL TRADING: Cerrar orden real
                    await self.exchange.create_market_order(symbol, side, pos['quantity'])
                    logger.info(f"💰 Cierre REAL ejecutado")

                # Calcular P&L
                if direction == 'LONG':
                    pnl_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                else:
                    pnl_pct = ((pos['entry_price'] - current_price) / pos['entry_price']) * 100

                # Guardar trade cerrado
                pos['exit_time'] = datetime.now()
                pos['exit_price'] = current_price
                pos['exit_reason'] = exit_reason
                pos['pnl_pct'] = pnl_pct
                pos['status'] = 'closed'

                self._save_trade(pos)

                logger.info(f"🎯 Posición cerrada: {exit_reason} | P&L: {pnl_pct:+.2f}%")
                self.current_position = None

            except Exception as e:
                logger.error(f"Error cerrando posición: {e}")

    def _save_trade(self, trade):
        """Guarda trade en CSV"""
        try:
            df = pd.DataFrame([trade])

            if self.trades_file.exists():
                df.to_csv(self.trades_file, mode='a', header=False, index=False)
            else:
                df.to_csv(self.trades_file, index=False)

            logger.info(f"💾 Trade guardado en {self.trades_file}")
        except Exception as e:
            logger.error(f"Error guardando trade: {e}")

    async def trading_loop(self):
        """Loop principal de trading"""
        logger.info("🚀 Iniciando bot de trading...")

        # Cargar modelo
        if not self.load_model():
            return

        # Conectar exchange
        if not await self.initialize_exchange():
            return

        logger.info("✓ Bot listo para operar")
        self.is_running = True

        # Loop principal
        while self.is_running:
            try:
                # Obtener datos en vivo (1h y 4h)
                df, df_4h = await self.fetch_live_data()

                if df.empty:
                    logger.warning("No hay datos disponibles")
                    await asyncio.sleep(60)
                    continue

                # Calcular features (pasando datos de 4h para macro features)
                df = self.calculate_features(df, df_4h)
                current_price = df['close'].iloc[-1]

                # Verificar posición actual
                await self.check_position(current_price)

                # Si no hay posición abierta, buscar nueva señal
                if not self.current_position:
                    signal, confidence = self.make_prediction(df)

                    if signal:
                        await self.execute_trade(signal, confidence, current_price)

                # Esperar 1 hora (para trading 1h)
                logger.info(f"⏳ Esperando próxima vela... (Precio: ${current_price:.2f})")
                await asyncio.sleep(3600)  # 1 hora

            except Exception as e:
                logger.error(f"Error en trading loop: {e}")
                await asyncio.sleep(60)

        # Cleanup
        if self.exchange:
            await self.exchange.close()

        logger.info("🛑 Bot detenido")

# =================== FUNCIONES AUXILIARES ===================

@st.cache_data(ttl=60)
def load_price_data(hours=24):
    """Carga datos de precio desde CacheManager"""
    try:
        # Cargar datos usando CacheManager
        df = cache_mgr.load_data('ETHUSDT_1h')

        if df is not None and not df.empty:
            # Asegurar timestamp como índice
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp')
            elif df.index.name != 'timestamp':
                # Si ya es índice pero sin nombre, renombrar
                df.index.name = 'timestamp'

            # Filtrar últimas N horas
            cutoff = datetime.now() - timedelta(hours=hours)
            df = df[df.index >= cutoff]
            return df
    except Exception as e:
        st.error(f"Error cargando datos: {e}")

    return pd.DataFrame()

def load_model_info():
    """Carga información del modelo"""
    try:
        model_path = Path('models/xgboost_model.json')
        if model_path.exists():
            mod_time = datetime.fromtimestamp(model_path.stat().st_mtime)
            return {
                'exists': True,
                'last_trained': mod_time,
                'age_hours': (datetime.now() - mod_time).total_seconds() / 3600
            }
    except:
        pass
    return {'exists': False}

def load_trades_history():
    """Carga historial de trades en vivo o backtest"""
    # Intentar cargar trades en vivo primero
    live_file = Path('logs/live_trades.csv')
    backtest_file = Path('logs/trades_history.csv')

    for file in [live_file, backtest_file]:
        try:
            if file.exists():
                df = pd.read_csv(file)
                if not df.empty:
                    return df
        except Exception as e:
            logger.warning(f"Error cargando {file}: {e}")

    # Si no hay trades, retornar DataFrame vacío
    return pd.DataFrame(columns=[
        'entry_time', 'exit_time', 'direction', 'entry_price',
        'exit_price', 'pnl_pct', 'exit_reason'
    ])

def run_bot_async(bot):
    """Ejecuta el bot en un nuevo event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.trading_loop())
    finally:
        loop.close()

def start_trading_bot():
    """Inicia el bot en un thread separado"""
    if 'bot' not in st.session_state or st.session_state.bot is None:
        st.session_state.bot = LiveTradingBot()

    bot = st.session_state.bot

    if not bot.is_running:
        # Iniciar bot en thread separado
        bot_thread = threading.Thread(target=run_bot_async, args=(bot,), daemon=True)
        bot_thread.start()
        st.session_state['bot_thread'] = bot_thread
        st.session_state['bot_running'] = True
        logger.info("✅ Bot iniciado en background")
    else:
        logger.warning("⚠️ Bot ya está corriendo")

def stop_trading_bot():
    """Detiene el bot"""
    if 'bot' in st.session_state and st.session_state.bot:
        bot = st.session_state.bot
        bot.is_running = False
        st.session_state['bot_running'] = False
        logger.info("🛑 Bot detenido")

def load_config():
    """Carga configuración"""
    try:
        with open('config_15min.json', 'r') as f:
            return json.load(f)
    except:
        return {}


st.sidebar.title("⚙️ Control Panel")

# Estado del bot
st.sidebar.header("🤖 Estado del Bot")
bot_status = st.sidebar.empty()
bot_status.success("🟢 Bot Iniciado" if st.session_state.get('bot_running', False) else "🔴 Bot Detenido")

# Controles
col1, col2 = st.sidebar.columns(2)
if col1.button("▶️ Iniciar", width="stretch"):
    start_trading_bot()
    st.rerun()

if col2.button("⏸️ Detener", width="stretch"):
    stop_trading_bot()
    st.rerun()

# Información de Futuros
st.sidebar.header("⚙️ Configuración Futuros")
config = load_config()
trading_config = config.get('trading', {})
exchange_config = config.get('exchange', {})

# Selector de modo de trading
trading_mode = st.sidebar.radio(
    "Modo de Trading",
    ["Testnet Binance (Dinero Ficticio)", "Paper Trading (Simulado Local)", "Real Trading (Dinero Real)"],
    index=0,
    help="Testnet = Binance real con dinero ficticio | Paper = Simulación local | Real = Dinero real"
)

# Indicadores visuales y configuración
if trading_mode == "Testnet Binance (Dinero Ficticio)":
    st.sidebar.success("🧪 Testnet de Binance (Dinero Ficticio)")
    is_paper_trading = False
    is_testnet = True
    st.sidebar.info("Conecta a testnet.binancefuture.com con dinero ficticio de Binance")
elif trading_mode == "Paper Trading (Simulado Local)":
    st.sidebar.success("🖥️ Paper Trading (Simulación Local)")
    is_paper_trading = True
    is_testnet = False
    st.sidebar.info("Simula trades localmente sin conectar a Binance")
else:
    st.sidebar.error("🔥 REAL TRADING (Dinero Real)")
    is_paper_trading = False
    is_testnet = False
    st.sidebar.warning("⚠️ USA DINERO REAL - Ten mucho cuidado")

# Mostrar configuración de futuros
st.sidebar.subheader("Parámetros de Futuros")

# Leverage selector
leverage = st.sidebar.select_slider(
    "Apalancamiento (Leverage)",
    options=[1, 2, 3, 5, 10, 20, 50],
    value=trading_config.get('leverage', 1),
    help="1x = Sin apalancamiento (más seguro), 20x = 20 veces tu capital (MUY RIESGOSO)"
)

# Margin mode selector
margin_mode = st.sidebar.radio(
    "Tipo de Margen",
    ["ISOLATED", "CROSS"],
    index=0 if trading_config.get('margin_mode', 'ISOLATED') == 'ISOLATED' else 1,
    help="ISOLATED = solo pierdes esa posición | CROSS = puedes perder todo"
)

# Position size
position_size = st.sidebar.number_input(
    "Tamaño de Posición (USD)",
    min_value=10,
    max_value=1000,
    value=trading_config.get('position_size_usd', 100),
    step=10,
    help="Cantidad en USD por cada trade"
)

# Mostrar resumen de configuración
mode_display = "Testnet (Ficticio)" if is_testnet and not is_paper_trading else ("Paper (Simulado)" if is_paper_trading else "REAL (Dinero Real)")
st.sidebar.info(f"""
**Mercado:** Futuros (Futures)
**Símbolo:** {exchange_config.get('symbol', 'ETHUSDT')}
**Modo:** {mode_display}
**Apalancamiento:** {leverage}x
**Margen:** {margin_mode}
**Posición:** ${position_size} USD
""")

# Si modo testnet, mostrar campos para API keys
if is_testnet and not is_paper_trading:
    st.sidebar.subheader("🔑 API Keys Testnet")

    testnet_key = st.sidebar.text_input(
        "Testnet API Key",
        value=exchange_config.get('testnet_api_key', ''),
        type="password",
        help="Obtén keys en: https://testnet.binancefuture.com"
    )

    testnet_secret = st.sidebar.text_input(
        "Testnet API Secret",
        value=exchange_config.get('testnet_api_secret', ''),
        type="password"
    )

    if not testnet_key or not testnet_secret:
        st.sidebar.warning("⚠️ Configura las API keys de Testnet para operar")
        st.sidebar.markdown("[Obtener keys de Testnet](https://testnet.binancefuture.com)")

# Advertencia de riesgo si leverage > 1
if leverage > 1:
    risk_exposure = position_size * leverage
    st.sidebar.warning(f"⚠️ RIESGO: Con {leverage}x leverage y ${position_size}, controlas ${risk_exposure} de ETH")

    # Calcular precio de liquidación aproximado
    liquidation_move = (1 / leverage) * 100
    st.sidebar.error(f"🚨 Liquidación si ETH se mueve {liquidation_move:.1f}% en tu contra")

# Guardar configuración actualizada en session_state
if 'trading_settings' not in st.session_state:
    st.session_state.trading_settings = {}

st.session_state.trading_settings.update({
    'leverage': leverage,
    'margin_mode': margin_mode,
    'position_size_usd': position_size,
    'is_paper_trading': is_paper_trading,
    'is_testnet': is_testnet
})

# Botón para aplicar cambios
if st.sidebar.button("💾 Aplicar Cambios", type="primary"):
    # Guardar en config file
    config['trading']['leverage'] = leverage
    config['trading']['margin_mode'] = margin_mode
    config['trading']['position_size_usd'] = position_size
    config['exchange']['paper_trading'] = is_paper_trading
    config['exchange']['testnet'] = is_testnet

    # Si es testnet, guardar API keys
    if is_testnet and not is_paper_trading:
        config['exchange']['testnet_api_key'] = testnet_key
        config['exchange']['testnet_api_secret'] = testnet_secret

    with open('config_15min.json', 'w') as f:
        json.dump(config, f, indent=2)

    st.sidebar.success("✅ Configuración guardada!")
    st.sidebar.info("⚠️ Reinicia el bot para aplicar cambios")

# Configuración
st.sidebar.header("📊 Parámetros de Trading")

threshold = st.sidebar.slider(
    "Threshold de Confianza",
    min_value=0.5,
    max_value=0.95,
    value=config.get('trading', {}).get('prediction_threshold', 0.70),
    step=0.05
)

sl_pct = st.sidebar.slider(
    "Stop Loss %",
    min_value=0.01,
    max_value=0.05,
    value=config.get('trading', {}).get('stop_loss_pct', 0.02),
    step=0.005,
    format="%.3f"
)

tp_pct = st.sidebar.slider(
    "Take Profit %",
    min_value=0.02,
    max_value=0.10,
    value=config.get('trading', {}).get('take_profit_pct', 0.05),
    step=0.005,
    format="%.3f"
)

# Timeframe selector
st.sidebar.header("⏱️ Timeframe")
timeframe_options = {
    "6 horas": 6,
    "12 horas": 12,
    "1 día": 24,
    "2 días": 48,
    "1 semana": 168,
    "2 semanas": 336,
    "1 mes": 720,
    "3 meses": 2160,
    "Todo": 999999
}
selected_tf = st.sidebar.selectbox(
    "Mostrar últimas:",
    list(timeframe_options.keys()),
    index=2
)
hours_to_show = timeframe_options[selected_tf]

# Auto-refresh
auto_refresh = st.sidebar.checkbox("🔄 Auto-actualizar", value=True)
if auto_refresh:
    refresh_rate = st.sidebar.slider("Cada (segundos):", 5, 60, 10)


# =================== TABS STRUCTURE ===================

# Crear tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Dashboard",
    "🧠 Training",
    "📡 Signals",
    "🔧 Models",
    "📈 Backtest"
])

# =================== TAB 1: DASHBOARD ===================

with tab1:
    # =================== HEADER ===================

    st.title("📈 ETH Trading Bot Dashboard")
    st.markdown("---")
    
    # Métricas principales
    col1, col2, col3, col4, col5 = st.columns(5)
    
    # Cargar datos
    df_price = load_price_data(hours=hours_to_show)
    trades_df = load_trades_history()
    model_info = load_model_info()
    
    # Precio actual
    if not df_price.empty:
        current_price = df_price['close'].iloc[-1]
        prev_price = df_price['close'].iloc[-25] if len(df_price) > 25 else df_price['close'].iloc[0]
        price_change = ((current_price - prev_price) / prev_price) * 100
    
        col1.metric(
            "💵 Precio ETH",
            f"${current_price:,.2f}",
            f"{price_change:+.2f}% (24h)"
        )
    
    # Trades totales
    total_trades = len(trades_df)
    wins = len(trades_df[trades_df['pnl_pct'] > 0])
    losses = total_trades - wins
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    col2.metric(
        "📊 Trades Totales",
        total_trades,
        f"Win Rate: {win_rate:.1f}%"
    )
    
    # P&L Total
    total_pnl = trades_df['pnl_pct'].sum() if not trades_df.empty else 0
    col3.metric(
        "💰 P&L Total",
        f"{total_pnl:+.2f}%",
        "En últimas 24h"
    )
    
    # Profit Factor
    wins_sum = trades_df[trades_df['pnl_pct'] > 0]['pnl_pct'].sum()
    losses_sum = abs(trades_df[trades_df['pnl_pct'] < 0]['pnl_pct'].sum())
    profit_factor = (wins_sum / losses_sum) if losses_sum > 0 else 0
    
    col4.metric(
        "📈 Profit Factor",
        f"{profit_factor:.2f}",
        "Ganancias/Pérdidas"
    )
    
    # Modelo
    if model_info['exists']:
        age_str = f"{model_info['age_hours']:.1f}h ago"
        col5.metric(
            "🧠 Modelo",
            "Actualizado",
            age_str
        )
    else:
        col5.metric("🧠 Modelo", "No Entrenado", "❌")
    
    st.markdown("---")
    
    # =================== GRÁFICO PRINCIPAL ===================
    
    st.header("📊 Gráfico de Trading")
    
    if not df_price.empty:
        # Crear figura con subplots
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
            subplot_titles=('Precio + Trades', 'P&L Acumulado')
        )
    
        # === Panel 1: Candlestick + Trades ===
        fig.add_trace(
            go.Candlestick(
                x=df_price.index,
                open=df_price['open'],
                high=df_price['high'],
                low=df_price['low'],
                close=df_price['close'],
                name='ETH/USDT',
                increasing_line_color='#27AE60',
                decreasing_line_color='#E74C3C'
            ),
            row=1, col=1
        )
    
        # Agregar trades como markers
        for _, trade in trades_df.iterrows():
            entry_time = pd.to_datetime(trade['entry_time'])
            exit_time = pd.to_datetime(trade['exit_time'])
    
            # Solo mostrar si está en el rango visible
            if entry_time < df_price.index[0]:
                continue
    
            is_win = trade['pnl_pct'] > 0
            color = '#27AE60' if is_win else '#E74C3C'
    
            # Marker de entrada
            fig.add_trace(
                go.Scatter(
                    x=[entry_time],
                    y=[trade['entry_price']],
                    mode='markers',
                    marker=dict(
                        symbol='triangle-up' if trade['direction'] == 'LONG' else 'triangle-down',
                        size=15,
                        color=color,
                        line=dict(width=2, color='white')
                    ),
                    name=f"{trade['direction']} Entry",
                    showlegend=False,
                    hovertemplate=f"<b>{trade['direction']} Entry</b><br>" +
                                  f"Price: ${trade['entry_price']:.2f}<br>" +
                                  f"Time: {entry_time}<extra></extra>"
                ),
                row=1, col=1
            )
    
            # Marker de salida
            fig.add_trace(
                go.Scatter(
                    x=[exit_time],
                    y=[trade['exit_price']],
                    mode='markers',
                    marker=dict(
                        symbol='triangle-down' if trade['direction'] == 'LONG' else 'triangle-up',
                        size=15,
                        color=color,
                        line=dict(width=2, color='white')
                    ),
                    name=f"{trade['direction']} Exit",
                    showlegend=False,
                    hovertemplate=f"<b>{trade['direction']} Exit ({trade['exit_reason']})</b><br>" +
                                  f"Price: ${trade['exit_price']:.2f}<br>" +
                                  f"P&L: {trade['pnl_pct']:+.2f}%<br>" +
                                  f"Time: {exit_time}<extra></extra>"
                ),
                row=1, col=1
            )
    
            # Línea conectando entrada/salida
            fig.add_trace(
                go.Scatter(
                    x=[entry_time, exit_time],
                    y=[trade['entry_price'], trade['exit_price']],
                    mode='lines',
                    line=dict(color=color, width=1, dash='dot'),
                    showlegend=False,
                    hoverinfo='skip'
                ),
                row=1, col=1
            )
    
        # === Panel 2: P&L Acumulado ===
        if not trades_df.empty:
            trades_sorted = trades_df.sort_values('exit_time')
            trades_sorted['cumulative_pnl'] = trades_sorted['pnl_pct'].cumsum()
    
            fig.add_trace(
                go.Scatter(
                    x=pd.to_datetime(trades_sorted['exit_time']),
                    y=trades_sorted['cumulative_pnl'],
                    mode='lines',
                    name='P&L Acumulado',
                    line=dict(color='#16A085', width=2),
                    fill='tozeroy',
                    fillcolor='rgba(22, 160, 133, 0.2)'
                ),
                row=2, col=1
            )
    
            # Línea en 0
            fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=2, col=1)
    
        # Layout con mejor zoom
        fig.update_layout(
            height=800,
            showlegend=True,
            hovermode='x unified',
            xaxis_rangeslider_visible=False,
            template='plotly_white',
            xaxis_type='date'
        )
    
        # Configurar zoom para que se adapte al timeframe seleccionado
        if not df_price.empty:
            fig.update_xaxes(
                title_text="Fecha",
                range=[df_price.index.min(), df_price.index.max()],
                row=1, col=1
            )
            fig.update_xaxes(
                title_text="Fecha",
                range=[df_price.index.min(), df_price.index.max()],
                row=2, col=1
            )
    
        fig.update_yaxes(title_text="Precio (USDT)", row=1, col=1)
        fig.update_yaxes(title_text="P&L Acumulado (%)", row=2, col=1)
    
        st.plotly_chart(fig, width="stretch")
    
    else:
        st.warning("⚠️ No hay datos de precio disponibles. Ejecuta primero el pipeline de entrenamiento.")
    
    # =================== TABLA DE TRADES ===================
    
    st.header("📋 Historial de Trades")
    
    # Mostrar info del bot si está corriendo
    if st.session_state.get('bot_running', False):
        # Verificar si hay posición abierta
        if 'bot' in st.session_state and st.session_state.bot and st.session_state.bot.current_position:
            pos = st.session_state.bot.current_position
            st.warning(f"🎯 Posición Abierta: {pos['direction']} @ ${pos['entry_price']:.2f} | SL: ${pos['stop_loss']:.2f} | TP: ${pos['take_profit']:.2f}")
        else:
            st.info("🤖 Bot operando en vivo - Esperando señal de trading...")
    
    if not trades_df.empty and 'entry_time' in trades_df.columns:
        # Formatear DataFrame para mostrar
        display_df = trades_df.copy()
    
        # Seleccionar solo las columnas que queremos mostrar (en orden)
        display_cols = []
        if 'entry_time' in display_df.columns:
            display_df['entry_time'] = pd.to_datetime(display_df['entry_time']).dt.strftime('%Y-%m-%d %H:%M')
            display_cols.append('entry_time')
    
        if 'exit_time' in display_df.columns:
            display_df['exit_time'] = pd.to_datetime(display_df['exit_time'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
            display_cols.append('exit_time')
    
        if 'direction' in display_df.columns:
            display_cols.append('direction')
    
        if 'entry_price' in display_df.columns:
            display_df['entry_price'] = display_df['entry_price'].apply(lambda x: f"${x:.2f}")
            display_cols.append('entry_price')
    
        if 'exit_price' in display_df.columns:
            display_df['exit_price'] = display_df['exit_price'].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "N/A")
            display_cols.append('exit_price')
    
        if 'pnl_pct' in display_df.columns:
            display_df['pnl_pct'] = display_df['pnl_pct'].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A")
            display_cols.append('pnl_pct')
    
        if 'exit_reason' in display_df.columns:
            display_cols.append('exit_reason')
    
        # Añadir confianza si existe (útil para debugging)
        if 'confidence' in display_df.columns:
            display_df['confidence'] = display_df['confidence'].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "N/A")
            display_cols.append('confidence')
    
        # Seleccionar solo las columnas disponibles
        display_df = display_df[display_cols]
    
        # Renombrar columnas dinámicamente
        column_mapping = {
            'entry_time': 'Entrada',
            'exit_time': 'Salida',
            'direction': 'Dirección',
            'entry_price': 'Precio Entrada',
            'exit_price': 'Precio Salida',
            'pnl_pct': 'P&L %',
            'exit_reason': 'Razón',
            'confidence': 'Confianza'
        }
        display_df = display_df.rename(columns=column_mapping)
    
        st.dataframe(
            display_df,
            width="stretch",
            height=400
        )
    else:
        st.info("No hay trades registrados aún. Inicia el bot para comenzar a operar.")
    
    # =================== ESTADÍSTICAS ===================
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.header("📊 Estadísticas de Trading")
    
        if not trades_df.empty:
            # Keep data as numbers, format in display
            avg_win = trades_df[trades_df['pnl_pct'] > 0]['pnl_pct'].mean()
            avg_loss = trades_df[trades_df['pnl_pct'] < 0]['pnl_pct'].mean()
            best_trade = trades_df['pnl_pct'].max()
            worst_trade = trades_df['pnl_pct'].min()
    
            # Create DataFrame with formatted strings only
            stats_display = pd.DataFrame({
                'Métrica': ['Total Trades', 'Wins', 'Losses', 'Win Rate', 'Avg Win', 'Avg Loss', 'Best Trade', 'Worst Trade', 'Profit Factor'],
                'Valor': [
                    str(total_trades),
                    str(wins),
                    str(losses),
                    f"{win_rate:.1f}%",
                    f"{avg_win:.2f}%",
                    f"{avg_loss:.2f}%",
                    f"{best_trade:.2f}%",
                    f"{worst_trade:.2f}%",
                    f"{profit_factor:.2f}"
                ]
            })
    
            st.table(stats_display.set_index('Métrica'))
    
    with col2:
        st.header("⚙️ Configuración Actual")
    
        # Create DataFrame with formatted strings only
        config_display = pd.DataFrame({
            'Parámetro': ['Threshold', 'Stop Loss', 'Take Profit', 'Timeframe', 'Max Positions', 'Position Size'],
            'Valor': [
                f"{threshold:.0%}",
                f"{sl_pct:.1%}",
                f"{tp_pct:.1%}",
                '1 hora',
                str(config.get('trading', {}).get('max_positions', 1)),
                f"${config.get('trading', {}).get('position_size_usd', 100)}"
            ]
        })
    
        st.table(config_display.set_index('Parámetro'))
    
    # =================== BOT LOGS ===================
    
    if st.session_state.get('bot_running', False):
        st.markdown("---")
        st.header("📝 Logs del Bot")
    
        log_file = Path('logs/trading_bot.log')
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    # Mostrar últimas 20 líneas
                    recent_logs = ''.join(lines[-20:])
                    st.code(recent_logs, language='log')
            except Exception as e:
                st.error(f"Error leyendo logs: {e}")
        else:
            st.info("Esperando logs del bot...")
    
    # =================== FOOTER ===================
    
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    col1.caption(f"🕒 Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    col2.caption(f"📊 Trades cargados: {len(trades_df)}")
    col3.caption(f"🤖 Estado: {'🟢 OPERANDO' if st.session_state.get('bot_running', False) else '🔴 DETENIDO'}")
    
    # Auto-refresh
    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()


# =================== TAB 2: TRAINING ===================

with tab2:
    if not _panels_loaded:
        st.error(f"❌ Error cargando paneles: {_panels_error}")
        st.code(_panels_traceback)
    else:
        try:
            render_training_panel()
        except Exception as e:
            st.error(f"❌ Error en Training Panel: {str(e)}")
            st.code(f"{type(e).__name__}: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# =================== TAB 3: SIGNALS ===================

with tab3:
    if not _panels_loaded:
        st.error(f"❌ Error cargando paneles: {_panels_error}")
        st.code(_panels_traceback)
    else:
        try:
            render_signals_panel()
        except Exception as e:
            st.error(f"❌ Error en Signals Panel: {str(e)}")
            st.code(f"{type(e).__name__}: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# =================== TAB 4: MODELS ===================

with tab4:
    if not _panels_loaded:
        st.error(f"❌ Error cargando paneles: {_panels_error}")
        st.code(_panels_traceback)
    else:
        try:
            render_models_panel()
        except Exception as e:
            st.error(f"❌ Error en Models Panel: {str(e)}")
            st.code(f"{type(e).__name__}: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# =================== TAB 5: BACKTEST ===================

with tab5:
    if not _panels_loaded:
        st.error(f"❌ Error cargando paneles: {_panels_error}")
        st.code(_panels_traceback)
    else:
        try:
            render_backtest_panel()
        except Exception as e:
            st.error(f"❌ Error en Backtest Panel: {str(e)}")
            st.code(f"{type(e).__name__}: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
