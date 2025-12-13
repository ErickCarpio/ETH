"""
On-Chain Data Fetcher - Descarga datos reales de flujos de exchange
Integración con APIs de Glassnode, CryptoQuant, o alternativas gratuitas
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


class OnChainDataFetcher:
    """
    Descarga y procesa datos on-chain de múltiples fuentes:
    - CryptoQuant API (gratuita con límites)
    - Glassnode API (requiere suscripción)
    - Alternativas gratuitas (CoinGecko, IntoTheBlock)
    """
    
    def __init__(self, api_keys: Dict[str, str] = None):
        """
        Args:
            api_keys: Dict con keys para diferentes servicios
                     {'glassnode': 'key', 'cryptoquant': 'key'}
        """
        self.api_keys = api_keys or {}
        self.base_urls = {
            'glassnode': 'https://api.glassnode.com/v1/metrics',
            'cryptoquant': 'https://api.cryptoquant.com/v1',
            'coingecko': 'https://api.coingecko.com/api/v3'
        }
    
    def fetch_exchange_netflow(self, 
                               symbol: str = 'ETH',
                               days: int = 730,
                               source: str = 'cryptoquant') -> pd.DataFrame:
        """
        Descarga flujo neto de exchange (Inflows - Outflows)
        
        Args:
            symbol: Símbolo (ETH, BTC)
            days: Días históricos
            source: 'cryptoquant', 'glassnode', o 'simulated'
        
        Returns:
            DataFrame con columnas: timestamp, net_flow
        """
        logger.info(f"Descargando exchange netflow para {symbol} ({days} días)")
        
        if source == 'cryptoquant' and 'cryptoquant' in self.api_keys:
            return self._fetch_from_cryptoquant(symbol, days)
        
        elif source == 'glassnode' and 'glassnode' in self.api_keys:
            return self._fetch_from_glassnode(symbol, days)
        
        else:
            logger.warning("Sin API keys válidas, usando datos simulados")
            return self._simulate_netflow_data(symbol, days)
    
    def _fetch_from_cryptoquant(self, symbol: str, days: int) -> pd.DataFrame:
        """
        CryptoQuant API - Exchange Flow
        
        Endpoint: /exchange-flows/all-exchange-flows
        Documentación: https://docs.cryptoquant.com/
        """
        try:
            endpoint = f"{self.base_urls['cryptoquant']}/market-data/exchange-flows"
            
            params = {
                'exchange': 'all_exchange',
                'window': 'day',
                'symbol': symbol.upper(),
                'from': int((datetime.now() - timedelta(days=days)).timestamp()),
                'to': int(datetime.now().timestamp())
            }
            
            headers = {
                'Authorization': f"Bearer {self.api_keys['cryptoquant']}"
            }
            
            response = requests.get(endpoint, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()['result']['data']
            
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['datetime'])
            df['net_flow'] = df['inflow'] - df['outflow']
            
            df = df[['timestamp', 'net_flow']].set_index('timestamp')
            
            logger.info(f"Descargados {len(df)} registros de CryptoQuant")
            return df
            
        except Exception as e:
            logger.error(f"Error en CryptoQuant API: {e}")
            return self._simulate_netflow_data(symbol, days)
    
    def _fetch_from_glassnode(self, symbol: str, days: int) -> pd.DataFrame:
        """
        Glassnode API - Exchange Net Position Change
        
        Endpoint: /addresses/net_position_change_all
        Documentación: https://docs.glassnode.com/
        """
        try:
            asset = symbol.upper()
            endpoint = f"{self.base_urls['glassnode']}/addresses/net_position_change_all"
            
            params = {
                'a': asset,
                'i': '24h',  # Intervalo diario
                'api_key': self.api_keys['glassnode'],
                's': int((datetime.now() - timedelta(days=days)).timestamp()),
                'u': int(datetime.now().timestamp())
            }
            
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['t'], unit='s')
            df['net_flow'] = df['v']
            
            df = df[['timestamp', 'net_flow']].set_index('timestamp')
            
            logger.info(f"Descargados {len(df)} registros de Glassnode")
            return df
            
        except Exception as e:
            logger.error(f"Error en Glassnode API: {e}")
            return self._simulate_netflow_data(symbol, days)
    
    def _simulate_netflow_data(self, symbol: str, days: int) -> pd.DataFrame:
        """
        Genera datos simulados de netflow para testing
        Basado en patrones realistas de mercado
        """
        logger.warning("⚠️ USANDO DATOS SIMULADOS - No usar en producción")
        
        dates = pd.date_range(
            end=datetime.now(),
            periods=days,
            freq='D'
        )
        
        # Simular flujos con componentes:
        # 1. Tendencia (correlacionada con precio)
        # 2. Estacionalidad (fin de semana menos actividad)
        # 3. Eventos (ballenas moviendo fondos)
        
        trend = np.linspace(0, 100, days) + np.random.randn(days) * 50
        seasonality = 30 * np.sin(np.arange(days) * 2 * np.pi / 7)  # Ciclo semanal
        
        # Eventos de ballenas (random spikes)
        whale_events = np.zeros(days)
        whale_days = np.random.choice(days, size=int(days * 0.05), replace=False)
        whale_events[whale_days] = np.random.randn(len(whale_days)) * 500
        
        net_flow = trend + seasonality + whale_events
        
        df = pd.DataFrame({
            'net_flow': net_flow
        }, index=dates)
        
        df.index.name = 'timestamp'
        
        logger.info(f"Generados {len(df)} registros simulados")
        return df
    
    def fetch_whale_transactions(self, 
                                 symbol: str = 'ETH',
                                 min_value_usd: float = 1_000_000,
                                 hours: int = 24) -> pd.DataFrame:
        """
        Descarga transacciones grandes (ballenas) recientes
        
        Args:
            symbol: Símbolo
            min_value_usd: Valor mínimo en USD para considerar "ballena"
            hours: Horas hacia atrás
        
        Returns:
            DataFrame con transacciones grandes
        """
        logger.info(f"Buscando transacciones > ${min_value_usd:,.0f}")
        
        # Aquí integrarías con Whale Alert API o similar
        # Por ahora retornamos estructura vacía
        
        return pd.DataFrame({
            'timestamp': [],
            'value_usd': [],
            'from_exchange': [],
            'to_exchange': []
        })
    
    def calculate_exchange_reserve(self, 
                                   symbol: str = 'ETH',
                                   days: int = 365) -> pd.DataFrame:
        """
        Calcula reservas totales en exchanges
        Útil para detectar patrones de acumulación/distribución
        
        Returns:
            DataFrame con timestamp, reserve
        """
        # Placeholder - integrar con Glassnode o CryptoQuant
        logger.info("Calculando reservas de exchange...")
        
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
        
        # Simulación: reservas decrecientes = bullish (gente sacando de exchanges)
        reserves = 2_000_000 - np.linspace(0, 200_000, days) + np.random.randn(days) * 10_000
        
        return pd.DataFrame({
            'reserve': reserves
        }, index=dates)
    
    def get_composite_onchain_signal(self, 
                                     symbol: str = 'ETH',
                                     days: int = 730) -> pd.DataFrame:
        """
        Combina múltiples métricas on-chain en un DataFrame completo
        
        Returns:
            DataFrame con todas las métricas on-chain listas para features
        """
        logger.info("=" * 60)
        logger.info("CONSTRUYENDO DATASET ON-CHAIN COMPLETO")
        logger.info("=" * 60)
        
        # 1. Net Flow
        netflow_df = self.fetch_exchange_netflow(symbol, days)
        
        # 2. Reservas
        reserve_df = self.calculate_exchange_reserve(symbol, min(days, 365))
        
        # Combinar
        onchain_df = netflow_df.join(reserve_df, how='outer')
        onchain_df.ffill(inplace=True)
        
        # Métricas derivadas
        onchain_df['reserve_change'] = onchain_df['reserve'].pct_change()
        onchain_df['netflow_ma7'] = onchain_df['net_flow'].rolling(7).mean()
        onchain_df['netflow_volatility'] = onchain_df['net_flow'].rolling(7).std()
        
        logger.info(f"Dataset on-chain construido: {onchain_df.shape}")
        logger.info(f"Columnas: {list(onchain_df.columns)}")
        
        return onchain_df


# Funciones de utilidad para integración con DataManager

def integrate_onchain_with_ohlcv(ohlcv_df: pd.DataFrame, 
                                 onchain_df: pd.DataFrame,
                                 resample_freq: str = '4H') -> pd.DataFrame:
    """
    Fusiona datos on-chain (diarios) con OHLCV (4H)
    
    Args:
        ohlcv_df: DataFrame con precios 4H
        onchain_df: DataFrame con datos on-chain diarios
        resample_freq: Frecuencia objetivo
    
    Returns:
        DataFrame fusionado
    """
    # Resamplear on-chain a la frecuencia de OHLCV
    onchain_resampled = onchain_df.resample(resample_freq).ffill()
    
    # Merge por índice temporal
    merged = ohlcv_df.join(onchain_resampled, how='left')
    
    # Forward fill para valores faltantes
    onchain_cols = onchain_df.columns
    merged[onchain_cols] = merged[onchain_cols].ffill()
    
    logger.info(f"Datos on-chain integrados con OHLCV: {merged.shape}")
    
    return merged


# Testing
if __name__ == "__main__":
    # Test con datos simulados
    fetcher = OnChainDataFetcher()
    
    # Obtener netflow
    netflow = fetcher.fetch_exchange_netflow('ETH', days=730)
    print(f"\nNetflow shape: {netflow.shape}")
    print(f"\nÚltimos 5 registros:")
    print(netflow.tail())
    
    # Obtener dataset completo
    onchain_data = fetcher.get_composite_onchain_signal('ETH', days=730)
    print(f"\nDataset completo:")
    print(onchain_data.info())
    print(f"\nEstadísticas:")
    print(onchain_data.describe())
    
    # Test de integración
    dates = pd.date_range(end=datetime.now(), periods=1000, freq='4H')
    dummy_ohlcv = pd.DataFrame({
        'close': np.random.randn(1000).cumsum() + 2000
    }, index=dates)
    
    merged = integrate_onchain_with_ohlcv(dummy_ohlcv, onchain_data)
    print(f"\nDatos fusionados: {merged.shape}")
    print(merged.tail())