"""
DefiLlama Fetcher - Stablecoin Market Data (100% Gratis)
Obtiene datos de liquidez de stablecoins como proxy de capital entrante/saliente
No requiere API keys
FIXED: Windows timestamp compatibility
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DefiLlamaFetcher:
    """
    Fetcher para datos de stablecoins de DefiLlama

    Métricas clave:
    - stablecoin_mcap: Market cap total de stablecoins (USDT + USDC + DAI)
    - stablecoin_mcap_change: Cambio en market cap (proxy de capital flows)
    - stablecoin_dominance: % stablecoins vs total crypto market cap

    Lógica:
    - ↑ Market cap stablecoins = Dinero fresco listo para comprar = Bullish
    - ↓ Market cap stablecoins = Salida de capital = Bearish
    """

    def __init__(self):
        self.base_url = "https://stablecoins.llama.fi"
        # Top stablecoins por market cap
        self.stablecoins = {
            'USDT': 1,  # Tether
            'USDC': 2,  # USD Coin
            'DAI': 3,   # Dai
            'BUSD': 4,  # Binance USD (deprecated pero puede tener historial)
        }

    def fetch_stablecoin_history(self, days: int = 730) -> pd.DataFrame:
        """
        Descarga histórico de market cap de stablecoins

        Args:
            days: Días de histórico (default 2 años)

        Returns:
            DataFrame con timestamp, total_mcap, mcap_change, dominance
        """
        logger.info(f"📊 Descargando datos de stablecoins (DefiLlama)...")

        try:
            # Endpoint para histórico de TODOS los stablecoins agregados
            url = f"{self.base_url}/stablecoincharts/all"

            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()

            logger.info(f"📥 Recibidos {len(data)} registros de DefiLlama API")

            # Parsear datos
            records = []
            skipped = 0
            for entry in data:
                try:
                    # DefiLlama retorna timestamp en segundos
                    date_val = entry.get('date', 0)

                    # CRITICAL FIX: Usar pd.to_datetime con unit='s' explícito
                    # Esto evita el error "year is out of range" en Windows
                    ts = pd.to_datetime(date_val, unit='s')

                    # Solo últimos N días
                    if ts < datetime.now() - timedelta(days=days):
                        continue

                    # Obtener market cap total
                    mcap_data = entry.get('totalCirculatingUSD', {})
                    if isinstance(mcap_data, dict):
                        total_mcap = mcap_data.get('peggedUSD', 0)
                    else:
                        total_mcap = mcap_data if isinstance(mcap_data, (int, float)) else 0

                    records.append({
                        'timestamp': ts,
                        'total_mcap': float(total_mcap)
                    })
                except Exception as e:
                    skipped += 1
                    if skipped <= 3:  # Solo mostrar primeros 3 errores
                        logger.warning(f"⚠️ Skipping entry: {e}")
                    continue

            logger.info(f"📊 Procesados: {len(records)}, Skipped: {skipped}")

            if not records:
                logger.warning("⚠️ No se obtuvieron datos de DefiLlama después de parsear")
                logger.warning(f"   Total de entries recibidas: {len(data)}")
                logger.warning(f"   Todas fueron filtradas/skipped")
                return pd.DataFrame()

            df = pd.DataFrame(records)
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)

            # Calcular métricas derivadas
            df['mcap_change_1d'] = df['total_mcap'].diff()
            df['mcap_change_7d'] = df['total_mcap'].diff(7)
            df['mcap_pct_change'] = df['total_mcap'].pct_change()

            # Rolling averages para suavizar
            df['mcap_ma7'] = df['total_mcap'].rolling(7, min_periods=1).mean()
            df['mcap_ma30'] = df['total_mcap'].rolling(30, min_periods=1).mean()

            # Trend: MA7 sobre MA30 indica tendencia
            df['mcap_trend'] = (df['mcap_ma7'] / df['mcap_ma30']) - 1

            logger.info(f"✓ DefiLlama: {len(df)} registros descargados")
            logger.info(f"  Market cap actual: ${df['total_mcap'].iloc[-1] / 1e9:.1f}B")
            logger.info(f"  Cambio 7d: ${df['mcap_change_7d'].iloc[-1] / 1e9:.2f}B")

            return df

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error descargando de DefiLlama: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"❌ Error procesando datos DefiLlama: {e}")
            return pd.DataFrame()

    def get_stablecoin_features(self, days: int = 730) -> pd.DataFrame:
        """
        Wrapper que retorna features listas para el modelo

        Returns:
            DataFrame con timestamp index y columnas:
            - stablecoin_mcap (normalizado)
            - stablecoin_flow_7d (cambio en 7 días, normalizado)
            - stablecoin_trend (MA7/MA30 - 1)
        """
        df = self.fetch_stablecoin_history(days)

        if df.empty:
            return pd.DataFrame(columns=['stablecoin_mcap', 'stablecoin_flow_7d', 'stablecoin_trend'])

        # Normalizar market cap (dividir por 100B para que sea escala similar a otras features)
        df['stablecoin_mcap'] = df['total_mcap'] / 1e11

        # Flow en 7 días (normalizado)
        df['stablecoin_flow_7d'] = df['mcap_change_7d'] / 1e10  # En decenas de billones

        # Trend ya está calculado
        df['stablecoin_trend'] = df['mcap_trend']

        # Retornar solo las columnas útiles
        return df[['stablecoin_mcap', 'stablecoin_flow_7d', 'stablecoin_trend']].fillna(0)


if __name__ == "__main__":
    # Test básico
    fetcher = DefiLlamaFetcher()
    df = fetcher.get_stablecoin_features(days=30)

    if not df.empty:
        print("\n" + "="*60)
        print("TEST DE DEFILLAMA FETCHER")
        print("="*60)
        print(f"\nÚltimos 5 registros:")
        print(df.tail())
        print(f"\nEstadísticas:")
        print(df.describe())
    else:
        print("❌ Test falló - No se obtuvieron datos")
