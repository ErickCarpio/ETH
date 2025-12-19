"""
Statistical Features Engine - Advanced Time Series Analysis
Implementa: Hurst, Kalman, Wavelet, FFT, Entropy, Fractal Dimension

Basado en config:
  "statistical": {
    "hurst_windows": [24, 72, 168],
    "kalman_initial_estimate": 0.01,
    "wavelet_scales": [1, 2, 4, 8, 16, 32, 64, 128],
    "fft_n_coefs": 20
  }
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Optional
from scipy import signal
from scipy.fft import fft
from scipy.stats import entropy as scipy_entropy
import pywt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StatisticalFeatures")


class StatisticalFeatureEngine:
    """
    Genera ~100 features estadísticas avanzadas para ML
    """

    def __init__(self, config: dict = None):
        """
        Args:
            config: Diccionario de configuración con parámetros estadísticos
        """
        if config is None:
            config = {}

        # Parámetros por defecto (de config_15min.json)
        self.hurst_windows = config.get('hurst_windows', [24, 72, 168])
        self.kalman_initial_estimate = config.get('kalman_initial_estimate', 0.01)
        self.wavelet_scales = config.get('wavelet_scales', [1, 2, 4, 8, 16, 32, 64, 128])
        self.fft_n_coefs = config.get('fft_n_coefs', 20)

        logger.info(f"📊 StatisticalFeatureEngine inicializado:")
        logger.info(f"   - Hurst windows: {self.hurst_windows}")
        logger.info(f"   - Wavelet scales: {len(self.wavelet_scales)} escalas")
        logger.info(f"   - FFT coefficients: {self.fft_n_coefs}")

    def calculate_hurst_exponent(self, series: np.ndarray, max_lag: int = 20) -> float:
        """
        Calcula el exponente de Hurst usando Rescaled Range (R/S) analysis.

        H < 0.5: Serie anti-persistente (mean-reverting)
        H = 0.5: Random walk (Brownian motion)
        H > 0.5: Serie persistente (trending)

        Args:
            series: Serie temporal
            max_lag: Máximo lag para el análisis R/S

        Returns:
            Exponente de Hurst (0 a 1)
        """
        if len(series) < max_lag * 2:
            return 0.5  # Default: random walk

        lags = range(2, max_lag)
        tau = []

        for lag in lags:
            # Dividir serie en chunks de tamaño lag
            n_chunks = len(series) // lag
            chunks = series[:n_chunks * lag].reshape((n_chunks, lag))

            # Para cada chunk, calcular Rescaled Range
            rs_values = []
            for chunk in chunks:
                if len(chunk) < 2:
                    continue

                mean = np.mean(chunk)
                deviations = chunk - mean
                cumulative_deviations = np.cumsum(deviations)

                R = np.max(cumulative_deviations) - np.min(cumulative_deviations)
                S = np.std(chunk)

                if S > 0:
                    rs_values.append(R / S)

            if len(rs_values) > 0:
                tau.append(np.mean(rs_values))
            else:
                tau.append(1.0)

        # Ajustar línea log-log para obtener H
        if len(tau) < 2:
            return 0.5

        log_lags = np.log(list(lags))
        log_tau = np.log(tau)

        # Regresión lineal
        poly = np.polyfit(log_lags, log_tau, 1)
        hurst = poly[0]

        # Clip a rango válido [0, 1]
        return np.clip(hurst, 0.0, 1.0)

    def calculate_kalman_filter(self, series: pd.Series) -> Dict[str, pd.Series]:
        """
        Aplica Filtro de Kalman para estimar el estado real y la tendencia.

        Returns:
            Dictionary con:
            - kalman_estimate: Estado filtrado
            - kalman_gain: Ganancia de Kalman
            - kalman_residual: Residual (observación - estimado)
        """
        n = len(series)

        # Inicialización
        Q = self.kalman_initial_estimate  # Process noise
        R = 0.1  # Measurement noise

        x_est = series.iloc[0]  # Estado inicial
        P = 1.0  # Error covarianza inicial

        estimates = []
        gains = []
        residuals = []

        for z in series:
            # Predicción
            x_pred = x_est
            P_pred = P + Q

            # Actualización (Kalman Gain)
            K = P_pred / (P_pred + R)

            # Corrección
            x_est = x_pred + K * (z - x_pred)
            P = (1 - K) * P_pred

            # Guardar
            estimates.append(x_est)
            gains.append(K)
            residuals.append(z - x_est)

        return {
            'kalman_estimate': pd.Series(estimates, index=series.index),
            'kalman_gain': pd.Series(gains, index=series.index),
            'kalman_residual': pd.Series(residuals, index=series.index)
        }

    def calculate_wavelet_features(self, series: np.ndarray) -> Dict[str, float]:
        """
        Descompone la serie usando Wavelet Transform (Discrete Wavelet Transform).

        Returns:
            Features para cada escala: energy, variance, mean
        """
        features = {}

        # Usar Daubechies wavelet (db4)
        wavelet = 'db4'

        for scale in self.wavelet_scales:
            try:
                # Continuous Wavelet Transform (aproximación con dwt)
                coeffs = pywt.downcoef('d', series, wavelet, level=int(np.log2(scale)) + 1)

                if len(coeffs) > 0:
                    features[f'wavelet_energy_scale_{scale}'] = np.sum(coeffs ** 2)
                    features[f'wavelet_variance_scale_{scale}'] = np.var(coeffs)
                    features[f'wavelet_mean_scale_{scale}'] = np.mean(np.abs(coeffs))
                else:
                    features[f'wavelet_energy_scale_{scale}'] = 0.0
                    features[f'wavelet_variance_scale_{scale}'] = 0.0
                    features[f'wavelet_mean_scale_{scale}'] = 0.0

            except Exception as e:
                # Si falla para alguna escala, usar 0
                features[f'wavelet_energy_scale_{scale}'] = 0.0
                features[f'wavelet_variance_scale_{scale}'] = 0.0
                features[f'wavelet_mean_scale_{scale}'] = 0.0

        return features

    def calculate_fft_coefficients(self, series: np.ndarray) -> Dict[str, float]:
        """
        Calcula coeficientes FFT (Fast Fourier Transform) del dominio de frecuencia.

        Returns:
            Top N coeficientes FFT (magnitudes)
        """
        # Aplicar FFT
        fft_values = fft(series)

        # Tomar solo la mitad (simetría)
        fft_magnitudes = np.abs(fft_values[:len(fft_values) // 2])

        # Normalizar
        fft_magnitudes = fft_magnitudes / len(series)

        # Tomar top N
        features = {}
        for i in range(min(self.fft_n_coefs, len(fft_magnitudes))):
            features[f'fft_coef_{i}'] = fft_magnitudes[i]

        # Rellenar con 0 si hay menos coeficientes que n_coefs
        for i in range(len(fft_magnitudes), self.fft_n_coefs):
            features[f'fft_coef_{i}'] = 0.0

        return features

    def calculate_sample_entropy(self, series: np.ndarray, m: int = 2, r: float = 0.2) -> float:
        """
        Calcula Sample Entropy (SampEn) - medida de complejidad/regularidad.

        SampEn bajo: Serie regular, predecible
        SampEn alto: Serie compleja, impredecible

        Args:
            series: Serie temporal
            m: Tamaño del patrón (embedding dimension)
            r: Tolerancia (% de std)

        Returns:
            Sample Entropy
        """
        N = len(series)

        if N < m + 1:
            return 0.0

        # Normalizar serie
        series = (series - np.mean(series)) / (np.std(series) + 1e-8)
        tolerance = r * np.std(series)

        def _maxdist(x_i, x_j):
            return max([abs(ua - va) for ua, va in zip(x_i, x_j)])

        def _phi(m):
            x = [[series[j] for j in range(i, i + m)] for i in range(N - m + 1)]
            C = [len([1 for x_j in x if _maxdist(x_i, x_j) <= tolerance]) - 1 for x_i in x]
            return sum(C)

        phi_m = _phi(m)
        phi_m1 = _phi(m + 1)

        # Evitar división por cero y log de cero
        if phi_m == 0 or phi_m1 == 0:
            return 0.0

        ratio = phi_m1 / phi_m

        # Evitar log de valores <= 0
        if ratio <= 0:
            return 0.0

        return -np.log(ratio)

    def calculate_approximate_entropy(self, series: np.ndarray, m: int = 2, r: float = 0.2) -> float:
        """
        Calcula Approximate Entropy (ApEn) - medida de aleatoriedad.

        Similar a SampEn pero más rápido de calcular.
        """
        N = len(series)

        if N < m + 1:
            return 0.0

        # Normalizar
        std_val = np.std(series)
        if std_val < 1e-8:
            return 0.0

        series = (series - np.mean(series)) / std_val
        tolerance = r

        def _phi(m):
            if N - m + 1 <= 0:
                return 0.0

            patterns = np.array([series[i:i + m] for i in range(N - m + 1)])
            C = np.zeros(N - m + 1)

            for i in range(N - m + 1):
                template = patterns[i]
                distances = np.max(np.abs(patterns - template), axis=1)
                C[i] = np.sum(distances <= tolerance) / (N - m + 1)

            # Evitar log(0) reemplazando valores muy pequeños
            C = np.maximum(C, 1e-10)
            result = np.sum(np.log(C)) / (N - m + 1)

            # Verificar que el resultado es finito
            if not np.isfinite(result):
                return 0.0

            return result

        try:
            phi_m = _phi(m)
            phi_m1 = _phi(m + 1)
            apen = phi_m - phi_m1

            # Verificar que el resultado es finito
            if not np.isfinite(apen):
                return 0.0

            return apen
        except:
            return 0.0

    def calculate_fractal_dimension(self, series: np.ndarray) -> float:
        """
        Calcula Fractal Dimension usando Higuchi's method.

        FD cercano a 1: Serie suave, tendencial
        FD cercano a 2: Serie rugosa, ruidosa

        Returns:
            Fractal Dimension (1 a 2)
        """
        N = len(series)

        if N < 10:
            return 1.5  # Default

        k_max = min(10, N // 4)

        L = []
        x = np.arange(1, k_max + 1)

        for k in range(1, k_max + 1):
            Lk = []
            for m in range(1, k + 1):
                Lmk = 0
                maxI = (N - m) // k

                for i in range(1, maxI):
                    Lmk += abs(series[m + i * k - 1] - series[m + (i - 1) * k - 1])

                normalization = (N - 1) / (maxI * k)
                Lmk = Lmk * normalization / k
                Lk.append(Lmk)

            L.append(np.mean(Lmk))

        # Regresión log-log
        if len(L) < 2:
            return 1.5

        log_x = np.log(x)
        log_L = np.log(L)

        poly = np.polyfit(log_x, log_L, 1)
        fd = -poly[0]  # Pendiente negativa

        return np.clip(fd, 1.0, 2.0)

    def compute_all_features(self, df: pd.DataFrame, price_col: str = 'close') -> pd.DataFrame:
        """
        Calcula TODAS las features estadísticas para un DataFrame.

        Args:
            df: DataFrame con columna de precio
            price_col: Nombre de la columna de precio

        Returns:
            DataFrame con ~100 nuevas columnas de features
        """
        logger.info("📊 Calculando features estadísticas...")

        df = df.copy()

        # Serie de retornos (más estacionaria que precio)
        returns = df[price_col].pct_change().fillna(0).values
        prices = df[price_col].values

        # 1. HURST EXPONENT (3 features)
        logger.info("   - Hurst exponent (3 ventanas)...")
        for window in self.hurst_windows:
            hurst_values = []
            for i in range(len(df)):
                if i < window:
                    hurst_values.append(0.5)  # Default
                else:
                    segment = returns[i - window:i]
                    h = self.calculate_hurst_exponent(segment, max_lag=min(20, window // 4))
                    hurst_values.append(h)

            df[f'hurst_{window}'] = hurst_values

        # 2. KALMAN FILTER (3 features)
        logger.info("   - Kalman filter...")
        kalman_results = self.calculate_kalman_filter(df[price_col])
        df['kalman_estimate'] = kalman_results['kalman_estimate']
        df['kalman_gain'] = kalman_results['kalman_gain']
        df['kalman_residual'] = kalman_results['kalman_residual']

        # 3. WAVELET FEATURES (8 scales × 3 stats = 24 features)
        logger.info("   - Wavelet decomposition (8 escalas)...")
        window_wavelet = 128  # Ventana para wavelet

        # Inicializar columnas
        for scale in self.wavelet_scales:
            df[f'wavelet_energy_scale_{scale}'] = 0.0
            df[f'wavelet_variance_scale_{scale}'] = 0.0
            df[f'wavelet_mean_scale_{scale}'] = 0.0

        # Calcular en rolling window
        for i in range(len(df)):
            if i < window_wavelet:
                continue  # Dejar en 0

            segment = returns[i - window_wavelet:i]
            wavelet_feats = self.calculate_wavelet_features(segment)

            for key, value in wavelet_feats.items():
                df.loc[df.index[i], key] = value

        # 4. FFT COEFFICIENTS (20 features)
        logger.info("   - FFT coefficients...")
        window_fft = 64

        # Inicializar columnas
        for i in range(self.fft_n_coefs):
            df[f'fft_coef_{i}'] = 0.0

        # Calcular en rolling window
        for i in range(len(df)):
            if i < window_fft:
                continue

            segment = returns[i - window_fft:i]
            fft_feats = self.calculate_fft_coefficients(segment)

            for key, value in fft_feats.items():
                df.loc[df.index[i], key] = value

        # 5. ENTROPY FEATURES (6 features)
        logger.info("   - Entropy features...")
        window_entropy = 50

        df['sample_entropy'] = 0.0
        df['approximate_entropy'] = 0.0
        df['shannon_entropy'] = 0.0

        for i in range(len(df)):
            if i < window_entropy:
                continue

            segment = returns[i - window_entropy:i]

            # Sample Entropy
            try:
                sampen = self.calculate_sample_entropy(segment, m=2, r=0.2)
                df.loc[df.index[i], 'sample_entropy'] = sampen
            except:
                df.loc[df.index[i], 'sample_entropy'] = 0.0

            # Approximate Entropy
            try:
                apen = self.calculate_approximate_entropy(segment, m=2, r=0.2)
                df.loc[df.index[i], 'approximate_entropy'] = apen
            except:
                df.loc[df.index[i], 'approximate_entropy'] = 0.0

            # Shannon Entropy (de histograma)
            try:
                hist, _ = np.histogram(segment, bins=10, density=True)
                hist = hist[hist > 0]  # Remover ceros
                shan_ent = scipy_entropy(hist)
                df.loc[df.index[i], 'shannon_entropy'] = shan_ent
            except:
                df.loc[df.index[i], 'shannon_entropy'] = 0.0

        # Volatility-based entropy features
        df['entropy_volatility_ratio'] = df['sample_entropy'] / (df[price_col].pct_change().rolling(20).std() + 1e-8)
        df['entropy_trend_ratio'] = df['approximate_entropy'] / (df[price_col].rolling(20).mean().pct_change().abs() + 1e-8)
        df['entropy_complexity'] = df['sample_entropy'] * df['shannon_entropy']

        # 6. FRACTAL DIMENSION (3 features)
        logger.info("   - Fractal dimension...")
        windows_fd = [50, 100, 200]

        for window in windows_fd:
            fd_values = []
            for i in range(len(df)):
                if i < window:
                    fd_values.append(1.5)  # Default
                else:
                    segment = prices[i - window:i]
                    fd = self.calculate_fractal_dimension(segment)
                    fd_values.append(fd)

            df[f'fractal_dim_{window}'] = fd_values

        # 7. ADDITIONAL STATISTICAL FEATURES (Complementarias)
        logger.info("   - Additional statistical features...")

        # Skewness y Kurtosis en múltiples ventanas
        for window in [20, 50, 100]:
            df[f'skewness_{window}'] = df[price_col].pct_change().rolling(window).skew()
            df[f'kurtosis_{window}'] = df[price_col].pct_change().rolling(window).kurt()

        # Autocorrelación (Lag 1, 5, 10)
        for lag in [1, 5, 10]:
            df[f'autocorr_lag_{lag}'] = df[price_col].pct_change().rolling(50).apply(
                lambda x: x.autocorr(lag=lag) if len(x) > lag else 0, raw=False
            )

        # Detrended Fluctuation Analysis (DFA) - versión simplificada
        window_dfa = 100
        df['dfa_fluctuation'] = 0.0

        for i in range(len(df)):
            if i < window_dfa:
                continue

            segment = returns[i - window_dfa:i]
            # Cumulative sum (profile)
            profile = np.cumsum(segment - np.mean(segment))

            # Detrend (linear fit)
            x = np.arange(len(profile))
            coeffs = np.polyfit(x, profile, 1)
            trend = np.polyval(coeffs, x)
            detrended = profile - trend

            # Fluctuation
            fluctuation = np.sqrt(np.mean(detrended ** 2))
            df.loc[df.index[i], 'dfa_fluctuation'] = fluctuation

        # Fill NaN
        df = df.fillna(0)

        # Contar features generadas
        statistical_cols = [col for col in df.columns if any(
            keyword in col for keyword in [
                'hurst', 'kalman', 'wavelet', 'fft', 'entropy', 'fractal',
                'skewness', 'kurtosis', 'autocorr', 'dfa'
            ]
        )]

        logger.info(f"✅ Statistical features generadas: {len(statistical_cols)}")

        # CRÍTICO: Limpiar valores inf y NaN para XGBoost
        # XGBoost no puede manejar inf, -inf, o valores extremadamente grandes
        for col in statistical_cols:
            if col in df.columns:
                # Reemplazar inf con 0
                df[col] = df[col].replace([np.inf, -np.inf], 0.0)

                # Rellenar NaN con 0
                df[col] = df[col].fillna(0.0)

                # Clip valores extremos (opcional pero recomendado)
                # Mantener valores en rango razonable [-1e6, 1e6]
                df[col] = df[col].clip(-1e6, 1e6)

        logger.info(f"🧹 Statistical features limpiadas (inf/NaN → 0)")

        return df


# --- PRUEBA UNITARIA ---
if __name__ == "__main__":
    logger.info("🧪 Probando StatisticalFeatureEngine...")

    # Generar serie de prueba
    np.random.seed(42)
    n = 500
    t = np.linspace(0, 10, n)

    # Serie con tendencia + ruido + ciclo
    trend = 0.5 * t
    cycle = 10 * np.sin(2 * np.pi * t / 5)
    noise = np.random.randn(n) * 2
    series = trend + cycle + noise + 100

    df_test = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=n, freq='1h'),
        'close': series
    })
    df_test.set_index('timestamp', inplace=True)

    # Configuración de prueba
    config = {
        'hurst_windows': [24, 72, 168],
        'kalman_initial_estimate': 0.01,
        'wavelet_scales': [1, 2, 4, 8, 16, 32, 64, 128],
        'fft_n_coefs': 20
    }

    # Calcular features
    engine = StatisticalFeatureEngine(config)
    df_result = engine.compute_all_features(df_test, price_col='close')

    # Mostrar resultados
    print("\n📊 RESUMEN DE FEATURES ESTADÍSTICAS:")
    print(f"   Total features: {len(df_result.columns) - 1}")  # -1 por 'close'

    # Mostrar algunas features
    print("\n🔹 Últimas 5 filas (muestra):")
    statistical_cols = [col for col in df_result.columns if col != 'close'][:10]
    print(df_result[statistical_cols].tail())

    print("\n✅ Prueba completada exitosamente!")
