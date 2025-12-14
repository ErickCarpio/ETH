# FASE 1: Infraestructura de Datos en Tiempo Real ✅

## Resumen

Implementación completa de la infraestructura base para datos de mercado en tiempo real y cálculo de features microestructurales institucionales.

## Componentes Implementados

### 1. WebSocket Manager (`data/managers/websocket_manager.py`)
Gestor de conexiones persistentes con Binance WebSocket API

**Características:**
- ✅ Auto-reconexión con exponential backoff
- ✅ Buffer de eventos durante reconexión (max 1000 eventos)
- ✅ Heartbeat/Pong automático (ping_interval=20s, timeout=10s)
- ✅ Manejo de múltiples streams simultáneos
- ✅ Callbacks async para procesamiento de datos
- ✅ Health monitoring (tiempo desde último mensaje, contadores de errores)

**Clases:**
- `WebSocketManager`: Manager genérico para cualquier stream
- `DepthStreamManager`: Especializado para order book depth streams
- `TradeStreamManager`: Especializado para trade streams

**Ejemplo de uso:**
```python
manager = DepthStreamManager()
await manager.connect_depth('ethusdt', callback, update_speed='100ms')
```

### 2. Order Book L2 Reconstructor (`data/managers/orderbook_reconstructor.py`)
Reconstruye y mantiene order book L2 sincronizado con Binance

**Características:**
- ✅ Protocolo completo de sincronización de Binance
- ✅ Buffer de eventos pre-snapshot
- ✅ Validación de secuencia de updates (U/u fields)
- ✅ Detección y recuperación de desincronización
- ✅ Cálculo de microstructure features básicas (OBI, spread, micro-price)

**Features calculadas:**
- Best bid/ask (precio + cantidad)
- Spread absoluto y mid-price
- **Micro-price** (precio ponderado por volumen L1)
- **OBI (Order Book Imbalance)** en niveles 5, 10, 20
- **Weighted mid-price** (promedio ponderado por volumen)
- Depth statistics (volumen agregado por niveles)

**Ejemplo de uso:**
```python
reconstructor = OrderBookReconstructor('ETHUSDT')
await reconstructor.initialize()  # Fetch snapshot inicial
await reconstructor.process_depth_update(event)  # Procesar deltas
orderbook = reconstructor.get_orderbook()
print(orderbook.get_micro_price())
```

### 3. Rate Limiter Universal (`data/managers/rate_limiter.py`)
Control de rate limits con sliding window algorithm

**Características:**
- ✅ Sliding window rate limiting
- ✅ Múltiples límites por fuente (ej: 1200/min + 100/10s)
- ✅ Safety margin configurable (default 90% del límite)
- ✅ Backoff automático cuando se acerca al límite
- ✅ Métricas de uso por fuente
- ✅ Configuraciones predefinidas (Binance, Coinglass, DefiLlama)

**Ejemplo de uso:**
```python
limiter = MultiSourceRateLimiter()
limiter.add_source("binance", create_binance_limiter().limits)
await limiter.acquire("binance", endpoint="/api/v3/ticker")
```

### 4. QuestDB Storage (`data/storage/questdb_storage.py`)
Almacenamiento de time-series en QuestDB

**Características:**
- ✅ Batch inserts (max 1000 rows por batch)
- ✅ Auto-creación de tablas
- ✅ Particionamiento por día
- ✅ Queries optimizadas para agregaciones

**Tablas creadas:**
- `orderbook_snapshots`: Snapshots de order book cada 10s
- `microstructure_features`: Features calculadas (VPIN, OFI, etc.)
- `trades`: Trades individuales

**Ejemplo de uso:**
```python
storage = QuestDBStorage(host="localhost", port=8812)
storage.initialize_tables()
storage.insert_orderbook_snapshot(snapshot_dict)
storage.flush_all_batches()
```

### 5. Microstructure Features Calculator (`microstructure/features.py`)
Cálculo de features institucionales avanzadas

