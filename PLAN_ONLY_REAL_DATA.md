# 🎯 PLAN: SOLO DATOS REALES - Sin Simulaciones

## Filosofía: "If we don't have real data, we don't use the feature"

---

## FASE 0: LIMPIEZA INMEDIATA (1-2 días)

### Objetivo:
Eliminar TODAS las features basadas en datos simulados/inexistentes

### Features a ELIMINAR:

#### 1. Phase 1 Microstructure (19 features) - NO HAY ORDER BOOK REAL
```python
# EN feature_engineering.py - ELIMINAR BLOQUE COMPLETO:
Lines ~367-428: Bloque microstructure_df

Features a eliminar:
- obi_5_mean, obi_5_std
- obi_20_mean, obi_20_std
- obi_5_momentum, obi_5_regime
- vpin_mean, vpin_std, vpin_trend
- vpin_regime, vpin_volume_sync
- spread_bps_mean, spread_bps_std, spread_bps_min, spread_bps_max
- relative_spread
- total_bid_depth, total_ask_depth
- depth_imbalance
```

#### 2. Phase 5 Interactions que usan microstructure (12 features)
```python
# EN feature_engineering.py - ELIMINAR:
Lines ~650-670: Microstructure × Price interactions

Features a eliminar:
- obi_returns_sync
- obi_returns_divergence
- vpin_vol_stress
- spread_volume_impact
- obi_depth_ratio
- spread_vol_ratio
- resistance_rejection
- support_conviction
- obi_squared
- distribution_risk (usa VPIN)
- liquidity_stress_composite (usa VPIN + spread)
```

### ✅ Features a MANTENER (~130-140):

**Phase 0 - Base (30):**
- ✅ OHLCV, returns, log_returns
- ✅ Volatility (6h, 12h, 24h, 72h)
- ✅ RSI, ATR
- ✅ BTC Dominance

**Phase 2 - Derivatives (30-40):**
- ✅ Funding rate features (SI `collect_derivatives.py` corriendo)
- ✅ Open Interest features
- ✅ Liquidations features

**Phase 3 - Statistical (27):**
- ✅ Skewness, Kurtosis
- ✅ Autocorrelation
- ✅ Volatility clustering
- ✅ Volume profile
- ✅ Support/Resistance

**Phase 4 - tsfresh (20):**
- ✅ Change quantiles
- ✅ Regime persistence
- ✅ ApEn, Benford

**Phase 5 - Interactions (20-25):**
- ✅ Momentum × Volatility (3)
- ✅ Derivatives × Price (4) - si hay datos
- ✅ Important ratios (4)
- ✅ Regime-based (4)
- ✅ Polynomial (2)
- ✅ Momentum/leverage composites (2)

**Phase 6 - Ensemble:**
- ✅ Mantener (funciona con cualquier número de features)

---

## FASE 1: INFRAESTRUCTURA REAL-TIME (2 semanas)

### Objetivo:
Construir pipeline de datos tick-by-tick desde Binance WebSocket

### 1.1 WebSocket Manager (Semana 1, Días 1-3)

**Archivo:** `data/managers/websocket_manager.py`

**Funcionalidad:**
```python
class WebSocketManager:
    """
    Gestiona conexiones WebSocket persistentes con Binance

    APIs usadas (100% GRATIS):
    - wss://stream.binance.com:9443/ws/ethusdt@depth@100ms (Order Book)
    - wss://stream.binance.com:9443/ws/ethusdt@trade (Trades)
    - wss://fstream.binance.com/ws/!forceOrder@arr (Liquidaciones)
    """

    def __init__(self, symbols=['ETHUSDT']):
        self.connections = {}
        self.reconnect_delay = 1  # Exponential backoff
        self.max_reconnect_delay = 60

    async def connect(self, stream_name):
        """Establece conexión WebSocket"""

    async def subscribe(self, streams: list):
        """Suscribe a múltiples streams"""

    def on_message(self, callback):
        """Handler de mensajes entrantes"""

    async def reconnect(self, stream_name):
        """Auto-reconexión con backoff exponencial"""

    def health_check(self):
        """Verifica latencia y estado de conexión"""
```

