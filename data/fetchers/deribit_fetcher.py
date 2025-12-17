"""
Deribit Options Fetcher - FASE 3.1
===================================

Descarga cadena de opciones de Deribit y calcula GEX (Gamma Exposure).

API Deribit (GRATIS):
- Endpoint: https://www.deribit.com/api/v2/public/get_book_summary_by_currency
- Límite: 20 req/10s
- No requiere autenticación para datos públicos

GEX (Gamma Exposure):
- Mide exposición gamma de market makers por strike
- GEX positivo = soporte (MM compran en caídas)
- GEX negativo = resistencia (MM venden en subidas)

Fórmula:
GEX_strike = Gamma × Open_Interest × Spot_Price × 0.01
"""

import aiohttp
import asyncio
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

# Para cálculo de Greeks
try:
    from py_vollib.black_scholes.greeks.analytical import gamma as bs_gamma
    from py_vollib.black_scholes.implied_volatility import implied_volatility
    VOLLIB_AVAILABLE = True
except ImportError:
    VOLLIB_AVAILABLE = False
    logging.warning("py_vollib not available - install with: pip install py_vollib")

logger = logging.getLogger(__name__)


class DeribOptions:
    """
    Fetcher para opciones de Deribit con cálculo de GEX.

    Workflow:
    1. Fetch cadena de opciones (todas las expiraciones)
    2. Calcular Greeks (gamma) con Black-Scholes
    3. Calcular GEX por strike
    4. Agregar GEX total y por nivel de precio
    """

    def __init__(self, currency: str = "ETH"):
        """
        Initialize Deribit Options Fetcher.

        Args:
            currency: Moneda (ETH o BTC)
        """
        self.currency = currency.upper()
        self.base_url = "https://www.deribit.com/api/v2/public"

        # Rate limiting (20 req/10s = 2 req/s)
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 500ms entre requests

    async def _rate_limited_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """
        Hace request con rate limiting.

        Args:
            endpoint: Endpoint de API
            params: Parámetros del request

        Returns:
            JSON response o None si error
        """
        # Rate limiting
        now = asyncio.get_event_loop().time()
        elapsed = now - self.last_request_time

        if elapsed < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - elapsed)

        self.last_request_time = asyncio.get_event_loop().time()

        # Make request
        url = f"{self.base_url}/{endpoint}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('result')
                    else:
                        logger.error(f"Request failed: {response.status}")
                        return None

        except Exception as e:
            logger.error(f"Request error: {e}")
            return None

    async def get_current_price(self) -> Optional[float]:
        """
        Obtiene precio spot actual.

        Returns:
            Precio actual o None
        """
        result = await self._rate_limited_request(
            'get_index_price',
            {'index_name': f'{self.currency.lower()}_usd'}
        )

        if result:
            return result.get('index_price')

        return None

    async def get_options_chain(self,
                                kind: str = "option",
                                expired: bool = False) -> Optional[List[Dict]]:
        """
        Obtiene cadena completa de opciones.

        Args:
            kind: 'option' o 'future'
            expired: Incluir opciones expiradas

        Returns:
            Lista de instrumentos de opciones
        """
        result = await self._rate_limited_request(
            'get_book_summary_by_currency',
            {
                'currency': self.currency,
                'kind': kind
            }
        )

        if not result:
            return None

        # Filtrar opciones expiradas si requerido
        if not expired:
            result = [opt for opt in result if not opt.get('instrument_name', '').endswith('EXPIRED')]

        logger.info(f"✓ Fetched {len(result)} {kind}s for {self.currency}")

        return result

    def parse_instrument_name(self, instrument: str) -> Optional[Dict]:
        """
        Parsea nombre de instrumento de Deribit.

        Formato: ETH-31DEC21-4000-C
        - ETH: Currency
        - 31DEC21: Expiration date
        - 4000: Strike
        - C/P: Call/Put

        Args:
            instrument: Nombre del instrumento

        Returns:
            Dict con parsed data
        """
        try:
            parts = instrument.split('-')

            if len(parts) != 4:
                return None

            currency, expiry_str, strike_str, option_type = parts

            # Parse expiration
            expiry = datetime.strptime(expiry_str, '%d%b%y')

            # Parse strike
            strike = float(strike_str)

            # Parse option type
            is_call = option_type == 'C'

            return {
                'currency': currency,
                'expiry': expiry,
                'strike': strike,
                'option_type': 'call' if is_call else 'put',
                'is_call': is_call
            }

        except Exception as e:
            logger.debug(f"Failed to parse {instrument}: {e}")
            return None

    def calculate_gamma(self,
                       spot: float,
                       strike: float,
                       time_to_expiry: float,
                       iv: float,
                       risk_free_rate: float = 0.0) -> Optional[float]:
        """
        Calcula gamma usando Black-Scholes.

        Args:
            spot: Precio spot
            strike: Strike price
            time_to_expiry: Tiempo a expiración (años)
            iv: Implied Volatility (decimal, ej: 0.80 = 80%)
            risk_free_rate: Tasa libre de riesgo

        Returns:
            Gamma o None si error
        """
        if not VOLLIB_AVAILABLE:
            logger.warning("py_vollib not available, cannot calculate gamma")
            return None

        try:
            # Black-Scholes gamma (igual para calls y puts)
            gamma = bs_gamma(
                flag='c',  # No importa (gamma es igual para call/put)
                S=spot,
                K=strike,
                t=time_to_expiry,
                r=risk_free_rate,
                sigma=iv
            )

            return gamma

        except Exception as e:
            logger.debug(f"Gamma calculation failed: {e}")
            return None

    async def calculate_gex(self,
                           spot_price: Optional[float] = None,
                           min_oi: int = 10) -> pd.DataFrame:
        """
        Calcula GEX (Gamma Exposure) por strike.

        Args:
            spot_price: Precio spot (None = fetch actual)
            min_oi: OI mínimo para incluir opción

        Returns:
            DataFrame con GEX por strike
        """
        # Obtener precio spot
        if spot_price is None:
            spot_price = await self.get_current_price()

        if not spot_price:
            logger.error("Could not get spot price")
            return pd.DataFrame()

        logger.info(f"Calculating GEX for {self.currency} @ ${spot_price:.2f}")

        # Obtener cadena de opciones
        options = await self.get_options_chain()

        if not options:
            logger.error("Could not fetch options chain")
            return pd.DataFrame()

        # Procesar cada opción
        gex_data = []

        for option in options:
            instrument_name = option.get('instrument_name', '')

            # Parse instrument
            parsed = self.parse_instrument_name(instrument_name)

            if not parsed:
                continue

            # Extraer datos
            strike = parsed['strike']
            expiry = parsed['expiry']
            is_call = parsed['is_call']

            # Open interest
            open_interest = option.get('open_interest', 0)

            if open_interest < min_oi:
                continue

            # Implied volatility (mark_iv en decimal)
            iv = option.get('mark_iv', 80) / 100  # Convertir de % a decimal

            # Time to expiry (en años)
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
            # Nota: Asumimos que dealers están SHORT las opciones (posición usual)
            # Por tanto, el GEX del dealer es negativo del OI
            dealer_position = -open_interest

            # GEX = Gamma × OI × Spot × 0.01
            # El 0.01 es porque gamma mide cambio por $1 de movimiento
            gex = gamma * dealer_position * spot_price * 0.01

            # Ajustar signo para calls vs puts
            # Calls: GEX positivo si dealers short
            # Puts: GEX negativo si dealers short
            if not is_call:
                gex = -gex

            gex_data.append({
                'strike': strike,
                'expiry': expiry,
                'days_to_expiry': days_to_expiry,
                'option_type': 'call' if is_call else 'put',
                'open_interest': open_interest,
                'iv': iv,
                'gamma': gamma,
                'gex': gex,
                'spot': spot_price
            })

        # Crear DataFrame
        df = pd.DataFrame(gex_data)

        if df.empty:
            logger.warning("No GEX data calculated")
            return df

        # Agregar GEX por strike (sumar calls + puts)
        gex_by_strike = df.groupby('strike')['gex'].sum().reset_index()
        gex_by_strike.columns = ['strike', 'gex_total']

        logger.info(f"✓ Calculated GEX for {len(df)} options across {len(gex_by_strike)} strikes")

        return df, gex_by_strike

    def get_gex_levels(self,
                      gex_by_strike: pd.DataFrame,
                      spot_price: float,
                      n_levels: int = 10) -> Dict:
        """
        Identifica niveles clave de GEX.

        Args:
            gex_by_strike: DataFrame con GEX por strike
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

        return {
            'spot_price': spot_price,
            'total_gex': gex_by_strike['gex_total'].sum(),
            'total_positive_gex': gex_by_strike[gex_by_strike['gex_total'] > 0]['gex_total'].sum(),
            'total_negative_gex': gex_by_strike[gex_by_strike['gex_total'] < 0]['gex_total'].sum(),
            'support_levels': support_levels.to_dict('records'),
            'resistance_levels': resistance_levels.to_dict('records'),
            'nearest_support': self._find_nearest_level(support_levels, spot_price, direction='below'),
            'nearest_resistance': self._find_nearest_level(resistance_levels, spot_price, direction='above')
        }

    def _find_nearest_level(self,
                           levels: pd.DataFrame,
                           spot: float,
                           direction: str) -> Optional[Dict]:
        """
        Encuentra nivel más cercano en dirección específica.

        Args:
            levels: DataFrame con strikes
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

        return nearest.to_dict()


