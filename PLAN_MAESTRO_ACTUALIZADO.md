# 📋 PLAN MAESTRO ACTUALIZADO - SOLO DATOS REALES
**Fecha:** 2024-12-14
**Filosofía:** "If we don't have real data, we don't use the feature"

---

## 🔍 AUDITORÍA COMPLETA - LO QUE YA EXISTE

### ✅ INFRAESTRUCTURA REAL-TIME (FASE 1) - **90% COMPLETA**

#### WebSocket & Order Book
| Componente | Archivo | Estado | Funcionalidad |
|------------|---------|--------|---------------|
| **WebSocket Manager** | `data/managers/websocket_manager.py` | ✅ EXISTE | Conexiones persistentes, auto-reconexión, heartbeat |
| **Order Book Reconstructor** | `data/managers/orderbook_reconstructor.py` | ✅ EXISTE | Sincronización L2, validación de secuencia |
| **Realtime Data Manager** | `data/managers/realtime_data_manager.py` | ✅ EXISTE | Orquestador completo de WebSocket + Features |
| **Rate Limiter** | `data/managers/rate_limiter.py` | ✅ EXISTE | Token bucket, múltiples APIs |

#### Microstructure Calculators (REALES)
| Componente | Archivo | Estado | Features |
|------------|---------|--------|----------|
| **Microstructure Features** | `microstructure/features.py` | ✅ EXISTE | OBI, VPIN, OFI, Kyle's Lambda, Roll Spread, Micro-price |
| **OBI Calculator** | `features/microstructure/order_book_features.py` | ✅ EXISTE | Order Book Imbalance multi-nivel |
| **VPIN Calculator** | `features/microstructure/vpin_calculator.py` | ✅ EXISTE | Volume-synchronized PIN con BVC |
| **Micro-price** | `features/microstructure/micro_price_calculator.py` | ✅ EXISTE | Stoikov micro-price |

#### Storage
| Componente | Archivo | Estado | Funcionalidad |
|------------|---------|--------|---------------|
| **QuestDB Storage** | `data/storage/questdb_storage.py` | ✅ EXISTE | Time-series DB, inserción/queries |
| **QuestDB Connector** | `data/storage/questdb_connector.py` | ✅ EXISTE | Conexión low-level |

#### Collectors
| Componente | Archivo | Estado | Qué Colecta |
|------------|---------|--------|-------------|
| **Microstructure Collector** | `collect_microstructure.py` | ✅ EXISTE | Order book L2, Trades, Features microestructura |
| **Derivatives Collector** | `collect_derivatives.py` | ✅ EXISTE | Funding, Liquidaciones, Open Interest |
| **Historical Generator** | `generate_historical_microstructure.py` | ✅ EXISTE | Snapshots históricos (OBI, spread) |

---

### ✅ DERIVATIVES (FASE 3) - **80% COMPLETA**

| Componente | Archivo | Estado | Qué Colecta |
|------------|---------|--------|-------------|
| **Derivatives Manager** | `data/managers/derivatives_manager.py` | ✅ EXISTE | Funding rates, OI, Liquidaciones |
| **Derivatives Collector** | `collect_derivatives.py` | ✅ EXISTE | Stream real-time de Binance Futures |

**Features Disponibles (REALES):**
- Funding rates (mark price stream)
- Open Interest (polling 30s)
- Liquidaciones (WebSocket en vivo)

**Lo que FALTA:**
- ❌ Deribit GEX (Gamma Exposure de opciones)
- ❌ Funding cross-exchange (Binance vs Bybit)
- ❌ Advanced OI features (velocidad, percentiles)

---

### ✅ OTHER FETCHERS - **COMPLETOS**

| Componente | Archivo | Estado | Qué Trae |
|------------|---------|--------|----------|
| **DefiLlama** | `data/fetchers/defillama_fetcher.py` | ✅ EXISTE | TVL, Stablecoin flows |
| **Sentiment** | `data/fetchers/sentiment_fetcher.py` | ✅ EXISTE | NewsAPI, CryptoPanic |
| **On-chain** | `data/fetchers/onchain_data_fetcher.py` | ✅ EXISTE | Glassnode/CryptoQuant (requiere API key) |

---

### ❌ LO QUE FALTA COMPLETAMENTE

#### Fase 4: Estadística Avanzada (0% implementado)
- ❌ `features/statistical/hurst_calculator.py` - Exponente de Hurst
- ❌ `features/statistical/entropy_calculator.py` - Entropía espectral/aproximada
- ❌ `features/statistical/kalman_filter.py` - Filtro de Kalman
- ❌ `features/statistical/wavelet_features.py` - FFT, Wavelets

