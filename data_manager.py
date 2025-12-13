"""
Data Manager - Gestión de Datos con CACHÉ LOCAL
Guarda datos en disco (/data). Incluye compatibilidad con Orquestador.
"""
import ccxt.async_support as ccxt
import pandas as pd
from datetime import datetime, timedelta
import asyncio
import logging
from pathlib import Path
import os

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
            
            # 3. Sentiment & Onchain (Carga simple de caché por ahora)
            if include_sentiment:
                result['sentiment'] = self._load_from_cache("sentiment")
            if include_onchain:
                result['onchain'] = self._load_from_cache("onchain")
                
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