# 🔍 AUDITORÍA COMPLETA: Datos Reales vs Simulados

## ❌ FEATURES A ELIMINAR (Datos Simulados/Inexistentes)

### Phase 1: Microstructure (19 features) - **TODAS SIMULADAS**
**Problema:** Calculadas sobre datos que NO EXISTEN (no tenemos order book real)

| Feature | Razón para Eliminar |
|---------|-------------------|
| `obi_5_mean`, `obi_5_std` | No tenemos order book depth 5 niveles |
| `obi_20_mean`, `obi_20_std` | No tenemos order book depth 20 niveles |
| `obi_5_momentum`, `obi_5_regime` | Derivadas de OBI inexistente |
| `vpin_mean`, `vpin_std`, `vpin_trend` | VPIN requiere BVC (Bulk Volume Classification) sobre trades tick-by-tick |
| `vpin_regime`, `vpin_volume_sync` | Derivadas de VPIN inexistente |
| `spread_bps_mean`, `spread_bps_std` | No tenemos bid-ask spread real |
| `spread_bps_min`, `spread_bps_max` | No tenemos bid-ask spread real |
| `relative_spread` | No tenemos bid-ask spread real |
| `total_bid_depth`, `total_ask_depth` | No tenemos order book depth |
| `depth_imbalance` | No tenemos order book depth |
| `obi_returns_divergence` | Derivada de OBI inexistente (Phase 5) |

**Total a eliminar:** 19 features (Phase 1) + derivadas en Phase 5

---

### Phase 2: Derivatives - **PARCIALMENTE REAL**

#### ✅ MANTENER (Datos REALES disponibles):

Estas features SÍ tienen datos reales si los collectors están corriendo:

| Feature | Fuente Real | Estado |
|---------|-------------|--------|
| `funding_rate_last`, `funding_rate_ma_10` | Binance Futures API | ✅ REAL |
| `funding_rate_std_10`, `funding_rate_delta_sum` | Binance Futures API | ✅ REAL |
| `funding_rate_trend` | Calculado sobre funding real | ✅ REAL |
| `oi_last`, `oi_delta_sum` | Binance Futures API | ✅ REAL |
| `oi_delta_pct_mean`, `oi_trend` | Binance Futures API | ✅ REAL |
| `liq_count_5m_sum`, `liq_volume_5m_sum` | Binance Futures WebSocket | ✅ REAL |
| `liq_notional_5m_sum` | Binance Futures WebSocket | ✅ REAL |
| `liq_long_pct_mean`, `liq_short_pct_mean` | Binance Futures WebSocket | ✅ REAL |
| `liq_imbalance_mean` | Calculado sobre liquidaciones reales | ✅ REAL |

**Condición:** Requiere que `collect_derivatives.py` esté corriendo y poblando QuestDB.

#### ⚠️ VERIFICAR (Pueden ser reales si hay datos):

| Feature | Requiere | Estado |
|---------|----------|--------|
| `funding_vol_24h`, `funding_autocorr` | 24h+ de datos funding | ⚠️ Depende |
| `oi_autocorr`, `oi_vol_24h` | 24h+ de datos OI | ⚠️ Depende |
| `liq_intensity`, `liq_clustering` | Datos agregados liquidaciones | ⚠️ Depende |

---

### Phase 3: Statistical - **TODAS REALES** ✅

Estas features se calculan sobre precio/volumen de CCXT (datos reales):

- ✅ Skewness, Kurtosis (returns, volume)
- ✅ Autocorrelation
- ✅ Volatility clustering
- ✅ Volume profile
- ✅ Support/Resistance detection

**Total: 27 features - MANTENER**

---

### Phase 4: tsfresh-inspired - **TODAS REALES** ✅

Calculadas sobre precio/volumen real:

- ✅ Change quantiles
- ✅ Regime persistence
- ✅ Complexity measures (ApEn, Benford)

**Total: 20 features - MANTENER**

---

### Phase 5: Interactions - **PARCIALMENTE REAL**

