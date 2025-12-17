"""
GEX Calculator - FASE 3.1
==========================

Calcula Gamma Exposure (GEX) a partir de datos de opciones.

GEX (Gamma Exposure):
- Mide exposición gamma de market makers por strike
- GEX positivo = soporte (MM compran en caídas para hedgear)
- GEX negativo = resistencia (MM venden en subidas para hedgear)

Fórmula:
GEX_strike = Gamma × Open_Interest × Spot_Price × 0.01

El 0.01 es porque gamma mide cambio de delta por $1 de movimiento.

Market Maker Positioning:
- Dealers típicamente están SHORT opciones (venden premium)
- Por tanto, su posición gamma es -OI (negativo del open interest)
- Calls: Si dealers short calls, GEX positivo → compran en caídas
- Puts: Si dealers short puts, GEX negativo → venden en subidas

Features calculadas:
1. GEX total por strike
2. GEX neto (positivo - negativo)
3. Niveles de soporte (GEX positivo)
4. Niveles de resistencia (GEX negativo)
5. Strike con mayor GEX absoluto
6. Distancia a niveles clave
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

# Para cálculo de Greeks
try:
    from py_vollib.black_scholes.greeks.analytical import gamma as bs_gamma
    VOLLIB_AVAILABLE = True
except ImportError:
    VOLLIB_AVAILABLE = False
    logging.warning("py_vollib not available - install with: pip install py_vollib")

logger = logging.getLogger(__name__)


class GEXCalculator:
    """
    Calculador de Gamma Exposure (GEX) para opciones.

    Workflow:
    1. Recibir cadena de opciones (calls + puts)
    2. Calcular gamma usando Black-Scholes
    3. Calcular GEX por strike: Gamma × OI × Spot × 0.01
    4. Agregar por strike (sumar calls + puts)
    5. Identificar niveles clave de soporte/resistencia
    """

    def __init__(self, risk_free_rate: float = 0.0):
        """
        Initialize GEX Calculator.

        Args:
            risk_free_rate: Tasa libre de riesgo (decimal, ej: 0.05 = 5%)
        """
        self.risk_free_rate = risk_free_rate

        if not VOLLIB_AVAILABLE:
            logger.warning("py_vollib not available - GEX calculation will fail")

    def calculate_gamma(self,
                       spot: float,
                       strike: float,
                       time_to_expiry: float,
                       iv: float) -> Optional[float]:
        """
        Calcula gamma usando Black-Scholes.

        Args:
            spot: Precio spot
            strike: Strike price
            time_to_expiry: Tiempo a expiración (años)
            iv: Implied Volatility (decimal, ej: 0.80 = 80%)

        Returns:
            Gamma o None si error
        """
        if not VOLLIB_AVAILABLE:
            return None

        try:
            # Black-Scholes gamma (igual para calls y puts)
            gamma = bs_gamma(
                flag='c',  # No importa (gamma es igual para call/put)
                S=spot,
                K=strike,
                t=time_to_expiry,
                r=self.risk_free_rate,
                sigma=iv
            )

            return gamma

        except Exception as e:
            logger.debug(f"Gamma calculation failed for strike {strike}: {e}")
            return None

    def calculate_gex_from_options(self,
                                  options_df: pd.DataFrame,
                                  spot_price: float,
                                  min_oi: int = 10) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Calcula GEX a partir de DataFrame de opciones.

        Args:
            options_df: DataFrame con columnas:
                       - strike: Strike price
                       - expiry: Fecha de expiración
                       - option_type: 'call' o 'put'
                       - open_interest: OI
                       - iv: Implied volatility (decimal)
            spot_price: Precio spot actual
            min_oi: OI mínimo para incluir opción

        Returns:
            Tuple[df_detailed, df_by_strike]
            - df_detailed: GEX por cada opción individual
            - df_by_strike: GEX agregado por strike
        """
        if options_df.empty:
            logger.warning("Empty options DataFrame")
            return pd.DataFrame(), pd.DataFrame()

        # Filter por OI mínimo
        options_df = options_df[options_df['open_interest'] >= min_oi].copy()

        if options_df.empty:
            logger.warning(f"No options with OI >= {min_oi}")
            return pd.DataFrame(), pd.DataFrame()

        gex_data = []

        for idx, row in options_df.iterrows():
            strike = row['strike']
            expiry = row['expiry']
            option_type = row['option_type']
            open_interest = row['open_interest']
            iv = row['iv']

            # Time to expiry (años)
            if isinstance(expiry, str):
                expiry = datetime.strptime(expiry, '%Y-%m-%d')

            now = datetime.now()
            days_to_expiry = (expiry - now).days
            time_to_expiry = max(days_to_expiry / 365.0, 0.001)  # Mínimo 0.001

            # Calcular gamma
            gamma = self.calculate_gamma(
                spot=spot_price,
                strike=strike,
                time_to_expiry=time_to_expiry,
                iv=iv
            )

            if gamma is None:
                continue

            # Calcular GEX
            # Asumimos que dealers están SHORT las opciones (posición usual)
            dealer_position = -open_interest

            # GEX = Gamma × Dealer_Position × Spot × 0.01
            gex = gamma * dealer_position * spot_price * 0.01

            # Ajustar signo para puts
            # Calls: GEX positivo si dealers short (compran en caídas)
            # Puts: GEX negativo si dealers short (venden en subidas)
            is_call = option_type.lower() == 'call'
            if not is_call:
                gex = -gex

            gex_data.append({
                'strike': strike,
                'expiry': expiry,
                'days_to_expiry': days_to_expiry,
                'option_type': option_type,
                'open_interest': open_interest,
                'iv': iv,
                'gamma': gamma,
                'gex': gex,
                'spot': spot_price
            })

        # Crear DataFrame detallado
        df_detailed = pd.DataFrame(gex_data)

        if df_detailed.empty:
            logger.warning("No GEX data calculated")
            return df_detailed, pd.DataFrame()

        # Agregar GEX por strike (sumar calls + puts)
        df_by_strike = df_detailed.groupby('strike').agg({
            'gex': 'sum',
            'open_interest': 'sum',
            'gamma': 'mean'
        }).reset_index()

        df_by_strike.columns = ['strike', 'gex_total', 'total_oi', 'avg_gamma']

        logger.info(f"✓ Calculated GEX for {len(df_detailed)} options across {len(df_by_strike)} strikes")

        return df_detailed, df_by_strike

    def get_gex_levels(self,
                      gex_by_strike: pd.DataFrame,
                      spot_price: float,
                      n_levels: int = 10) -> Dict:
        """
        Identifica niveles clave de GEX.

        Args:
            gex_by_strike: DataFrame con columnas 'strike' y 'gex_total'
            spot_price: Precio spot actual
            n_levels: Número de niveles a retornar

        Returns:
            Dict con niveles de soporte/resistencia
        """
        if gex_by_strike.empty:
            return {}

        # Ordenar por GEX absoluto
        sorted_gex = gex_by_strike.sort_values('gex_total', key=abs, ascending=False)

        # Top N niveles
        top_levels = sorted_gex.head(n_levels)

        # Separar soporte (GEX positivo) y resistencia (GEX negativo)
        support_levels = top_levels[top_levels['gex_total'] > 0].sort_values('strike')
        resistance_levels = top_levels[top_levels['gex_total'] < 0].sort_values('strike')

        # Total GEX metrics
        total_gex = gex_by_strike['gex_total'].sum()
        total_positive_gex = gex_by_strike[gex_by_strike['gex_total'] > 0]['gex_total'].sum()
        total_negative_gex = gex_by_strike[gex_by_strike['gex_total'] < 0]['gex_total'].sum()

        # Find nearest levels
        nearest_support = self._find_nearest_level(support_levels, spot_price, direction='below')
        nearest_resistance = self._find_nearest_level(resistance_levels, spot_price, direction='above')

        return {
            'spot_price': spot_price,
            'total_gex': total_gex,
            'total_positive_gex': total_positive_gex,
            'total_negative_gex': total_negative_gex,
            'net_gex': total_gex,
            'gex_skew': total_positive_gex / abs(total_negative_gex) if total_negative_gex != 0 else float('inf'),
            'support_levels': support_levels.to_dict('records'),
            'resistance_levels': resistance_levels.to_dict('records'),
            'nearest_support': nearest_support,
            'nearest_resistance': nearest_resistance,
            'num_support_levels': len(support_levels),
            'num_resistance_levels': len(resistance_levels)
        }

    def _find_nearest_level(self,
                           levels: pd.DataFrame,
                           spot: float,
                           direction: str) -> Optional[Dict]:
        """
        Encuentra nivel más cercano en dirección específica.

        Args:
            levels: DataFrame con 'strike' y 'gex_total'
            spot: Precio spot
            direction: 'above' o 'below'

        Returns:
            Dict con nivel más cercano
        """
        if levels.empty:
            return None

        if direction == 'above':
            candidates = levels[levels['strike'] > spot]
            if candidates.empty:
                return None
            nearest = candidates.sort_values('strike').iloc[0]
        else:  # below
            candidates = levels[levels['strike'] < spot]
            if candidates.empty:
                return None
            nearest = candidates.sort_values('strike', ascending=False).iloc[0]

        result = nearest.to_dict()
        result['distance_pct'] = ((nearest['strike'] - spot) / spot) * 100

        return result

    def calculate_gex_features(self,
                              gex_by_strike: pd.DataFrame,
                              spot_price: float) -> Dict:
        """
        Calcula features derivados de GEX para modelo.

        Args:
            gex_by_strike: DataFrame con GEX por strike
            spot_price: Precio spot

        Returns:
            Dict con 25 features de GEX
        """
        if gex_by_strike.empty:
            return self._get_empty_features()

        levels = self.get_gex_levels(gex_by_strike, spot_price, n_levels=10)

        # Base metrics
        features = {
            'gex_total': levels['total_gex'],
            'gex_positive': levels['total_positive_gex'],
            'gex_negative': levels['total_negative_gex'],
            'gex_net': levels['net_gex'],
            'gex_skew': levels['gex_skew'],
        }

        # Nearest levels
        if levels['nearest_support']:
            features['gex_support_strike'] = levels['nearest_support']['strike']
            features['gex_support_value'] = levels['nearest_support']['gex_total']
            features['gex_support_distance_pct'] = levels['nearest_support']['distance_pct']
        else:
            features['gex_support_strike'] = 0
            features['gex_support_value'] = 0
            features['gex_support_distance_pct'] = -100

        if levels['nearest_resistance']:
            features['gex_resistance_strike'] = levels['nearest_resistance']['strike']
            features['gex_resistance_value'] = levels['nearest_resistance']['gex_total']
            features['gex_resistance_distance_pct'] = levels['nearest_resistance']['distance_pct']
        else:
            features['gex_resistance_strike'] = 0
            features['gex_resistance_value'] = 0
            features['gex_resistance_distance_pct'] = 100

        # GEX distribution
        gex_values = gex_by_strike['gex_total'].values
        features['gex_mean'] = np.mean(gex_values)
        features['gex_std'] = np.std(gex_values)
        features['gex_max'] = np.max(np.abs(gex_values))
        features['gex_range'] = np.max(gex_values) - np.min(gex_values)

        # Strike distribution
        strikes = gex_by_strike['strike'].values
        features['gex_strike_range'] = np.max(strikes) - np.min(strikes)
        features['gex_num_strikes'] = len(strikes)
        features['gex_avg_strike_spacing'] = np.mean(np.diff(sorted(strikes))) if len(strikes) > 1 else 0

        # Concentration metrics
        top_3_gex = gex_by_strike.nlargest(3, 'gex_total', keep='all')['gex_total'].sum()
        features['gex_top3_concentration'] = top_3_gex / levels['total_gex'] if levels['total_gex'] != 0 else 0

        # Position relative to spot
        below_spot = gex_by_strike[gex_by_strike['strike'] < spot_price]['gex_total'].sum()
        above_spot = gex_by_strike[gex_by_strike['strike'] > spot_price]['gex_total'].sum()
        features['gex_below_spot'] = below_spot
        features['gex_above_spot'] = above_spot
        features['gex_spot_ratio'] = above_spot / abs(below_spot) if below_spot != 0 else float('inf')

        # Clamp infinities
        for key in features:
            if features[key] == float('inf'):
                features[key] = 999999
            elif features[key] == float('-inf'):
                features[key] = -999999

        return features

    def _get_empty_features(self) -> Dict:
        """Retorna features vacíos cuando no hay datos."""
        return {
            'gex_total': 0,
            'gex_positive': 0,
            'gex_negative': 0,
            'gex_net': 0,
            'gex_skew': 0,
            'gex_support_strike': 0,
            'gex_support_value': 0,
            'gex_support_distance_pct': 0,
            'gex_resistance_strike': 0,
            'gex_resistance_value': 0,
            'gex_resistance_distance_pct': 0,
            'gex_mean': 0,
            'gex_std': 0,
            'gex_max': 0,
            'gex_range': 0,
            'gex_strike_range': 0,
            'gex_num_strikes': 0,
            'gex_avg_strike_spacing': 0,
            'gex_top3_concentration': 0,
            'gex_below_spot': 0,
            'gex_above_spot': 0,
            'gex_spot_ratio': 0
        }