**Features implementadas:**
- ✅ **OBI (Order Book Imbalance)** en múltiples niveles
- ✅ **OFI (Order Flow Imbalance)** - flujo neto de órdenes
- ✅ **VPIN** (Volume-Synchronized Probability of Informed Trading)
- ✅ **Micro-price** (precio ponderado por volumen)
- ✅ **Roll Spread** (bid-ask bounce measure)
- ✅ **Kyle's Lambda** (permanent price impact estimate)
- ✅ **Effective Spread** por trade

**Ejemplo de uso:**
```python
calc = MicrostructureFeatures('ETHUSDT')
calc.add_orderbook_snapshot(orderbook_dict)
calc.add_trade(trade_dict)
features = calc.get_all_features(current_orderbook)
print(features['vpin'])  # 0.0 - 1.0
```

### 6. Realtime Data Manager (`data/managers/realtime_data_manager.py`)
**Orquestador principal** que integra todos los componentes

**Características:**
- ✅ Integra WebSocket + Order Book + Features + Storage
- ✅ Streaming de datos en tiempo real
- ✅ Cálculo automático de features cada 1 segundo (cada 10 depth updates)
- ✅ Almacenamiento periódico en QuestDB (cada 10s)
- ✅ Sistema de callbacks para features calculadas
- ✅ Health monitoring y estadísticas completas

**Ejemplo de uso:**
```python
manager = RealtimeDataManager(
    symbol="ETHUSDT",
    enable_storage=True,
    enable_trades=True
)

# Registrar callback para recibir features
async def on_features(features):
    print(f"OBI: {features['obi_5']}, VPIN: {features['vpin']}")

manager.register_feature_callback(on_features)

# Iniciar
await manager.start()

# Obtener features actuales
features = manager.get_current_features()

# Ver estadísticas
stats = manager.get_stats()
print(f"Updates/sec: {stats['depth_updates_per_sec']}")
```

## Estructura de Archivos

```
ETH/
├── data/
│   ├── __init__.py
│   ├── managers/
│   │   ├── __init__.py
│   │   ├── websocket_manager.py          # WebSocket connections
│   │   ├── orderbook_reconstructor.py    # Order Book L2
│   │   ├── rate_limiter.py               # Rate limiting
│   │   └── realtime_data_manager.py      # Orquestador principal
│   └── storage/
│       ├── __init__.py
│       └── questdb_storage.py            # QuestDB integration
├── microstructure/
│   ├── __init__.py
│   └── features.py                       # VPIN, OFI, OBI, etc.
├── requirements.txt                       # Actualizado con dependencias
└── PHASE1_README.md                      # Este archivo
```

## Dependencias Agregadas

```
websockets>=12.0          # WebSocket client
psycopg2-binary>=2.9.0    # QuestDB connection
aiohttp>=3.9.0            # Async HTTP client
asyncio-throttle>=1.0.0   # Rate limiting
```

## Instalación

```bash
pip install -r requirements.txt
```

**Opcional - QuestDB:**
```bash
# Descargar QuestDB
wget https://github.com/questdb/questdb/releases/download/7.3.0/questdb-7.3.0-rt-linux-amd64.tar.gz
tar -xvf questdb-7.3.0-rt-linux-amd64.tar.gz
cd questdb-7.3.0-rt-linux-amd64

# Iniciar
./bin/questdb.sh start

# UI disponible en: http://localhost:9000
# PostgreSQL wire protocol en: localhost:8812
```

## Testing

### Test básico de componentes individuales:
```python
# Test WebSocket Manager
python data/managers/websocket_manager.py

# Test Order Book Reconstructor
python data/managers/orderbook_reconstructor.py

# Test Rate Limiter
python data/managers/rate_limiter.py

# Test QuestDB Storage (requiere QuestDB corriendo)
python data/storage/questdb_storage.py

# Test Microstructure Features
python microstructure/features.py
```

