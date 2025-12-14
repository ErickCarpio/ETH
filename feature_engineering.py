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

        # ===== PHASE 3: STATISTICAL FEATURES =====

        # Rolling Statistics (skewness, kurtosis) sobre ventanas variables
        for w in [12, 24, 72]:  # 12h (2d), 24h (1d), 72h (3d)
            # Skewness (asimetría) - detecta distribuciones asimétricas
            df[f'returns_skew_{w}h'] = df['returns'].rolling(w).skew()

            # Kurtosis (curtosis) - detecta colas gordas (risk of extreme moves)
            df[f'returns_kurt_{w}h'] = df['returns'].rolling(w).kurt()

            # Volume skew y kurtosis
            df[f'volume_skew_{w}h'] = df['volume'].rolling(w).skew()
            df[f'volume_kurt_{w}h'] = df['volume'].rolling(w).kurt()

        # Autocorrelation of returns (momentum persistence)
        df['returns_autocorr_6h'] = df['returns'].rolling(6).apply(lambda x: x.autocorr(), raw=False)
        df['returns_autocorr_24h'] = df['returns'].rolling(24).apply(lambda x: x.autocorr(), raw=False)

        # Volatility Clustering (GARCH-like)
        # Si volatilidad actual > volatilidad pasada → clustering
        df['vol_clustering_24h'] = df['volatility_24h'] / (df['volatility_24h'].shift(6) + 1e-8)

        # Squared returns (proxy for realized variance)
        df['returns_squared'] = df['returns'] ** 2
        df['vol_garch_proxy'] = df['returns_squared'].rolling(24).mean()

        # Volume Profile Features
        # Price range vs volume
        df['price_range'] = (df['high'] - df['low']) / (df['close'] + 1e-8)
        df['volume_price_range'] = df['volume'] * df['price_range']

        # Volume momentum
        df['volume_ma_24h'] = df['volume'].rolling(24).mean()
        df['volume_momentum'] = df['volume'] / (df['volume_ma_24h'] + 1e-8)

        # Volume trend
        df['volume_trend_24h'] = df['volume'].rolling(24).apply(
            lambda x: 1 if x.iloc[-1] > x.iloc[0] else -1, raw=False
        )

        # Support/Resistance Detection (simplified)
        # Local minima/maxima en ventanas rolling
        df['is_local_min'] = ((df['low'] == df['low'].rolling(12, center=True).min())).astype(int)
        df['is_local_max'] = ((df['high'] == df['high'].rolling(12, center=True).max())).astype(int)

        # Distance to recent support/resistance
        rolling_min = df['low'].rolling(72).min()
        rolling_max = df['high'].rolling(72).max()

        df['dist_to_support'] = (df['close'] - rolling_min) / (df['close'] + 1e-8)
        df['dist_to_resistance'] = (rolling_max - df['close']) / (df['close'] + 1e-8)

        # Support/Resistance strength (how many times price tested this level)
        df['support_strength'] = (df['low'].rolling(72).apply(
            lambda x: (abs(x - x.min()) < x.min() * 0.01).sum(), raw=False
        ))

        df['resistance_strength'] = (df['high'].rolling(72).apply(
            lambda x: (abs(x - x.max()) < x.max() * 0.01).sum(), raw=False
        ))

        # Fill NaN from Phase 3 features
        phase3_cols = [
            'returns_skew_12h', 'returns_skew_24h', 'returns_skew_72h',
            'returns_kurt_12h', 'returns_kurt_24h', 'returns_kurt_72h',
            'volume_skew_12h', 'volume_skew_24h', 'volume_skew_72h',
            'volume_kurt_12h', 'volume_kurt_24h', 'volume_kurt_72h',
            'returns_autocorr_6h', 'returns_autocorr_24h',
            'vol_clustering_24h', 'returns_squared', 'vol_garch_proxy',
            'price_range', 'volume_price_range', 'volume_ma_24h', 'volume_momentum', 'volume_trend_24h',
            'is_local_min', 'is_local_max', 'dist_to_support', 'dist_to_resistance',
            'support_strength', 'resistance_strength'
        ]
        for col in phase3_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)

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
                           defillama_df=None, coinglass_df=None, microstructure_df=None, derivatives_df=None):
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

        # Derivatives Features (Fase 2 - Funding, Liquidations, Open Interest)
        if derivatives_df is not None and not derivatives_df.empty:
            try:
                # Resample a 4h (datos vienen cada 1s para funding, 30s para OI)
                deriv_res = derivatives_df.resample('4h').agg({
                    # Funding Rate
                    'funding_rate': 'last',  # Último valor
                    'funding_rate_ma_10': 'last',
                    'funding_rate_std_10': 'last',
                    'funding_rate_delta': 'sum',  # Cambio total en 4h

                    # Liquidations (sum over 4h window)
                    'liq_count_5m': 'sum',
                    'liq_volume_5m': 'sum',
                    'liq_notional_5m': 'sum',
                    'liq_long_pct': 'mean',  # Promedio de %
                    'liq_short_pct': 'mean',
                    'liq_imbalance': 'mean',

                    # Open Interest
                    'oi': 'last',  # Último valor
                    'oi_delta': 'sum',  # Delta total en 4h
                    'oi_delta_pct': 'mean'
                })

                # Flatten columns si hay multi-level
                deriv_res.columns = ['_'.join(col).strip('_') if isinstance(col, tuple) else col
                                    for col in deriv_res.columns]

                df = df.join(deriv_res, how='left')
                logger.info(f"✓ Derivatives features agregadas: {list(deriv_res.columns)}")

                # Crear features derivadas
                if 'funding_rate_last' in df.columns:
                    # Funding rate regime
                    df['funding_extreme'] = (abs(df['funding_rate_last']) > 0.0005).astype(int)

                    # Funding rate momentum (cambio en funding)
                    df['funding_momentum'] = df['funding_rate_last'].diff()

                if 'liq_imbalance_mean' in df.columns:
                    # Liquidation cascade: muchas liquidaciones con fuerte imbalance
                    df['liq_cascade_risk'] = (
                        (df['liq_count_5m_sum'] > df['liq_count_5m_sum'].quantile(0.75)) &
                        (abs(df['liq_imbalance_mean']) > 0.5)
                    ).astype(int)

                if 'oi_last' in df.columns and 'oi_delta_sum' in df.columns:
                    # OI change rate
                    df['oi_change_rate'] = df['oi_delta_sum'] / (df['oi_last'] + 1e-8)

                # Advanced Ratios (Phase 2 completion)
                if 'oi_last' in df.columns and 'volume' in df.columns:
                    # OI/Volume ratio - indica apalancamiento del mercado
                    df['oi_volume_ratio'] = df['oi_last'] / (df['volume'] + 1e-8)

                if 'funding_rate_last' in df.columns and 'oi_last' in df.columns:
                    # Funding/OI ratio - cost of leverage
                    df['funding_oi_ratio'] = df['funding_rate_last'] * df['oi_last']

                if 'liq_volume_5m_sum' in df.columns and 'volume' in df.columns:
                    # Liquidation/Volume ratio - stress indicator
                    df['liq_volume_ratio'] = df['liq_volume_5m_sum'] / (df['volume'] + 1e-8)

                if 'liq_notional_5m_sum' in df.columns:
                    # Liquidation intensity per hour
                    df['liq_intensity'] = df['liq_notional_5m_sum'] / 4.0  # 4h window

                # Statistical Features (Phase 2 completion)
                if 'funding_rate_last' in df.columns:
                    # Funding rate volatility
                    df['funding_vol_24h'] = df['funding_rate_last'].rolling(6).std()  # 6 periods = 24h
                    df['funding_vol_7d'] = df['funding_rate_last'].rolling(42).std()  # 42 periods = 7d

                    # Funding rate trend
                    df['funding_trend_24h'] = df['funding_rate_last'].rolling(6).apply(
                        lambda x: 1 if x.iloc[-1] > x.iloc[0] else -1, raw=False
                    )

                if 'oi_last' in df.columns:
                    # OI volatility
                    df['oi_vol_24h'] = df['oi_last'].pct_change().rolling(6).std()
                    df['oi_vol_7d'] = df['oi_last'].pct_change().rolling(42).std()

                    # OI autocorrelation (persistence)
                    df['oi_autocorr'] = df['oi_last'].rolling(12).apply(
                        lambda x: x.autocorr(), raw=False
                    )

                if 'liq_count_5m_sum' in df.columns:
                    # Liquidation clustering
                    df['liq_cluster_24h'] = df['liq_count_5m_sum'].rolling(6).sum()
                    df['liq_cluster_7d'] = df['liq_count_5m_sum'].rolling(42).sum()

                    # Liquidation spike detection
                    liq_mean = df['liq_count_5m_sum'].rolling(24).mean()
                    liq_std = df['liq_count_5m_sum'].rolling(24).std()
                    df['liq_spike'] = ((df['liq_count_5m_sum'] - liq_mean) / (liq_std + 1e-8)).clip(-5, 5)

                if 'liq_imbalance_mean' in df.columns:
                    # Liquidation regime persistence
                    df['liq_regime_persist'] = df['liq_imbalance_mean'].rolling(6).mean()

                # Cross-derivatives features
                if 'funding_rate_last' in df.columns and 'liq_imbalance_mean' in df.columns:
                    # Funding-Liquidation correlation
                    df['funding_liq_corr'] = df['funding_rate_last'].rolling(12).corr(df['liq_imbalance_mean'])

                if 'oi_change_rate' in df.columns and 'funding_rate_last' in df.columns:
                    # OI growth with high funding = risky longs building
                    df['oi_funding_risk'] = df['oi_change_rate'] * df['funding_rate_last']

                # Cross-asset features (BTC dominance interactions)
                if 'BTCDOM' in df.columns:
                    # BTC dominance trend
                    df['btcdom_trend'] = df['BTCDOM'].diff()
                    df['btcdom_vol'] = df['BTCDOM'].rolling(6).std()

                    # ETH performance vs BTC dominance
                    if 'returns' in df.columns:
                        df['eth_vs_btcdom'] = df['returns'] * (-df['btcdom_trend'])  # ETH up when BTC.D down

                    # Funding rate vs BTC dominance
                    if 'funding_rate_last' in df.columns:
                        df['funding_vs_btcdom'] = df['funding_rate_last'] * df['btcdom_trend']

                # Price-Derivatives interactions
                if 'returns' in df.columns:
                    if 'funding_rate_last' in df.columns:
                        # Returns-Funding correlation
                        df['returns_funding_corr'] = df['returns'].rolling(12).corr(df['funding_rate_last'])

                    if 'liq_imbalance_mean' in df.columns:
                        # Price moves with liquidation direction
                        df['returns_liq_sync'] = df['returns'] * df['liq_imbalance_mean']

                    if 'oi_change_rate' in df.columns:
                        # Price-OI divergence (bearish if OI grows but price falls)
                        df['price_oi_divergence'] = df['returns'] - df['oi_change_rate']

                # Volatility-Derivatives interactions
                if 'ATR' in df.columns:
                    if 'liq_cluster_24h' in df.columns:
                        # Volatility with liquidation clusters
                        df['vol_liq_stress'] = df['ATR'] * df['liq_cluster_24h']

                    if 'funding_vol_24h' in df.columns:
                        # Combined volatility measure
                        df['combined_vol'] = df['ATR'] * df['funding_vol_24h']

            except Exception as e:
                logger.warning(f"⚠️ Error agregando derivatives features: {e}")

        # Fill NaN para derivatives features si no se agregaron
        deriv_cols = [
            # Base derivatives
            'funding_rate_last', 'funding_rate_ma_10_last', 'funding_rate_std_10_last',
            'funding_rate_delta_sum', 'liq_count_5m_sum', 'liq_volume_5m_sum',
            'liq_notional_5m_sum', 'liq_long_pct_mean', 'liq_short_pct_mean',
            'liq_imbalance_mean', 'oi_last', 'oi_delta_sum', 'oi_delta_pct_mean',
            # Derived features
            'funding_extreme', 'funding_momentum', 'liq_cascade_risk', 'oi_change_rate',
            # Advanced ratios
            'oi_volume_ratio', 'funding_oi_ratio', 'liq_volume_ratio', 'liq_intensity',
            # Statistical features
            'funding_vol_24h', 'funding_vol_7d', 'funding_trend_24h',
            'oi_vol_24h', 'oi_vol_7d', 'oi_autocorr',
            'liq_cluster_24h', 'liq_cluster_7d', 'liq_spike', 'liq_regime_persist',
            # Cross-derivatives
            'funding_liq_corr', 'oi_funding_risk',
            # Cross-asset
            'btcdom_trend', 'btcdom_vol', 'eth_vs_btcdom', 'funding_vs_btcdom',
            # Price-Derivatives interactions
            'returns_funding_corr', 'returns_liq_sync', 'price_oi_divergence',
            # Volatility-Derivatives interactions
            'vol_liq_stress', 'combined_vol'
        ]
        for col in deriv_cols:
            if col not in df.columns:
                df[col] = 0.0
            else:
                df[col] = df[col].fillna(0)

        df.dropna(inplace=True)
        cols_to_drop = ['open', 'high', 'low', 'close', 'volume']
        self.feature_names = [c for c in df.columns if c not in cols_to_drop]

        return df