**Streams a conectar:**
1. `ethusdt@depth@100ms` → Order Book updates cada 100ms
2. `ethusdt@trade` → Todos los trades en tiempo real
3. `!forceOrder@arr` (Futures) → Liquidaciones en vivo

**Criterios de éxito:**
- ✅ Conexión estable >24h sin caídas
- ✅ Latencia promedio <50ms
- ✅ 0% pérdida de mensajes durante reconexión
- ✅ Auto-reconexión funcional con backoff

---

### 1.2 Order Book Reconstructor (Semana 1, Días 4-7)

**Archivo:** `data/fetchers/orderbook_fetcher.py`

**Funcionalidad:**
```python
class OrderBookReconstructor:
    """
    Reconstruye order book L2 local en memoria

    Algoritmo Binance:
    1. Buffer eventos del WebSocket
    2. GET /api/v3/depth?symbol=ETHUSDT&limit=5000 (snapshot inicial)
    3. Descartar eventos con u <= lastUpdateId
    4. Aplicar eventos donde U <= lastUpdateId+1 AND u >= lastUpdateId+1
    5. Mantener dict: bids{price: qty}, asks{price: qty}
    6. Si qty=0 → eliminar nivel del book
    """

    def __init__(self):
        self.bids = {}  # {price: quantity}
        self.asks = {}
        self.last_update_id = 0
        self.is_synchronized = False

    async def initialize_book(self):
        """Obtiene snapshot inicial via REST"""
        url = "https://api.binance.com/api/v3/depth"
        params = {'symbol': 'ETHUSDT', 'limit': 5000}

    def apply_diff(self, event):
        """Aplica diff del WebSocket"""
        # Validar secuencia
        if event['U'] <= self.last_update_id + 1 and event['u'] >= self.last_update_id + 1:
            self._update_book(event['b'], self.bids)  # Update bids
            self._update_book(event['a'], self.asks)  # Update asks
            self.last_update_id = event['u']

    def _update_book(self, updates, book_side):
        """Actualiza un lado del book (bid o ask)"""
        for price, qty in updates:
            price_float = float(price)
            qty_float = float(qty)

            if qty_float == 0:
                book_side.pop(price_float, None)  # Remove
            else:
                book_side[price_float] = qty_float  # Update

    def get_book(self, depth=20):
        """Retorna top N niveles del book"""
        sorted_bids = sorted(self.bids.items(), reverse=True)[:depth]
        sorted_asks = sorted(self.asks.items())[:depth]

        return {
            'bids': sorted_bids,
            'asks': sorted_asks,
            'mid_price': (sorted_bids[0][0] + sorted_asks[0][0]) / 2
        }

    def validate_sequence(self):
        """Verifica integridad del book"""
        # Comparar con snapshot REST cada 5 min
```

**Criterios de éxito:**
- ✅ Book local idéntico al exchange (validar con REST)
- ✅ Latencia de actualización <10ms
- ✅ 0 gaps en secuencia de updates
- ✅ Manejo correcto de qty=0 (eliminar nivel)

---

### 1.3 Trades Aggregator (Semana 2, Días 1-2)

**Archivo:** `data/fetchers/trades_aggregator.py`

**Funcionalidad:**
```python
class TradesAggregator:
    """
    Agrega trades tick-by-tick en buckets de volumen para VPIN

    Stream: ethusdt@trade
    Output: Buckets de volumen constante (ej: 1000 ETH por bucket)
    """

    def __init__(self, bucket_size_eth=1000):
        self.bucket_size = bucket_size_eth
        self.current_bucket = []
        self.current_volume = 0
        self.completed_buckets = []

    def add_trade(self, trade):
        """Agrega trade al bucket actual"""
        self.current_bucket.append(trade)
        self.current_volume += trade['quantity']

        # Si bucket completo, cerrar y empezar nuevo
        if self.current_volume >= self.bucket_size:
            self.completed_buckets.append(self.current_bucket)
            self.current_bucket = []
            self.current_volume = 0

    def get_buckets(self, n=50):
        """Retorna últimos N buckets para VPIN"""
        return self.completed_buckets[-n:]
```

