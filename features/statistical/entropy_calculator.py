"""
Entropy Calculator
==================

Calculates various entropy measures to quantify:
- Spectral entropy: Complexity in frequency domain
- Approximate entropy: Regularity and predictability
- Sample entropy: Complexity without self-matches
- Permutation entropy: Order pattern complexity

Features generated: ~20
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional
import logging

try:
    import antropy as ant
    ANTROPY_AVAILABLE = True
except ImportError:
    ANTROPY_AVAILABLE = False
    logging.warning("antropy not available - entropy features will use fallback methods")

from scipy import signal
from scipy.stats import entropy


class EntropyCalculator:
    """
    Calculates entropy-based features for complexity and predictability analysis.

    Lower entropy = more predictable
    Higher entropy = more complex/random
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize entropy calculator.

        Args:
            logger: Logger instance for debugging
        """
        self.logger = logger or logging.getLogger(__name__)

    def spectral_entropy(self, returns: np.ndarray, sf: float = 1.0, method: str = 'welch') -> float:
        """
        Calculate spectral entropy using power spectral density.

        Measures complexity in the frequency domain. High values indicate
        presence of multiple frequencies (complex signal).

        Args:
            returns: Return series
            sf: Sampling frequency (default 1.0 for hourly data)
            method: 'welch' or 'fft'

        Returns:
            Spectral entropy value (0-1)
        """
        if len(returns) < 10:
            return 0.5

        try:
            if ANTROPY_AVAILABLE:
                se = ant.spectral_entropy(returns, sf=sf, method=method, normalize=True)
                return float(np.clip(se, 0, 1))
            else:
                # Fallback implementation
                if method == 'welch':
                    freqs, psd = signal.welch(returns, fs=sf)
                else:
                    freqs = np.fft.rfftfreq(len(returns), 1/sf)
                    psd = np.abs(np.fft.rfft(returns))**2

                # Normalize PSD
                psd_norm = psd / np.sum(psd)

                # Calculate entropy
                se = entropy(psd_norm, base=2)

                # Normalize to [0, 1]
                max_entropy = np.log2(len(psd_norm))
                if max_entropy > 0:
                    se = se / max_entropy

                return float(np.clip(se, 0, 1))

        except Exception as e:
            self.logger.warning(f"Error calculating spectral entropy: {e}")
            return 0.5

    def approximate_entropy(self, returns: np.ndarray, m: int = 2, r: Optional[float] = None) -> float:
        """
        Calculate approximate entropy (ApEn).

        Measures regularity and unpredictability. Lower values indicate more
        regular, predictable time series.

        Args:
            returns: Return series
            m: Pattern length (default 2)
            r: Tolerance (default is 0.2 * std)

        Returns:
            Approximate entropy value
        """
        if len(returns) < 10 * m:
            return 1.0

        try:
            if r is None:
                r = 0.2 * np.std(returns, ddof=1)

            if ANTROPY_AVAILABLE:
                apen = ant.app_entropy(returns, order=m, metric='chebyshev')
                return float(np.clip(apen, 0, 2))
            else:
                # Simplified fallback
                n = len(returns)

                def _maxdist(x_i, x_j):
                    return max([abs(ua - va) for ua, va in zip(x_i, x_j)])

                def _phi(m):
                    x = [[returns[j] for j in range(i, i + m)] for i in range(n - m + 1)]
                    C = [len([1 for x_j in x if _maxdist(x_i, x_j) <= r]) / (n - m + 1.0) for x_i in x]
                    return (n - m + 1.0) ** (-1) * sum(np.log(C))

                apen = abs(_phi(m) - _phi(m + 1))
                return float(np.clip(apen, 0, 2))

        except Exception as e:
            self.logger.warning(f"Error calculating approximate entropy: {e}")
            return 1.0

    def sample_entropy(self, returns: np.ndarray, m: int = 2, r: Optional[float] = None) -> float:
        """
        Calculate sample entropy (SampEn).

        Similar to ApEn but more consistent and doesn't count self-matches.
        Lower values = more regular.

        Args:
            returns: Return series
            m: Pattern length
            r: Tolerance

        Returns:
            Sample entropy value
        """
        if len(returns) < 10 * m:
            return 1.0

        try:
            if r is None:
                r = 0.2 * np.std(returns, ddof=1)

            if ANTROPY_AVAILABLE:
                sampen = ant.sample_entropy(returns, order=m)
                return float(np.clip(sampen, 0, 2))
            else:
                # Simplified fallback
                n = len(returns)

                def _maxdist(x_i, x_j):
                    return max([abs(ua - va) for ua, va in zip(x_i, x_j)])

                def _phi(m):
                    x = [[returns[j] for j in range(i, i + m)] for i in range(n - m)]
                    B = 0
                    for i in range(len(x)):
                        for j in range(len(x)):
                            if i != j and _maxdist(x[i], x[j]) <= r:
                                B += 1
                    return B

                B_m = _phi(m)
                B_m1 = _phi(m + 1)

                if B_m > 0:
                    sampen = -np.log(B_m1 / B_m)
                else:
                    sampen = 1.0

                return float(np.clip(sampen, 0, 2))

        except Exception as e:
            self.logger.warning(f"Error calculating sample entropy: {e}")
            return 1.0

    def permutation_entropy(self, returns: np.ndarray, order: int = 3, normalize: bool = True) -> float:
        """
        Calculate permutation entropy (PE).

        Measures complexity based on order patterns. Robust to noise.

        Args:
            returns: Return series
            order: Embedding dimension (typically 3-7)
            normalize: Whether to normalize to [0, 1]

        Returns:
            Permutation entropy value
        """
        if len(returns) < 10 * order:
            return 0.5

        try:
            if ANTROPY_AVAILABLE:
                pe = ant.perm_entropy(returns, order=order, normalize=normalize)
                return float(np.clip(pe, 0, 1))
            else:
                # Fallback implementation
                n = len(returns)
                permutations = {}

                # Generate all permutation patterns
                for i in range(n - order):
                    # Get subsequence
                    subseq = returns[i:i + order]

                    # Get permutation pattern (argsort gives rank order)
                    pattern = tuple(np.argsort(subseq))

                    # Count pattern
                    permutations[pattern] = permutations.get(pattern, 0) + 1

                # Calculate probabilities
                total = sum(permutations.values())
                probs = [count / total for count in permutations.values()]

                # Calculate entropy
                pe = entropy(probs, base=2)

                # Normalize if requested
                if normalize:
                    max_entropy = np.log2(np.math.factorial(order))
                    if max_entropy > 0:
                        pe = pe / max_entropy

                return float(np.clip(pe, 0, 1))

        except Exception as e:
            self.logger.warning(f"Error calculating permutation entropy: {e}")
            return 0.5

    def multiscale_entropy(self, returns: np.ndarray, scales: list = [1, 2, 3, 5]) -> Dict[str, float]:
        """
        Calculate entropy at multiple time scales.

        Args:
            returns: Return series
            scales: List of coarse-graining scales

        Returns:
            Dictionary with entropy at each scale
        """
        features = {}

        for scale in scales:
            if len(returns) < 20 * scale:
                features[f'entropy_scale_{scale}'] = 0.5
                continue

            # Coarse-grain the series
            n = len(returns) // scale
            coarse_grained = np.array([np.mean(returns[i*scale:(i+1)*scale]) for i in range(n)])

            # Calculate sample entropy on coarse-grained series
            se = self.sample_entropy(coarse_grained, m=2)
            features[f'entropy_scale_{scale}'] = se

        return features

    def calculate_entropy_percentiles(self, returns: np.ndarray, window: int = 168) -> Dict[str, float]:
        """
        Calculate current entropy relative to historical distribution.

        Args:
            returns: Return series
            window: Window size for rolling calculation

        Returns:
            Dictionary with percentile features
        """
        features = {}

        if len(returns) < window * 2:
            return {
                'spectral_entropy_percentile': 0.5,
                'approx_entropy_percentile': 0.5,
                'sample_entropy_percentile': 0.5,
                'perm_entropy_percentile': 0.5
            }

        try:
            # Calculate rolling entropy values
            n_windows = min(30, len(returns) // window)
            se_history = []
            apen_history = []
            sampen_history = []
            pe_history = []

            for i in range(n_windows):
                start_idx = -(window * (i + 1))
                end_idx = -(window * i) if i > 0 else None
                window_returns = returns[start_idx:end_idx]

                if len(window_returns) >= window:
                    se_history.append(self.spectral_entropy(window_returns))
                    apen_history.append(self.approximate_entropy(window_returns))
                    sampen_history.append(self.sample_entropy(window_returns))
                    pe_history.append(self.permutation_entropy(window_returns))

            # Current values
            current_se = self.spectral_entropy(returns[-window:])
            current_apen = self.approximate_entropy(returns[-window:])
            current_sampen = self.sample_entropy(returns[-window:])
            current_pe = self.permutation_entropy(returns[-window:])

            # Calculate percentiles
            if se_history:
                features['spectral_entropy_percentile'] = np.mean([v < current_se for v in se_history])
                features['approx_entropy_percentile'] = np.mean([v < current_apen for v in apen_history])
                features['sample_entropy_percentile'] = np.mean([v < current_sampen for v in sampen_history])
                features['perm_entropy_percentile'] = np.mean([v < current_pe for v in pe_history])
            else:
                features = {
                    'spectral_entropy_percentile': 0.5,
                    'approx_entropy_percentile': 0.5,
                    'sample_entropy_percentile': 0.5,
                    'perm_entropy_percentile': 0.5
                }

        except Exception as e:
            self.logger.warning(f"Error calculating entropy percentiles: {e}")
            features = {
                'spectral_entropy_percentile': 0.5,
                'approx_entropy_percentile': 0.5,
                'sample_entropy_percentile': 0.5,
                'perm_entropy_percentile': 0.5
            }

        return features

    def calculate_all_features(self, df: pd.DataFrame, price_col: str = 'close') -> Dict[str, float]:
        """
        Calculate all entropy-based features.

        Args:
            df: DataFrame with OHLCV data
            price_col: Name of price column

        Returns:
            Dictionary of features
        """
        features = {}

        if price_col not in df.columns or len(df) < 24:
            # Return placeholder features
            return {
                'spectral_entropy': 0.5,
                'approx_entropy': 1.0,
                'sample_entropy': 1.0,
                'perm_entropy_3': 0.5,
                'perm_entropy_5': 0.5,
                'perm_entropy_7': 0.5,
                'entropy_scale_1': 0.5,
                'entropy_scale_2': 0.5,
                'entropy_scale_3': 0.5,
                'entropy_scale_5': 0.5,
                'spectral_entropy_percentile': 0.5,
                'approx_entropy_percentile': 0.5,
                'sample_entropy_percentile': 0.5,
                'perm_entropy_percentile': 0.5,
                'entropy_complexity_index': 0.5,
                'entropy_predictability_score': 0.5,
                'entropy_regime_structured': 0,
                'entropy_regime_chaotic': 0,
                'entropy_diversity': 0.5,
                'entropy_stability': 0.5
            }

        # Calculate returns
        prices = df[price_col].values
        returns = np.diff(np.log(prices))
        returns = returns[np.isfinite(returns)]

        if len(returns) < 24:
            return features

        # Base entropy measures
        features['spectral_entropy'] = self.spectral_entropy(returns)
        features['approx_entropy'] = self.approximate_entropy(returns, m=2)
        features['sample_entropy'] = self.sample_entropy(returns, m=2)

        # Permutation entropy with different orders
        features['perm_entropy_3'] = self.permutation_entropy(returns, order=3)
        features['perm_entropy_5'] = self.permutation_entropy(returns, order=5)
        if len(returns) >= 100:
            features['perm_entropy_7'] = self.permutation_entropy(returns, order=7)
        else:
            features['perm_entropy_7'] = 0.5

        # Multiscale entropy
        multiscale = self.multiscale_entropy(returns, scales=[1, 2, 3, 5])
        features.update(multiscale)

        # Entropy percentiles
        percentiles = self.calculate_entropy_percentiles(returns, window=min(168, len(returns) // 2))
        features.update(percentiles)

        # Composite features
        # Complexity index (avg of normalized entropies)
        features['entropy_complexity_index'] = np.mean([
            features['spectral_entropy'],
            features['perm_entropy_3']
        ])

        # Predictability score (inverse of entropy)
        features['entropy_predictability_score'] = 1.0 - features['entropy_complexity_index']

        # Regime classification based on entropy
        avg_entropy = np.mean([features['sample_entropy'], features['approx_entropy']])
        features['entropy_regime_structured'] = 1 if avg_entropy < 0.7 else 0
        features['entropy_regime_chaotic'] = 1 if avg_entropy > 1.3 else 0

        # Entropy diversity (variance across different measures)
        entropy_values = [
            features['spectral_entropy'],
            features['perm_entropy_3'],
            features['perm_entropy_5']
        ]
        features['entropy_diversity'] = np.std(entropy_values)

        # Entropy stability (consistency across scales)
        scale_entropies = [features.get(f'entropy_scale_{s}', 0.5) for s in [1, 2, 3, 5]]
        features['entropy_stability'] = 1.0 - np.std(scale_entropies)

        return features


def add_entropy_features(df: pd.DataFrame, price_col: str = 'close') -> pd.DataFrame:
    """
    Convenience function to add entropy features to a DataFrame.

    Args:
        df: DataFrame with OHLCV data
        price_col: Name of price column

    Returns:
        DataFrame with added entropy features
    """
    calculator = EntropyCalculator()
    features = calculator.calculate_all_features(df, price_col)

    for key, value in features.items():
        df[key] = value

    return df