#### Fase 5: tsfresh Auto-generación (0% implementado)
- ❌ `features/automated/tsfresh_engine.py` - Motor tsfresh
- ❌ `features/automated/feature_selector.py` - Selección estadística

---

## 🚨 PROBLEMA CRÍTICO IDENTIFICADO

### El Problema: feature_engineering.py NO usa los datos reales

**Lo que eliminamos hoy:**
- 31 features "simuladas" de `feature_engineering.py`

**La realidad:**
- ✅ Los calculadores REALES existen (microstructure/features.py)
- ✅ Los collectors están guardando en QuestDB
- ❌ `feature_engineering.py` NO los estaba usando

**Conclusión:**
Eliminamos las features simuladas, pero la infraestructura REAL ya existe y funciona. Solo falta conectarla.

---

## 🎯 NUEVO PLAN DE IMPLEMENTACIÓN

### FASE 0: VALIDACIÓN Y CONEXIÓN (1-2 días) - **CRÍTICO**

#### 0.1. Verificar Collectors Funcionando
**Objetivo:** Confirmar que los collectors están corriendo y guardando datos

```bash
# Paso 1: Verificar QuestDB está corriendo
# Revisar si hay datos en las tablas

# Paso 2: Ejecutar collectors (si no están corriendo)
python collect_microstructure.py  # Dejar 1h mínimo
python collect_derivatives.py     # Dejar 24h mínimo

# Paso 3: Verificar datos en QuestDB
# Query: microstructure_features table
# Query: funding_rates table
# Query: liquidations table
```

**Criterios de éxito:**
- ✅ QuestDB tiene >100 rows en microstructure_features
- ✅ QuestDB tiene >1000 rows en funding_rates
- ✅ QuestDB tiene >50 rows en liquidations
- ✅ Collectors corren sin errores por >1 hora

#### 0.2. Conectar feature_engineering.py con Datos Reales
**Objetivo:** Modificar `feature_engineering.py` para cargar desde QuestDB

**Cambios necesarios:**

1. **En `data_manager.py`:**
   - Ya existe `load_microstructure_features()`
   - Ya existe `load_derivatives_features()`
   - ✅ Verificar que están funcionando

2. **En `feature_engineering.py`:**
   - Cambiar de microstructure_df (simulado) a datos REALES de QuestDB
   - Las 19 features microestructura se RECUPERAN (ahora con datos reales)
   - Las 12 features de interactions se RECUPERAN

**Resultado:**
- ~145 features → ~176 features (todas REALES)
- Accuracy esperada: 74-78% (vs 70-74% simulado)

---

### FASE 1: COMPLETAR MICROESTRUCTURA (3-5 días)

**Status:** 90% completo, solo falta integración

#### 1.1. Verificar Microstructure Features Working (1 día)
- ✅ `microstructure/features.py` tiene todos los calculadores
- ❓ Verificar que `collect_microstructure.py` los usa correctamente
- ❓ Verificar que se guardan en QuestDB correctamente

#### 1.2. Re-integrar en feature_engineering.py (1 día)
- Cargar microstructure_df desde QuestDB
- Resamplear de 10s (guardado) a 4h (features)
- Calcular agregaciones (mean, std, max, min, velocity)

#### 1.3. Testing (1 día)
- Verificar 19 features microestructura se calculan
- Verificar no hay NaN/inf
- Verificar correlación con precio

**Features recuperadas:** +19 microestructura REALES
- obi_5, obi_10, obi_20
- vpin, vpin_regime
- spread_bps, relative_spread
- micro_price
- kyle_lambda, roll_spread
- obi_divergence, vpin_regime, spread_widening

**Total features: ~145 + 19 = 164 features REALES**

---

### FASE 2: COMPLETAR DERIVATIVES (3-5 días)

**Status:** 80% completo, falta GEX y features avanzados

#### 2.1. Verificar Derivatives Collector (1 día)
- ✅ `collect_derivatives.py` ya existe
- ✅ Colecta funding, OI, liquidaciones
- ❓ Verificar datos en QuestDB

#### 2.2. Agregar Deribit GEX (2 días)

**NUEVO archivo:** `data/fetchers/deribit_fetcher.py`

**Funcionalidad:**
- GET /public/get_book_summary_by_currency?currency=ETH
- Calcular Greeks con py_vollib
- Agregar GEX total y por strike
- Guardar en QuestDB

