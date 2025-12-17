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

        # ===== PHASE 4: TSFRESH-INSPIRED FEATURES =====
        # Implementación manual de features populares de tsfresh
        # Más eficiente que correr tsfresh completo en cada timestep

        # Change Quantiles - detecta magnitud de cambios en diferentes percentiles
        for w in [12, 24]:
            # Quantile changes in returns
            df[f'returns_q10_{w}h'] = df['returns'].rolling(w).quantile(0.1)
            df[f'returns_q90_{w}h'] = df['returns'].rolling(w).quantile(0.9)
            df[f'returns_iqr_{w}h'] = df[f'returns_q90_{w}h'] - df[f'returns_q10_{w}h']

        # Absolute Sum of Changes - momentum indicator
        df['abs_sum_changes_24h'] = df['returns'].rolling(24).apply(lambda x: np.abs(np.diff(x)).sum(), raw=False)

        # Count Above/Below Mean - regime persistence
        for w in [12, 24]:
            mean_val = df['close'].rolling(w).mean()
            df[f'count_above_mean_{w}h'] = (df['close'] > mean_val).rolling(w).sum()
            df[f'count_below_mean_{w}h'] = (df['close'] < mean_val).rolling(w).sum()

        # Longest Strike Above/Below Mean - trend strength
        def longest_strike_above_mean(x):
            if len(x) < 2:
                return 0
            mean_val = x.mean()
            above = x > mean_val
            max_strike = 0
            current_strike = 0
            for val in above:
                if val:
                    current_strike += 1
                    max_strike = max(max_strike, current_strike)
                else:
                    current_strike = 0
            return max_strike

        df['longest_strike_above_24h'] = df['close'].rolling(24).apply(longest_strike_above_mean, raw=False)

        # Number of Crossings (mean) - volatility/indecision
        def count_mean_crossings(x):
            if len(x) < 2:
                return 0
            mean_val = x.mean()
            above = x > mean_val
            return (above.diff() != 0).sum()

        df['mean_crossings_24h'] = df['close'].rolling(24).apply(count_mean_crossings, raw=False)

        # Linear Trend - price/volume direction
        def linear_trend_slope(x):
            if len(x) < 2:
                return 0
            indices = np.arange(len(x))
            try:
                slope = np.polyfit(indices, x, 1)[0]
                return slope
            except:
                return 0

        df['price_trend_slope_24h'] = df['close'].rolling(24).apply(linear_trend_slope, raw=False)
        df['volume_trend_slope_24h'] = df['volume'].rolling(24).apply(linear_trend_slope, raw=False)

        # Variance Larger Than Standard Deviation - distribution check
        df['var_larger_std_24h'] = (
            df['returns'].rolling(24).var() > df['returns'].rolling(24).std()
        ).astype(int)

        # Ratio Beyond r Sigma - outlier detection
        def ratio_beyond_r_sigma(x, r=2):
            if len(x) < 2:
                return 0
            mean_val = x.mean()
            std_val = x.std()
            if std_val == 0:
                return 0
            beyond = np.abs(x - mean_val) > (r * std_val)
            return beyond.sum() / len(x)

        df['ratio_beyond_2sigma_24h'] = df['returns'].rolling(24).apply(
            lambda x: ratio_beyond_r_sigma(x, r=2), raw=False
        )

        # Range Count - number of unique values in range
        df['range_count_24h'] = df['close'].rolling(24).apply(lambda x: len(np.unique(x.round(2))), raw=False)

        # Approximate Entropy - complexity measure
        def approximate_entropy(x, m=2, r=0.2):
            """Simplified ApEn calculation"""
            if len(x) < m + 1:
                return 0
            try:
                std_val = x.std()
                if std_val == 0:
                    return 0
                r_scaled = r * std_val

                def _maxdist(x_i, x_j, m):
                    return max([abs(ua - va) for ua, va in zip(x_i, x_j)])

                def _phi(m):
                    patterns = np.array([[x[j] for j in range(i, i + m)] for i in range(len(x) - m + 1)])
                    C = []
                    for pattern in patterns:
                        count = sum([1 for p in patterns if _maxdist(p, pattern, m) <= r_scaled])
                        C.append(count / (len(x) - m + 1))
                    return np.mean(np.log(C))

                return abs(_phi(m) - _phi(m + 1))
            except:
                return 0

        df['approx_entropy_24h'] = df['returns'].rolling(24).apply(
            lambda x: approximate_entropy(x.values), raw=False
        )

        # Benford Correlation - first digit distribution (detects manipulation)
        def benford_correlation(x):
            """Correlation with Benford's Law"""
            if len(x) < 2:
                return 0
            try:
                # Get first digits
                first_digits = []
                for val in x:
                    if val != 0:
                        first_digit = int(str(abs(val)).replace('.', '')[0])
                        if first_digit > 0:
                            first_digits.append(first_digit)

                if len(first_digits) < 2:
                    return 0

                # Benford distribution
                benford = np.array([np.log10(1 + 1/d) for d in range(1, 10)])

                # Observed distribution
                observed = np.zeros(9)
                for digit in first_digits:
                    observed[digit - 1] += 1
                observed = observed / observed.sum()

                # Correlation
                return np.corrcoef(benford, observed)[0, 1]
            except:
                return 0

        df['benford_corr_24h'] = df['volume'].rolling(24).apply(benford_correlation, raw=False)

        # Fill NaN from Phase 4 features
        phase4_cols = [
            'returns_q10_12h', 'returns_q90_12h', 'returns_iqr_12h',
            'returns_q10_24h', 'returns_q90_24h', 'returns_iqr_24h',
            'abs_sum_changes_24h',
            'count_above_mean_12h', 'count_below_mean_12h',
            'count_above_mean_24h', 'count_below_mean_24h',
            'longest_strike_above_24h', 'mean_crossings_24h',
            'price_trend_slope_24h', 'volume_trend_slope_24h',
            'var_larger_std_24h', 'ratio_beyond_2sigma_24h',
            'range_count_24h', 'approx_entropy_24h', 'benford_corr_24h'
        ]
        for col in phase4_cols:
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

        # ===== PHASE 1: MICROSTRUCTURE FEATURES (REAL DATA FROM QUESTDB) =====
        # Import microstructure integration module
        try:
            from features.microstructure.microstructure_integration import (
                add_microstructure_features,
                add_microstructure_interactions
            )

            # Add microstructure features from QuestDB data
            df = add_microstructure_features(df, microstructure_df)

            logger.info("✅ Microstructure features agregadas (19 features)")

        except Exception as e:
            logger.warning(f"⚠️ No se pudieron agregar microstructure features: {e}")
            # Continuar sin microstructure (placeholders serán agregados automáticamente)

        # ===== PHASE 4: STATISTICAL FEATURES (ADVANCED ANALYSIS) =====
        # Advanced statistical analysis: Hurst, Entropy, Kalman, Wavelets
        try:
            from features.statistical.hurst_calculator import HurstCalculator
            from features.statistical.entropy_calculator import EntropyCalculator
            from features.statistical.kalman_filter import KalmanFeatureExtractor
            from features.statistical.wavelet_features import WaveletFeatures

            # Hurst Exponent (memory and regime detection)
            hurst_calc = HurstCalculator()
            hurst_features = hurst_calc.calculate_all_features(df, price_col='close')
            for key, value in hurst_features.items():
                df[key] = value

            # Entropy (complexity and predictability)
            entropy_calc = EntropyCalculator()
            entropy_features = entropy_calc.calculate_all_features(df, price_col='close')
            for key, value in entropy_features.items():
                df[key] = value

            # Kalman Filter (state estimation and noise reduction)
            kalman_calc = KalmanFeatureExtractor()
            kalman_features = kalman_calc.calculate_all_features(df, price_col='close', auto_tune=True)
            for key, value in kalman_features.items():
                df[key] = value

            # Wavelets and FFT (frequency analysis)
            wavelet_calc = WaveletFeatures()
            wavelet_features = wavelet_calc.calculate_all_features(df, price_col='close')
            for key, value in wavelet_features.items():
                df[key] = value

            logger.info("✅ FASE 4 Statistical features agregadas (~100 features)")
            logger.info(f"  - Hurst: {len(hurst_features)} features")
            logger.info(f"  - Entropy: {len(entropy_features)} features")
            logger.info(f"  - Kalman: {len(kalman_features)} features")
            logger.info(f"  - Wavelet/FFT: {len(wavelet_features)} features")

        except Exception as e:
            logger.warning(f"⚠️ No se pudieron agregar statistical features (FASE 4): {e}")
            import traceback
            logger.warning(traceback.format_exc())
            # Continuar sin statistical features

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

        # ===== PHASE 5: FEATURE INTERACTIONS =====
        # Polynomial features (degree 2) y ratios inteligentes entre features clave

        # 1. MOMENTUM × VOLATILITY INTERACTIONS
        if 'returns' in df.columns and 'volatility_24h' in df.columns:
            df['momentum_vol_interaction'] = df['returns'] * df['volatility_24h']
            df['returns_volatility_ratio'] = df['returns'] / (df['volatility_24h'] + 1e-8)

        if 'RSI_14' in df.columns and 'volatility_24h' in df.columns:
            df['rsi_vol_interaction'] = (df['RSI_14'] - 50) * df['volatility_24h']

        # 2. MICROSTRUCTURE × PRICE INTERACTIONS (REAL DATA)
        try:
            from features.microstructure.microstructure_integration import add_microstructure_interactions
            df = add_microstructure_interactions(df)
            logger.info("✅ Microstructure interactions agregadas (12 features)")
        except Exception as e:
            logger.warning(f"⚠️ No se pudieron agregar microstructure interactions: {e}")

        # 3. DERIVATIVES × PRICE INTERACTIONS
        if 'funding_rate_last' in df.columns and 'returns' in df.columns:
            df['funding_returns_carry'] = df['funding_rate_last'] * df['returns']
            df['funding_returns_divergence'] = abs(df['funding_rate_last']) - abs(df['returns'])

        if 'liq_imbalance_mean' in df.columns and 'returns' in df.columns:
            df['liq_price_confirmation'] = df['liq_imbalance_mean'] * df['returns']

        if 'oi_change_rate' in df.columns and 'volume' in df.columns:
            df['oi_volume_buildup'] = df['oi_change_rate'] * np.log1p(df['volume'])

        # 4. RATIOS IMPORTANTES
        # Volume-based ratios
        if 'volume' in df.columns:
            df['volume_ma_6h'] = df['volume'].rolling(6).mean()
            df['volume_ma_72h'] = df['volume'].rolling(72).mean()

            if 'volume_ma_6h' in df.columns and 'volume_ma_72h' in df.columns:
                df['volume_trend_ratio'] = df['volume_ma_6h'] / (df['volume_ma_72h'] + 1e-8)

        # Volatility ratios
        if 'volatility_6h' in df.columns and 'volatility_72h' in df.columns:
            df['volatility_expansion'] = df['volatility_6h'] / (df['volatility_72h'] + 1e-8)

        # Microstructure ratios - Now included in add_microstructure_interactions()
        # obi_depth_ratio, spread_vol_ratio

        # Derivatives ratios
        if 'liq_long_pct_mean' in df.columns and 'liq_short_pct_mean' in df.columns:
            df['liq_long_short_ratio'] = df['liq_long_pct_mean'] / (df['liq_short_pct_mean'] + 1e-8)

        # 5. CONDITIONAL FEATURES (If-Then Logic)
        # extreme_risk_regime, manipulation_signal - Now included in add_microstructure_interactions()

        # High funding + increasing OI = overleveraged longs
        if 'funding_rate_last' in df.columns and 'oi_change_rate' in df.columns:
            funding_high = df['funding_rate_last'] > df['funding_rate_last'].quantile(0.75)
            oi_increasing = df['oi_change_rate'] > 0
            df['overleveraged_longs'] = (funding_high & oi_increasing).astype(int)

        # Liquidation cascade + price drop = capitulation
        if 'liq_cascade_risk' in df.columns and 'returns' in df.columns:
            cascade_risk = df['liq_cascade_risk'] == 1
            price_drop = df['returns'] < -0.02
            df['capitulation_signal'] = (cascade_risk & price_drop).astype(int)

        # resistance_rejection - Now included in add_microstructure_interactions()

        # 6. POLYNOMIAL FEATURES (Selected Key Features)
        # Square of important features
        if 'returns' in df.columns:
            df['returns_squared_interaction'] = df['returns'] ** 2

        # obi_squared - Now included in add_microstructure_interactions()

        if 'funding_rate_last' in df.columns:
            df['funding_squared'] = df['funding_rate_last'] ** 2

        # 7. CROSS-FEATURE PRODUCTS (Most Predictive Combinations)
        if 'RSI_14' in df.columns and 'volume_momentum' in df.columns:
            df['rsi_volume_momentum'] = (df['RSI_14'] - 50) * df['volume_momentum']

        if 'returns_skew_24h' in df.columns and 'returns_kurt_24h' in df.columns:
            df['distribution_risk'] = df['returns_skew_24h'] * df['returns_kurt_24h']

        if 'support_strength' in df.columns and 'dist_to_support' in df.columns:
            df['support_conviction'] = df['support_strength'] * (1 / (df['dist_to_support'] + 0.01))

        # 8. REGIME-BASED FEATURES
        # Define regime based on volatility and trend
        if 'volatility_24h' in df.columns and 'returns' in df.columns:
            vol_median = df['volatility_24h'].median()
            returns_median = df['returns'].median()

            # 4 regimes: low_vol_up, low_vol_down, high_vol_up, high_vol_down
            low_vol = df['volatility_24h'] < vol_median
            high_vol = df['volatility_24h'] >= vol_median
            up_trend = df['returns'] > returns_median
            down_trend = df['returns'] <= returns_median

            df['regime_low_vol_up'] = (low_vol & up_trend).astype(int)
            df['regime_low_vol_down'] = (low_vol & down_trend).astype(int)
            df['regime_high_vol_up'] = (high_vol & up_trend).astype(int)
            df['regime_high_vol_down'] = (high_vol & down_trend).astype(int)

        # 9. COMPOSITE INDICATORS
        # Combined momentum score
        if 'returns' in df.columns and 'RSI_14' in df.columns and 'volume_momentum' in df.columns:
            df['momentum_composite'] = (
                df['returns'].rolling(6).mean() * 0.4 +
                (df['RSI_14'] - 50) / 50 * 0.3 +
                df['volume_momentum'] * 0.3
            )

        # liquidity_stress_composite REMOVED (uses spread + VPIN - no real order book data)

        # Combined leverage risk
        if 'funding_rate_last' in df.columns and 'oi_change_rate' in df.columns and 'liq_count_5m_sum' in df.columns:
            funding_norm = (df['funding_rate_last'] - df['funding_rate_last'].mean()) / (df['funding_rate_last'].std() + 1e-8)
            oi_norm = (df['oi_change_rate'] - df['oi_change_rate'].mean()) / (df['oi_change_rate'].std() + 1e-8)
            liq_norm2 = (df['liq_count_5m_sum'] - df['liq_count_5m_sum'].mean()) / (df['liq_count_5m_sum'].std() + 1e-8)

            df['leverage_risk_composite'] = (funding_norm + oi_norm + liq_norm2) / 3

        # Fill NaN for Phase 5 features (CLEANED - removed simulated microstructure features)
        phase5_cols = [
            # Momentum × Volatility (3)
            'momentum_vol_interaction', 'returns_volatility_ratio', 'rsi_vol_interaction',
            # Derivatives × Price (4)
            'funding_returns_carry', 'funding_returns_divergence', 'liq_price_confirmation', 'oi_volume_buildup',
            # Ratios (3)
            'volume_ma_6h', 'volume_ma_72h', 'volume_trend_ratio', 'volatility_expansion',
            'liq_long_short_ratio',
            # Conditional (2 - removed 3)
            'overleveraged_longs', 'capitulation_signal',
            # Polynomial (2 - removed 1)
            'returns_squared_interaction', 'funding_squared',
            # Cross-products (3)
            'rsi_volume_momentum', 'distribution_risk', 'support_conviction',
            # Regime (4)
            'regime_low_vol_up', 'regime_low_vol_down', 'regime_high_vol_up', 'regime_high_vol_down',
            # Composites (2 - removed 1)
            'momentum_composite', 'leverage_risk_composite'
        ]
        for col in phase5_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)

        # ===== PHASE 6: TSFRESH AUTO-GENERATION (100 features) =====
        # Automated feature extraction from 7 key time series
        try:
            from features.automated import get_tsfresh_features

            # Create target for feature selection (next period price movement)
            target = df['close'].pct_change().shift(-1)
            target = (target > 0).astype(int)  # Binary: up (1) or down (0)

            # Key time series for tsfresh extraction
            tsfresh_columns = [
                'close',  # Price
                'volume',  # Volume
                'OBI_L5',  # Order Book Imbalance
                'VPIN',  # Volume-synchronized PIN
                'funding_rate_last',  # Funding rate (renamed from funding_rate)
                'stablecoin_flow_7d',  # Stablecoin flows
                'open_interest_norm'  # Open Interest
            ]

            # Filter to available columns
            available_tsfresh_cols = [col for col in tsfresh_columns if col in df.columns]

            if len(available_tsfresh_cols) >= 3:  # Need at least 3 time series
                logger.info(f"Extracting tsfresh features from {len(available_tsfresh_cols)} time series...")

                tsfresh_features = get_tsfresh_features(
                    df,
                    target,
                    columns=available_tsfresh_cols,
                    n_top=100,  # Select top 100 features
                    use_cache=True  # Cache for fast reuse
                )

                if not tsfresh_features.empty:
                    # Merge tsfresh features
                    df = df.join(tsfresh_features, how='left')
                    df = df.fillna(method='ffill').fillna(0)

                    logger.info(f"✅ FASE 6: tsfresh features agregadas ({tsfresh_features.shape[1]} features)")
                    logger.info(f"  Sample features: {list(tsfresh_features.columns[:5])}")
                else:
                    logger.warning("⚠️ tsfresh returned empty features")
            else:
                logger.warning(f"⚠️ Only {len(available_tsfresh_cols)} time series available for tsfresh (need 3+)")

        except ImportError:
            logger.warning("⚠️ tsfresh not available - install with: pip install tsfresh")
        except Exception as e:
            logger.warning(f"⚠️ Could not add tsfresh features (FASE 6): {e}")
            import traceback
            logger.warning(traceback.format_exc())

        df.dropna(inplace=True)
        cols_to_drop = ['open', 'high', 'low', 'close', 'volume']
        self.feature_names = [c for c in df.columns if c not in cols_to_drop]

        return df