# 📊 APIs del Proyecto y Asignación para 20 Pares

## 🔍 Resumen de APIs Identificadas

### 1. **Binance (OHLCV + WebSocket)**
- **Fuente**: `ccxt.binanceusdm`, WebSocket Binance
- **Uso**: Datos OHLCV, orderbook L2, trades
- **Autenticación**: API keys (solo para trading, no para datos públicos)
- **Rate Limits**:
  - REST API: 2400 requests/min (40 req/s) por IP
  - WebSocket: 300 conexiones por IP, 10 mensajes/s por stream
- **Asignación para 20 pares**: ✅ SIN PROBLEMA
  - Descargar OHLCV de 20 pares secuencialmente
  - Total: ~40 requests (1h + 4h + 15m por par)
  - Tiempo estimado: ~2-3 minutos con rate limiting

---

### 2. **NewsAPI** ⚠️ CRÍTICO
- **Fuente**: `data/fetchers/sentiment_fetcher.py` (línea 81-105)
- **URL**: `https://newsapi.org/v2/everything`
- **Uso**: Noticias de criptomonedas para sentiment analysis
- **Autenticación**: API key en header `X-Api-Key`
- **Rate Limits**:
  - **Free Tier**: 100 requests/día
  - **Límite histórico**: Solo 28 días atrás
- **Asignación para 20 pares**: ⚠️ **5 requests por par = 100 total/día**
  ```python
  # MODIFICAR en sentiment_fetcher.py
  max_news_per_pair = 5  # 5 × 20 pares = 100 requests
  ```
- **Problema**: Si entrenamos con 730 días de histórico, solo podemos obtener noticias de los últimos 28 días
- **Solución**:
  - Usar CryptoPanic como fuente principal (sin límites)
  - NewsAPI solo para últimos 28 días

---

### 3. **CryptoPanic**
- **Fuente**: `data/fetchers/sentiment_fetcher.py` (línea 107-144)
- **URL**: `https://cryptopanic.com/api/v1/posts/`
- **Uso**: Noticias y sentiment de crypto
- **Autenticación**: `auth_token` en query params
- **Rate Limits**:
  - **Free Tier**: No especificado en docs, pero existe
  - Estimado: ~1000 requests/día
  - Paginación: 20 posts por página
- **Asignación para 20 pares**: ✅ VIABLE
  ```python
  # Estrategia: 5 páginas por par
  pages_per_pair = 5
  total_requests = 20 × 5 = 100 requests
  noticias_por_par = 5 × 20 = ~100 noticias
  ```

---

### 4. **Coinglass (Derivatives)**
- **Fuente**: `data/fetchers/coinglass_fetcher.py`
- **URL**: `https://open-api.coinglass.com/public/v2`
- **Uso**: Open Interest, Funding Rates, Long/Short Ratios
- **Autenticación**: Header `coinglassSecret`
- **Rate Limits**:
  - Free tier: No especificado oficialmente
  - Código implementa retry con 60s wait en 429 error
- **Endpoints**:
  - `indicator/open_interest_chart` - OI histórico (daily)
  - `indicator/funding_rates_chart` - Funding rate (8h intervals)
- **Asignación para 20 pares**: ⚠️ REQUIERE API KEY
  ```python
  # Si tienes API key:
  # 2 requests por par (OI + Funding) = 40 requests
  # Sin API key: usa datos simulados (fallback implementado)
  ```

---

### 5. **DefiLlama (Stablecoins)** ✅
- **Fuente**: `data/fetchers/defillama_fetcher.py`
- **URL**: `https://stablecoins.llama.fi`
- **Uso**: Market cap de stablecoins (indicador macro)
- **Autenticación**: ❌ No requiere API key
- **Rate Limits**: ❌ Sin límites (100% gratis)
- **Asignación para 20 pares**: ✅ SIN PROBLEMA
  ```python
  # Los datos de stablecoins son GLOBALES (no por par)
  # Solo 1 request total para obtener histórico completo
  ```

---