**Features nuevas:** ~15
- gex_total, gex_call, gex_put
- gex_by_strike (distribution)
- iv_skew, put_call_ratio
- max_pain_price

#### 2.3. Advanced Derivatives Features (1 día)

**En `features/derivatives/` (NUEVO directorio):**

`funding_features.py`:
- funding_velocity (cambio 8h)
- funding_cross_exchange (Binance vs Bybit)
- funding_predicted_next

`liquidation_features.py`:
- liq_cluster_detection (>$1M in 1min)
- liq_cascade_risk
- liq_long_short_ratio

`oi_features.py`:
- oi_velocity (cambio por hora)
- oi_percentile_90d
- oi_divergence_spot

**Features nuevas:** ~20

**Total features: 164 + 15 (GEX) + 20 (advanced) = 199 features REALES**

---

### FASE 3: ESTADÍSTICA AVANZADA (1 semana)

**Status:** 0% implementado, pero es INDEPENDIENTE (no requiere WebSocket)

#### 3.1. Hurst Exponent (1-2 días)

**NUEVO archivo:** `features/statistical/hurst_calculator.py`

**Librería:** `nolds` (gratuita)

**Funcionalidad:**
```python
def calculate_hurst(prices, method='RS'):
    # R/S analysis para detectar mean reversion vs trending
    # H < 0.5 → mean reverting
    # H = 0.5 → random walk
    # H > 0.5 → trending

def calculate_hurst_rolling(prices, windows=[24,72,168]):
    # Hurst en ventanas móviles
```

**Features:** ~10
- hurst_24h, hurst_72h, hurst_7d
- hurst_velocity (cambio en memoria)
- regime_duration
- hurst_regime (mean_rev/random/trend)

#### 3.2. Entropy Measures (2 días)

**NUEVO archivo:** `features/statistical/entropy_calculator.py`

**Librería:** `antropy` (gratuita)

**Funcionalidad:**
```python
def spectral_entropy(returns):
    # Complejidad en dominio de frecuencia

def approximate_entropy(returns, m=2, r=0.2):
    # ApEn - predecibilidad de la serie

def sample_entropy(returns):
    # SampEn - estructura repetible

def permutation_entropy(returns, order=3):
    # PermEn - orden secuencial
```

**Features:** ~15
- spectral_entropy_24h, spectral_entropy_72h
- approx_entropy_24h
- sample_entropy_24h
- perm_entropy_24h

#### 3.3. Kalman Filter (2 días)

**NUEVO archivo:** `features/statistical/kalman_filter.py`

**Librería:** `filterpy` (gratuita)

**Funcionalidad:**
```python
class KalmanPriceFilter:
    def __init__(self, initial_price):
        # Inicializar filtro

    def update(self, new_price):
        # Actualizar con nueva medición

    def get_filtered_price(self):
        # Precio filtrado (estado verdadero)

    def get_residuals(self):
        # Residuales (precio real - filtrado)

    def get_prediction(self):
        # Predicción próximo precio
```

**Features:** ~12
- kalman_filtered_price
- kalman_residual (distancia real vs filtrado)
- kalman_residual_std
- kalman_gain (confianza)
- kalman_prediction_next

#### 3.4. Wavelets & FFT (2 días)

**NUEVO archivo:** `features/statistical/wavelet_features.py`

**Librería:** `pywt` (gratuita)

**Funcionalidad:**
```python
def calculate_fft(prices, n_coefs=20):
    # Fast Fourier Transform
    # Descompone precio en frecuencias

def calculate_cwt(prices, scales=np.arange(1,128)):
    # Continuous Wavelet Transform
    # Análisis tiempo-frecuencia

def get_dominant_frequencies(fft_result):
    # Top 5 frecuencias dominantes

def energy_by_band(cwt_result):
    # Energía en bandas de frecuencia
```

**Features:** ~25
- fft_coef_1 a fft_coef_10 (top 10 coeficientes)
- dominant_freq_1, dominant_freq_2, dominant_freq_3
- wavelet_energy_high, wavelet_energy_mid, wavelet_energy_low
- wavelet_entropy

**Total features FASE 3:** ~62

**Total acumulado: 199 + 62 = 261 features REALES**

---

### FASE 4: tsfresh AUTO-GENERACIÓN (1 semana)

**Status:** 0% implementado

#### 4.1. tsfresh Engine (3 días)

**NUEVO archivo:** `features/automated/tsfresh_engine.py`

**Librería:** `tsfresh` (gratuita)

