"""
Feature Selector - Statistical Feature Selection
==================================================

Advanced feature selection using statistical tests and redundancy removal.

Methods:
- Hypothesis testing (correlation, p-values)
- Benjamini-Hochberg FDR correction
- Redundancy removal (correlation threshold)
- Feature importance ranking

Target: Filter 1,750 features → 100 elite features
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from scipy import stats
from scipy.stats import spearmanr, pearsonr
import logging

logger = logging.getLogger(__name__)


class FeatureSelector:
    """
    Statistical feature selection with multiple testing correction.

    Pipeline:
    1. Calculate significance (correlation + p-values)
    2. Apply FDR correction (Benjamini-Hochberg)
    3. Remove redundant features (high correlation between features)
    4. Rank by importance
    """

    def __init__(self, fdr_level: float = 0.05, correlation_threshold: float = 0.95):
        """
        Initialize feature selector.

        Args:
            fdr_level: False Discovery Rate for hypothesis testing
            correlation_threshold: Remove features with correlation > this
        """
        self.fdr_level = fdr_level
        self.correlation_threshold = correlation_threshold
        self.feature_scores = None
        self.selected_features = None

    def calculate_significance(self,
                               features: pd.DataFrame,
                               target: pd.Series,
                               method: str = 'pearson') -> pd.DataFrame:
        """
        Calculate correlation and p-values for each feature vs target.

        Args:
            features: Feature DataFrame
            target: Target variable
            method: 'pearson' or 'spearman'

        Returns:
            DataFrame with columns: feature, correlation, p_value, abs_correlation
        """
        results = []

        # Align indices
        common_idx = features.index.intersection(target.index)
        features_aligned = features.loc[common_idx]
        target_aligned = target.loc[common_idx]

        if len(common_idx) < 10:
            logger.warning(f"Only {len(common_idx)} samples for significance testing")
            return pd.DataFrame(columns=['feature', 'correlation', 'p_value', 'abs_correlation'])

        logger.info(f"Calculating significance for {len(features.columns)} features...")

        for col in features.columns:
            try:
                # Remove NaN
                mask = ~(features_aligned[col].isna() | target_aligned.isna())
                x = features_aligned.loc[mask, col]
                y = target_aligned.loc[mask]

                if len(x) < 10:
                    continue

                # Calculate correlation
                if method == 'pearson':
                    corr, p_value = pearsonr(x, y)
                elif method == 'spearman':
                    corr, p_value = spearmanr(x, y)
                else:
                    raise ValueError(f"Unknown method: {method}")

                if not np.isnan(corr) and not np.isnan(p_value):
                    results.append({
                        'feature': col,
                        'correlation': corr,
                        'p_value': p_value,
                        'abs_correlation': abs(corr)
                    })

            except Exception as e:
                logger.debug(f"Error calculating significance for {col}: {e}")
                continue

        df_results = pd.DataFrame(results)

        if df_results.empty:
            logger.warning("No valid correlations calculated")
            return df_results

        # Sort by absolute correlation
        df_results = df_results.sort_values('abs_correlation', ascending=False)

        logger.info(f"✓ Calculated significance for {len(df_results)} features")
        logger.info(f"  Top correlation: {df_results.iloc[0]['abs_correlation']:.4f} ({df_results.iloc[0]['feature']})")

        return df_results

    def apply_fdr_correction(self, p_values: np.ndarray, method: str = 'bh') -> np.ndarray:
        """
        Apply Benjamini-Hochberg FDR correction for multiple testing.

        The Benjamini-Hochberg procedure:
        1. Sort p-values in ascending order
        2. For each p-value at rank i, compare with (i/m) * alpha
        3. Find largest i where p_i <= (i/m) * alpha
        4. Reject all hypotheses H_1, ..., H_i

        Args:
            p_values: Array of p-values
            method: 'bh' for Benjamini-Hochberg

        Returns:
            Boolean array indicating which features pass FDR correction
        """
        if len(p_values) == 0:
            return np.array([])

        m = len(p_values)
        sorted_idx = np.argsort(p_values)
        sorted_p = p_values[sorted_idx]

        # Benjamini-Hochberg critical values
        critical_values = (np.arange(1, m + 1) / m) * self.fdr_level

        # Find largest i where p_i <= critical_value_i
        passed = sorted_p <= critical_values
        if not passed.any():
            logger.warning(f"No features passed FDR correction at level {self.fdr_level}")
            return np.zeros(m, dtype=bool)

        # All hypotheses up to largest passing index are rejected (features kept)
        max_passing_idx = np.where(passed)[0][-1]

        # Create boolean mask
        rejected = np.zeros(m, dtype=bool)
        rejected[sorted_idx[:max_passing_idx + 1]] = True

        logger.info(f"✓ FDR correction: {rejected.sum()}/{m} features passed (FDR={self.fdr_level})")

        return rejected

    def remove_redundant(self,
                        features: pd.DataFrame,
                        threshold: Optional[float] = None) -> List[str]:
        """
        Remove redundant features with high inter-correlation.

        Strategy:
        - Calculate correlation matrix between all features
        - For each pair with correlation > threshold:
          - Keep the feature with higher correlation to target
          - Remove the other one

        Args:
            features: Feature DataFrame (should be already filtered by significance)
            threshold: Correlation threshold (default: self.correlation_threshold)

        Returns:
            List of selected feature names (non-redundant)
        """
        if threshold is None:
            threshold = self.correlation_threshold

        if features.empty or len(features.columns) == 0:
            return []

        logger.info(f"Removing redundant features (correlation > {threshold})...")

        # Calculate feature correlation matrix
        corr_matrix = features.corr().abs()

        # Set diagonal to 0 (self-correlation)
        np.fill_diagonal(corr_matrix.values, 0)

        # Find redundant pairs
        redundant_pairs = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i + 1, len(corr_matrix.columns)):
                if corr_matrix.iloc[i, j] > threshold:
                    feat_i = corr_matrix.columns[i]
                    feat_j = corr_matrix.columns[j]
                    redundant_pairs.append((feat_i, feat_j, corr_matrix.iloc[i, j]))

        if not redundant_pairs:
            logger.info("✓ No redundant features found")
            return list(features.columns)

        logger.info(f"Found {len(redundant_pairs)} redundant pairs")

        # Track which features to keep
        features_to_keep = set(features.columns)

        # For each redundant pair, remove the one with lower target correlation
        if self.feature_scores is not None:
            scores_dict = dict(zip(self.feature_scores['feature'], self.feature_scores['abs_correlation']))

            for feat_i, feat_j, corr_ij in redundant_pairs:
                # Skip if already removed
                if feat_i not in features_to_keep or feat_j not in features_to_keep:
                    continue

                # Compare correlations with target
                score_i = scores_dict.get(feat_i, 0)
                score_j = scores_dict.get(feat_j, 0)

                # Remove the one with lower score
                if score_i >= score_j:
                    features_to_keep.discard(feat_j)
                else:
                    features_to_keep.discard(feat_i)
        else:
            # No scores available, just remove one arbitrarily
            for feat_i, feat_j, corr_ij in redundant_pairs:
                if feat_i in features_to_keep and feat_j in features_to_keep:
                    features_to_keep.discard(feat_j)

        selected = list(features_to_keep)
        logger.info(f"✓ Kept {len(selected)}/{len(features.columns)} non-redundant features")

        return selected

    def rank_by_importance(self,
                          feature_scores: pd.DataFrame,
                          n_top: Optional[int] = None) -> pd.DataFrame:
        """
        Rank features by importance.

        Importance score = abs(correlation) * (1 - p_value)

        Args:
            feature_scores: DataFrame with correlation and p_value columns
            n_top: Keep only top N features (None = keep all)

        Returns:
            Ranked DataFrame with importance scores
        """
        if feature_scores.empty:
            return feature_scores

        # Calculate importance score
        feature_scores['importance'] = (
            feature_scores['abs_correlation'] * (1 - feature_scores['p_value'])
        )

        # Sort by importance
        feature_scores = feature_scores.sort_values('importance', ascending=False)

        # Keep top N
        if n_top is not None and len(feature_scores) > n_top:
            feature_scores = feature_scores.head(n_top)
            logger.info(f"✓ Ranked and selected top {n_top} features")
        else:
            logger.info(f"✓ Ranked {len(feature_scores)} features by importance")

        return feature_scores

    def select(self,
              features: pd.DataFrame,
              target: pd.Series,
              n_top: int = 100,
              method: str = 'pearson') -> Tuple[List[str], pd.DataFrame]:
        """
        Full selection pipeline.

        Steps:
        1. Calculate significance (correlation + p-values)
        2. Apply FDR correction
        3. Remove redundant features
        4. Rank by importance
        5. Select top N

        Args:
            features: Feature DataFrame
            target: Target variable
            n_top: Number of features to select
            method: Correlation method ('pearson' or 'spearman')

        Returns:
            Tuple of (selected_feature_names, feature_scores_df)
        """
        logger.info(f"Starting feature selection pipeline ({len(features.columns)} candidates → {n_top} selected)...")

        # 1. Calculate significance
        scores = self.calculate_significance(features, target, method=method)

        if scores.empty:
            logger.warning("No features passed significance testing")
            return [], pd.DataFrame()

        self.feature_scores = scores

        # 2. Apply FDR correction
        passed_fdr = self.apply_fdr_correction(scores['p_value'].values)
        scores_fdr = scores[passed_fdr].copy()

        if scores_fdr.empty:
            logger.warning(f"No features passed FDR correction at level {self.fdr_level}")
            # Fallback: take top features by correlation
            logger.info(f"Fallback: selecting top {n_top} by correlation")
            scores_ranked = self.rank_by_importance(scores, n_top=n_top)
            selected = scores_ranked['feature'].tolist()
            return selected, scores_ranked

        logger.info(f"After FDR: {len(scores_fdr)} features")

        # 3. Remove redundant features
        features_fdr = features[scores_fdr['feature'].tolist()]
        non_redundant = self.remove_redundant(features_fdr)

        scores_non_redundant = scores_fdr[scores_fdr['feature'].isin(non_redundant)].copy()

        logger.info(f"After redundancy removal: {len(scores_non_redundant)} features")

        # 4. Rank and select top N
        scores_ranked = self.rank_by_importance(scores_non_redundant, n_top=n_top)

        selected = scores_ranked['feature'].tolist()

        logger.info(f"✅ Feature selection complete: {len(selected)} features selected")
        logger.info(f"  Top 5 features:")
        for i, row in scores_ranked.head(5).iterrows():
            logger.info(f"    {row['feature']}: corr={row['correlation']:.4f}, p={row['p_value']:.4e}")

        self.selected_features = selected

        return selected, scores_ranked


def select_features(features: pd.DataFrame,
                   target: pd.Series,
                   n_top: int = 100,
                   fdr_level: float = 0.05,
                   correlation_threshold: float = 0.95,
                   method: str = 'pearson') -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Convenience function for feature selection.

    Args:
        features: Feature DataFrame
        target: Target variable
        n_top: Number of features to select
        fdr_level: False Discovery Rate
        correlation_threshold: Redundancy threshold
        method: Correlation method

    Returns:
        Tuple of (selected_features_df, scores_df)
    """
    selector = FeatureSelector(fdr_level=fdr_level, correlation_threshold=correlation_threshold)
    selected_names, scores = selector.select(features, target, n_top=n_top, method=method)

    if not selected_names:
        return pd.DataFrame(), pd.DataFrame()

    selected_features = features[selected_names]

    return selected_features, scores


