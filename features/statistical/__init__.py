"""
Statistical Features Module
============================

Advanced statistical analysis for feature engineering:
- Hurst exponent (memory and regime detection)
- Entropy measures (complexity and predictability)
- Kalman filtering (state estimation)
- Wavelets and FFT (frequency analysis)

Total features: ~100
"""

from .hurst_calculator import HurstCalculator
from .entropy_calculator import EntropyCalculator
from .kalman_filter import SimpleKalmanFilter
from .wavelet_features import WaveletFeatures

__all__ = [
    'HurstCalculator',
    'EntropyCalculator',
    'SimpleKalmanFilter',
    'WaveletFeatures'
]