### Test integración completa:
```python
python data/managers/realtime_data_manager.py
```

## Features Microestructurales - Explicación

### OBI (Order Book Imbalance)
Mide el desequilibrio de volumen entre bids y asks.
- **Fórmula:** `(bid_volume - ask_volume) / (bid_volume + ask_volume)`
- **Rango:** [-1, 1]
- **Interpretación:**
  - OBI > 0: Presión compradora
  - OBI < 0: Presión vendedora
  - OBI ≈ 0: Equilibrio

### OFI (Order Flow Imbalance)
Mide el **flujo neto** de órdenes (cambios en volumen).
- **Fórmula:** `Σ(ΔBid_volume) - Σ(ΔAsk_volume)`
- **Interpretación:**
  - OFI > 0: Flujo de compra dominante
  - OFI < 0: Flujo de venta dominante

### VPIN (Volume-Synchronized Probability of Informed Trading)
Estima la probabilidad de que haya traders informados activos.
- **Fórmula:** `Σ|V_buy - V_sell| / Σ V_total` (sobre buckets de volumen)
- **Rango:** [0, 1]
- **Interpretación:**
  - VPIN > 0.5: Alta probabilidad de trading informado (alguien sabe algo)
  - VPIN < 0.3: Trading normal
  - **Usado por:** traders institucionales para detectar flujos tóxicos

### Micro-price
Precio ponderado por volumen en L1 (mejor bid/ask).
- **Fórmula:** `(bid_price * ask_qty + ask_price * bid_qty) / (bid_qty + ask_qty)`
- **Ventaja vs mid-price:** Refleja la dirección esperada del próximo trade

### Kyle's Lambda
Mide el price impact **permanente** de un trade.
- **Fórmula:** `λ = Cov(ΔP, V_signed) / Var(V_signed)`
- **Interpretación:** Por cada unidad de volumen comprado, ¿cuánto sube el precio permanentemente?
- **Usado por:** market makers para pricing y algorithmic execution

### Roll Spread
Estima el spread efectivo desde la covarianza de cambios de precio.
- **Fórmula:** `2 * sqrt(-Cov(ΔP_t, ΔP_{t-1}))`
- **Ventaja:** No requiere conocer las transacciones, solo precios

## Próximos Pasos - Fase 2

- [ ] Implementar features adicionales de microstructure:
  - Trade flow toxicity (Easley et al. 2012)
  - Realized spread
  - Price impact measures
  - Trade intensity (Poisson model)

- [ ] Integrar datos de derivados en tiempo real:
  - Funding rate (vía WebSocket)
  - Open Interest deltas
  - Liquidaciones en tiempo real

- [ ] Conectar features calculadas al sistema de trading existente:
  - Modificar `feature_engineering.py` para usar `RealtimeDataManager`
  - Agregar features microestructurales al modelo XGBoost
  - Backtesting con features de QuestDB

## Métricas de Performance Esperadas

**Con Binance WebSocket a 100ms:**
- Depth updates: ~10/segundo
- Latencia de procesamiento: <10ms
- Features calculadas: 1/segundo (cada 10 updates)
- Storage: Batch de 1000 rows cada ~100 segundos

**Recursos:**
- CPU: <5% (un core)
- RAM: ~100MB (buffers + order book)
- Network: ~50 KB/s (WebSocket)

## Referencias

1. Easley, D., López de Prado, M. M., & O'Hara, M. (2012). "Flow Toxicity and Liquidity in a High Frequency World"
2. Cont, R., Kukanov, A., & Stoikov, S. (2014). "The Price Impact of Order Book Events"
3. Kyle, A. S. (1985). "Continuous Auctions and Insider Trading"
4. Roll, R. (1984). "A Simple Implicit Measure of the Effective Bid-Ask Spread"

---

**Status:** ✅ Fase 1 Completada

**Próxima Fase:** Fase 2 - Features avanzadas + Derivados en tiempo real