**Funcionalidad:**
```python
from tsfresh.feature_extraction import EfficientFCParameters, extract_features
from tsfresh.feature_selection import select_features

class TsfreshEngine:
    def __init__(self, mode='efficient'):
        # 'efficient' = ~250 features/serie
        # 'comprehensive' = ~800 features/serie

    def extract_from_series(self, df, column_id, column_sort, column_value):
        # Extrae features automáticamente

    def select_relevant(self, features, target):
        # Filtra features significativas
```

**Series a procesar:**
1. close (precio)
2. volume
3. returns
4. volatility_24h
5. obi_5 (si disponible)
6. vpin (si disponible)
7. funding_rate (si disponible)

**Configuración:** EfficientFCParameters
- ~250 features por serie
- 7 series × 250 = **1,750 features brutas**

#### 4.2. Feature Selector (2 días)

**NUEVO archivo:** `features/automated/feature_selector.py`

**Funcionalidad:**
```python
class StatisticalFeatureSelector:
    def __init__(self, alpha=0.05, max_corr=0.95):
        # alpha: p-value threshold
        # max_corr: correlation threshold

    def select_significant(self, features, target):
        # Test de hipótesis
        # Benjamini-Hochberg correction

    def remove_redundant(self, features):
        # Elimina features correlacionadas >0.95

    def rank_by_importance(self, features, target):
        # Ranking final por importancia
```

**Pipeline:**
1. Extraer 1,750 features con tsfresh
2. Test de significancia → Descartar p > 0.05
3. Eliminar redundantes (corr > 0.95)
4. Ranking por importancia
5. Top 100 features elite

**Features seleccionadas:** +100 (de 1,750)

**Total acumulado: 261 + 100 = 361 features REALES**

---

### FASE 5: ENSEMBLE (Ya completo) ✅

**Status:** 100% implementado (Phase 6 ya hecho)

- ✅ XGBoost, LightGBM, CatBoost, RandomForest
- ✅ Simple Average, Weighted Voting, Stacking
- ✅ main_orchestrator_ensemble.py

**Funciona con cualquier número de features.**

---

## 📊 RESUMEN DE FEATURES - ROADMAP COMPLETO

| Fase | Features | Tipo de Datos | Estado |
|------|----------|---------------|--------|
| **Fase 0: Base (Ya existe)** | 30 | CCXT OHLCV | ✅ COMPLETO |
| **Fase 0.1: Conexión** | +19 | Microestructura REAL (QuestDB) | ⚠️ PENDIENTE CONECTAR |
| **Fase 0.2: Interactions** | +12 | Basadas en microestructura real | ⚠️ PENDIENTE CONECTAR |
| **Fase 1: Microestructura (verificar)** | 0 | Ya en Fase 0.1 | ✅ EXISTE, FALTA CONECTAR |
| **Fase 2: Derivatives Advanced** | +35 | GEX (Deribit) + Advanced features | ❌ FALTA IMPLEMENTAR |
| **Fase 3: Estadística Avanzada** | +62 | Hurst, Entropy, Kalman, Wavelets | ❌ FALTA IMPLEMENTAR |
| **Fase 4: tsfresh** | +100 | Auto-generación + selección | ❌ FALTA IMPLEMENTAR |
| **Fase 5: Ensemble** | N/A | Ya implementado | ✅ COMPLETO |
| **TOTAL** | **~258-358** | **100% DATOS REALES** | **60% completo** |

---

## 🎯 PRIORIDADES Y TIMELINE

### SEMANA 1: VALIDACIÓN Y CONEXIÓN (CRÍTICO)
**Días 1-2: Fase 0 - Validar infraestructura existente**
- Verificar collectors corriendo
- Verificar datos en QuestDB
- Conectar feature_engineering.py con datos reales
- **Resultado:** 176 features REALES (vs 145 actuales)

**Días 3-5: Fase 1 - Completar microestructura**
- Testing de features microestructura
- Verificar calidad de datos
- **Resultado:** Confirmar 19 features microestructura funcionan

### SEMANA 2: DERIVATIVES AVANZADOS
**Días 1-3: Implementar Deribit GEX**
- Nuevo fetcher
- Cálculo de Greeks
- Storage en QuestDB

**Días 4-5: Advanced derivatives features**
- Funding velocity, cross-exchange
- Liquidation clusters
- OI advanced

**Resultado:** +35 features → Total: 211 features REALES

### SEMANA 3: ESTADÍSTICA AVANZADA
**Días 1-2: Hurst + Entropy**
- hurst_calculator.py
- entropy_calculator.py
- **+25 features**

