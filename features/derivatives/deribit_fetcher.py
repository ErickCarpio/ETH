"""
Deribit Options Fetcher - Gamma Exposure (GEX) Calculator
Fase 3.1: Opciones y posicionamiento institucional

Deribit API (GRATUITA):
- Endpoint: /public/get_book_summary_by_currency
- Límite: 20 req/10s (suficiente con 1 req/min)
- Sin API key necesaria

GEX (Gamma Exposure):
- Mide el riesgo gamma de los market makers
- Niveles con alto GEX actúan como imanes de precio
- GEX negativo = alta volatilidad esperada
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
from scipy.stats import norm

logger = logging.getLogger(__name__)

# Lazy import de py_vollib (opcional)
try:
    from py_vollib.black_scholes import black_scholes
    from py_vollib.black_scholes.greeks.analytical import gamma
    VOLLIB_AVAILABLE = True
except ImportError:
    VOLLIB_AVAILABLE = False
    logger.warning("py_vollib no disponible - instala con: pip install py_vollib")


class DeribitFetcher:
    """
    Fetcher para opciones de Deribit y cálculo de GEX

    Features calculadas:
    - GEX total (call + put)
    - GEX por strike
    - GEX skew (call vs put)
    - Niveles críticos (max pain, gamma flip)
    - IV metrics
    """

    BASE_URL = "https://www.deribit.com/api/v2"

    def __init__(self, currency: str = "ETH"):
        """
        Args:
            currency: 'ETH' o 'BTC'
        """
        self.currency = currency
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })

    def fetch_options_chain(self, kind: str = "option") -> List[Dict]:
        """
        Obtiene la cadena de opciones completa de Deribit

        Args:
            kind: 'option' para opciones, 'future' para futuros

        Returns:
            Lista de instrumentos con sus datos
        """
        endpoint = f"{self.BASE_URL}/public/get_book_summary_by_currency"
        params = {
            "currency": self.currency,
            "kind": kind
        }

        try:
            response = self.session.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                logger.info(f"✅ Opciones descargadas: {len(data['result'])} instrumentos")
                return data["result"]
            else:
                logger.warning(f"⚠️ No se encontraron opciones para {self.currency}")
                return []

        except Exception as e:
            logger.error(f"❌ Error fetching options: {e}")
            return []

    def get_spot_price(self) -> float:
        """
        Obtiene el precio spot actual desde Deribit index

        Returns:
            Precio spot de ETH o BTC
        """
        endpoint = f"{self.BASE_URL}/public/get_index_price"
        params = {"index_name": f"{self.currency.lower()}_usd"}

        try:
            response = self.session.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                price = data["result"]["index_price"]
                logger.info(f"💰 Spot price {self.currency}: ${price:,.2f}")
                return price
            else:
                logger.warning("⚠️ No se pudo obtener precio spot")
                return 0.0

        except Exception as e:
            logger.error(f"❌ Error fetching spot price: {e}")
            return 0.0

    def parse_instrument_name(self, instrument_name: str) -> Optional[Dict]:
        """
        Parsea el nombre del instrumento de Deribit

        Formato: ETH-25DEC24-3000-C
        - ETH: Currency
        - 25DEC24: Expiration
        - 3000: Strike
        - C/P: Call/Put

        Returns:
            Dict con parsed data o None si falla
        """
        try:
            parts = instrument_name.split("-")

            if len(parts) != 4:
                return None

            currency, exp_str, strike_str, option_type = parts

            # Parsear strike
            strike = float(strike_str)

            # Parsear fecha de expiración
            # Formato: 25DEC24 → 2024-12-25
            day = int(exp_str[:2])
            month_str = exp_str[2:5]
            year = int("20" + exp_str[5:7])

            month_map = {
                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
            }
            month = month_map.get(month_str)

            if not month:
                return None

            expiration_date = datetime(year, month, day)

            return {
                'currency': currency,
                'expiration': expiration_date,
                'strike': strike,
                'option_type': option_type,  # 'C' or 'P'
                'instrument_name': instrument_name
            }

        except Exception as e:
            logger.debug(f"Error parsing {instrument_name}: {e}")
            return None

    def calculate_gamma(self,
                       spot: float,
                       strike: float,
                       time_to_expiry: float,
                       iv: float,
                       option_type: str,
                       risk_free_rate: float = 0.05) -> float:
        """
        Calcula gamma usando Black-Scholes

        Args:
            spot: Precio spot actual
            strike: Strike price
            time_to_expiry: Tiempo hasta expiración en años
            iv: Implied Volatility (0-1)
            option_type: 'C' o 'P'
            risk_free_rate: Tasa libre de riesgo (default 5%)

        Returns:
            Gamma value
        """
        if not VOLLIB_AVAILABLE:
            # Aproximación simple si no hay py_vollib
            d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * iv ** 2) * time_to_expiry) / (iv * np.sqrt(time_to_expiry))
            gamma_value = norm.pdf(d1) / (spot * iv * np.sqrt(time_to_expiry))
            return gamma_value

        try:
            # Usar py_vollib para cálculo exacto
            flag = 'c' if option_type == 'C' else 'p'
            gamma_value = gamma(
                flag=flag,
                S=spot,
                K=strike,
                t=time_to_expiry,
                r=risk_free_rate,
                sigma=iv
            )
            return gamma_value

        except Exception as e:
            logger.debug(f"Error calculating gamma: {e}")
            return 0.0

    def calculate_gex_for_strike(self,
                                 spot: float,
                                 strike: float,
                                 gamma_value: float,
                                 open_interest: float,
                                 option_type: str) -> float:
        """
        Calcula GEX (Gamma Exposure) para un strike

        GEX = Gamma × OI × Spot² × 0.01

        Dealers están típicamente short opciones (long gamma del retail)
        Por eso multiplicamos por -1 para dealer exposure

        Args:
            spot: Precio spot
            strike: Strike price
            gamma_value: Gamma calculado
            open_interest: Open Interest en contratos
            option_type: 'C' o 'P'

        Returns:
            GEX value (puede ser negativo)
        """
        # Deribit reporta OI en USD, convertir a contratos
        # 1 contrato ETH = $10 de notional
        contracts = open_interest / 10

        # GEX formula
        # Multiplicamos por spot para normalizar
        gex = gamma_value * contracts * spot * spot * 0.01

        # Dealers suelen estar short calls (presión vendedora cuando spot sube)
        # Y short puts (presión compradora cuando spot baja)
        # Sign convention: negativo = dealer tiene que vender, positivo = comprar
        if option_type == 'C':
            gex = -gex  # Calls: dealer short → GEX negativo
        else:
            gex = gex   # Puts: dealer short → GEX positivo

        return gex

    def calculate_all_gex(self) -> Dict:
        """
        Calcula GEX completo para toda la cadena de opciones

        Returns:
            Dict con:
            - gex_total: GEX total
            - gex_call: GEX solo calls
            - gex_put: GEX solo puts
            - gex_by_strike: Dict {strike: gex}
            - strike_max_gex: Strike con mayor GEX absoluto
            - max_pain: Precio con menor pérdida para dealers
            - gamma_flip_level: Nivel donde GEX cambia de signo
        """
        # 1. Obtener spot price
        spot = self.get_spot_price()

        if spot == 0:
            return {}

        # 2. Obtener cadena de opciones
        options = self.fetch_options_chain()

        if not options:
            return {}

        # 3. Calcular GEX por cada opción
        gex_data = []
        gex_by_strike = {}

        for option in options:
            # Parsear instrumento
            parsed = self.parse_instrument_name(option.get("instrument_name", ""))

            if not parsed:
                continue

            # Filtrar opciones muy OTM (>30% de distancia)
            strike = parsed['strike']
            if abs(strike - spot) / spot > 0.30:
                continue

            # Obtener datos
            iv = option.get("mark_iv", 0) / 100  # IV en decimal
            open_interest_usd = option.get("open_interest", 0)
            expiration = parsed['expiration']
            option_type = parsed['option_type']

            # Calcular time to expiry
            time_to_expiry = max((expiration - datetime.now()).total_seconds() / (365.25 * 24 * 3600), 0.001)

            # Calcular gamma
            gamma_val = self.calculate_gamma(
                spot=spot,
                strike=strike,
                time_to_expiry=time_to_expiry,
                iv=max(iv, 0.01),  # Evitar IV=0
                option_type=option_type
            )

            # Calcular GEX
            gex = self.calculate_gex_for_strike(
                spot=spot,
                strike=strike,
                gamma_value=gamma_val,
                open_interest=open_interest_usd,
                option_type=option_type
            )

            # Agregar a lista
            gex_data.append({
                'strike': strike,
                'gex': gex,
                'gamma': gamma_val,
                'oi': open_interest_usd,
                'iv': iv,
                'option_type': option_type,
                'expiration': expiration,
                'days_to_expiry': time_to_expiry * 365.25
            })

            # Acumular por strike
            if strike not in gex_by_strike:
                gex_by_strike[strike] = 0
            gex_by_strike[strike] += gex

        if not gex_data:
            logger.warning("⚠️ No se pudo calcular GEX (datos insuficientes)")
            return {}

        # 4. Calcular métricas agregadas
        df = pd.DataFrame(gex_data)

        gex_total = df['gex'].sum()
        gex_call = df[df['option_type'] == 'C']['gex'].sum()
        gex_put = df[df['option_type'] == 'P']['gex'].sum()

        # Strike con mayor GEX absoluto
        df['abs_gex'] = df['gex'].abs()
        strike_max_gex = df.loc[df['abs_gex'].idxmax(), 'strike']

        # Max pain: strike donde la suma de OI × |strike - spot| es mínima
        # (simplificación: strike con mayor OI total)
        strike_oi = df.groupby('strike')['oi'].sum()
        max_pain = strike_oi.idxmax()

        # Gamma flip level: donde GEX cruza de negativo a positivo
        # (simplificación: strike más cercano donde GEX cambia de signo)
        strikes_sorted = sorted(gex_by_strike.keys())
        gamma_flip = None

        for i in range(len(strikes_sorted) - 1):
            s1, s2 = strikes_sorted[i], strikes_sorted[i + 1]
            gex1, gex2 = gex_by_strike[s1], gex_by_strike[s2]

            if (gex1 < 0 and gex2 > 0) or (gex1 > 0 and gex2 < 0):
                # Interpolate
                gamma_flip = s1 + (s2 - s1) * abs(gex1) / (abs(gex1) + abs(gex2))
                break

        result = {
            'timestamp': datetime.now(),
            'spot_price': spot,
            'gex_total': gex_total,
            'gex_call': gex_call,
            'gex_put': gex_put,
            'gex_skew': (gex_call - gex_put) / (abs(gex_call) + abs(gex_put) + 1e-8),
            'gex_by_strike': gex_by_strike,
            'strike_max_gex': strike_max_gex,
            'max_pain_price': max_pain,
            'gamma_flip_level': gamma_flip if gamma_flip else spot,
            'total_oi': df['oi'].sum(),
            'iv_mean': df['iv'].mean(),
            'iv_skew': df[df['option_type'] == 'P']['iv'].mean() - df[df['option_type'] == 'C']['iv'].mean(),
            'put_call_ratio': len(df[df['option_type'] == 'P']) / (len(df[df['option_type'] == 'C']) + 1),
            'options_analyzed': len(df)
        }

        logger.info(f"✅ GEX calculado:")
        logger.info(f"   Total GEX: ${gex_total:,.0f}")
        logger.info(f"   Call GEX: ${gex_call:,.0f}")
        logger.info(f"   Put GEX: ${gex_put:,.0f}")
        logger.info(f"   Strike Max GEX: ${strike_max_gex:,.0f}")
        logger.info(f"   Max Pain: ${max_pain:,.0f}")
        logger.info(f"   Gamma Flip: ${gamma_flip:,.2f}" if gamma_flip else "   Gamma Flip: N/A")

        return result


# Testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("🎯 Deribit GEX Calculator - Test\n")

    fetcher = DeribitFetcher(currency="ETH")

    print("📊 Calculando GEX para ETH...\n")

    gex = fetcher.calculate_all_gex()

    if gex:
        print(f"\n✅ RESULTADOS:")
        print(f"   Spot Price: ${gex['spot_price']:,.2f}")
        print(f"   GEX Total: ${gex['gex_total']:,.0f}")
        print(f"   GEX Calls: ${gex['gex_call']:,.0f}")
        print(f"   GEX Puts: ${gex['gex_put']:,.0f}")
        print(f"   GEX Skew: {gex['gex_skew']:.3f}")
        print(f"   Strike Max GEX: ${gex['strike_max_gex']:,.0f}")
        print(f"   Max Pain: ${gex['max_pain_price']:,.0f}")
        print(f"   Gamma Flip: ${gex['gamma_flip_level']:,.2f}")
        print(f"   Put/Call Ratio: {gex['put_call_ratio']:.2f}")
        print(f"   Opciones analizadas: {gex['options_analyzed']}")

        print(f"\n📈 Top 5 strikes por GEX:")
        sorted_strikes = sorted(gex['gex_by_strike'].items(), key=lambda x: abs(x[1]), reverse=True)[:5]
        for strike, gex_val in sorted_strikes:
            print(f"   ${strike:,.0f}: ${gex_val:,.0f}")
    else:
        print("❌ No se pudo calcular GEX")
