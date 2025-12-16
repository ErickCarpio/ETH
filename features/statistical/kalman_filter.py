"""
Kalman Filter for Price Series
================================

Implements a simple Kalman filter for:
- State estimation (filtered price)
- Noise reduction
- Prediction
- Residual analysis (distance from predicted)

Features generated: ~15

Note: This is a simplified 1D Kalman filter since filterpy is not available.
For production, consider using filterpy when possible.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
import logging


class SimpleKalmanFilter:
    """
    Simple 1D Kalman filter for price series.

    State model:
        x[k] = x[k-1] + w[k]    (random walk)
        y[k] = x[k] + v[k]      (observed price)

    where:
        x = true price state
        y = observed price
        w = process noise
        v = measurement noise
    """

    def __init__(self,
                 process_variance: float = 1e-5,
                 measurement_variance: float = 1e-4,
                 initial_value: Optional[float] = None,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize Kalman filter.

        Args:
            process_variance: Process noise variance (Q)
            measurement_variance: Measurement noise variance (R)
            initial_value: Initial price estimate
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

        # Process noise covariance
        self.Q = process_variance

        # Measurement noise covariance
        self.R = measurement_variance

        # State estimate
        self.x = initial_value

        # Estimate error covariance
        self.P = 1.0

        # Kalman gain
        self.K = 0.0

        # History for analysis
        self.filtered_prices = []
        self.predicted_prices = []
        self.residuals = []
        self.innovations = []
        self.kalman_gains = []

    def predict(self) -> float:
        """
        Predict next state (prediction step).

        Returns:
            Predicted state
        """
        # State prediction: x[k|k-1] = x[k-1|k-1]
        x_pred = self.x

        # Error covariance prediction: P[k|k-1] = P[k-1|k-1] + Q
        self.P = self.P + self.Q

        return x_pred

    def update(self, measurement: float) -> float:
        """
        Update state estimate with new measurement (update step).

        Args:
            measurement: Observed price

        Returns:
            Updated state estimate (filtered price)
        """
        # Prediction step
        x_pred = self.predict()
        self.predicted_prices.append(x_pred)

        # Innovation (measurement residual)
        innovation = measurement - x_pred
        self.innovations.append(innovation)

        # Innovation covariance
        S = self.P + self.R

        # Kalman gain
        self.K = self.P / S
        self.kalman_gains.append(self.K)

        # State update
        self.x = x_pred + self.K * innovation

        # Error covariance update
        self.P = (1 - self.K) * self.P

        # Store filtered value
        self.filtered_prices.append(self.x)

        # Calculate residual (difference from filtered)
        residual = measurement - self.x
        self.residuals.append(residual)

        return self.x

    def filter_series(self, prices: np.ndarray) -> np.ndarray:
        """
        Filter an entire price series.

        Args:
            prices: Array of prices

        Returns:
            Array of filtered prices
        """
        if len(prices) == 0:
            return np.array([])

        # Initialize with first price
        self.x = prices[0]
        self.P = 1.0
        self.filtered_prices = []
        self.predicted_prices = []
        self.residuals = []
        self.innovations = []
        self.kalman_gains = []

        # Filter each observation
        filtered = []
        for price in prices:
            filtered_price = self.update(price)
            filtered.append(filtered_price)

        return np.array(filtered)

    def get_prediction(self) -> float:
        """
        Get next price prediction.

        Returns:
            Predicted next price
        """
        return self.x

    def get_filtered_price(self) -> float:
        """
        Get current filtered price estimate.

        Returns:
            Current state estimate
        """
        return self.x

    def get_residuals(self) -> np.ndarray:
        """
        Get residuals (observed - filtered).

        Returns:
            Array of residuals
        """
        return np.array(self.residuals)

    def get_innovations(self) -> np.ndarray:
        """
        Get innovations (observed - predicted).

        Returns:
            Array of innovations
        """
        return np.array(self.innovations)

    def get_kalman_gain_history(self) -> np.ndarray:
        """
        Get history of Kalman gains.

        Returns:
            Array of Kalman gains
        """
        return np.array(self.kalman_gains)

    def auto_tune(self, prices: np.ndarray) -> Tuple[float, float]:
        """
        Automatically tune Q and R parameters based on price series.

        Args:
            prices: Historical prices

        Returns:
            Tuple of (optimal_Q, optimal_R)
        """
        if len(prices) < 10:
            return self.Q, self.R

        # Calculate returns variance as proxy for process noise
        returns = np.diff(prices) / prices[:-1]
        returns_var = np.var(returns)

        # Process variance (smaller = smoother filter)
        Q_optimal = returns_var * 0.01

        # Measurement variance
        price_std = np.std(prices)
        R_optimal = (price_std * 0.001) ** 2

        return Q_optimal, R_optimal


class KalmanFeatureExtractor:
    """
    Extract features from Kalman filter analysis.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize feature extractor.

        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def calculate_all_features(self,
                               df: pd.DataFrame,
                               price_col: str = 'close',
                               auto_tune: bool = True) -> Dict[str, float]:
        """
        Calculate all Kalman filter features.

        Args:
            df: DataFrame with OHLCV data
            price_col: Name of price column
            auto_tune: Whether to auto-tune filter parameters

        Returns:
            Dictionary of features
        """
        features = {}

        if price_col not in df.columns or len(df) < 24:
            # Return placeholder features
            return {
                'kalman_filtered_price': 0.0,
                'kalman_predicted_price': 0.0,
                'kalman_residual': 0.0,
                'kalman_residual_std': 0.0,
                'kalman_residual_mean': 0.0,
                'kalman_innovation': 0.0,
                'kalman_gain': 0.5,
                'kalman_gain_avg': 0.5,
                'kalman_gain_trend': 0.0,
                'kalman_price_deviation': 0.0,
                'kalman_price_deviation_pct': 0.0,
                'kalman_noise_ratio': 0.5,
                'kalman_trend_strength': 0.0,
                'kalman_residual_autocorr': 0.0,
                'kalman_prediction_error': 0.0
            }

        prices = df[price_col].values

        # Initialize filter
        kf = SimpleKalmanFilter()

        # Auto-tune if requested
        if auto_tune:
            Q, R = kf.auto_tune(prices)
            kf = SimpleKalmanFilter(process_variance=Q, measurement_variance=R)

        # Filter the series
        filtered_prices = kf.filter_series(prices)

        # Current values
        current_price = prices[-1]
        features['kalman_filtered_price'] = kf.get_filtered_price()
        features['kalman_predicted_price'] = kf.get_prediction()

        # Residuals
        residuals = kf.get_residuals()
        if len(residuals) > 0:
            features['kalman_residual'] = residuals[-1]
            features['kalman_residual_std'] = np.std(residuals[-min(24, len(residuals)):])
            features['kalman_residual_mean'] = np.mean(residuals[-min(24, len(residuals)):])
        else:
            features['kalman_residual'] = 0.0
            features['kalman_residual_std'] = 0.0
            features['kalman_residual_mean'] = 0.0

        # Innovations
        innovations = kf.get_innovations()
        if len(innovations) > 0:
            features['kalman_innovation'] = innovations[-1]
        else:
            features['kalman_innovation'] = 0.0

        # Kalman gain
        gains = kf.get_kalman_gain_history()
        if len(gains) > 0:
            features['kalman_gain'] = gains[-1]
            features['kalman_gain_avg'] = np.mean(gains[-min(24, len(gains)):])

            # Kalman gain trend (increasing = more trust in measurements)
            if len(gains) >= 10:
                recent_gains = gains[-10:]
                features['kalman_gain_trend'] = (recent_gains[-1] - recent_gains[0]) / 10
            else:
                features['kalman_gain_trend'] = 0.0
        else:
            features['kalman_gain'] = 0.5
            features['kalman_gain_avg'] = 0.5
            features['kalman_gain_trend'] = 0.0

        # Price deviation from filtered
        features['kalman_price_deviation'] = current_price - features['kalman_filtered_price']
        if features['kalman_filtered_price'] != 0:
            features['kalman_price_deviation_pct'] = (features['kalman_price_deviation'] /
                                                      features['kalman_filtered_price']) * 100
        else:
            features['kalman_price_deviation_pct'] = 0.0

        # Noise ratio (residual std / price std)
        price_std = np.std(prices[-min(24, len(prices)):])
        if price_std > 0:
            features['kalman_noise_ratio'] = features['kalman_residual_std'] / price_std
        else:
            features['kalman_noise_ratio'] = 0.5

        # Trend strength (filtered price velocity)
        if len(filtered_prices) >= 10:
            filtered_returns = np.diff(filtered_prices[-10:])
            features['kalman_trend_strength'] = np.mean(filtered_returns)
        else:
            features['kalman_trend_strength'] = 0.0

        # Residual autocorrelation (if residuals are autocorrelated, model is missing something)
        if len(residuals) >= 20:
            recent_residuals = residuals[-20:]
            residual_mean = np.mean(recent_residuals)
            if np.std(recent_residuals) > 0:
                acf = np.corrcoef(recent_residuals[:-1] - residual_mean,
                                recent_residuals[1:] - residual_mean)[0, 1]
                features['kalman_residual_autocorr'] = acf if not np.isnan(acf) else 0.0
            else:
                features['kalman_residual_autocorr'] = 0.0
        else:
            features['kalman_residual_autocorr'] = 0.0

        # Prediction error (absolute % error on last prediction)
        if len(prices) >= 2 and len(kf.predicted_prices) >= 1:
            last_prediction = kf.predicted_prices[-1]
            last_actual = prices[-1]
            if last_actual != 0:
                features['kalman_prediction_error'] = abs((last_actual - last_prediction) / last_actual) * 100
            else:
                features['kalman_prediction_error'] = 0.0
        else:
            features['kalman_prediction_error'] = 0.0

        return features


def add_kalman_features(df: pd.DataFrame,
                       price_col: str = 'close',
                       auto_tune: bool = True) -> pd.DataFrame:
    """
    Convenience function to add Kalman filter features to a DataFrame.

    Args:
        df: DataFrame with OHLCV data
        price_col: Name of price column
        auto_tune: Whether to auto-tune filter parameters

    Returns:
        DataFrame with added Kalman features
    """
    extractor = KalmanFeatureExtractor()
    features = extractor.calculate_all_features(df, price_col, auto_tune)

    for key, value in features.items():
        df[key] = value

    return df