---

### 1.4 QuestDB Integration (Semana 2, Días 3-5)

**Archivo:** `data/storage/questdb_storage.py` (mejorar existente)

**Nuevas tablas:**

```sql
-- Order book snapshots (cada 1 segundo)
CREATE TABLE orderbook_snapshots (
    timestamp TIMESTAMP,
    symbol SYMBOL,
    bid_prices DOUBLE[],   -- Array de top 20 bid prices
    bid_vols DOUBLE[],     -- Array de top 20 bid volumes
    ask_prices DOUBLE[],
    ask_vols DOUBLE[],
    mid_price DOUBLE,
    spread_bps DOUBLE
) TIMESTAMP(timestamp) PARTITION BY DAY;

-- Trades tick-by-tick
CREATE TABLE trades (
    timestamp TIMESTAMP,
    symbol SYMBOL,
    price DOUBLE,
    quantity DOUBLE,
    is_buyer_maker BOOLEAN,  -- Para BVC classification
    trade_id LONG
) TIMESTAMP(timestamp) PARTITION BY HOUR;

-- Volume buckets (para VPIN)
CREATE TABLE volume_buckets (
    timestamp TIMESTAMP,
    symbol SYMBOL,
    bucket_id LONG,
    volume_buy DOUBLE,
    volume_sell DOUBLE,
    order_imbalance DOUBLE,
    trade_count INT
) TIMESTAMP(timestamp) PARTITION BY DAY;
```

**Funciones de ingesta:**
```python
class QuestDBStorage:

    async def insert_orderbook_snapshot(self, book):
        """Guarda snapshot del order book"""

    async def insert_trade(self, trade):
        """Guarda trade individual"""

    async def insert_volume_bucket(self, bucket):
        """Guarda bucket de volumen para VPIN"""

    async def query_obi(self, symbol, depth, window):
        """Calcula OBI histórico"""
        sql = f"""
        SELECT
            timestamp,
            (bid_vols[1:5] - ask_vols[1:5]) / (bid_vols[1:5] + ask_vols[1:5]) as obi_5
        FROM orderbook_snapshots
        WHERE symbol = '{symbol}'
        AND timestamp >= dateadd('h', -{window}, now())
        ORDER BY timestamp DESC
        """

    async def query_vpin(self, symbol, n_buckets):
        """Calcula VPIN desde buckets"""
        sql = f"""
        SELECT
            timestamp,
            avg(order_imbalance) as vpin
        FROM (
            SELECT * FROM volume_buckets
            WHERE symbol = '{symbol}'
            ORDER BY timestamp DESC
            LIMIT {n_buckets}
        )
        """
```

---

## FASE 2: FEATURES MICROESTRUCTURA REALES (2 semanas)

### Una vez tengamos WebSocket + Order Book funcionando, implementar:

### 2.1 Real OBI (Order Book Imbalance)

**Archivo:** `features/microstructure/order_book_features.py`

```python
def calculate_obi_real(book, levels=[1, 5, 10, 20]):
    """
    OBI real desde order book L2

    Args:
        book: Dict con 'bids' y 'asks' (top 20 niveles)
        levels: Profundidades a calcular OBI

    Returns:
        Dict con OBI_1, OBI_5, OBI_10, OBI_20
    """
    obi_features = {}

    for level in levels:
        bid_volume = sum([qty for price, qty in book['bids'][:level]])
        ask_volume = sum([qty for price, qty in book['asks'][:level]])

        obi = (bid_volume - ask_volume) / (bid_volume + ask_volume + 1e-8)
        obi_features[f'obi_{level}'] = obi

    return obi_features

def calculate_obi_weighted(book, decay=0.5):
    """
    OBI ponderado por distancia exponencial

    OBI_weighted = Σ(vol_i × e^(-λ×dist_i))_bid - Σ(...)_ask
                   ────────────────────────────────────────────
                          Σ(vol_i × e^(-λ×dist_i))_total
    """
    mid_price = book['mid_price']

    weighted_bid = 0
    weighted_ask = 0

    for price, qty in book['bids']:
        dist = (mid_price - price) / mid_price
        weight = qty * np.exp(-decay * dist)
        weighted_bid += weight

    for price, qty in book['asks']:
        dist = (price - mid_price) / mid_price
        weight = qty * np.exp(-decay * dist)
        weighted_ask += weight

    obi_weighted = (weighted_bid - weighted_ask) / (weighted_bid + weighted_ask + 1e-8)

    return obi_weighted
```

