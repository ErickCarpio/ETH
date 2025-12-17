"""
Hurst Exponent Calculator
==========================

Calculates Hurst exponent to detect:
- Memory in price series (H > 0.5: trending, H < 0.5: mean-reverting, H = 0.5: random walk)
- Regime changes (transition between trending/mean-reverting)
- Regime duration (how long in current regime)

Features generated: ~15
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
import logging

try:
    import nolds
    NOLDS_AVAILABLE = True
except (ImportError, TypeError) as e:
    NOLDS_AVAILABLE = False
    logging.warning(f"nolds not available - Hurst exponent features will use fallback method. Error: {e}")


class HurstCalculator:
    """
    Calculates Hurst exponent and related features for time series analysis.

    Hurst Exponent interpretation:
    - H < 0.5: Mean-reverting (anti-persistent)
    - H = 0.5: Random walk (geometric Brownian motion)
    - H > 0.5: Trending (persistent)
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize Hurst calculator.

        Args:
            logger: Logger instance for debugging
        """
        self.logger = logger or logging.getLogger(__name__)
        self.regime_history = []
        self.regime_threshold = 0.5  # Threshold for regime classification

    def calculate_hurst_rs(self, prices: np.ndarray, min_window: int = 10) -> float:
        """
        Calculate Hurst exponent using Rescaled Range (R/S) method.

        This is a fallback method when nolds is not available.

        Args:
            prices: Price series (numpy array)
            min_window: Minimum window size for R/S calculation

        Returns:
            Hurst exponent value (0-1)
        """
        if len(prices) < min_window * 2:
            return 0.5  # Not enough data, assume random walk

        try:
            # Convert prices to returns
            returns = np.diff(np.log(prices))

            # Remove any NaN or inf values
            returns = returns[np.isfinite(returns)]

            if len(returns) < min_window:
                return 0.5

            # Calculate R/S statistic for different window sizes
            window_sizes = []
            rs_values = []

            for window in range(min_window, len(returns) // 2, max(1, len(returns) // 20)):
                n_windows = len(returns) // window
                rs_for_window = []

                for i in range(n_windows):
                    window_data = returns[i * window:(i + 1) * window]

                    if len(window_data) < min_window:
                        continue

                    # Calculate mean
                    mean = np.mean(window_data)

                    # Calculate cumulative deviations
                    cumdev = np.cumsum(window_data - mean)

                    # Calculate range
                    R = np.max(cumdev) - np.min(cumdev)

                    # Calculate standard deviation
                    S = np.std(window_data, ddof=1)

                    if S > 0 and R > 0:
                        rs_for_window.append(R / S)

                if rs_for_window:
                    window_sizes.append(window)
                    rs_values.append(np.mean(rs_for_window))

            if len(window_sizes) < 2:
                return 0.5

            # Fit log(R/S) = H * log(n) + c
            # H is the slope
            log_windows = np.log(window_sizes)
            log_rs = np.log(rs_values)

            # Remove any inf or nan
            valid_idx = np.isfinite(log_windows) & np.isfinite(log_rs)
            if np.sum(valid_idx) < 2:
                return 0.5

            log_windows = log_windows[valid_idx]
            log_rs = log_rs[valid_idx]

            # Linear regression
            hurst = np.polyfit(log_windows, log_rs, 1)[0]

            # Clip to valid range
            hurst = np.clip(hurst, 0, 1)

            return float(hurst)

        except Exception as e:
            self.logger.warning(f"Error calculating Hurst (R/S): {e}")
            return 0.5

    def calculate_hurst(self, prices: np.ndarray, method: str = 'rs') -> float:
        """
        Calculate Hurst exponent using specified method.

        Args:
            prices: Price series
            method: 'rs' for rescaled range (default), or nolds methods if available

        Returns:
            Hurst exponent
        """
        if not NOLDS_AVAILABLE or method == 'rs':
            return self.calculate_hurst_rs(prices)

        try:
            # Use nolds library if available
            hurst = nolds.hurst_rs(prices, nvals=None, fit='RANSAC')
            return float(np.clip(hurst, 0, 1))
        except Exception as e:
            self.logger.warning(f"Error with nolds.hurst_rs, falling back to R/S: {e}")
            return self.calculate_hurst_rs(prices)

    def calculate_hurst_rolling(self,
                                prices: pd.Series,
                                windows: List[int] = [24, 72, 168]) -> Dict[str, float]:
        """
        Calculate Hurst exponent over multiple rolling windows.

        Args:
            prices: Price series (pandas Series with DatetimeIndex)
            windows: List of window sizes (in number of periods)

        Returns:
            Dictionary with Hurst values for each window
        """
        features = {}

        for window in windows:
            if len(prices) >= window:
                window_prices = prices.iloc[-window:].values
                hurst = self.calculate_hurst(window_prices)
                features[f'hurst_{window}h'] = hurst
            else:
                features[f'hurst_{window}h'] = 0.5

        return features

    def calculate_hurst_velocity(self,
                                 prices: pd.Series,
                                 window: int = 72,
                                 lookback: int = 24) -> float:
        """
        Calculate rate of change in Hurst exponent.

        This measures how quickly the market is transitioning between regimes.

        Args:
            prices: Price series
            window: Window size for Hurst calculation
            lookback: How far back to look for velocity calculation

        Returns:
            Hurst velocity (change per period)
        """
        if len(prices) < window + lookback:
            return 0.0

        # Current Hurst
        current_hurst = self.calculate_hurst(prices.iloc[-window:].values)

        # Past Hurst
        past_hurst = self.calculate_hurst(prices.iloc[-(window + lookback):-lookback].values)

        # Velocity
        velocity = (current_hurst - past_hurst) / lookback

        return float(velocity)

    def detect_regime(self, hurst: float) -> str:
        """
        Classify market regime based on Hurst exponent.

        Args:
            hurst: Hurst exponent value

        Returns:
            'trending', 'random', or 'mean_reverting'
        """
        if hurst > 0.55:
            return 'trending'
        elif hurst < 0.45:
            return 'mean_reverting'
        else:
            return 'random'

    def calculate_regime_duration(self,
                                  prices: pd.Series,
                                  window: int = 72,
                                  check_interval: int = 24) -> int:
        """
        Calculate how long the market has been in the current regime.

        Args:
            prices: Price series
            window: Window size for Hurst calculation
            check_interval: Interval to check for regime changes

        Returns:
            Duration in number of periods
        """
        if len(prices) < window + check_interval:
            return 1

        # Get current regime
        current_hurst = self.calculate_hurst(prices.iloc[-window:].values)
        current_regime = self.detect_regime(current_hurst)

        # Look back to find when regime changed
        duration = 0
        max_lookback = min(len(prices) - window, 30 * check_interval)  # Max 30 checks

        for i in range(check_interval, max_lookback, check_interval):
            past_hurst = self.calculate_hurst(prices.iloc[-(window + i):-i].values)
            past_regime = self.detect_regime(past_hurst)

            if past_regime == current_regime:
                duration = i
            else:
                break

        return duration

    def calculate_all_features(self, df: pd.DataFrame, price_col: str = 'close') -> Dict[str, float]:
        """
        Calculate all Hurst-related features.

        Args:
            df: DataFrame with OHLCV data
            price_col: Name of price column to use

        Returns:
            Dictionary of features
        """
        features = {}

        if price_col not in df.columns or len(df) < 24:
            # Return placeholder features if not enough data
            return {
                'hurst_24h': 0.5,
                'hurst_72h': 0.5,
                'hurst_168h': 0.5,
                'hurst_velocity_24h': 0.0,
                'hurst_velocity_72h': 0.0,
                'hurst_regime_trending': 0,
                'hurst_regime_mean_reverting': 0,
                'hurst_regime_random': 1,
                'hurst_regime_duration': 1,
                'hurst_stability': 0.0,
                'hurst_24_72_diff': 0.0,
                'hurst_72_168_diff': 0.0,
                'hurst_trend_strength': 0.0,
                'hurst_mean_revert_strength': 0.0,
                'hurst_persistence': 0.5
            }

        prices = df[price_col]

        # Rolling Hurst values
        rolling_hurst = self.calculate_hurst_rolling(prices, windows=[24, 72, 168])
        features.update(rolling_hurst)

        # Hurst velocities
        features['hurst_velocity_24h'] = self.calculate_hurst_velocity(prices, window=72, lookback=24)
        features['hurst_velocity_72h'] = self.calculate_hurst_velocity(prices, window=168, lookback=72)

        # Regime detection
        current_hurst = features.get('hurst_72h', 0.5)
        regime = self.detect_regime(current_hurst)
        features['hurst_regime_trending'] = 1 if regime == 'trending' else 0
        features['hurst_regime_mean_reverting'] = 1 if regime == 'mean_reverting' else 0
        features['hurst_regime_random'] = 1 if regime == 'random' else 0

        # Regime duration
        features['hurst_regime_duration'] = self.calculate_regime_duration(prices, window=72, check_interval=24)

        # Hurst stability (lower std = more stable regime)
        if len(prices) >= 168:
            hurst_series = []
            for i in range(0, min(7, len(prices) // 24)):  # Last 7 days worth
                start_idx = -(24 * (i + 3))
                end_idx = -(24 * i) if i > 0 else None
                window_prices = prices.iloc[start_idx:end_idx].values
                if len(window_prices) >= 24:
                    hurst_series.append(self.calculate_hurst(window_prices))

            features['hurst_stability'] = 1.0 - np.std(hurst_series) if hurst_series else 0.0
        else:
            features['hurst_stability'] = 0.0

        # Hurst differences (term structure)
        features['hurst_24_72_diff'] = features.get('hurst_24h', 0.5) - features.get('hurst_72h', 0.5)
        features['hurst_72_168_diff'] = features.get('hurst_72h', 0.5) - features.get('hurst_168h', 0.5)

        # Trend/Mean-reversion strength (distance from 0.5)
        features['hurst_trend_strength'] = max(0, current_hurst - 0.5)
        features['hurst_mean_revert_strength'] = max(0, 0.5 - current_hurst)
        features['hurst_persistence'] = current_hurst

        return features


def add_hurst_features(df: pd.DataFrame, price_col: str = 'close') -> pd.DataFrame:
    """
    Convenience function to add Hurst features to a DataFrame.

    Args:
        df: DataFrame with OHLCV data
        price_col: Name of price column

    Returns:
        DataFrame with added Hurst features
    """
    calculator = HurstCalculator()
    features = calculator.calculate_all_features(df, price_col)

    for key, value in features.items():
        df[key] = value

    return df
