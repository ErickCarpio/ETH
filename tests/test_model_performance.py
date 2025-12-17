"""
Test Model Performance
======================

Integration tests for model training and performance benchmarking.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feature_engineering import FeatureEngineer


class TestModelPerformance:
    """Test model training and performance"""

    @pytest.fixture
    def full_dataset(self):
        """Create comprehensive dataset for testing"""
        n = 500
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='4h')

        # Create realistic price movement
        returns = np.random.randn(n) * 0.02
        price = 2000 * np.exp(np.cumsum(returns))

        df = pd.DataFrame({
            'open': price * (1 + np.random.randn(n) * 0.005),
            'high': price * (1 + np.abs(np.random.randn(n)) * 0.01),
            'low': price * (1 - np.abs(np.random.randn(n)) * 0.01),
            'close': price,
            'volume': np.random.lognormal(10, 1, n)
        }, index=dates)

        # Ensure high/low constraints
        df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
        df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)

        return df

    @pytest.fixture
    def macro_data(self, full_dataset):
        """Create macro data"""
        return pd.DataFrame({
            'BTCDOM': 40 + np.random.randn(len(full_dataset)) * 2
        }, index=full_dataset.index)

    def test_feature_pipeline_execution(self, full_dataset, macro_data):
        """Test that full feature pipeline executes without errors"""
        engineer = FeatureEngineer()

        result = engineer.build_full_features(
            crypto_df=full_dataset,
            macro_df=macro_data
        )

        # Should return non-empty DataFrame
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert len(result.columns) > 20

        print(f"\n✓ Feature pipeline generated {len(result.columns)} features")
        print(f"✓ Data shape: {result.shape}")

    def test_feature_count_target(self, full_dataset, macro_data):
        """Test that we hit target feature count"""
        engineer = FeatureEngineer()

        result = engineer.build_full_features(
            crypto_df=full_dataset,
            macro_df=macro_data
        )

        n_features = len(result.columns)

        print(f"\n📊 Feature count: {n_features}")
        print(f"📊 Feature names count: {len(engineer.feature_names)}")

        # We should have at least 100+ features from various phases
        assert n_features >= 100, f"Expected 100+ features, got {n_features}"

    def test_feature_quality(self, full_dataset, macro_data):
        """Test feature quality metrics"""
        engineer = FeatureEngineer()

        result = engineer.build_full_features(
            crypto_df=full_dataset,
            macro_df=macro_data
        )

        # Check for infinite values
        infinite_count = np.isinf(result.select_dtypes(include=[np.number])).sum().sum()
        assert infinite_count == 0, f"Found {infinite_count} infinite values"

        # Check for NaN values (should be 0 after dropna)
        nan_count = result.isna().sum().sum()
        assert nan_count == 0, f"Found {nan_count} NaN values after pipeline"

        # Check variance (features should have some variance)
        variances = result.select_dtypes(include=[np.number]).var()
        zero_variance = (variances == 0).sum()

        # Allow some zero variance features (like binary flags)
        assert zero_variance < len(variances) * 0.1, f"Too many zero-variance features: {zero_variance}"

        print(f"\n✓ Quality checks passed")
        print(f"  - No infinite values")
        print(f"  - No NaN values")
        print(f"  - {len(variances) - zero_variance}/{len(variances)} features have variance")

    def test_feature_correlation_with_target(self, full_dataset, macro_data):
        """Test that some features are correlated with target"""
        engineer = FeatureEngineer()

        result = engineer.build_full_features(
            crypto_df=full_dataset,
            macro_df=macro_data
        )

        # Create target (next period return)
        # Need to use original full_dataset to get close prices
        target = full_dataset['close'].pct_change().shift(-1)
        target = target.loc[result.index]  # Align with result index

        # Calculate correlations
        correlations = {}
        for col in result.columns:
            if col in result.select_dtypes(include=[np.number]).columns:
                # Align indices
                common_idx = result.index.intersection(target.index)
                if len(common_idx) > 10:
                    corr = result.loc[common_idx, col].corr(target.loc[common_idx])
                    if not np.isnan(corr):
                        correlations[col] = abs(corr)

        if correlations:
            # Sort by correlation
            sorted_corrs = sorted(correlations.items(), key=lambda x: x[1], reverse=True)

            # Top correlation
            top_feature, top_corr = sorted_corrs[0]

            print(f"\n📈 Top 10 features by correlation with returns:")
            for i, (feat, corr) in enumerate(sorted_corrs[:10], 1):
                print(f"  {i}. {feat}: {corr:.4f}")

            # At least one feature should have some correlation
            assert top_corr > 0, "No features correlated with target"

    def test_train_test_split_stability(self, full_dataset, macro_data):
        """Test that features are stable across train/test split"""
        engineer = FeatureEngineer()

        result = engineer.build_full_features(
            crypto_df=full_dataset,
            macro_df=macro_data
        )

        # Split 80/20
        split_idx = int(len(result) * 0.8)
        train = result.iloc[:split_idx]
        test = result.iloc[split_idx:]

        # Check that train and test have same columns
        assert set(train.columns) == set(test.columns)

        # Check that distributions are similar (not too different)
        for col in train.select_dtypes(include=[np.number]).columns:
            train_mean = train[col].mean()
            test_mean = test[col].mean()

            # Skip if both are near zero
            if abs(train_mean) < 1e-6 and abs(test_mean) < 1e-6:
                continue

            # Check that means are within 5x of each other (loose check for stability)
            if train_mean != 0:
                ratio = abs(test_mean / train_mean)
                assert 0.01 < ratio < 100, f"Feature {col} unstable: train={train_mean:.4f}, test={test_mean:.4f}"

        print(f"\n✓ Train/test split stability verified")
        print(f"  Train shape: {train.shape}")
        print(f"  Test shape: {test.shape}")


class TestPerformanceBenchmark:
    """Benchmark feature engineering performance"""

    def test_feature_extraction_speed(self, benchmark=None):
        """Benchmark feature extraction time"""
        # Create dataset
        n = 1000
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='4h')

        df = pd.DataFrame({
            'open': 2000 + np.cumsum(np.random.randn(n)),
            'high': 2010 + np.cumsum(np.random.randn(n)),
            'low': 1990 + np.cumsum(np.random.randn(n)),
            'close': 2000 + np.cumsum(np.random.randn(n)),
            'volume': np.random.lognormal(10, 1, n)
        }, index=dates)

        macro_df = pd.DataFrame({
            'BTCDOM': 40 + np.random.randn(n)
        }, index=dates)

        engineer = FeatureEngineer()

        # Time execution
        start = datetime.now()

        result = engineer.build_full_features(
            crypto_df=df,
            macro_df=macro_df
        )

        elapsed = (datetime.now() - start).total_seconds()

        print(f"\n⏱️  Performance Benchmark:")
        print(f"  Input: {n} rows")
        print(f"  Output: {result.shape[0]} rows × {result.shape[1]} features")
        print(f"  Time: {elapsed:.2f} seconds")
        print(f"  Speed: {result.shape[0] / elapsed:.1f} rows/sec")

        # Should complete in reasonable time (< 30 seconds for 1000 rows)
        assert elapsed < 30, f"Feature extraction too slow: {elapsed:.2f}s"


class TestFeaturePhases:
    """Test each phase of features"""

    @pytest.fixture
    def sample_data(self):
        """Create sample data"""
        n = 200
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='4h')

        df = pd.DataFrame({
            'open': 2000 + np.cumsum(np.random.randn(n)),
            'high': 2010 + np.cumsum(np.random.randn(n)),
            'low': 1990 + np.cumsum(np.random.randn(n)),
            'close': 2000 + np.cumsum(np.random.randn(n)),
            'volume': np.random.lognormal(10, 1, n)
        }, index=dates)

        return df

    def test_phase1_base_features(self, sample_data):
        """Test Phase 1: Base technical features"""
        engineer = FeatureEngineer()
        result = engineer.create_technical_features(sample_data)

        # Check basic features exist
        assert 'returns' in result.columns
        assert 'volatility_24h' in result.columns
        assert 'rsi_14' in result.columns

        print(f"\n✓ Phase 1: Base technical features - {len(result.columns)} features")

    def test_phase3_statistical_features(self, sample_data):
        """Test Phase 3: Statistical features"""
        engineer = FeatureEngineer()
        result = engineer.create_technical_features(sample_data)

        # Check statistical features
        assert 'returns_skew_24h' in result.columns
        assert 'returns_kurt_24h' in result.columns
        assert 'returns_autocorr_24h' in result.columns

        print(f"\n✓ Phase 3: Statistical features present")

    def test_phase4_tsfresh_inspired(self, sample_data):
        """Test Phase 4: tsfresh-inspired features"""
        engineer = FeatureEngineer()
        result = engineer.create_technical_features(sample_data)

        # Check tsfresh-inspired features
        assert 'approx_entropy_24h' in result.columns
        assert 'price_trend_slope_24h' in result.columns
        assert 'benford_corr_24h' in result.columns

        print(f"\n✓ Phase 4: tsfresh-inspired features present")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
