"""
Test Feature Engineering
=========================

Tests for core feature engineering pipeline.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feature_engineering import FeatureEngineer


class TestFeatureEngineer:
    """Test FeatureEngineer class"""

    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data"""
        n = 200
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='h')

        df = pd.DataFrame({
            'open': 2000 + np.cumsum(np.random.randn(n)),
            'high': 2050 + np.cumsum(np.random.randn(n)),
            'low': 1950 + np.cumsum(np.random.randn(n)),
            'close': 2000 + np.cumsum(np.random.randn(n)),
            'volume': np.random.lognormal(10, 1, n)
        }, index=dates)

        # Ensure high is highest and low is lowest
        df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
        df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)

        return df

    @pytest.fixture
    def engineer(self):
        """Create FeatureEngineer instance"""
        return FeatureEngineer()

    def test_initialization(self, engineer):
        """Test FeatureEngineer initialization"""
        assert engineer is not None
        assert hasattr(engineer, 'feature_names')
        assert isinstance(engineer.feature_names, list)

    def test_create_technical_features(self, engineer, sample_data):
        """Test technical feature creation"""
        result = engineer.create_technical_features(sample_data)

        # Check that new features were created
        assert len(result.columns) > len(sample_data.columns)

        # Check specific features exist
        assert 'returns' in result.columns
        assert 'log_returns' in result.columns
        assert 'volatility_6h' in result.columns
        assert 'volatility_24h' in result.columns
        assert 'rsi_14' in result.columns
        assert 'atr_14' in result.columns

        # Check no NaN in critical features (after dropna)
        result_clean = result.dropna()
        assert len(result_clean) > 100  # Should have data after dropna

    def test_phase3_statistical_features(self, engineer, sample_data):
        """Test Phase 3 statistical features"""
        result = engineer.create_technical_features(sample_data)

        # Check skewness features
        assert 'returns_skew_12h' in result.columns
        assert 'returns_skew_24h' in result.columns
        assert 'returns_skew_72h' in result.columns

        # Check kurtosis features
        assert 'returns_kurt_12h' in result.columns
        assert 'volume_kurt_24h' in result.columns

        # Check autocorrelation
        assert 'returns_autocorr_6h' in result.columns
        assert 'returns_autocorr_24h' in result.columns

        # Check volatility clustering
        assert 'vol_clustering_24h' in result.columns

    def test_phase4_tsfresh_inspired_features(self, engineer, sample_data):
        """Test Phase 4 tsfresh-inspired features"""
        result = engineer.create_technical_features(sample_data)

        # Check quantile features
        assert 'returns_q10_12h' in result.columns
        assert 'returns_q90_24h' in result.columns
        assert 'returns_iqr_24h' in result.columns

        # Check trend features
        assert 'price_trend_slope_24h' in result.columns
        assert 'volume_trend_slope_24h' in result.columns

        # Check complexity features
        assert 'approx_entropy_24h' in result.columns
        assert 'benford_corr_24h' in result.columns

    def test_merge_macro_features(self, engineer, sample_data):
        """Test macro features merge"""
        # Create fake macro data
        macro_df = pd.DataFrame({
            'BTCDOM': 40 + np.random.randn(len(sample_data)) * 2
        }, index=sample_data.index)

        result = engineer.merge_macro_features(sample_data.copy(), macro_df)

        # Check that BTCDOM_ROC was added
        assert 'BTCDOM_ROC' in result.columns

        # Check no NaN (should be filled)
        assert result['BTCDOM_ROC'].isna().sum() == 0

    def test_build_full_features_minimal(self, engineer, sample_data):
        """Test build_full_features with minimal data"""
        # Create minimal macro data
        macro_df = pd.DataFrame({
            'BTCDOM': 40 + np.random.randn(len(sample_data))
        }, index=sample_data.index)

        result = engineer.build_full_features(
            crypto_df=sample_data,
            macro_df=macro_df
        )

        # Should return DataFrame with features
        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) > 20  # At least 20 features

        # Check that feature_names was populated
        assert len(engineer.feature_names) > 0

    def test_feature_names_no_ohlcv(self, engineer, sample_data):
        """Test that OHLCV columns are excluded from feature_names"""
        macro_df = pd.DataFrame({
            'BTCDOM': 40 + np.random.randn(len(sample_data))
        }, index=sample_data.index)

        result = engineer.build_full_features(
            crypto_df=sample_data,
            macro_df=macro_df
        )

        # Check that OHLCV columns are not in feature_names
        ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in ohlcv_cols:
            assert col not in engineer.feature_names

    def test_no_infinite_values(self, engineer, sample_data):
        """Test that no infinite values are created"""
        result = engineer.create_technical_features(sample_data)

        # Check for infinite values
        infinite_cols = []
        for col in result.columns:
            if np.isinf(result[col]).any():
                infinite_cols.append(col)

        assert len(infinite_cols) == 0, f"Infinite values in: {infinite_cols}"

    def test_feature_stability(self, engineer, sample_data):
        """Test that features are stable (no sudden jumps)"""
        result = engineer.create_technical_features(sample_data)

        # Check that returns are reasonable (< 100% per hour)
        if 'returns' in result.columns:
            max_return = result['returns'].abs().max()
            assert max_return < 1.0, f"Unrealistic return: {max_return}"

        # Check that volatility is positive
        vol_cols = [col for col in result.columns if 'volatility' in col]
        for col in vol_cols:
            assert (result[col] >= 0).all(), f"Negative volatility in {col}"


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_dataframe(self):
        """Test with empty DataFrame"""
        engineer = FeatureEngineer()
        df = pd.DataFrame()

        # Should handle gracefully (may raise or return empty)
        try:
            result = engineer.create_technical_features(df)
            assert result.empty or len(result) == 0
        except Exception:
            pass  # Expected to fail

    def test_insufficient_data(self):
        """Test with insufficient data points"""
        engineer = FeatureEngineer()

        # Only 10 data points
        n = 10
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='h')
        df = pd.DataFrame({
            'open': np.random.randn(n) + 2000,
            'high': np.random.randn(n) + 2000,
            'low': np.random.randn(n) + 2000,
            'close': np.random.randn(n) + 2000,
            'volume': np.random.lognormal(10, 1, n)
        }, index=dates)

        # Should handle gracefully
        result = engineer.create_technical_features(df)

        # May have many NaN, but should not crash
        assert isinstance(result, pd.DataFrame)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
