"""
Coinglass Fetcher - Datos de Derivados (Freemium)
Open Interest, Funding Rates, Long/Short Ratios
Requiere API key gratuita: https://www.coinglass.com/pricing/api
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CoinglassFetcher:
    """
    Fetcher para datos de derivados de Coinglass

    Métricas clave:
    - open_interest: Interés abierto total en futuros de ETH
    - funding_rate: Tasa de financiamiento (positivo = más longs, negativo = más shorts)
    - long_short_ratio: Ratio de cuentas long vs short

    Lógica:
    - OI ↑ + Precio ↑ = Tendencia fuerte (bullish)
    - OI ↓ + Precio ↑ = Distribución (bearish)
    - Funding rate muy alto = Posible squeeze de longs
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://open-api.coinglass.com/public/v2"
        self.headers = {}
        if api_key:
            self.headers['coinglassSecret'] = api_key

    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Helper para hacer requests con rate limiting"""
        try:
            url = f"{self.base_url}/{endpoint}"
            response = requests.get(url, headers=self.headers, params=params, timeout=10)

            if response.status_code == 429:
                logger.warning("⚠️ Rate limit alcanzado, esperando 60s...")
                time.sleep(60)
                response = requests.get(url, headers=self.headers, params=params, timeout=10)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error en request a Coinglass: {e}")
            return None

    def fetch_open_interest_history(self, symbol: str = "ETH", days: int = 730) -> pd.DataFrame:
        """
        Descarga histórico de Open Interest

        Args:
            symbol: Símbolo (ETH, BTC)
            days: Días de histórico

        Returns:
            DataFrame con timestamp, open_interest
        """
        if not self.api_key:
            logger.warning("⚠️ Sin API key de Coinglass - Usando datos simulados")
            return self._simulate_open_interest(days)

        logger.info(f"📊 Descargando Open Interest de {symbol}...")

        try:
            # Endpoint para OI histórico
            endpoint = "indicator/open_interest_chart"
            params = {
                'symbol': symbol,
                'interval': '0'  # Daily data
            }

            data = self._make_request(endpoint, params)

            if not data or 'data' not in data:
                logger.warning("⚠️ No se obtuvieron datos de OI")
                return self._simulate_open_interest(days)

            # Parsear respuesta
            records = []
            for entry in data['data']:
                ts = datetime.fromtimestamp(entry['t'] / 1000)  # Timestamp en ms

                if ts < datetime.now() - timedelta(days=days):
                    continue

                records.append({
                    'timestamp': ts,
                    'open_interest': entry.get('v', 0)  # Value
                })

            df = pd.DataFrame(records)
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)

            # Calcular derivadas
            df['oi_change'] = df['open_interest'].pct_change()
            df['oi_ma7'] = df['open_interest'].rolling(7, min_periods=1).mean()

            logger.info(f"✓ Open Interest: {len(df)} registros")

            return df

        except Exception as e:
            logger.error(f"❌ Error procesando OI: {e}")
            return self._simulate_open_interest(days)

    def fetch_funding_rate_history(self, symbol: str = "ETH", days: int = 90) -> pd.DataFrame:
        """
        Descarga histórico de Funding Rates

        Args:
            symbol: Símbolo
            days: Días de histórico (limitado a 90 para free tier)

        Returns:
            DataFrame con timestamp, funding_rate
        """
        if not self.api_key:
            logger.warning("⚠️ Sin API key de Coinglass - Funding rate = 0")
            return pd.DataFrame(columns=['funding_rate'])

        logger.info(f"📊 Descargando Funding Rate de {symbol}...")

        try:
            endpoint = "indicator/funding_rates_chart"
            params = {
                'symbol': symbol,
                'interval': '8h'  # Funding rate cada 8h
            }

            data = self._make_request(endpoint, params)

            if not data or 'data' not in data:
                return pd.DataFrame(columns=['funding_rate'])

            records = []
            for entry in data['data']:
                ts = datetime.fromtimestamp(entry['t'] / 1000)

                if ts < datetime.now() - timedelta(days=days):
                    continue

                # Funding rate promedio de todos los exchanges
                avg_fr = np.mean([v for v in entry.values() if isinstance(v, (int, float))])

                records.append({
                    'timestamp': ts,
                    'funding_rate': avg_fr
                })

            df = pd.DataFrame(records)
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)

            logger.info(f"✓ Funding Rate: {len(df)} registros")

            return df

        except Exception as e:
            logger.error(f"❌ Error procesando Funding Rate: {e}")
            return pd.DataFrame(columns=['funding_rate'])

    def _simulate_open_interest(self, days: int) -> pd.DataFrame:
        """Genera OI simulado basado en volatilidad (fallback)"""
        logger.info("📉 Generando Open Interest simulado...")

        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')

        # OI correlacionado con volatilidad + tendencia
        np.random.seed(42)
        trend = np.linspace(1e9, 1.5e9, days)  # Tendencia alcista en OI
        noise = np.random.normal(0, 5e7, days)  # Ruido

        oi = trend + noise

        df = pd.DataFrame({
            'open_interest': oi,
            'oi_change': np.random.normal(0, 0.02, days),
            'oi_ma7': pd.Series(oi).rolling(7, min_periods=1).mean()
        }, index=dates)

        df.index.name = 'timestamp'
        return df

    def get_derivatives_features(self, symbol: str = "ETH", days: int = 730) -> pd.DataFrame:
        """
        Retorna features de derivados listas para el modelo

        Returns:
            DataFrame con:
            - open_interest_norm (normalizado)
            - oi_change (% change diario)
            - funding_rate (si disponible)
        """
        # Open Interest (siempre, aunque sea simulado)
        oi_df = self.fetch_open_interest_history(symbol, days)

        # Funding Rate (solo si hay API key)
        if self.api_key:
            fr_df = self.fetch_funding_rate_history(symbol, min(days, 90))
        else:
            fr_df = pd.DataFrame(columns=['funding_rate'])

        # Merge
        if not oi_df.empty and not fr_df.empty:
            result = oi_df.join(fr_df, how='left')
        else:
            result = oi_df

        # Normalizar OI (dividir por 1B)
        if 'open_interest' in result.columns:
            result['open_interest_norm'] = result['open_interest'] / 1e9
        else:
            result['open_interest_norm'] = 0.0

        # Fill NaN en funding rate
        if 'funding_rate' not in result.columns:
            result['funding_rate'] = 0.0
        else:
            result['funding_rate'] = result['funding_rate'].fillna(0)

        # Retornar solo features útiles
        features = ['open_interest_norm', 'oi_change', 'funding_rate']
        return result[[col for col in features if col in result.columns]].fillna(0)


if __name__ == "__main__":
    # Test básico (sin API key)
    fetcher = CoinglassFetcher(api_key=None)
    df = fetcher.get_derivatives_features(days=30)

    print("\n" + "="*60)
    print("TEST DE COINGLASS FETCHER")
    print("="*60)
    print(f"\nÚltimos 5 registros:")
    print(df.tail())
    print(f"\nEstadísticas:")
    print(df.describe())