**Features generadas:** 6
- `obi_1_real`, `obi_5_real`, `obi_10_real`, `obi_20_real`
- `obi_weighted_real`
- `obi_velocity_real` (cambio en OBI/segundo)

---

### 2.2 Real VPIN (Volume-Synchronized PIN)

**Archivo:** `features/microstructure/vpin_calculator.py`

```python
def classify_volume_bvc(trades):
    """
    Bulk Volume Classification (Easley et al. 2012)

    Algoritmo:
    1. Calcular Z-score del cambio de precio
    2. Clasificar volumen usando CDF normal
    """
    from scipy.stats import norm

    classified_trades = []

    for i in range(1, len(trades)):
        # Cambio de precio
        delta_p = trades[i]['price'] - trades[i-1]['price']

        # Volatilidad reciente (últimos 100 trades)
        recent_deltas = [t['price'] - trades[max(0, j-1)]['price']
                        for j, t in enumerate(trades[max(0, i-100):i])]
        sigma = np.std(recent_deltas)

        # Z-score
        z = delta_p / (sigma + 1e-8)

        # Clasificar volumen
        phi_z = norm.cdf(z)  # CDF de normal estándar
        v_buy = trades[i]['quantity'] * phi_z
        v_sell = trades[i]['quantity'] * (1 - phi_z)

        classified_trades.append({
            'timestamp': trades[i]['timestamp'],
            'v_buy': v_buy,
            'v_sell': v_sell,
            'price': trades[i]['price']
        })

    return classified_trades

def calculate_vpin_real(buckets, n=50):
    """
    VPIN real desde buckets de volumen

    Args:
        buckets: Lista de buckets con volume_buy y volume_sell
        n: Número de buckets a promediar

    Returns:
        VPIN value [0, 1]
    """
    if len(buckets) < n:
        return np.nan

    recent_buckets = buckets[-n:]

    # Order Imbalance por bucket
    oi_values = []
    for bucket in recent_buckets:
        v_buy = bucket['volume_buy']
        v_sell = bucket['volume_sell']
        oi = abs(v_buy - v_sell) / (v_buy + v_sell + 1e-8)
        oi_values.append(oi)

    # VPIN = promedio de OI
    vpin = np.mean(oi_values)

    return vpin
```

**Features generadas:** 5
- `vpin_real` (VPIN calculado correctamente)
- `vpin_percentile_90d` (percentil histórico)
- `vpin_trend_1h` (tendencia de VPIN)
- `vpin_regime` (alto/bajo basado en percentil)
- `vpin_volume_sync` (VPIN × volumen)

---

### 2.3 Real Spread & Depth

**Archivo:** `features/microstructure/order_book_features.py`

```python
def calculate_spread_features(book):
    """
    Spread features desde order book real
    """
    best_bid = book['bids'][0][0]
    best_ask = book['asks'][0][0]
    mid_price = (best_bid + best_ask) / 2

    # Spread absoluto
    spread_abs = best_ask - best_bid

    # Spread en basis points
    spread_bps = (spread_abs / mid_price) * 10000

    # Spread relativo
    relative_spread = spread_abs / mid_price

    return {
        'spread_abs': spread_abs,
        'spread_bps': spread_bps,
        'relative_spread': relative_spread
    }

def calculate_depth_features(book, depth=20):
    """
    Depth features desde order book real
    """
    total_bid_depth = sum([qty for price, qty in book['bids'][:depth]])
    total_ask_depth = sum([qty for price, qty in book['asks'][:depth]])

    depth_imbalance = (total_bid_depth - total_ask_depth) / (total_bid_depth + total_ask_depth + 1e-8)

    return {
        'total_bid_depth': total_bid_depth,
        'total_ask_depth': total_ask_depth,
        'depth_imbalance': depth_imbalance
    }
```