if __name__ == "__main__":
    # Test with synthetic data
    logger.info("Testing feature selector...")

    # Create synthetic features
    n_samples = 1000
    n_features = 200

    np.random.seed(42)

    # Create target
    target = pd.Series(np.random.randn(n_samples) > 0, name='target').astype(int)

    # Create features
    features = pd.DataFrame()

    # 50 informative features (correlated with target)
    for i in range(50):
        noise = np.random.randn(n_samples) * 0.5
        signal = target.values + noise
        features[f'informative_{i}'] = signal

    # 50 redundant features (correlated with informative features)
    for i in range(50):
        base = features[f'informative_{i % 50}']
        noise = np.random.randn(n_samples) * 0.1
        features[f'redundant_{i}'] = base + noise

    # 100 random features (no correlation)
    for i in range(100):
        features[f'random_{i}'] = np.random.randn(n_samples)

    # Select features
    selected, scores = select_features(features, target, n_top=30)

    print("\n" + "="*60)
    print("FEATURE SELECTOR TEST")
    print("="*60)
    print(f"\nInput: {features.shape[1]} features, {n_samples} samples")
    print(f"Output: {selected.shape[1]} features selected")
    print(f"\nTop 10 features:")
    print(scores.head(10)[['feature', 'correlation', 'p_value', 'importance']])

    # Check how many informative vs random features were selected
    informative_count = sum('informative' in f for f in selected.columns)
    redundant_count = sum('redundant' in f for f in selected.columns)
    random_count = sum('random' in f for f in selected.columns)

    print(f"\nSelected feature breakdown:")
    print(f"  Informative: {informative_count}")
    print(f"  Redundant: {redundant_count}")
    print(f"  Random: {random_count}")