if __name__ == "__main__":
    # Ejemplo de uso
    logging.basicConfig(level=logging.INFO)

    # Sample options data
    options_data = {
        'strike': [1800, 1850, 1900, 1950, 2000, 2050, 2100],
        'expiry': ['2025-12-31'] * 7,
        'option_type': ['call', 'call', 'call', 'call', 'put', 'put', 'put'],
        'open_interest': [1000, 1500, 2000, 2500, 2000, 1500, 1000],
        'iv': [0.80, 0.75, 0.70, 0.65, 0.70, 0.75, 0.80]
    }

    df_options = pd.DataFrame(options_data)
    spot = 1950

    # Calculate GEX
    calc = GEXCalculator()
    df_detailed, df_by_strike = calc.calculate_gex_from_options(df_options, spot)

    print("\n" + "="*60)
    print("GEX BY STRIKE")
    print("="*60)
    print(df_by_strike)

    # Get levels
    levels = calc.get_gex_levels(df_by_strike, spot)
    print("\n" + "="*60)
    print("GEX LEVELS")
    print("="*60)
    print(f"Total GEX: ${levels['total_gex']:,.0f}")
    print(f"Positive GEX: ${levels['total_positive_gex']:,.0f}")
    print(f"Negative GEX: ${levels['total_negative_gex']:,.0f}")

    if levels['nearest_support']:
        print(f"\nNearest Support: ${levels['nearest_support']['strike']:.0f} "
              f"(${levels['nearest_support']['gex_total']:,.0f})")

    if levels['nearest_resistance']:
        print(f"Nearest Resistance: ${levels['nearest_resistance']['strike']:.0f} "
              f"(${levels['nearest_resistance']['gex_total']:,.0f})")

    # Calculate features
    features = calc.calculate_gex_features(df_by_strike, spot)
    print("\n" + "="*60)
    print("GEX FEATURES")
    print("="*60)
    for key, value in features.items():
        print(f"{key}: {value:.2f}")
