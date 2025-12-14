"""
Feature Engineering - Construcción de Features
CORREGIDO: Pandas FutureWarnings ('4H' -> '4h')
"""
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FeatureEngineer:
    def __init__(self):
        self.feature_names = []
    
    def create_technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        
        for w in [6, 24, 72]:
            df[f'volatility_{w}h'] = df['returns'].rolling(w).std()
            
        # RSI 14
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-8)
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # ATR 14
        tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
        df['atr_14'] = tr.rolling(14).mean()
            
        return df
    
    def merge_macro_features(self, df: pd.DataFrame, macro_df: pd.DataFrame) -> pd.DataFrame:
        """Fusiona datos macro (BTCDOM)"""
        df = df.copy()
        
        if macro_df is None or macro_df.empty or not isinstance(macro_df.index, pd.DatetimeIndex):
            df['BTCDOM_ROC'] = 0.0
            return df

        try:
            # FIX: Usar '4h' minúscula para evitar warnings
            macro_4h = macro_df.resample('4h').ffill()
            
            if 'BTCDOM' in macro_4h.columns:
                macro_4h['BTCDOM_ROC'] = macro_4h['BTCDOM'].pct_change()
                cols_to_join = ['BTCDOM_ROC']
                df = df.join(macro_4h[cols_to_join], how='left')
                df['BTCDOM_ROC'] = df['BTCDOM_ROC'].ffill().fillna(0)
            else:
                df['BTCDOM_ROC'] = 0.0
            
        except Exception as e:
            logger.error(f"Error macro features: {e}")
            df['BTCDOM_ROC'] = 0.0
        
        return df

    def build_full_features(self, crypto_df, macro_df, onchain_df=None, sentiment_df=None,
                           defillama_df=None, coinglass_df=None, microstructure_df=None):
        logger.info("Construyendo features...")
        df = self.create_technical_features(crypto_df)

        # On-chain seguro
        if onchain_df is not None and not onchain_df.empty:
            try:
                # FIX: Usar '4h' minúscula
                onchain_res = onchain_df.resample('4h').ffill()
                df = df.join(onchain_res, how='left')

                if 'net_flow' in df.columns:
                    # Z-Score robusto
                    rolling_mean = df['net_flow'].rolling(42).mean()
                    rolling_std = df['net_flow'].rolling(42).std()
                    df['Net_Flow_Z'] = ((df['net_flow'] - rolling_mean) / (rolling_std + 1e-8)).clip(-5,5)
            except: pass

        if 'Net_Flow_Z' not in df.columns: df['Net_Flow_Z'] = 0.0

        # Macro
        df = self.merge_macro_features(df, macro_df)

        # Sentiment
        if sentiment_df is not None and 'FinBERT_Score' in sentiment_df.columns:
            df = df.join(sentiment_df[['FinBERT_Score']], how='left')

        # Ensure FinBERT_Score column exists (create with default value if missing)
        if 'FinBERT_Score' not in df.columns:
            df['FinBERT_Score'] = 0.0
        else:
            df['FinBERT_Score'] = df['FinBERT_Score'].fillna(0)

        # DefiLlama (Stablecoins)
        if defillama_df is not None and not defillama_df.empty:
            try:
                # Resample a 4h
                defillama_res = defillama_df.resample('4h').ffill()
                df = df.join(defillama_res, how='left')
                logger.info(f"✓ DefiLlama features agregadas: {list(defillama_res.columns)}")
            except Exception as e:
                logger.warning(f"⚠️ Error agregando DefiLlama features: {e}")

        # Coinglass (Derivados)
        if coinglass_df is not None and not coinglass_df.empty:
            try:
                # Resample a 4h
                coinglass_res = coinglass_df.resample('4h').ffill()
                df = df.join(coinglass_res, how='left')
                logger.info(f"✓ Coinglass features agregadas: {list(coinglass_res.columns)}")
            except Exception as e:
                logger.warning(f"⚠️ Error agregando Coinglass features: {e}")

        # Fill NaN para features de DefiLlama/Coinglass si no se agregaron
        for col in ['stablecoin_mcap', 'stablecoin_flow_7d', 'stablecoin_trend',
                   'open_interest_norm', 'oi_change', 'funding_rate']:
            if col not in df.columns:
                df[col] = 0.0
            else:
                df[col] = df[col].fillna(0)

        # Microstructure Features (Fase 1 - Real-time Order Book)
        if microstructure_df is not None and not microstructure_df.empty:
            try:
                # Resample a 4h (las features microestructurales vienen cada 1s o 10s)
                micro_res = microstructure_df.resample('4h').agg({
                    # OBI (Order Book Imbalance) - promedio en la ventana
                    'obi_5': 'mean',
                    'obi_10': 'mean',
                    'obi_20': 'mean',

                    # VPIN (Informed Trading Probability) - promedio y máximo
                    'vpin': ['mean', 'max'],

                    # OFI (Order Flow Imbalance) - suma acumulada
                    'ofi': 'sum',

                    # Spread metrics
                    'spread': 'mean',
                    'spread_bps': 'mean',

                    # Price metrics
                    'micro_price': 'mean',

                    # Kyle's Lambda (price impact)
                    'kyle_lambda': 'mean',

                    # Roll Spread
                    'roll_spread': 'mean'
                })

                # Flatten multi-level columns
                micro_res.columns = ['_'.join(col).strip('_') if isinstance(col, tuple) else col
                                    for col in micro_res.columns]

                df = df.join(micro_res, how='left')
                logger.info(f"✓ Microstructure features agregadas: {list(micro_res.columns)}")

                # Crear features derivadas
                if 'obi_5_mean' in df.columns and 'obi_20_mean' in df.columns:
                    # OBI divergence: cuando el corto plazo difiere del largo plazo
                    df['obi_divergence'] = df['obi_5_mean'] - df['obi_20_mean']

                if 'vpin_mean' in df.columns:
                    # VPIN regime: alta toxicidad vs normal
                    df['vpin_regime'] = (df['vpin_mean'] > 0.4).astype(int)

                if 'spread_bps_mean' in df.columns:
                    # Spread widening: indicador de volatilidad
                    df['spread_widening'] = df['spread_bps_mean'].pct_change()

            except Exception as e:
                logger.warning(f"⚠️ Error agregando microstructure features: {e}")

        # Fill NaN para microstructure features si no se agregaron
        micro_cols = ['obi_5_mean', 'obi_10_mean', 'obi_20_mean', 'vpin_mean', 'vpin_max',
                     'ofi_sum', 'spread_mean', 'spread_bps_mean', 'micro_price_mean',
                     'kyle_lambda_mean', 'roll_spread_mean', 'obi_divergence',
                     'vpin_regime', 'spread_widening']
        for col in micro_cols:
            if col not in df.columns:
                df[col] = 0.0
            else:
                df[col] = df[col].fillna(0)

        df.dropna(inplace=True)
        cols_to_drop = ['open', 'high', 'low', 'close', 'volume']
        self.feature_names = [c for c in df.columns if c not in cols_to_drop]

        return df