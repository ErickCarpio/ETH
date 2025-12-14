# FASE 2 - STATUS ACTUAL

## 🎯 Objetivo de Fase 2
Agregar features de derivados en tiempo real y microestructura avanzada
- Meta: 124 features totales (de 44 base)
- Accuracy esperada: 65-70%

---

## ✅ COMPLETADO (70%)

### 1. Derivatives Data Streaming

**DerivativesDataManager** (`data/managers/derivatives_manager.py`)
- ✅ Funding Rate WebSocket (mark price stream @1s)
  - Tracking de cambios en funding rate
  - MA(10), std, delta calculation
  - Trend detection (bullish/bearish/neutral)

- ✅ Liquidations Streaming (forceOrder stream)
  - Real-time liquidation events
  - Side tracking (long vs short liquidations)
  - Volume, notional, price tracking
  - 5-minute window aggregations

- ✅ Open Interest Polling (cada 30s)
  - Current OI tracking
  - Delta calculation
  - Trend detection (increasing/decreasing/stable)

**Features de Derivados (14 features):**
```python
{
    'funding_rate': float,
    'funding_rate_ma_10': float,
    'funding_rate_std_10': float,
    'funding_rate_delta': float,
    'funding_rate_trend': str,  # bullish/bearish/neutral

    'liq_count_5m': int,
    'liq_volume_5m': float,
    'liq_notional_5m': float,
    'liq_long_pct': float,
    'liq_short_pct': float,
    'liq_imbalance': float,  # +1 = all longs, -1 = all shorts

    'oi': float,
    'oi_delta': float,
    'oi_delta_pct': float,
    'oi_trend': str  # increasing/decreasing/stable
}
```

### 2. Advanced Microstructure Features

**MicrostructureFeatures** (`microstructure/features.py`) - Nuevas funciones:

- ✅ **Trade Flow Toxicity** (Easley et al. 2012)
  - Mide reversión de precio post-trade
  - Indica información adversa en el trade
  - Window: últimos 50 trades

- ✅ **Realized Spread**
  - Separa adverse selection de liquidity provision
  - Calcula spread real vs. efectivo
  - Window: últimos 20 trades

- ✅ **Quote Intensity**
  - Actualizaciones del order book por segundo
  - Detecta quote stuffing / manipulación
  - Indica alta volatilidad esperada

- ✅ **Order Arrival Rate**
  - Trades por minuto
  - Detecta eventos de noticias
  - Indica probabilidad de informed trading

- ✅ **Price Impact Estimation**
  - Simula market order de 1 ETH
  - Calcula slippage en bps
  - Walk-through del order book

**Features Microestructurales Avanzadas (5 features):**
```python
{
    'trade_flow_toxicity': float,
    'realized_spread': float,
    'quote_intensity': float,  # quotes/sec
    'order_arrival_rate': float,  # trades/min
    'price_impact_1eth': float  # bps
}
```

### 3. QuestDB Storage

**QuestDBStorage** (`data/storage/questdb_storage.py`) - Nuevas tablas:

- ✅ `funding_rates` table
  - timestamp, symbol, funding_rate, funding_rate_delta, mark_price
  - Particionado por día

- ✅ `liquidations` table
  - timestamp, symbol, side, quantity, price, avg_price, notional
  - Particionado por día

- ✅ `open_interest` table
  - timestamp, symbol, oi, oi_delta, oi_delta_pct
  - Particionado por día

**Batch Insert Support:**
- ✅ `insert_funding_rate()`
- ✅ `insert_liquidation()`
- ✅ `insert_open_interest()`
- ✅ Flush automático al alcanzar batch_size (1000 rows)

### 4. Data Collection

**collect_derivatives.py** - Nuevo collector script
- ✅ Integra DerivativesDataManager + QuestDB
- ✅ Stats printing cada 10 segundos
- ✅ Callbacks para todos los eventos
- ✅ Graceful shutdown con Ctrl+C
- ✅ Funciona sin QuestDB (solo monitoring)

**Uso:**
```bash
python collect_derivatives.py
# Déjalo corriendo 24h para datos óptimos
```

---

## ⏳ PENDIENTE (30%)

### 1. Integración con Feature Engineering

**Necesario:**
- [ ] Modificar `feature_engineering.py` para agregar columna `derivatives_df`
- [ ] Resample derivatives features de 1s/30s a 4h
- [ ] Merge con otras features en el DataFrame principal
- [ ] Handle missing data (derivados pueden tener gaps)