async def main():
    """
    Ejemplo de uso del Deribit Options Fetcher.
    """
    # Crear fetcher
    fetcher = DeribOptions(currency='ETH')

    # Obtener precio spot
    spot = await fetcher.get_current_price()
    print(f"\n{fetcher.currency} Spot Price: ${spot:.2f}")

    # Calcular GEX
    print(f"\nCalculating GEX...")
    df, gex_by_strike = await fetcher.calculate_gex(spot_price=spot)

    if not gex_by_strike.empty:
        # Niveles clave
        levels = fetcher.get_gex_levels(gex_by_strike, spot)

        print("\n" + "="*60)
        print("GEX ANALYSIS")
        print("="*60)
        print(f"Total GEX: ${levels['total_gex']:,.0f}")
        print(f"Positive GEX (Support): ${levels['total_positive_gex']:,.0f}")
        print(f"Negative GEX (Resistance): ${levels['total_negative_gex']:,.0f}")

        print(f"\nTop Support Levels:")
        for level in levels['support_levels'][:5]:
            print(f"  ${level['strike']:.0f} - GEX: ${level['gex_total']:,.0f}")

        print(f"\nTop Resistance Levels:")
        for level in levels['resistance_levels'][:5]:
            print(f"  ${level['strike']:.0f} - GEX: ${level['gex_total']:,.0f}")

        if levels['nearest_support']:
            print(f"\nNearest Support: ${levels['nearest_support']['strike']:.0f} (GEX: ${levels['nearest_support']['gex_total']:,.0f})")

        if levels['nearest_resistance']:
            print(f"Nearest Resistance: ${levels['nearest_resistance']['strike']:.0f} (GEX: ${levels['nearest_resistance']['gex_total']:,.0f})")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if not VOLLIB_AVAILABLE:
        print("\n⚠️  py_vollib not installed")
        print("Install with: pip install py_vollib")
        print("This is required for Greeks calculation\n")

    asyncio.run(main())