#### ❌ ELIMINAR (Dependen de microstructure simulada):

```python
# Microstructure × Price (5 features)
'obi_returns_sync'           # OBI no existe
'obi_returns_divergence'     # OBI no existe
'vpin_vol_stress'            # VPIN no existe
'spread_volume_impact'       # Spread no existe
'depth_returns_momentum'     # Depth no existe

# Ratios con microstructure (3 features)
'obi_depth_ratio'            # OBI no existe
'spread_vol_ratio'           # Spread no existe

# Conditional features (2 features)
'resistance_rejection'       # Usa OBI no existente

# Cross-feature products (1 feature)
'support_conviction'         # Usa OBI no existente

# Polynomial features (1 feature)
'obi_squared'                # OBI no existe
```

**Total a eliminar:** ~12 features de Phase 5

#### ✅ MANTENER (Dependen de datos reales):

```python
# Momentum × Volatility (3 features)
'momentum_vol_interaction'
'returns_volatility_ratio'
'rsi_vol_interaction'

# Derivatives × Price (4 features) - SI HAY DATOS DERIVATIVES
'funding_returns_carry'
'funding_returns_divergence'
'liq_price_confirmation'
'oi_volume_buildup'

# Ratios importantes (4 features)
'volume_trend_ratio'
'volatility_expansion'
'liq_long_short_ratio'

# Polynomial (2 features)
'returns_squared_interaction'
'funding_squared'

# Regime-based (4 features)
'regime_low_vol_up', 'regime_low_vol_down'
'regime_high_vol_up', 'regime_high_vol_down'

# Composite indicators (3 features)
'momentum_composite'
'liquidity_stress_composite'  # ELIMINAR si usa VPIN
'leverage_risk_composite'
```

**Total a mantener:** ~20-25 features (dependiendo de derivatives data)

---

### Phase 6: Ensemble - **MANTENER** ✅

El ensemble es válido independientemente de las features (solo necesita features reales).

---

## 📊 RESUMEN EJECUTIVO

| Phase | Features Originales | Features REALES | Features a ELIMINAR |
|-------|---------------------|-----------------|---------------------|
| **Phase 0 (Base)** | 30 | 30 ✅ | 0 |
| **Phase 1 (Microstructure)** | 19 | 0 ❌ | **19** |
| **Phase 2 (Derivatives)** | 43 | ~30-40 ⚠️ | ~3-13 (depende datos) |
| **Phase 3 (Statistical)** | 27 | 27 ✅ | 0 |
| **Phase 4 (tsfresh)** | 20 | 20 ✅ | 0 |
| **Phase 5 (Interactions)** | 37 | ~25 ⚠️ | **~12** |
| **Phase 6 (Ensemble)** | N/A | N/A ✅ | 0 |
| **TOTAL** | **176** | **~132-142** | **~34-44** |

---

## ✅ FEATURES REALES CONFIRMADAS (~130-140 total)

### 1. Base Features (30) - CCXT Data
- ✅ OHLCV (open, high, low, close, volume)
- ✅ Returns, log_returns
- ✅ Volatility (6h, 12h, 24h, 72h)
- ✅ RSI, ATR
- ✅ BTC Dominance (macro)

### 2. Statistical Features (27) - Calculadas sobre CCXT
- ✅ Skewness, Kurtosis (returns, volume)
- ✅ Autocorrelation
- ✅ Volatility clustering, GARCH proxy
- ✅ Volume profile, momentum
- ✅ Support/Resistance detection

### 3. tsfresh-inspired (20) - Calculadas sobre CCXT
- ✅ Change quantiles
- ✅ Regime persistence (longest strike above mean)
- ✅ Complexity measures (ApEn, Benford)
- ✅ Linear trend slope & R²

### 4. Derivatives Features (~30-40) - **SI `collect_derivatives.py` está corriendo**
- ✅ Funding rate (last, MA, std, delta, trend)
- ✅ Open Interest (last, delta, pct, trend)
- ✅ Liquidations (count, volume, notional, long/short %, imbalance)
- ⚠️ Requiere 24h+ de datos para features avanzadas

