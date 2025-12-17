"""
Automated Feature Extraction Module (FASE 5)
=============================================

Automatic feature generation using tsfresh library.

Modules:
- tsfresh_engine: Automated feature extraction
- feature_selector: Statistical feature selection

Usage:
    from features.automated import get_tsfresh_features

    features = get_tsfresh_features(df, target, n_top=100)
"""

from .tsfresh_engine import TSFreshEngine, get_tsfresh_features
from .feature_selector import FeatureSelector, select_features

__all__ = [
    'TSFreshEngine',
    'get_tsfresh_features',
    'FeatureSelector',
    'select_features'
]
