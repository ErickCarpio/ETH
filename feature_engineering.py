"""
Feature Engineering - Construcción de Features
ACTUALIZADO: Soporte para 15min (trading) + 4H (macro contexto) + Statistical Features
"""
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FeatureEngineer:
    def __init__(self, config: dict = None):
        self.feature_names = []
        self.config = config if config is not None else {}

        # Inicializar Statistical Feature Engine si está habilitado
        self.statistical_engine = None
        if self.config.get('features', {}).get('use_statistical', False):
            try:
                from features.statistical.statistical_features import StatisticalFeatureEngine
                stat_config = self.config.get('features', {}).get('statistical', {})
                self.statistical_engine = StatisticalFeatureEngine(stat_config)
                logger.info("✅ Statistical Feature Engine activado")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo inicializar Statistical Features: {e}")
                self.statistical_engine = None

    def create_technical_features(self, df: pd.DataFrame, timeframe='15m') -> pd.DataFrame:
        """
        Crea features técnicas adaptadas al timeframe

        Args:
            df: DataFrame con OHLCV
            timeframe: '15m' o '4h' para ajustar ventanas
        """
        df = df.copy()
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

        # Ajustar ventanas según timeframe
        if timeframe == '15m':
            # Ventanas en velas de 15min
            # 4 velas = 1h, 24 velas = 6h, 96 velas = 24h
            windows = [4, 24, 96]
            window_names = ['1h', '6h', '24h']
        else:  # 4h
            # Ventanas en velas de 4h
            # 6 velas = 1 día, 24 velas = 4 días, 72 velas = 12 días
            windows = [6, 24, 72]
            window_names = ['1d', '4d', '12d']

        for w, name in zip(windows, window_names):
            df[f'volatility_{name}'] = df['returns'].rolling(w).std()

        # RSI 14 (mantener 14 velas independiente del timeframe)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-8)
        df['rsi_14'] = 100 - (100 / (1 + rs))

        # ATR 14
        tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
        df['atr_14'] = tr.rolling(14).mean()

        return df

    def add_4h_macro_features(self, df_15min: pd.DataFrame, df_4h: pd.DataFrame) -> pd.DataFrame:
        """
        Agrega features de timeframe superior (4H) al timeframe de trading (15min)
        Estas features proveen contexto macro de tendencia

        Args:
            df_15min: DataFrame de 15min (trading timeframe)
            df_4h: DataFrame de 4H (macro timeframe)

        Returns:
            df_15min con features macro agregadas
        """
        if df_4h is None or df_4h.empty:
            logger.warning("⚠️ No hay datos de 4H, saltando features macro")
            return df_15min

        df = df_15min.copy()

        try:
            # Calcular features en 4H
            df_4h = df_4h.copy()
            df_4h['returns_4h'] = df_4h['close'].pct_change()

            # Tendencia (SMA)
            df_4h['sma_20_4h'] = df_4h['close'].rolling(20).mean()
            df_4h['sma_50_4h'] = df_4h['close'].rolling(50).mean()
            df_4h['trend_4h'] = (df_4h['sma_20_4h'] > df_4h['sma_50_4h']).astype(float)

            # Volatilidad 4H
            df_4h['volatility_24h_4h'] = df_4h['returns_4h'].rolling(24).std()  # 4 días

            # RSI 4H
            delta_4h = df_4h['close'].diff()
            gain_4h = (delta_4h.where(delta_4h > 0, 0)).rolling(14).mean()
            loss_4h = (-delta_4h.where(delta_4h < 0, 0)).rolling(14).mean()
            rs_4h = gain_4h / (loss_4h + 1e-8)
            df_4h['rsi_4h'] = 100 - (100 / (1 + rs_4h))

            # Momentum 4H
            df_4h['momentum_12h_4h'] = df_4h['close'].pct_change(3)  # 12 horas

            # Resamplear a 15min
            macro_cols = ['sma_20_4h', 'sma_50_4h', 'trend_4h', 'volatility_24h_4h', 'rsi_4h', 'momentum_12h_4h']
            df_4h_resampled = df_4h[macro_cols].resample('15min').ffill()

            # Join con df_15min
            df = df.join(df_4h_resampled, how='left')

            # Fill NaN
            for col in macro_cols:
                if col in df.columns:
                    df[col] = df[col].ffill().fillna(0)

            logger.info(f"✓ Agregadas {len(macro_cols)} features macro de 4H")

        except Exception as e:
            logger.error(f"❌ Error agregando features macro de 4H: {e}")
            # Agregar columnas vacías si falla
            for col in ['sma_20_4h', 'sma_50_4h', 'trend_4h', 'volatility_24h_4h', 'rsi_4h', 'momentum_12h_4h']:
                if col not in df.columns:
                    df[col] = 0.0

        return df

    def merge_macro_features(self, df: pd.DataFrame, macro_df: pd.DataFrame) -> pd.DataFrame:
        """Fusiona datos macro (BTCDOM)"""
        df = df.copy()

        if macro_df is None or macro_df.empty or not isinstance(macro_df.index, pd.DatetimeIndex):
            df['BTCDOM_ROC'] = 0.0
            return df

        try:
            # Resamplear a 15min para alinear con df
            macro_15m = macro_df.resample('15min').ffill()

            if 'BTCDOM' in macro_15m.columns:
                macro_15m['BTCDOM_ROC'] = macro_15m['BTCDOM'].pct_change()
                cols_to_join = ['BTCDOM_ROC']
                df = df.join(macro_15m[cols_to_join], how='left')
                df['BTCDOM_ROC'] = df['BTCDOM_ROC'].ffill().fillna(0)
            else:
                df['BTCDOM_ROC'] = 0.0

        except Exception as e:
            logger.error(f"Error macro features: {e}")
            df['BTCDOM_ROC'] = 0.0

        return df

    def build_full_features(self, crypto_df, macro_df, crypto_4h_df=None, onchain_df=None, sentiment_df=None,
                           defillama_df=None, coinglass_df=None):
        """
        Construye features completas para 15min con contexto macro de 4H

        Args:
            crypto_df: DataFrame de 15min (principal)
            macro_df: DataFrame de BTCDOM
            crypto_4h_df: DataFrame de 4H para features macro
            onchain_df: Datos on-chain
            sentiment_df: Datos de sentimiento
            defillama_df: Datos de stablecoins
            coinglass_df: Datos de derivados
        """
        logger.info("Construyendo features...")

        # Features técnicas en 15min
        df = self.create_technical_features(crypto_df, timeframe='15m')

        # Features macro de 4H (CRÍTICO para contexto)
        if crypto_4h_df is not None and not crypto_4h_df.empty:
            df = self.add_4h_macro_features(df, crypto_4h_df)
        else:
            logger.warning("⚠️ No se proporcionaron datos de 4H - se perderá contexto macro")

        # On-chain seguro (resamplear a 15min)
        if onchain_df is not None and not onchain_df.empty:
            try:
                onchain_res = onchain_df.resample('15min').ffill()
                df = df.join(onchain_res, how='left')

                if 'net_flow' in df.columns:
                    # Z-Score robusto
                    rolling_mean = df['net_flow'].rolling(42).mean()
                    rolling_std = df['net_flow'].rolling(42).std()
                    df['Net_Flow_Z'] = ((df['net_flow'] - rolling_mean) / (rolling_std + 1e-8)).clip(-5,5)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"⚠️ Error procesando onchain data: {e}")
                pass

        if 'Net_Flow_Z' not in df.columns: df['Net_Flow_Z'] = 0.0

        # Macro (BTCDOM)
        df = self.merge_macro_features(df, macro_df)

        # Sentiment
        if sentiment_df is not None and 'FinBERT_Score' in sentiment_df.columns:
            df = df.join(sentiment_df[['FinBERT_Score']], how='left')

        # Ensure FinBERT_Score column exists (create with default value if missing)
        if 'FinBERT_Score' not in df.columns:
            df['FinBERT_Score'] = 0.0
        else:
            df['FinBERT_Score'] = df['FinBERT_Score'].fillna(0)

        # DefiLlama (Stablecoins) - resamplear a 15min
        if defillama_df is not None and not defillama_df.empty:
            try:
                defillama_res = defillama_df.resample('15min').ffill()
                df = df.join(defillama_res, how='left')
                logger.info(f"✓ DefiLlama features agregadas: {list(defillama_res.columns)}")
            except Exception as e:
                logger.warning(f"⚠️ Error agregando DefiLlama features: {e}")

        # Coinglass (Derivados) - resamplear a 15min
        if coinglass_df is not None and not coinglass_df.empty:
            try:
                coinglass_res = coinglass_df.resample('15min').ffill()
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

        # STATISTICAL FEATURES (Hurst, Kalman, Wavelet, FFT, Entropy, Fractal)
        if self.statistical_engine is not None:
            logger.info("🔬 Calculando Statistical Features (~100 features)...")
            try:
                # Necesitamos columna 'close' para statistical features
                if 'close' in crypto_df.columns:
                    df_with_close = df.copy()
                    df_with_close['close'] = crypto_df['close']

                    # Calcular statistical features
                    df = self.statistical_engine.compute_all_features(df_with_close, price_col='close')

                    logger.info("✅ Statistical Features agregadas exitosamente")
                else:
                    logger.warning("⚠️ Columna 'close' no encontrada, saltando statistical features")
            except Exception as e:
                logger.error(f"❌ Error calculando Statistical Features: {e}")

        df.dropna(inplace=True)
        cols_to_drop = ['open', 'high', 'low', 'close', 'volume']
        self.feature_names = [c for c in df.columns if c not in cols_to_drop]

        logger.info(f"✓ Features totales: {len(self.feature_names)}")
        return df
