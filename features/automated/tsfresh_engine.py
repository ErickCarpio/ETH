"""
tsfresh Auto-Feature Engine
=============================

Automatic feature extraction using tsfresh library.
Generates ~1,750 features from 7 key time series, then filters to top 100.

Time series processed:
- close (price)
- volume
- OBI_L5 (Order Book Imbalance)
- VPIN (Volume-synchronized PIN)
- funding_rate
- stablecoin_flow_7d
- open_interest_norm

Features generated: ~100 (filtered from 1,750)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
import pickle
import os

try:
    from tsfresh import extract_features, select_features
    from tsfresh.utilities.dataframe_functions import impute
    from tsfresh.feature_extraction import EfficientFCParameters, MinimalFCParameters
    TSFRESH_AVAILABLE = True
except ImportError:
    TSFRESH_AVAILABLE = False
    logging.warning("tsfresh not available - using fallback feature extraction")

logger = logging.getLogger(__name__)


class TSFreshEngine:
    """
    Automated feature extraction using tsfresh.

    Workflow:
    1. Prepare data in tsfresh format (long format with id column)
    2. Extract features using EfficientFCParameters
    3. Select top features using statistical tests
    4. Cache selected features for fast reuse
    """

    def __init__(self, cache_dir: str = './cache/tsfresh'):
        """
        Initialize tsfresh engine.

        Args:
            cache_dir: Directory to cache selected features
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.selected_features = None
        self.feature_importance = None

    def prepare_data_for_tsfresh(self,
                                  df: pd.DataFrame,
                                  columns: List[str],
                                  id_column: str = 'window_id',
                                  time_column: str = 'time') -> pd.DataFrame:
        """
        Convert DataFrame to tsfresh format (long format).

        tsfresh expects:
        - id column: identifies which time series window
        - time column: time index within window
        - value columns: actual time series values

        Args:
            df: Input DataFrame with datetime index
            columns: Columns to convert to time series format
            id_column: Name for ID column
            time_column: Name for time column

        Returns:
            Long-format DataFrame ready for tsfresh
        """
        if not TSFRESH_AVAILABLE:
            logger.warning("tsfresh not available, returning empty DataFrame")
            return pd.DataFrame()

        # Create rolling windows (24h windows with 6h stride)
        window_size = 24
        stride = 6

        windows = []
        for i in range(0, len(df) - window_size, stride):
            window = df.iloc[i:i+window_size].copy()
            window[id_column] = i // stride
            window = window.reset_index()
            window[time_column] = range(len(window))
            windows.append(window)

        if not windows:
            logger.warning("No windows created, DataFrame too small")
            return pd.DataFrame()

        # Combine all windows
        df_long = pd.concat(windows, ignore_index=True)

        # Select relevant columns
        keep_cols = [id_column, time_column] + [col for col in columns if col in df_long.columns]
        df_long = df_long[keep_cols]

        logger.info(f"Created {len(windows)} windows for tsfresh extraction")
        return df_long

    def extract_features(self,
                        df_long: pd.DataFrame,
                        id_column: str = 'window_id',
                        time_column: str = 'time',
                        settings: Optional[Dict] = None) -> pd.DataFrame:
        """
        Extract features using tsfresh.

        Args:
            df_long: Long-format DataFrame
            id_column: Name of ID column
            time_column: Name of time column
            settings: Feature extraction settings (default: EfficientFCParameters)

        Returns:
            DataFrame with extracted features (one row per window)
        """
        if not TSFRESH_AVAILABLE:
            logger.warning("tsfresh not available, returning empty DataFrame")
            return pd.DataFrame()

        if df_long.empty:
            logger.warning("Empty DataFrame, cannot extract features")
            return pd.DataFrame()

        try:
            # Use EfficientFCParameters for comprehensive extraction
            if settings is None:
                settings = EfficientFCParameters()

            logger.info(f"Extracting tsfresh features from {len(df_long[id_column].unique())} windows...")

            # Extract features
            features = extract_features(
                df_long,
                column_id=id_column,
                column_sort=time_column,
                default_fc_parameters=settings,
                n_jobs=4,  # Parallel processing
                disable_progressbar=False
            )

            # Impute NaN values
            impute(features)

            logger.info(f"✓ Extracted {features.shape[1]} features from {features.shape[0]} windows")

            return features

        except Exception as e:
            logger.error(f"Error extracting tsfresh features: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return pd.DataFrame()

    def select_features(self,
                       features: pd.DataFrame,
                       target: pd.Series,
                       fdr_level: float = 0.05,
                       n_top: int = 100) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Select top features using statistical tests.

        Uses tsfresh's built-in feature selection with Benjamini-Hochberg correction.

        Args:
            features: Extracted features DataFrame
            target: Target variable (aligned with features index)
            fdr_level: False Discovery Rate level for hypothesis testing
            n_top: Number of top features to keep

        Returns:
            Tuple of (selected_features, feature_importance)
        """
        if not TSFRESH_AVAILABLE:
            logger.warning("tsfresh not available, returning empty selection")
            return pd.DataFrame(), pd.Series()

        if features.empty:
            logger.warning("Empty features, cannot select")
            return pd.DataFrame(), pd.Series()

        try:
            # Align indices
            common_idx = features.index.intersection(target.index)
            features_aligned = features.loc[common_idx]
            target_aligned = target.loc[common_idx]

            if len(common_idx) < 10:
                logger.warning(f"Only {len(common_idx)} samples, need more data for selection")
                return pd.DataFrame(), pd.Series()

            logger.info(f"Selecting features from {features.shape[1]} candidates...")

            # tsfresh built-in selection (includes Benjamini-Hochberg correction)
            selected = select_features(
                features_aligned,
                target_aligned,
                fdr_level=fdr_level,
                n_jobs=4
            )

            # If we have more features than n_top, rank by correlation and take top N
            if selected.shape[1] > n_top:
                # Calculate correlation with target
                correlations = {}
                for col in selected.columns:
                    try:
                        corr = abs(selected[col].corr(target_aligned))
                        if not np.isnan(corr):
                            correlations[col] = corr
                    except:
                        pass

                # Sort by correlation
                sorted_features = sorted(correlations.items(), key=lambda x: x[1], reverse=True)
                top_features = [feat for feat, corr in sorted_features[:n_top]]

                selected = selected[top_features]
                importance = pd.Series({feat: corr for feat, corr in sorted_features[:n_top]})
            else:
                # All selected features are important
                importance = pd.Series(1.0, index=selected.columns)

            logger.info(f"✓ Selected {selected.shape[1]} features (FDR={fdr_level})")

            self.selected_features = list(selected.columns)
            self.feature_importance = importance

            return selected, importance

        except Exception as e:
            logger.error(f"Error selecting features: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return pd.DataFrame(), pd.Series()

    def cache_selected_features(self, feature_names: List[str], filename: str = 'selected_features.pkl'):
        """
        Cache selected feature names for fast reuse.

        Args:
            feature_names: List of selected feature names
            filename: Cache file name
        """
        cache_path = os.path.join(self.cache_dir, filename)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(feature_names, f)
            logger.info(f"✓ Cached {len(feature_names)} features to {cache_path}")
        except Exception as e:
            logger.warning(f"Could not cache features: {e}")

    def load_cached_features(self, filename: str = 'selected_features.pkl') -> Optional[List[str]]:
        """
        Load cached feature names.

        Args:
            filename: Cache file name

        Returns:
            List of feature names, or None if not cached
        """
        cache_path = os.path.join(self.cache_dir, filename)
        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, 'rb') as f:
                feature_names = pickle.load(f)
            logger.info(f"✓ Loaded {len(feature_names)} cached features")
            return feature_names
        except Exception as e:
            logger.warning(f"Could not load cached features: {e}")
            return None

    def extract_and_select(self,
                          df: pd.DataFrame,
                          target: pd.Series,
                          columns: List[str],
                          n_top: int = 100,
                          use_cache: bool = True) -> pd.DataFrame:
        """
        Full pipeline: prepare, extract, select.

        Args:
            df: Input DataFrame with datetime index
            target: Target variable (same index as df)
            columns: Columns to extract features from
            n_top: Number of features to select
            use_cache: Whether to use cached feature selection

        Returns:
            DataFrame with selected features (one row per original df row)
        """
        # Check cache first
        if use_cache:
            cached_features = self.load_cached_features()
            if cached_features is not None:
                logger.info("Using cached feature selection")
                # Extract only cached features (fast)
                return self._extract_cached_features(df, columns, cached_features)

        # Full extraction pipeline
        logger.info(f"Running full tsfresh extraction on {len(columns)} columns...")

        # 1. Prepare data
        df_long = self.prepare_data_for_tsfresh(df, columns)

        if df_long.empty:
            logger.warning("Could not prepare data, returning empty features")
            return pd.DataFrame()

        # 2. Extract features
        features = self.extract_features(df_long)

        if features.empty:
            logger.warning("Could not extract features, returning empty")
            return pd.DataFrame()

        # 3. Align target with window IDs
        # Map window_id back to original timestamps
        window_size = 24
        stride = 6
        window_targets = []

        for i in range(0, len(df) - window_size, stride):
            window_id = i // stride
            # Use last value of window as target
            target_val = target.iloc[i + window_size - 1] if i + window_size - 1 < len(target) else np.nan
            window_targets.append({'window_id': window_id, 'target': target_val})

        target_df = pd.DataFrame(window_targets).set_index('window_id')['target']

        # 4. Select features
        selected, importance = self.select_features(features, target_df, n_top=n_top)

        if selected.empty:
            logger.warning("No features selected, returning empty")
            return pd.DataFrame()

        # 5. Cache selection
        if use_cache:
            self.cache_selected_features(list(selected.columns))

        # 6. Map back to original timestamps
        result = self._map_features_to_timestamps(selected, df.index, window_size, stride)

        return result

    def _extract_cached_features(self,
                                 df: pd.DataFrame,
                                 columns: List[str],
                                 feature_names: List[str]) -> pd.DataFrame:
        """
        Extract only pre-selected features (fast path).

        Args:
            df: Input DataFrame
            columns: Columns to extract from
            feature_names: Pre-selected feature names

        Returns:
            DataFrame with only selected features
        """
        # Parse feature names to extract settings
        # tsfresh feature names format: "column__feature_name__param1_val1__param2_val2"
        settings = self._parse_feature_names(feature_names)

        # Prepare data
        df_long = self.prepare_data_for_tsfresh(df, columns)

        # Extract with filtered settings
        features = self.extract_features(df_long, settings=settings)

        # Keep only selected features
        available_features = [f for f in feature_names if f in features.columns]
        features = features[available_features]

        # Map to timestamps
        window_size = 24
        stride = 6
        result = self._map_features_to_timestamps(features, df.index, window_size, stride)

        return result

    def _parse_feature_names(self, feature_names: List[str]) -> Dict:
        """
        Parse tsfresh feature names to extract settings.

        This is a simplified version - in production, you'd parse the full parameter set.
        For now, we'll just use EfficientFCParameters and filter afterward.

        Args:
            feature_names: List of feature names

        Returns:
            Feature extraction settings
        """
        # For simplicity, return EfficientFCParameters
        # tsfresh will extract all, we'll filter afterward
        return EfficientFCParameters()

    def _map_features_to_timestamps(self,
                                    features: pd.DataFrame,
                                    timestamps: pd.DatetimeIndex,
                                    window_size: int,
                                    stride: int) -> pd.DataFrame:
        """
        Map windowed features back to original timestamps.

        Each window ID corresponds to a time range. We'll forward-fill features
        to cover the full timestamp range.

        Args:
            features: Windowed features (index = window_id)
            timestamps: Original timestamps
            window_size: Window size in hours
            stride: Stride in hours

        Returns:
            Features aligned with original timestamps
        """
        # Create mapping from timestamp to window_id
        timestamp_to_window = {}

        for i in range(0, len(timestamps) - window_size, stride):
            window_id = i // stride
            # This window covers timestamps[i:i+window_size]
            for j in range(i, min(i + window_size, len(timestamps))):
                timestamp_to_window[timestamps[j]] = window_id

        # Create result DataFrame
        result = pd.DataFrame(index=timestamps, columns=features.columns, dtype=float)

        # Fill features for each timestamp
        for ts in timestamps:
            if ts in timestamp_to_window:
                window_id = timestamp_to_window[ts]
                if window_id in features.index:
                    result.loc[ts] = features.loc[window_id]

        # Forward fill missing values
        result = result.fillna(method='ffill')

        # Remaining NaN (at start) = 0
        result = result.fillna(0)

        return result


def get_tsfresh_features(df: pd.DataFrame,
                        target: pd.Series,
                        columns: Optional[List[str]] = None,
                        n_top: int = 100,
                        use_cache: bool = True) -> pd.DataFrame:
    """
    Convenience function to extract tsfresh features.

    Args:
        df: Input DataFrame with OHLCV and other features
        target: Target variable for feature selection
        columns: Columns to extract features from (default: key time series)
        n_top: Number of top features to select
        use_cache: Whether to use cached feature selection

    Returns:
        DataFrame with tsfresh features
    """
    if not TSFRESH_AVAILABLE:
        logger.warning("tsfresh not available, returning empty DataFrame")
        return pd.DataFrame()

    # Default columns: 7 key time series
    if columns is None:
        columns = [
            'close',  # Price
            'volume',  # Volume
            'OBI_L5',  # Order Book Imbalance
            'VPIN',  # Volume-synchronized PIN
            'funding_rate',  # Funding rate
            'stablecoin_flow_7d',  # Stablecoin flows
            'open_interest_norm'  # Open Interest
        ]

        # Filter to available columns
        columns = [col for col in columns if col in df.columns]

    if not columns:
        logger.warning("No valid columns for tsfresh extraction")
        return pd.DataFrame()

    logger.info(f"Extracting tsfresh features from {len(columns)} time series: {columns}")

    engine = TSFreshEngine()
    features = engine.extract_and_select(df, target, columns, n_top=n_top, use_cache=use_cache)

    return features


if __name__ == "__main__":
    # Test with synthetic data
    logger.info("Testing tsfresh engine...")

    # Create synthetic data
    n = 200
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='h')

    df = pd.DataFrame({
        'close': np.cumsum(np.random.randn(n)) + 2000,
        'volume': np.random.lognormal(10, 1, n),
        'OBI_L5': np.random.randn(n) * 0.1,
        'VPIN': np.random.rand(n) * 0.5,
        'funding_rate': np.random.randn(n) * 0.0001,
        'stablecoin_flow_7d': np.cumsum(np.random.randn(n)) * 1e6,
        'open_interest_norm': np.random.rand(n) + 1.0
    }, index=dates)

    # Create target (next hour return)
    target = df['close'].pct_change().shift(-1)
    target = (target > 0).astype(int)

    # Extract features
    if TSFRESH_AVAILABLE:
        features = get_tsfresh_features(df, target, n_top=20, use_cache=False)

        print("\n" + "="*60)
        print("TSFRESH ENGINE TEST")
        print("="*60)
        print(f"\nInput shape: {df.shape}")
        print(f"Output shape: {features.shape}")
        print(f"\nSample features:")
        print(features.head())
        print(f"\nFeature names:")
        print(features.columns.tolist()[:10])
    else:
        print("\n⚠️ tsfresh not available - install with: pip install tsfresh")