**Días 3-5: Kalman + Wavelets**
- kalman_filter.py
- wavelet_features.py
- **+37 features**

**Resultado:** +62 features → Total: 273 features REALES

### SEMANA 4: tsfresh + INTEGRACIÓN
**Días 1-3: tsfresh engine**
- tsfresh_engine.py
- Auto-generación 1,750 features

**Días 4-5: Feature selection**
- feature_selector.py
- Selección top 100
- **+100 features**

**Resultado:** +100 features → Total: **373 features REALES**

**Días 6-7: Testing end-to-end**
- Re-entrenar ensemble con ~373 features
- Validar accuracy >75%
- Backtest

---

## ✅ CRITERIOS DE ÉXITO

### Fase 0 (Fin Semana 1):
- ✅ Collectors corriendo >24h sin errores
- ✅ QuestDB con >10,000 rows microestructura
- ✅ feature_engineering.py carga datos reales
- ✅ 176 features REALES funcionando
- ✅ Accuracy: 74-76% (baseline real)

### Fase 2 (Fin Semana 2):
- ✅ GEX de Deribit calculándose
- ✅ 211 features REALES
- ✅ Accuracy: 75-77%

### Fase 3 (Fin Semana 3):
- ✅ Hurst, Kalman, Wavelets funcionando
- ✅ 273 features REALES
- ✅ Accuracy: 76-78%

### Fase 4 (Fin Semana 4):
- ✅ tsfresh generando 1,750 features
- ✅ Top 100 seleccionadas
- ✅ 373 features REALES en producción
- ✅ Accuracy: **77-80%**
- ✅ Sistema completo end-to-end

---

## 🚨 RIESGOS Y MITIGACIONES

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Collectors no tienen datos | Media | Correr collectors 24h antes de continuar |
| QuestDB vacío/corrupto | Baja | Backup diario, re-colectar si necesario |
| Microestructura features con bugs | Media | Testing exhaustivo en Fase 0 |
| tsfresh muy lento | Alta | Usar EfficientFCParameters, no ComprehensiveFCParameters |
| Overfitting con 373 features | Alta | Feature selection agresivo, regularización L1/L2 |

---

## 📋 CHECKLIST ANTES DE EMPEZAR

### Verificar Infraestructura:
- [ ] QuestDB instalado y corriendo
- [ ] `collect_microstructure.py` funciona sin errores
- [ ] `collect_derivatives.py` funciona sin errores
- [ ] `microstructure/features.py` calcula OBI, VPIN correctamente
- [ ] QuestDB tiene tablas: microstructure_features, funding_rates, liquidations
- [ ] QuestDB tiene >100 rows en cada tabla

### Verificar Librerías:
- [ ] `pip install nolds` (Hurst)
- [ ] `pip install antropy` (Entropy)
- [ ] `pip install filterpy` (Kalman)
- [ ] `pip install pywt` (Wavelets)
- [ ] `pip install tsfresh` (Auto-features)
- [ ] `pip install py_vollib` (Greeks para GEX)

### Verificar Código:
- [ ] `feature_engineering.py` limpio (sin features simuladas)
- [ ] `data_manager.py` tiene load_microstructure_features()
- [ ] `ensemble_trainer.py` funcionando

---

## 🎯 PRÓXIMO PASO INMEDIATO

**ACCIÓN 1: Verificar Collectors (HOY)**
```bash
# Terminal 1
python collect_microstructure.py

# Terminal 2
python collect_derivatives.py

# Esperar 10 minutos, luego verificar QuestDB
```

**ACCIÓN 2: Verificar Datos en QuestDB (HOY)**
```python
from data.storage.questdb_storage import QuestDBStorage
storage = QuestDBStorage()

# Check microstructure
df_micro = storage.read_microstructure_features('ETHUSDT', '2024-12-14', '2024-12-15')
print(f"Microstructure rows: {len(df_micro)}")

# Check derivatives
df_funding = storage.read_funding_rates('ETHUSDT', '2024-12-14', '2024-12-15')
print(f"Funding rows: {len(df_funding)}")
```

**ACCIÓN 3: Si hay datos → Conectar feature_engineering.py (MAÑANA)**
**ACCIÓN 4: Si NO hay datos → Dejar collectors corriendo 24h, luego continuar**

---

**Estado Final Esperado:**
- ✅ ~373 features 100% REALES
- ✅ Accuracy: 77-80%
- ✅ Sistema institucional completo
- ✅ 0% datos simulados
- ✅ Timeline: 4 semanas