**Código ejemplo:**
```python
def build_full_features(self, crypto_df, macro_df, onchain_df=None,
                       sentiment_df=None, defillama_df=None,
                       coinglass_df=None, microstructure_df=None,
                       derivatives_df=None):  # NUEVO

    # Resample derivatives a 4h
    if derivatives_df is not None:
        deriv_res = derivatives_df.resample('4h').agg({
            'funding_rate': 'last',
            'funding_rate_ma_10': 'last',
            'liq_count_5m': 'sum',
            'liq_volume_5m': 'sum',
            'oi': 'last',
            'oi_delta': 'sum'
        })
        # Merge con df principal
```

### 2. Data Manager Integration

**Necesario:**
- [ ] Modificar `data_manager.py` para cargar derivatives data desde QuestDB
- [ ] Fallback a archivo parquet si QuestDB no disponible
- [ ] Time-range queries para historical data

**Código ejemplo:**
```python
# En DataManager.load_datasets()
if self.questdb_storage:
    derivatives_df = self.load_derivatives_from_questdb(symbol, start_date, end_date)
else:
    # Fallback a archivo
    derivatives_file = self.data_dir / f"derivatives_{symbol}.parquet"
    if derivatives_file.exists():
        derivatives_df = pd.read_parquet(derivatives_file)
```

### 3. Main Orchestrator Integration

**Necesario:**
- [ ] Modificar `main_orchestrator.py` para pasar `derivatives_df`
- [ ] Handle caso donde derivatives_df está vacío (backward compatibility)

### 4. Testing

**Necesario:**
- [ ] Test script similar a `test_phase1.py` pero para derivatives
- [ ] Verificar que todos los streams funcionan
- [ ] Verificar que QuestDB guarda correctamente
- [ ] Test end-to-end con entrenamiento del modelo

---

## 📊 FEATURES TOTALES DISPONIBLES

### Breakdown por categoría:

| Categoría | Features | Status |
|-----------|----------|--------|
| Base (Fase 0) | 30 | ✅ |
| Microestructura Básica (Fase 1) | 14 | ✅ |
| Microestructura Avanzada (Fase 2) | 5 | ✅ |
| Derivados (Fase 2) | 14 | ✅ |
| **TOTAL ACTUAL** | **63** | **✅** |
| Meta Fase 2 | 124 | 🟡 70% |

### Features faltantes para completar Fase 2:

1. **GEX (Gamma Exposure)** - 5 features
   - Requiere datos de opciones de Binance
   - Gamma total, GEX por strike, volatility skew

2. **Advanced Ratios** - 8 features
   - OI/Volume ratio
   - Funding/OI ratio
   - Liquidation/Volume ratio
   - Term structure spreads

3. **Cross-asset Features** - 10 features
   - BTC/ETH correlation
   - Funding rate spreads
   - OI ratio BTC/ETH

4. **Statistical Features** - 24 features
   - Rolling statistics sobre derivados
   - Volatility clustering
   - Regime detection

---

## 🚀 PRÓXIMOS PASOS

### Opción A: Completar Fase 2 (30% restante)
**Tiempo estimado:** 1-2 semanas
**Resultado:** 124 features, 65-70% accuracy

**Tareas:**
1. Integrar con feature_engineering.py
2. Integrar con data_manager.py
3. Implementar GEX features
4. Implementar ratios avanzados
5. Testing completo

### Opción B: Saltar a Fase 4 (tsfresh)
**Tiempo estimado:** 1 semana
**Resultado:** 163 features (63 actuales + 100 tsfresh), 68-72% accuracy

**Ventajas:**
- Mejor ROI (más features en menos tiempo)
- tsfresh genera features automáticamente
- Feature selection incluido

**Tareas:**
1. Integrar Phase 2 actual (solo lo completado)
2. Instalar tsfresh
3. Configurar feature extraction
4. Feature selection
5. Testing

---

## 📝 RECOMENDACIÓN

**Integrar lo que tenemos ahora (63 features) y evaluar:**

1. **Completar integración** (1-2 días):
   - feature_engineering.py
   - data_manager.py
   - main_orchestrator.py

2. **Entrenar y evaluar** (1 día):
   - Ver si llegamos a 62-65% accuracy con 63 features

3. **Decidir según resultados:**
   - Si accuracy > 63%: Saltar a Fase 4 (tsfresh)
   - Si accuracy < 63%: Completar Fase 2 (GEX, ratios)

**Razón:** No tiene sentido gastar 2 semanas más en Fase 2 si con tsfresh podemos obtener mejores resultados en 1 semana.

---

## 🎯 META FINAL

- **Fase 1+2 actual:** 63 features → 62-65% accuracy (estimado)
- **Fase 1+2 completa:** 124 features → 65-70% accuracy
- **Fase 1+2+4 (tsfresh):** 224 features → 70-74% accuracy
- **Todas las fases:** 460+ features → 76-78% accuracy

**Timeline realista:**
- Integrar actual: 2 días
- Evaluar: 1 día
- Fase 4 (tsfresh): 1 semana
- **Total a 70-74%: 2 semanas** ⚡
