"""
Test tsfresh Auto-Generation
==============================

Tests for automated feature extraction using tsfresh.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from features.automated import TSFreshEngine, get_tsfresh_features
    from features.automated import FeatureSelector, select_features
    TSFRESH_AVAILABLE = True
except ImportError:
    TSFRESH_AVAILABLE = False
    pytestmark = pytest.mark.skip(reason="tsfresh not available")


class TestTSFreshEngine:
    """Test TSFreshEngine class"""

    @pytest.fixture
    def sample_data(self):
        """Create sample time series data"""
        n = 200
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='h')

        df = pd.DataFrame({
            'close': np.cumsum(np.random.randn(n)) + 2000,
            'volume': np.random.lognormal(10, 1, n),
            'OBI_L5': np.random.randn(n) * 0.1,
            'VPIN': np.random.rand(n) * 0.5
        }, index=dates)

        return df

    @pytest.fixture
    def target(self, sample_data):
        """Create target variable"""
        target = sample_data['close'].pct_change().shift(-1)
        target = (target > 0).astype(int)
        return target

    @pytest.fixture
    def engine(self):
        """Create TSFreshEngine instance"""
        return TSFreshEngine()

    def test_initialization(self, engine):
        """Test TSFreshEngine initialization"""
        assert engine is not None
        assert hasattr(engine, 'cache_dir')
        assert os.path.exists(engine.cache_dir)

    def test_prepare_data_for_tsfresh(self, engine, sample_data):
        """Test data preparation for tsfresh"""
        columns = ['close', 'volume']

        df_long = engine.prepare_data_for_tsfresh(sample_data, columns)

        if not TSFRESH_AVAILABLE:
            assert df_long.empty
            return

        # Check format
        assert 'window_id' in df_long.columns
        assert 'time' in df_long.columns
        assert 'close' in df_long.columns
        assert 'volume' in df_long.columns

        # Check that windows were created
        n_windows = df_long['window_id'].nunique()
        assert n_windows > 0

    def test_extract_features(self, engine, sample_data):
        """Test feature extraction"""
        if not TSFRESH_AVAILABLE:
            pytest.skip("tsfresh not available")

        columns = ['close', 'volume']
        df_long = engine.prepare_data_for_tsfresh(sample_data, columns)

        if df_long.empty:
            pytest.skip("Could not prepare data")

        features = engine.extract_features(df_long)

        # Should return DataFrame with features
        assert isinstance(features, pd.DataFrame)

        if not features.empty:
            # Should have multiple features
            assert features.shape[1] > 10

            # No NaN (should be imputed)
            assert features.isna().sum().sum() == 0

    def test_select_features(self, engine, sample_data, target):
        """Test feature selection"""
        if not TSFRESH_AVAILABLE:
            pytest.skip("tsfresh not available")

        # Create fake features
        n_features = 50
        n_samples = 100

        features = pd.DataFrame(
            np.random.randn(n_samples, n_features),
            columns=[f'feature_{i}' for i in range(n_features)]
        )

        target_small = target.iloc[:n_samples]

        selected, importance = engine.select_features(features, target_small, n_top=10)

        # Should return selected features
        assert isinstance(selected, pd.DataFrame)

        if not selected.empty:
            # Should select up to 10 features
            assert selected.shape[1] <= 10

            # Should have importance scores
            assert isinstance(importance, pd.Series)
            assert len(importance) > 0

    def test_cache_and_load(self, engine):
        """Test caching mechanism"""
        feature_names = ['feature_1', 'feature_2', 'feature_3']

        # Cache features
        engine.cache_selected_features(feature_names, filename='test_cache.pkl')

        # Load features
        loaded = engine.load_cached_features(filename='test_cache.pkl')

        assert loaded == feature_names


class TestFeatureSelector:
    """Test FeatureSelector class"""

    @pytest.fixture
    def sample_features(self):
        """Create sample features and target"""
        n_samples = 200
        n_features = 50

        # Create target
        target = pd.Series(np.random.randn(n_samples) > 0, name='target').astype(int)

        # Create features
        features = pd.DataFrame()

        # 20 informative features (correlated with target)
        for i in range(20):
            noise = np.random.randn(n_samples) * 0.5
            signal = target.values + noise
            features[f'informative_{i}'] = signal

        # 30 random features (no correlation)
        for i in range(30):
            features[f'random_{i}'] = np.random.randn(n_samples)

        return features, target

    @pytest.fixture
    def selector(self):
        """Create FeatureSelector instance"""
        return FeatureSelector(fdr_level=0.05, correlation_threshold=0.95)

    def test_initialization(self, selector):
        """Test FeatureSelector initialization"""
        assert selector is not None
        assert selector.fdr_level == 0.05
        assert selector.correlation_threshold == 0.95

    def test_calculate_significance(self, selector, sample_features):
        """Test significance calculation"""
        features, target = sample_features

        scores = selector.calculate_significance(features, target, method='pearson')

        # Should return DataFrame with scores
        assert isinstance(scores, pd.DataFrame)
        assert 'feature' in scores.columns
        assert 'correlation' in scores.columns
        assert 'p_value' in scores.columns
        assert 'abs_correlation' in scores.columns

        # Should have scores for all features
        assert len(scores) > 0

        # Should be sorted by abs_correlation
        assert scores['abs_correlation'].is_monotonic_decreasing

    def test_apply_fdr_correction(self, selector):
        """Test Benjamini-Hochberg FDR correction"""
        # Create p-values
        p_values = np.array([0.001, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 0.9])

        passed = selector.apply_fdr_correction(p_values)

        # Should return boolean array
        assert isinstance(passed, np.ndarray)
        assert passed.dtype == bool

        # At least some should pass
        assert passed.sum() > 0

        # Smallest p-value should pass
        assert passed[0] == True

    def test_remove_redundant(self, selector, sample_features):
        """Test redundancy removal"""
        features, target = sample_features

        # Add redundant features
        features['redundant_1'] = features['informative_0'] + np.random.randn(len(features)) * 0.01
        features['redundant_2'] = features['informative_0'] + np.random.randn(len(features)) * 0.01

        # Calculate scores first
        selector.feature_scores = selector.calculate_significance(features, target)

        # Remove redundant
        non_redundant = selector.remove_redundant(features, threshold=0.95)

        # Should remove some features
        assert len(non_redundant) < len(features.columns)

        # Should keep informative_0
        assert 'informative_0' in non_redundant

        # Should remove at least one redundant
        redundant_kept = sum(1 for f in non_redundant if 'redundant' in f)
        assert redundant_kept < 2  # At most 1 redundant kept

    def test_rank_by_importance(self, selector, sample_features):
        """Test importance ranking"""
        features, target = sample_features

        scores = selector.calculate_significance(features, target)

        ranked = selector.rank_by_importance(scores, n_top=10)

        # Should return DataFrame
        assert isinstance(ranked, pd.DataFrame)

        # Should have importance column
        assert 'importance' in ranked.columns

        # Should keep only top 10
        assert len(ranked) == 10

        # Should be sorted by importance
        assert ranked['importance'].is_monotonic_decreasing

    def test_full_selection_pipeline(self, selector, sample_features):
        """Test full selection pipeline"""
        features, target = sample_features

        selected, scores = selector.select(features, target, n_top=10, method='pearson')

        # Should return list of selected features
        assert isinstance(selected, list)
        assert len(selected) <= 10

        # Should return scores DataFrame
        assert isinstance(scores, pd.DataFrame)
        assert 'importance' in scores.columns

        # Selected features should prefer informative over random
        informative_count = sum(1 for f in selected if 'informative' in f)
        random_count = sum(1 for f in selected if 'random' in f)

        # Should select more informative than random
        assert informative_count > random_count


class TestConvenienceFunctions:
    """Test convenience functions"""

    @pytest.fixture
    def sample_data(self):
        """Create sample data"""
        n = 200
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='h')

        df = pd.DataFrame({
            'close': np.cumsum(np.random.randn(n)) + 2000,
            'volume': np.random.lognormal(10, 1, n),
            'OBI_L5': np.random.randn(n) * 0.1,
            'VPIN': np.random.rand(n) * 0.5
        }, index=dates)

        target = df['close'].pct_change().shift(-1)
        target = (target > 0).astype(int)

        return df, target

    def test_get_tsfresh_features(self, sample_data):
        """Test get_tsfresh_features convenience function"""
        if not TSFRESH_AVAILABLE:
            pytest.skip("tsfresh not available")

        df, target = sample_data

        # Run with cache disabled for testing
        features = get_tsfresh_features(
            df,
            target,
            columns=['close', 'volume'],
            n_top=10,
            use_cache=False
        )

        # Should return DataFrame
        assert isinstance(features, pd.DataFrame)

    def test_select_features_convenience(self, sample_data):
        """Test select_features convenience function"""
        df, target = sample_data

        # Create fake features
        features = pd.DataFrame(
            np.random.randn(len(df), 30),
            index=df.index,
            columns=[f'feature_{i}' for i in range(30)]
        )

        selected, scores = select_features(features, target, n_top=10)

        # Should return DataFrames
        assert isinstance(selected, pd.DataFrame)
        assert isinstance(scores, pd.DataFrame)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