### 6. **CryptoQuant (On-Chain)**
- **Fuente**: `data/fetchers/onchain_data_fetcher.py` (línea 66-104)
- **URL**: `https://api.cryptoquant.com/v1`
- **Uso**: Exchange netflow, reservas, whale movements
- **Autenticación**: Bearer token
- **Rate Limits**:
  - Free tier: Limitado (sin especificar)
  - Pro: 120 requests/min
- **Asignación para 20 pares**: ⚠️ REQUIERE API KEY
  ```python
  # Si tienes API key:
  # 1 request por par (netflow) = 20 requests
  # Sin API key: usa datos simulados (fallback implementado)
  ```

---

### 7. **Glassnode (On-Chain)**
- **Fuente**: `data/fetchers/onchain_data_fetcher.py` (línea 106-141)
- **URL**: `https://api.glassnode.com/v1/metrics`
- **Uso**: On-chain metrics (netflow, reserves)
- **Autenticación**: API key en query params
- **Rate Limits**:
  - Free tier: 10 requests/día (muy limitado)
  - Paid: 1000 requests/día
- **Asignación para 20 pares**: ❌ NO VIABLE CON FREE TIER
  ```python
  # Free tier: solo 10 requests/día → 0.5 pares
  # Alternativa: usar CryptoQuant o datos simulados
  ```

---

## 📋 Plan de Asignación para 20 Pares

### Estrategia General

```python
PAIRS = [
    'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT',
    'DOGE/USDT', 'MATIC/USDT', 'DOT/USDT', 'LINK/USDT', 'UNI/USDT',
    'ATOM/USDT', 'AVAX/USDT', 'LTC/USDT', 'ETC/USDT', 'FIL/USDT',
    'APT/USDT', 'ARB/USDT', 'OP/USDT', 'INJ/USDT', 'SUI/USDT'
]  # BTC EXCLUIDO

DAYS_HISTORICAL = 730  # 2 años
```

### Requests Totales por Entrenamiento Completo

| API | Requests por Par | Total (20 pares) | Límite Diario | ¿Viable? |
|-----|-----------------|------------------|---------------|----------|
| **Binance OHLCV** | 3 (15m, 1h, 4h) | 60 | 2400/min | ✅ Sí |
| **NewsAPI** | 5 | 100 | 100 | ⚠️ Justo en límite |
| **CryptoPanic** | 5 | 100 | ~1000 | ✅ Sí |
| **Coinglass** | 2 (OI + FR) | 40 | ??? | ⚠️ Requiere key |
| **DefiLlama** | 1 total | 1 | Sin límite | ✅ Sí |
| **CryptoQuant** | 1 | 20 | ??? | ⚠️ Requiere key |
| **Glassnode** | 1 | 20 | 10 | ❌ No (usar fallback) |

**Total estimado**: ~320 requests (si tienes todas las API keys)

---

## 🔧 Modificaciones Necesarias en el Código

### 1. `sentiment_fetcher.py`

```python
# Línea ~81 - MODIFICAR fetch_news_newsapi()
def fetch_news_newsapi(self, query: str = "ethereum", max_results: int = 5):  # Era 50
    """
    Descarga noticias de NewsAPI

    LÍMITE CRÍTICO: 100 requests/día
    Para 20 pares: 5 noticias × 20 = 100 requests
    """
    # ... rest of code
```

### 2. `coinglass_fetcher.py`

```python
# Agregar manejo de múltiples símbolos
def fetch_open_interest_history(self, symbol: str = "ETH", days: int = 730):
    """
    NOTA: Coinglass usa símbolos SIN /USDT
    ETH/USDT → ETH
    SOL/USDT → SOL
    """
    # ... existing code
```

### 3. Crear `train_multiple_pairs.py` (NUEVO)

