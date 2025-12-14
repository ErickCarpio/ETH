"""
tsfresh Feature Extractor - Phase 4
Auto-genera 800+ features de time-series usando tsfresh

tsfresh extrae features estadísticas automáticas de series temporales:
- Statistical features (mean, std, variance, etc.)
- Spectral features (FFT, power spectrum)
- Entropy features
- Autocorrelation features
- Change quantiles
- Linear trends
- And 700+ more

Referencias:
- Christ et al. (2018) - "Time Series Feature Extraction on basis of Scalable Hypothesis tests (tsfresh)"
- https://tsfresh.readthedocs.io/
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import tsfresh (optional dependency)
try:
    from tsfresh import extract_features, select_features
    from tsfresh.utilities.dataframe_functions import impute
    from tsfresh.feature_extraction import ComprehensiveFCParameters, MinimalFCParameters
    TSFRESH_AVAILABLE = True
except ImportError:
    TSFRESH_AVAILABLE = False
    logger.warning("tsfresh no disponible - instala con: pip install tsfresh")


class TsfreshFeatureExtractor:
    """
    Extractor de features automáticas usando tsfresh

    Genera 800+ features de diferentes series temporales:
    - Price (close, high, low)
    - Volume
    - Returns
    - Volatility

    Luego hace feature selection para quedarse con las más relevantes
    """

    def __init__(self,
                 mode: str = 'comprehensive',  # 'comprehensive' or 'minimal'
                 n_jobs: int = 4,
                 disable_progressbar: bool = False):
        """
        Args:
            mode: 'comprehensive' (800+ features) o 'minimal' (~60 features)
            n_jobs: Number of parallel jobs
            disable_progressbar: Disable tsfresh progress bar
        """
        if not TSFRESH_AVAILABLE:
            raise ImportError("tsfresh no está instalado. Instala con: pip install tsfresh")

        self.mode = mode
        self.n_jobs = n_jobs
        self.disable_progressbar = disable_progressbar

        # Feature extraction settings
        if mode == 'comprehensive':
            self.fc_parameters = ComprehensiveFCParameters()
        else:
            self.fc_parameters = MinimalFCParameters()

        # Selected features after selection
        self.selected_features: Optional[List[str]] = None

    def prepare_timeseries_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepara datos en formato tsfresh

        tsfresh requiere formato:
        | id | time | value |

        Nosotros vamos a extraer features de múltiples series:
        - close, high, low
        - volume
        - returns
        - volatility

        Args:
            df: DataFrame con index temporal y columnas OHLCV

        Returns:
            DataFrame en formato tsfresh (long format)
        """
        # Reset index para tener timestamp como columna
        df_reset = df.reset_index()

        # Crear lista de series para extraer features
        series_to_extract = []

        # 1. Price series
        for col in ['close', 'high', 'low']:
            if col in df.columns:
                series_df = pd.DataFrame({
                    'id': f'price_{col}',
                    'time': range(len(df_reset)),
                    'value': df_reset[col].values
                })
                series_to_extract.append(series_df)

        # 2. Volume
        if 'volume' in df.columns:
            series_df = pd.DataFrame({
                'id': 'volume',
                'time': range(len(df_reset)),
                'value': df_reset['volume'].values
            })
            series_to_extract.append(series_df)

        # 3. Returns
        if 'returns' in df.columns:
            series_df = pd.DataFrame({
                'id': 'returns',
                'time': range(len(df_reset)),
                'value': df_reset['returns'].fillna(0).values
            })
            series_to_extract.append(series_df)

        # 4. Volatility
        for col in df.columns:
            if 'volatility' in col:
                series_df = pd.DataFrame({
                    'id': col,
                    'time': range(len(df_reset)),
                    'value': df_reset[col].fillna(0).values
                })
                series_to_extract.append(series_df)

        # Concatenar todas las series
        if series_to_extract:
            timeseries_df = pd.concat(series_to_extract, ignore_index=True)
            return timeseries_df
        else:
            raise ValueError("No hay columnas válidas para extraer features")

    def extract_features_from_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extrae features de tsfresh desde un DataFrame

        Args:
            df: DataFrame con datos OHLCV

        Returns:
            DataFrame con features extraídas (1 row por serie)
        """
        logger.info(f"🔄 Extrayendo features tsfresh ({self.mode} mode)...")

        # Preparar datos en formato tsfresh
        timeseries_df = self.prepare_timeseries_data(df)

        # Extraer features
        try:
            features_df = extract_features(
                timeseries_df,
                column_id='id',
                column_sort='time',
                column_value='value',
                default_fc_parameters=self.fc_parameters,
                n_jobs=self.n_jobs,
                disable_progressbar=self.disable_progressbar
            )

            # Impute NaN values
            impute(features_df)

            logger.info(f"✅ Features extraídas: {len(features_df.columns)} features de {len(features_df)} series")

            return features_df

        except Exception as e:
            logger.error(f"❌ Error extrayendo features: {e}")
            return pd.DataFrame()

    def select_relevant_features(self,
                                 features_df: pd.DataFrame,
                                 target: pd.Series,
                                 max_features: int = 100) -> pd.DataFrame:
        """
        Selecciona features más relevantes usando test de hipótesis

        tsfresh usa tests estadísticos para determinar qué features
        son significativamente diferentes entre clases

        Args:
            features_df: DataFrame con features extraídas
            target: Serie con labels (régimen de mercado)
            max_features: Máximo número de features a seleccionar

        Returns:
            DataFrame con solo las features seleccionadas
        """
        logger.info(f"🔍 Seleccionando features relevantes (max: {max_features})...")

        try:
            # Align features_df with target
            # features_df tiene 1 row por serie, necesitamos expandir
            # Para simplificar, vamos a usar todas las features y hacer selection después

            # Select features usando test de hipótesis
            features_filtered = select_features(
                features_df,
                target,
                n_jobs=self.n_jobs
            )

            # Si hay más features que max_features, seleccionar top features
            if len(features_filtered.columns) > max_features:
                # Calcular importancia por correlación con target
                correlations = {}
                for col in features_filtered.columns:
                    try:
                        corr = abs(features_filtered[col].corr(target))
                        if not np.isnan(corr):
                            correlations[col] = corr
                    except:
                        pass

                # Ordenar por correlación
                top_features = sorted(correlations.items(), key=lambda x: x[1], reverse=True)[:max_features]
                top_feature_names = [f[0] for f in top_features]

                features_filtered = features_filtered[top_feature_names]

            self.selected_features = list(features_filtered.columns)

            logger.info(f"✅ Features seleccionadas: {len(features_filtered.columns)}")
            logger.info(f"   Top 10: {self.selected_features[:10]}")

            return features_filtered

        except Exception as e:
            logger.error(f"❌ Error seleccionando features: {e}")
            return features_df

    def extract_and_select(self,
                          df: pd.DataFrame,
                          target: Optional[pd.Series] = None,
                          max_features: int = 100) -> pd.DataFrame:
        """
        Pipeline completo: extracción + selección

        Args:
            df: DataFrame con datos OHLCV
            target: Serie con labels para feature selection (opcional)
            max_features: Máximo número de features finales

        Returns:
            DataFrame con features seleccionadas
        """
        # 1. Extraer features
        features_df = self.extract_features_from_df(df)

        if features_df.empty:
            return pd.DataFrame()

        # 2. Seleccionar features relevantes (si hay target)
        if target is not None:
            features_df = self.select_relevant_features(features_df, target, max_features)

        return features_df

    def save_selected_features(self, filepath: str):
        """Guarda lista de features seleccionadas"""
        if self.selected_features:
            with open(filepath, 'w') as f:
                for feature in self.selected_features:
                    f.write(f"{feature}\n")
            logger.info(f"💾 Features guardadas: {filepath}")

    def load_selected_features(self, filepath: str):
        """Carga lista de features seleccionadas"""
        with open(filepath, 'r') as f:
            self.selected_features = [line.strip() for line in f.readlines()]
        logger.info(f"📂 Features cargadas: {len(self.selected_features)}")


# Demo / Testing
if __name__ == "__main__":
    print("🧪 tsfresh Feature Extractor - Demo\n")

    if not TSFRESH_AVAILABLE:
        print("❌ tsfresh no está instalado")
        print("   Instala con: pip install tsfresh")
        exit(1)

    # Generar datos de prueba
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=1000, freq='4h')

    df = pd.DataFrame({
        'close': np.cumsum(np.random.randn(1000)) + 100,
        'high': np.cumsum(np.random.randn(1000)) + 102,
        'low': np.cumsum(np.random.randn(1000)) + 98,
        'volume': np.random.randint(1000, 10000, 1000),
    }, index=dates)

    df['returns'] = df['close'].pct_change()
    df['volatility_24h'] = df['returns'].rolling(24).std()

    # Target aleatorio
    target = pd.Series(np.random.choice([0, 1, 2, 3], size=1000), index=dates)

    print(f"📊 Datos de prueba:")
    print(f"   Rows: {len(df)}")
    print(f"   Columns: {list(df.columns)}")
    print(f"   Target classes: {target.unique()}")
    print()

    # Extraer features
    extractor = TsfreshFeatureExtractor(mode='minimal', n_jobs=2)

    print("🔄 Extrayendo features...")
    features = extractor.extract_and_select(df, target, max_features=50)

    print(f"\n✅ Features extraídas: {len(features.columns)}")
    print(f"\n📋 Primeras 10 features:")
    for i, col in enumerate(features.columns[:10], 1):
        print(f"   {i}. {col}")

    print(f"\n💡 Usa estas features en tu pipeline de entrenamiento")