### 5. Feature Interactions (~20-25)
- ✅ Momentum × Volatility (3)
- ✅ Derivatives × Price (4) - si hay derivatives data
- ✅ Important ratios (4)
- ✅ Regime-based (4)
- ✅ Polynomial (2)
- ✅ Composite indicators (2-3)

### 6. Optional Real Data (si configuradas)
- ⚠️ On-chain (Glassnode/CryptoQuant) - requiere API key
- ⚠️ Sentiment (NewsAPI) - ya implementado
- ⚠️ DefiLlama (TVL, stablecoin flows) - ya implementado

---

## 🚨 DATOS FALTANTES CRÍTICOS (Para Features Institucionales)

Para llegar a 400+ features REALES necesitamos:

### 1. WebSocket Order Book L2 (FASE 1 del plan original)
**Habilita:**
- ✅ OBI real (Order Book Imbalance) - 6 features
- ✅ Depth imbalance - 3 features
- ✅ Spread metrics - 5 features
- ✅ Micro-price (Stoikov) - 4 features
- ✅ OFI (Order Flow Imbalance) - 8 features
- **Total: +26 features reales**

### 2. Trades Tick-by-Tick (FASE 1)
**Habilita:**
- ✅ VPIN real (Volume-Synchronized PIN) - 5 features
- ✅ BVC (Bulk Volume Classification) - 3 features
- ✅ Trade flow analysis - 4 features
- **Total: +12 features reales**

### 3. Deribit Options Chain (FASE 3)
**Habilita:**
- ✅ GEX (Gamma Exposure) total - 1 feature
- ✅ GEX by strike (distribution) - 8 features
- ✅ Implied volatility skew - 6 features
- ✅ Put/Call ratio - 4 features
- ✅ Max pain calculation - 3 features
- **Total: +22 features reales**

### 4. Advanced Statistical (FASE 4)
**Habilita:**
- ✅ Hurst exponent (3 windows) - 3 features
- ✅ Spectral entropy - 4 features
- ✅ Kalman filter (price, residuals, prediction) - 8 features
- ✅ Wavelets/FFT (frequency bands) - 20 features
- **Total: +35 features reales**

### 5. tsfresh Auto-Generation (FASE 5)
**Habilita:**
- ✅ 800+ features auto-generadas → top 100 filtradas
- **Total: +100 features reales**

---

## 🎯 PLAN DE ACCIÓN

### Estado Actual Real:
- **~130-140 features reales** (si derivatives collector está corriendo)
- **Accuracy esperada:** 70-74% (vs 55% baseline)

### Para llegar a sistema institucional:
- **Necesitamos:** FASE 1-5 del plan original
- **Features reales finales:** ~330-400 features
- **Accuracy esperada:** 76-82%

---

## 📋 DECISIÓN REQUERIDA

¿Qué hacemos?

**OPCIÓN A: Limpiar y usar solo lo real actual (~130 features)**
- Eliminar 34-44 features simuladas
- Entrenar con ~130 features reales
- Probar accuracy (esperado: 70-74%)
- Tiempo: 1-2 días

**OPCIÓN B: Construir infraestructura real (FASE 1-5)**
- Implementar WebSocket + Order Book
- Implementar todos los collectors reales
- Llegar a 330-400 features reales
- Tiempo: 6-8 semanas

**OPCIÓN C: Híbrido - Quick wins primero**
- Limpiar features simuladas (Opción A)
- Implementar FASE 4 (estadística avanzada) - no requiere WebSocket
- ~130 + 35 = 165 features reales
- Tiempo: 1-2 semanas

---

**Mi recomendación:**

**OPCIÓN C** (Híbrido):
1. Esta semana: Limpiar features simuladas, probar con ~130 features reales
2. Próximas 2 semanas: FASE 4 (Hurst, Kalman, Wavelets) → +35 features
3. Si accuracy < 75%: Implementar FASE 1-2 (WebSocket + Microstructure real)

¿Cuál prefieres?