```python
#!/usr/bin/env python3
"""
Entrenamiento Multi-Par
Descarga datos y entrena modelo con 20 pares
"""

import asyncio
from pathlib import Path
from data_manager import DataManager
from feature_engineer import FeatureEngineer
import pandas as pd
import logging

logger = logging.getLogger(__name__)

PAIRS = [
    'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT',
    'DOGE/USDT', 'MATIC/USDT', 'DOT/USDT', 'LINK/USDT', 'UNI/USDT',
    'ATOM/USDT', 'AVAX/USDT', 'LTC/USDT', 'ETC/USDT', 'FIL/USDT',
    'APT/USDT', 'ARB/USDT', 'OP/USDT', 'INJ/USDT', 'SUI/USDT'
]

async def download_data_for_pair(symbol: str, days: int = 730):
    """Descarga datos para un par específico"""
    logger.info(f"📥 Descargando datos para {symbol}...")

    # Implementar descarga
    # - OHLCV (Binance)
    # - Sentiment (5 noticias de NewsAPI + CryptoPanic)
    # - Derivatives (si hay API key)
    # - On-chain (si hay API key, sino simulado)

    # Guardar en data/raw/{symbol}_730d.csv
    pass

async def main():
    """Descarga datos de los 20 pares"""

    logger.info("="*80)
    logger.info("INICIANDO DESCARGA DE DATOS PARA 20 PARES")
    logger.info("="*80)

    for i, symbol in enumerate(PAIRS, 1):
        logger.info(f"\n[{i}/20] Procesando {symbol}...")

        try:
            await download_data_for_pair(symbol, days=730)

            # Rate limiting (respetar APIs)
            await asyncio.sleep(2)  # 2s entre pares

        except Exception as e:
            logger.error(f"❌ Error en {symbol}: {e}")
            continue

    logger.info("\n✅ Descarga completada para todos los pares")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## ⚠️ Limitaciones Identificadas

### 1. NewsAPI - Histórico Limitado
- **Problema**: Free tier solo permite 28 días de histórico
- **Impacto**: No podemos obtener 730 días de noticias
- **Solución**:
  - Entrenar con datos de sentiment solo de últimos 28 días
  - Usar features de sentiment como opcional (NaN para datos antiguos)
  - Considerar upgrade a plan PRO ($449/mes) si sentiment es crítico

### 2. Glassnode - Free Tier Insuficiente
- **Problema**: Solo 10 requests/día
- **Impacto**: No alcanza para 20 pares
- **Solución**: Usar CryptoQuant o datos simulados

### 3. Coinglass - API Key Requerida
- **Problema**: Sin API key solo hay datos simulados
- **Impacto**: Features de derivatives no serán reales
- **Solución**:
  - Registrarse en Coinglass (free tier disponible)
  - O entrenar sin features de derivatives (eliminar 3 features)

---

## 🎯 Recomendación Final

### Opción A: Con API Keys Mínimas (RECOMENDADO)

**APIs necesarias**:
- ✅ Binance (gratis, sin key para datos públicos)
- ✅ CryptoPanic (gratis con registro)
- ✅ NewsAPI (gratis, 100 req/día) → 5 noticias/par
- ⚠️ Coinglass (gratis con registro) → OI + Funding Rate
- ✅ DefiLlama (gratis, sin key)

**Total de features**: 96
**Datos históricos**: 730 días (excepto news: solo 28 días)
**Tiempo de descarga**: ~30-45 minutos para 20 pares

### Opción B: Solo Datos Técnicos (Sin APIs Externas)

**APIs necesarias**:
- ✅ Binance solamente

**Total de features**: ~80 (sin derivatives, sentiment, stablecoins)
**Datos históricos**: 730 días completos
**Tiempo de descarga**: ~5-10 minutos

---

## 📝 Próximos Pasos

1. **Decidir qué API keys obtener** (recomiendo Opción A)
2. **Modificar `sentiment_fetcher.py`** para límite de 5 noticias/par
3. **Crear `train_multiple_pairs.py`** para loop de descarga
4. **Modificar `data_manager.py`** para soportar múltiples símbolos
5. **Entrenar modelo único** con columna `symbol` como feature adicional
6. **Actualizar `daily_signals.py`** para usar modelo multi-par

¿Quieres que implemente el script de descarga multi-par ahora?
