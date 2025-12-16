"""
Wavelet and FFT Features
=========================

Extracts frequency-domain features using:
- Fast Fourier Transform (FFT) - dominant frequencies
- Continuous Wavelet Transform (CWT) - time-frequency analysis
- Discrete Wavelet Transform (DWT) - multi-resolution analysis
- Energy distribution by frequency bands

Features generated: ~30
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, List
import logging

try:
    import pywt
    PYWT_AVAILABLE = True
except ImportError:
    PYWT_AVAILABLE = False
    logging.warning("PyWavelets not available - wavelet features will use FFT only")

from scipy import signal
from scipy.fft import fft, fftfreq


class WaveletFeatures:
    """
    Extract wavelet and frequency-domain features from price series.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize wavelet feature extractor.

        Args:
            logger: Logger instance for debugging
        """
        self.logger = logger or logging.getLogger(__name__)

    def calculate_fft(self,
                     returns: np.ndarray,
                     n_coefs: int = 20,
                     sampling_rate: float = 1.0) -> Dict[str, float]:
        """
        Calculate Fast Fourier Transform features.

        Args:
            returns: Return series
            n_coefs: Number of top coefficients to extract
            sampling_rate: Sampling rate (1.0 for hourly data)

        Returns:
            Dictionary with FFT features
        """
        features = {}

        if len(returns) < 10:
            # Not enough data
            for i in range(min(n_coefs, 5)):
                features[f'fft_coef_{i}'] = 0.0
            features['fft_dominant_freq'] = 0.0
            features['fft_dominant_period'] = 0.0
            features['fft_spectral_centroid'] = 0.0
            features['fft_spectral_rolloff'] = 0.0
            features['fft_spectral_bandwidth'] = 0.0
            return features

        try:
            # Calculate FFT
            fft_vals = fft(returns)
            freqs = fftfreq(len(returns), 1/sampling_rate)

            # Use only positive frequencies
            pos_mask = freqs > 0
            freqs_pos = freqs[pos_mask]
            fft_pos = np.abs(fft_vals[pos_mask])

            # Normalize
            fft_norm = fft_pos / np.sum(fft_pos) if np.sum(fft_pos) > 0 else fft_pos

            # Top N coefficients
            n_extract = min(n_coefs, len(fft_norm))
            for i in range(n_extract):
                if i < len(fft_norm):
                    features[f'fft_coef_{i}'] = float(fft_norm[i])
                else:
                    features[f'fft_coef_{i}'] = 0.0

            # Dominant frequency
            if len(fft_norm) > 0:
                dominant_idx = np.argmax(fft_norm)
                features['fft_dominant_freq'] = float(freqs_pos[dominant_idx])

                # Dominant period (inverse of frequency)
                if features['fft_dominant_freq'] > 0:
                    features['fft_dominant_period'] = 1.0 / features['fft_dominant_freq']
                else:
                    features['fft_dominant_period'] = 0.0
            else:
                features['fft_dominant_freq'] = 0.0
                features['fft_dominant_period'] = 0.0

            # Spectral centroid (center of mass of spectrum)
            if np.sum(fft_norm) > 0:
                features['fft_spectral_centroid'] = float(np.sum(freqs_pos * fft_norm) / np.sum(fft_norm))
            else:
                features['fft_spectral_centroid'] = 0.0

            # Spectral rolloff (frequency below which 85% of energy is contained)
            cumsum = np.cumsum(fft_norm)
            if len(cumsum) > 0 and cumsum[-1] > 0:
                rolloff_idx = np.where(cumsum >= 0.85 * cumsum[-1])[0]
                if len(rolloff_idx) > 0:
                    features['fft_spectral_rolloff'] = float(freqs_pos[rolloff_idx[0]])
                else:
                    features['fft_spectral_rolloff'] = 0.0
            else:
                features['fft_spectral_rolloff'] = 0.0

            # Spectral bandwidth (weighted std of frequencies)
            if np.sum(fft_norm) > 0:
                centroid = features['fft_spectral_centroid']
                variance = np.sum(((freqs_pos - centroid) ** 2) * fft_norm) / np.sum(fft_norm)
                features['fft_spectral_bandwidth'] = float(np.sqrt(variance))
            else:
                features['fft_spectral_bandwidth'] = 0.0

        except Exception as e:
            self.logger.warning(f"Error calculating FFT features: {e}")
            for i in range(min(n_coefs, 5)):
                features[f'fft_coef_{i}'] = 0.0
            features['fft_dominant_freq'] = 0.0
            features['fft_dominant_period'] = 0.0
            features['fft_spectral_centroid'] = 0.0
            features['fft_spectral_rolloff'] = 0.0
            features['fft_spectral_bandwidth'] = 0.0

        return features

    def calculate_cwt(self,
                     returns: np.ndarray,
                     wavelet: str = 'morl',
                     scales: Optional[np.ndarray] = None) -> Dict[str, float]:
        """
        Calculate Continuous Wavelet Transform features.

        Args:
            returns: Return series
            wavelet: Wavelet type ('morl', 'mexh', 'gaus1', etc.)
            scales: Array of scales to use

        Returns:
            Dictionary with CWT features
        """
        features = {}

        if not PYWT_AVAILABLE:
            self.logger.warning("PyWavelets not available, skipping CWT features")
            return {
                'cwt_energy_scale_1': 0.0,
                'cwt_energy_scale_2': 0.0,
                'cwt_energy_scale_4': 0.0,
                'cwt_energy_scale_8': 0.0,
                'cwt_energy_ratio_high_low': 1.0,
                'cwt_dominant_scale': 1.0
            }

        if len(returns) < 20:
            return {
                'cwt_energy_scale_1': 0.0,
                'cwt_energy_scale_2': 0.0,
                'cwt_energy_scale_4': 0.0,
                'cwt_energy_scale_8': 0.0,
                'cwt_energy_ratio_high_low': 1.0,
                'cwt_dominant_scale': 1.0
            }

        try:
            # Default scales (powers of 2)
            if scales is None:
                max_scale = min(len(returns) // 4, 64)
                scales = np.arange(1, max_scale, max(1, max_scale // 16))

            # Calculate CWT
            coefs, freqs = pywt.cwt(returns, scales, wavelet)

            # Energy at different scales
            energies = np.sum(np.abs(coefs) ** 2, axis=1)

            # Extract energy at specific scales
            scale_indices = {
                1: 0,
                2: min(1, len(scales) - 1),
                4: min(3, len(scales) - 1),
                8: min(7, len(scales) - 1)
            }

            for scale, idx in scale_indices.items():
                if idx < len(energies):
                    features[f'cwt_energy_scale_{scale}'] = float(energies[idx])
                else:
                    features[f'cwt_energy_scale_{scale}'] = 0.0

            # Energy ratio (high freq / low freq)
            high_freq_energy = np.sum(energies[:len(energies)//4]) if len(energies) >= 4 else 0
            low_freq_energy = np.sum(energies[3*len(energies)//4:]) if len(energies) >= 4 else 1

            if low_freq_energy > 0:
                features['cwt_energy_ratio_high_low'] = float(high_freq_energy / low_freq_energy)
            else:
                features['cwt_energy_ratio_high_low'] = 1.0

            # Dominant scale
            if len(energies) > 0:
                dominant_idx = np.argmax(energies)
                features['cwt_dominant_scale'] = float(scales[dominant_idx])
            else:
                features['cwt_dominant_scale'] = 1.0

        except Exception as e:
            self.logger.warning(f"Error calculating CWT features: {e}")
            features = {
                'cwt_energy_scale_1': 0.0,
                'cwt_energy_scale_2': 0.0,
                'cwt_energy_scale_4': 0.0,
                'cwt_energy_scale_8': 0.0,
                'cwt_energy_ratio_high_low': 1.0,
                'cwt_dominant_scale': 1.0
            }

        return features

    def calculate_dwt(self,
                     returns: np.ndarray,
                     wavelet: str = 'db4',
                     level: int = 3) -> Dict[str, float]:
        """
        Calculate Discrete Wavelet Transform features.

        DWT decomposes signal into approximation (low freq) and details (high freq).

        Args:
            returns: Return series
            wavelet: Wavelet type ('db4', 'sym2', 'coif1', etc.)
            level: Decomposition level

        Returns:
            Dictionary with DWT features
        """
        features = {}

        if not PYWT_AVAILABLE:
            return {
                'dwt_approx_energy': 0.5,
                'dwt_detail1_energy': 0.2,
                'dwt_detail2_energy': 0.2,
                'dwt_detail3_energy': 0.1
            }

        if len(returns) < 2 ** (level + 1):
            return {
                'dwt_approx_energy': 0.5,
                'dwt_detail1_energy': 0.2,
                'dwt_detail2_energy': 0.2,
                'dwt_detail3_energy': 0.1
            }

        try:
            # Perform DWT
            coeffs = pywt.wavedec(returns, wavelet, level=level)

            # coeffs = [cA_n, cD_n, cD_n-1, ..., cD_1]
            # cA_n is approximation coefficients (low frequency)
            # cD_i are detail coefficients (high frequency)

            total_energy = 0
            energies = []

            for coef in coeffs:
                energy = np.sum(np.array(coef) ** 2)
                energies.append(energy)
                total_energy += energy

            # Normalize energies
            if total_energy > 0:
                energies_norm = [e / total_energy for e in energies]
            else:
                energies_norm = [1.0 / len(energies)] * len(energies)

            # Approximation energy (low frequency component)
            features['dwt_approx_energy'] = float(energies_norm[0])

            # Detail energies (high frequency components)
            for i in range(1, min(level + 1, len(energies_norm))):
                features[f'dwt_detail{i}_energy'] = float(energies_norm[i])

            # Fill missing levels with 0
            for i in range(len(energies_norm), level + 1):
                features[f'dwt_detail{i}_energy'] = 0.0

        except Exception as e:
            self.logger.warning(f"Error calculating DWT features: {e}")
            features = {
                'dwt_approx_energy': 0.5,
                'dwt_detail1_energy': 0.2,
                'dwt_detail2_energy': 0.2,
                'dwt_detail3_energy': 0.1
            }

        return features

    def calculate_energy_bands(self, returns: np.ndarray) -> Dict[str, float]:
        """
        Calculate energy distribution in frequency bands.

        Divides spectrum into bands: very_low, low, mid, high, very_high

        Args:
            returns: Return series

        Returns:
            Dictionary with energy per band
        """
        features = {}

        if len(returns) < 20:
            return {
                'energy_band_very_low': 0.2,
                'energy_band_low': 0.2,
                'energy_band_mid': 0.2,
                'energy_band_high': 0.2,
                'energy_band_very_high': 0.2
            }

        try:
            # Calculate power spectral density
            freqs, psd = signal.welch(returns, nperseg=min(len(returns), 256))

            # Normalize
            total_power = np.sum(psd)
            if total_power > 0:
                psd_norm = psd / total_power
            else:
                psd_norm = psd

            # Define frequency bands (quantiles)
            n = len(freqs)
            bands = {
                'very_low': (0, n // 5),
                'low': (n // 5, 2 * n // 5),
                'mid': (2 * n // 5, 3 * n // 5),
                'high': (3 * n // 5, 4 * n // 5),
                'very_high': (4 * n // 5, n)
            }

            # Calculate energy in each band
            for band_name, (start, end) in bands.items():
                energy = np.sum(psd_norm[start:end])
                features[f'energy_band_{band_name}'] = float(energy)

        except Exception as e:
            self.logger.warning(f"Error calculating energy bands: {e}")
            features = {
                'energy_band_very_low': 0.2,
                'energy_band_low': 0.2,
                'energy_band_mid': 0.2,
                'energy_band_high': 0.2,
                'energy_band_very_high': 0.2
            }

        return features

    def calculate_all_features(self, df: pd.DataFrame, price_col: str = 'close') -> Dict[str, float]:
        """
        Calculate all wavelet and FFT features.

        Args:
            df: DataFrame with OHLCV data
            price_col: Name of price column

        Returns:
            Dictionary of features
        """
        features = {}

        if price_col not in df.columns or len(df) < 24:
            # Return placeholder features
            placeholder = {
                **{f'fft_coef_{i}': 0.0 for i in range(5)},
                'fft_dominant_freq': 0.0,
                'fft_dominant_period': 0.0,
                'fft_spectral_centroid': 0.0,
                'fft_spectral_rolloff': 0.0,
                'fft_spectral_bandwidth': 0.0,
                'cwt_energy_scale_1': 0.0,
                'cwt_energy_scale_2': 0.0,
                'cwt_energy_scale_4': 0.0,
                'cwt_energy_scale_8': 0.0,
                'cwt_energy_ratio_high_low': 1.0,
                'cwt_dominant_scale': 1.0,
                'dwt_approx_energy': 0.5,
                'dwt_detail1_energy': 0.2,
                'dwt_detail2_energy': 0.2,
                'dwt_detail3_energy': 0.1,
                'energy_band_very_low': 0.2,
                'energy_band_low': 0.2,
                'energy_band_mid': 0.2,
                'energy_band_high': 0.2,
                'energy_band_very_high': 0.2,
                'wavelet_complexity': 0.5,
                'wavelet_smoothness': 0.5
            }
            return placeholder

        # Calculate returns
        prices = df[price_col].values
        returns = np.diff(np.log(prices))
        returns = returns[np.isfinite(returns)]

        if len(returns) < 10:
            return features

        # FFT features
        fft_features = self.calculate_fft(returns, n_coefs=10)
        features.update(fft_features)

        # CWT features
        cwt_features = self.calculate_cwt(returns)
        features.update(cwt_features)

        # DWT features
        dwt_features = self.calculate_dwt(returns, level=3)
        features.update(dwt_features)

        # Energy bands
        energy_features = self.calculate_energy_bands(returns)
        features.update(energy_features)

        # Composite features
        # Wavelet complexity (high detail energy = more complex)
        detail_energies = [
            features.get('dwt_detail1_energy', 0),
            features.get('dwt_detail2_energy', 0),
            features.get('dwt_detail3_energy', 0)
        ]
        features['wavelet_complexity'] = sum(detail_energies)

        # Wavelet smoothness (high approx energy = smoother)
        features['wavelet_smoothness'] = features.get('dwt_approx_energy', 0.5)

        return features


def add_wavelet_features(df: pd.DataFrame, price_col: str = 'close') -> pd.DataFrame:
    """
    Convenience function to add wavelet/FFT features to a DataFrame.

    Args:
        df: DataFrame with OHLCV data
        price_col: Name of price column

    Returns:
        DataFrame with added wavelet features
    """
    extractor = WaveletFeatures()
    features = extractor.calculate_all_features(df, price_col)

    for key, value in features.items():
        df[key] = value

    return df
