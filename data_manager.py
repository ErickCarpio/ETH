"""
Data Manager - Gestión de Datos con CACHÉ LOCAL
Guarda datos en disco (/data). Incluye compatibilidad con Orquestador.
ACTUALIZADO: Ahora descarga On-Chain y Sentiment usando los fetchers
NOTA: Los fetchers se importan "lazy" para evitar dependencias obligatorias
"""
import ccxt.async_support as ccxt
import pandas as pd
from datetime import datetime, timedelta
import asyncio
import logging
from pathlib import Path
import os

# Los fetchers se importan solo cuando se necesitan (lazy import)
# para evitar errores si PyTorch/Transformers no están instalados

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataManager:
    def __init__(self, symbol: str = "ETH/USDT", window_years: int = 2):
        self.symbol = symbol
        self.window_days = window_years * 365
        self.exchange = None
        self.data_dir = Path("./data")
        self.data_dir.mkdir(exist_ok=True)
        
    async def initialize_exchange(self, api_key=None, secret=None, testnet=False):
        if self.exchange is not None: return
        options = {'defaultType': 'future'}
        self.exchange = ccxt.binance({'enableRateLimit': True, 'options': options})
        if testnet: self.exchange.set_sandbox_mode(True)

    async def close_exchange(self):
        if self.exchange: 
            await self.exchange.close()
            self.exchange = None
            
    def _get_cache_path(self, name: str) -> Path:
        safe_symbol = self.symbol.replace('/', '_')
        return self.data_dir / f"{name}_{safe_symbol}.parquet"
    
    def _load_from_cache(self, name: str, max_age_hours: int = 4) -> pd.DataFrame:
        file_path = self._get_cache_path(name)
        if file_path.exists():
            mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            age_hours = (datetime.now() - mod_time).total_seconds() / 3600
            if age_hours < max_age_hours:
                logger.info(f"📂 Cargando {name} desde caché local (Edad: {age_hours:.1f}h)")
                try: return pd.read_parquet(file_path)
                except: pass
        return pd.DataFrame()

    def _save_to_cache(self, df: pd.DataFrame, name: str):
        if df is not None and not df.empty:
            file_path = self._get_cache_path(name)
            df.to_parquet(file_path)
            # CSV de respaldo para inspección manual
            df.to_csv(str(file_path).replace('.parquet', '.csv'))

    async def _fetch_symbol_data(self, symbol):
        if self.exchange is None: await self.initialize_exchange(testnet=False)
        end_ts = int(datetime.now().timestamp() * 1000)
        start_ts = int((datetime.now() - timedelta(days=self.window_days)).timestamp() * 1000)
        
        logger.info(f"⬇️ Descargando {symbol}...")
        all_candles = []
        current_ts = start_ts
        while current_ts < end_ts:
            try:
                candles = await self.exchange.fetch_ohlcv(symbol, '4h', since=current_ts, limit=1000)
                if not candles: break
                all_candles.extend(candles)
                current_ts = candles[-1][0] + 1
                await asyncio.sleep(0.05) 
            except Exception: break
        
        if not all_candles: return pd.DataFrame()
        df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df

    async def get_full_dataset(self, include_onchain=False, include_sentiment=False, api_keys=None):
        try:
            # 1. Crypto
            crypto = self._load_from_cache("prices")
            if crypto.empty:
                crypto = await self._fetch_symbol_data(self.symbol)
                self._save_to_cache(crypto, "prices")

            # 2. Macro (BTCDOM)
            macro = self._load_from_cache("macro")
            if macro.empty:
                btcdom = await self._fetch_symbol_data("BTCDOM/USDT")
                if not btcdom.empty:
                    macro = pd.DataFrame({'BTCDOM': btcdom['close']})
                    self._save_to_cache(macro, "macro")

            result = {'crypto': crypto, 'macro': macro}

            # 3. On-Chain Data (Descarga real si no hay caché)
            if include_onchain:
                onchain_df = self._load_from_cache("onchain")

                if onchain_df.empty:
                    logger.info("⚡ Descargando datos On-Chain...")
                    try:
                        # Lazy import: solo importar cuando realmente se necesita
                        from onchain_data_fetcher import OnChainDataFetcher

                        # Extraer API keys de on-chain
                        onchain_keys = {}
                        if api_keys:
                            if 'cryptoquant' in api_keys:
                                onchain_keys['cryptoquant'] = api_keys['cryptoquant']
                            if 'glassnode' in api_keys:
                                onchain_keys['glassnode'] = api_keys['glassnode']

                        # Instanciar fetcher
                        fetcher = OnChainDataFetcher(api_keys=onchain_keys if onchain_keys else None)

                        # Ejecutar en thread separado (fetcher es síncrono)
                        symbol_base = self.symbol.split('/')[0]  # "ETH" de "ETH/USDT"
                        onchain_df = await asyncio.to_thread(
                            fetcher.get_composite_onchain_signal,
                            symbol=symbol_base,
                            days=self.window_days
                        )

                        # Guardar en caché
                        if not onchain_df.empty:
                            self._save_to_cache(onchain_df, "onchain")
                            logger.info(f"✓ On-Chain data descargada: {len(onchain_df)} registros")
                        else:
                            logger.warning("⚠️ On-Chain data vacía")

                    except Exception as e:
                        logger.error(f"❌ Error descargando on-chain: {e}")
                        onchain_df = pd.DataFrame()

                result['onchain'] = onchain_df

            # 4. Sentiment Data (Descarga real si no hay caché)
            if include_sentiment:
                sentiment_df = self._load_from_cache("sentiment")

                if sentiment_df.empty:
                    logger.info("🧠 Analizando sentimiento con FinBERT...")
                    try:
                        # Lazy import: solo importar cuando realmente se necesita
                        from sentiment_fetcher import SentimentFetcher

                        # Extraer API keys de sentiment
                        news_key = None
                        panic_key = None

                        if api_keys:
                            if 'newsapi' in api_keys:
                                news_key = api_keys['newsapi']
                            if 'cryptopanic' in api_keys:
                                panic_key = api_keys['cryptopanic']

                        # Instanciar fetcher
                        fetcher = SentimentFetcher(
                            news_api_key=news_key,
                            cryptopanic_key=panic_key
                        )

                        # Ejecutar análisis (puede tardar 5-10 min en primera ejecución)
                        sentiment_df = await asyncio.to_thread(
                            fetcher.get_sentiment_dataset,
                            days=28  # Limitado por NewsAPI gratuita
                        )

                        # Guardar en caché
                        if not sentiment_df.empty:
                            self._save_to_cache(sentiment_df, "sentiment")
                            logger.info(f"✓ Sentiment data procesada: {len(sentiment_df)} registros")
                        else:
                            logger.warning("⚠️ Sentiment data vacía")

                    except Exception as e:
                        logger.error(f"❌ Error procesando sentiment: {e}")
                        sentiment_df = pd.DataFrame()

                result['sentiment'] = sentiment_df

            # 5. DefiLlama Data (Stablecoins - SIEMPRE GRATIS)
            if include_onchain:  # Usamos el mismo flag que on-chain
                defillama_df = self._load_from_cache("defillama")

                if defillama_df.empty:
                    logger.info("💰 Descargando datos de Stablecoins (DefiLlama)...")
                    try:
                        # Lazy import
                        from defillama_fetcher import DefiLlamaFetcher

                        fetcher = DefiLlamaFetcher()

                        # Ejecutar en thread separado
                        defillama_df = await asyncio.to_thread(
                            fetcher.get_stablecoin_features,
                            days=self.window_days
                        )

                        # Guardar en caché
                        if not defillama_df.empty:
                            self._save_to_cache(defillama_df, "defillama")
                            logger.info(f"✓ DefiLlama data descargada: {len(defillama_df)} registros")
                        else:
                            logger.warning("⚠️ DefiLlama data vacía")

                    except Exception as e:
                        logger.error(f"❌ Error descargando DefiLlama: {e}")
                        defillama_df = pd.DataFrame()

                result['defillama'] = defillama_df

            # 6. Coinglass Data (Derivados - Freemium)
            if include_onchain:  # Usamos el mismo flag
                coinglass_df = self._load_from_cache("coinglass")

                if coinglass_df.empty:
                    logger.info("📈 Descargando datos de Derivados (Coinglass)...")
                    try:
                        # Lazy import
                        from coinglass_fetcher import CoinglassFetcher

                        # Extraer API key si existe
                        coinglass_key = None
                        if api_keys and 'coinglass' in api_keys:
                            coinglass_key = api_keys['coinglass']

                        fetcher = CoinglassFetcher(api_key=coinglass_key)

                        # Ejecutar en thread separado
                        symbol_base = self.symbol.split('/')[0]  # "ETH"
                        coinglass_df = await asyncio.to_thread(
                            fetcher.get_derivatives_features,
                            symbol=symbol_base,
                            days=self.window_days
                        )

                        # Guardar en caché
                        if not coinglass_df.empty:
                            self._save_to_cache(coinglass_df, "coinglass")
                            logger.info(f"✓ Coinglass data descargada: {len(coinglass_df)} registros")
                        else:
                            logger.warning("⚠️ Coinglass data vacía")

                    except Exception as e:
                        logger.error(f"❌ Error descargando Coinglass: {e}")
                        coinglass_df = pd.DataFrame()

                result['coinglass'] = coinglass_df

            return result
        finally:
            await self.close_exchange()

    async def update_daily(self, existing_df):
        """Actualiza precios y macro en caché y retorna los precios nuevos"""
        # 1. Actualizar Precios
        new_crypto = await self._fetch_symbol_data(self.symbol)
        self._save_to_cache(new_crypto, "prices")
        
        # 2. Actualizar Macro (Silencioso)
        btcdom = await self._fetch_symbol_data("BTCDOM/USDT")
        if not btcdom.empty:
            macro = pd.DataFrame({'BTCDOM': btcdom['close']})
            self._save_to_cache(macro, "macro")
            
        return new_crypto

    def fetch_macro_data(self):
        """
        Método de compatibilidad para el Orquestador.
        Retorna los datos macro desde el caché (actualizados por update_daily).
        """
        return self._load_from_cache("macro")