**Features generadas:** 6
- `spread_abs`, `spread_bps`, `relative_spread`
- `total_bid_depth`, `total_ask_depth`, `depth_imbalance`

---

### 2.4 Micro-Price (Stoikov)

**Archivo:** `features/microstructure/micro_price_calculator.py`

```python
def calculate_micro_price(book):
    """
    Micro-precio de Stoikov (mejor estimador del precio verdadero)

    Formula:
    micro_price = (bid_vol × ask_price + ask_vol × bid_price) / (bid_vol + ask_vol)
    """
    best_bid_price = book['bids'][0][0]
    best_ask_price = book['asks'][0][0]
    best_bid_vol = book['bids'][0][1]
    best_ask_vol = book['asks'][0][1]

    micro_price = (
        (best_bid_vol * best_ask_price + best_ask_vol * best_bid_price) /
        (best_bid_vol + best_ask_vol + 1e-8)
    )

    mid_price = (best_bid_price + best_ask_price) / 2

    # Ajuste del micro-precio vs mid-price
    micro_adj = (micro_price - mid_price) / (mid_price + 1e-8)

    return {
        'micro_price': micro_price,
        'micro_price_adj': micro_adj
    }
```

**Features generadas:** 2
- `micro_price` (precio verdadero estimado)
- `micro_price_adj` (ajuste vs mid-price)

---

## RESUMEN DE FEATURES REALES FINALES

### Después de Limpieza (FASE 0):
- **~130-140 features** (eliminando las 31-44 simuladas)

### Después de FASE 1-2 (WebSocket + Microestructura Real):
- **~130 existentes + 19 nuevas microestructura = ~150 features REALES**

### Features Microestructura Reales (19):
1. OBI real (6): `obi_1_real`, `obi_5_real`, `obi_10_real`, `obi_20_real`, `obi_weighted_real`, `obi_velocity_real`
2. VPIN real (5): `vpin_real`, `vpin_percentile_90d`, `vpin_trend_1h`, `vpin_regime`, `vpin_volume_sync`
3. Spread (3): `spread_abs`, `spread_bps`, `relative_spread`
4. Depth (3): `total_bid_depth`, `total_ask_depth`, `depth_imbalance`
5. Micro-price (2): `micro_price`, `micro_price_adj`

---

## CRONOGRAMA COMPLETO

### Semana 1: Limpieza + WebSocket
- **Días 1-2:** Limpiar features simuladas, probar con ~130 features reales
- **Días 3-5:** WebSocket Manager + conexiones persistentes
- **Días 6-7:** Order Book Reconstructor básico

### Semana 2: Order Book + QuestDB
- **Días 1-2:** Trades Aggregator + BVC classification
- **Días 3-4:** QuestDB nuevas tablas + ingesta
- **Días 5:** Validación WebSocket 24h estable

### Semana 3-4: Features Microestructura Reales
- **Días 1-2:** OBI real (6 features)
- **Días 3-5:** VPIN real (5 features)
- **Días 6-7:** Spread, Depth, Micro-price (8 features)

### Semana 4: Integración
- **Días 1-2:** Integrar nuevas features en `feature_engineering.py`
- **Días 3-4:** Re-entrenar ensemble con ~150 features reales
- **Días 5-7:** Validación y testing end-to-end

---

## MÉTRICAS DE ÉXITO

### Después de Limpieza (Semana 1):
- ✅ 0 features simuladas en el código
- ✅ ~130 features 100% reales
- ✅ Accuracy objetivo: 70-72% (baseline limpio)

### Después de FASE 1-2 (Semana 4):
- ✅ WebSocket estable 24/7
- ✅ Order Book sincronizado (0% error)
- ✅ 19 features microestructura REALES funcionando
- ✅ Accuracy objetivo: 74-77%

---

## ¿COMENZAMOS?

**Paso inmediato (HOY):**
1. Crear branch `cleanup-simulated-features`
2. Eliminar features simuladas de `feature_engineering.py`
3. Actualizar ensemble para funcionar con ~130 features
4. Probar training y validar accuracy baseline limpio

¿Procedo con la limpieza?
