# 🚀 GUÍA DE USO - Sistema de Trading ETH

## 📋 TABLA DE CONTENIDOS

1. [Inicio Rápido](#inicio-rápido)
2. [Estructura del Sistema](#estructura-del-sistema)
3. [Archivos Principales](#archivos-principales)
4. [Flujo de Trabajo](#flujo-de-trabajo)
5. [Configuración](#configuración)
6. [Ejecución](#ejecución)
7. [Troubleshooting](#troubleshooting)

---

## 🏃 INICIO RÁPIDO

### Opción 1: Sistema Completo (Recomendado)
```bash
# 1. Levantar QuestDB (base de datos)
docker run -p 9000:9000 -p 9009:9009 -p 8812:8812 \
  -v "$(pwd)/questdb_data:/var/lib/questdb" \
  questdb/questdb

# 2. En otra terminal, iniciar el sistema
python start_system.py
```

### Opción 2: Solo Recolección de Datos
```bash
# Recolectar datos de microestructura (Order Book, VPIN, OFI)
python collect_microstructure.py

# Recolectar datos de derivados (GEX, Funding, Liquidaciones)
python collect_derivatives.py
```

### Opción 3: Solo Entrenamiento
```bash
# Entrenar modelo con todas las features
python model_pipeline.py
```

---

## 🏗️ ESTRUCTURA DEL SISTEMA

```
ETH/
├── 🎯 ARCHIVOS PRINCIPALES (en root)
│   ├── start_system.py          → Inicia todo el sistema
│   ├── main_orchestrator.py     → Orquesta trading en vivo
│   ├── config_loader.py         → Carga configuración
│   ├── execution_bot.py         → Ejecuta trades
│   ├── feature_engineering.py   → Crea features para modelo
│   ├── model_pipeline.py        → Entrena modelo ML
│   ├── target_labeling.py       → Define targets (subida/bajada)
│   └── weighting_logic.py       → Pesos de muestras
│
├── 📊 data/ - DATOS EN TIEMPO REAL
│   ├── managers/                → Gestores de conexiones
│   │   ├── websocket_manager.py       → WebSocket Binance
│   │   ├── cache_manager.py           → Caché inteligente
│   │   ├── realtime_data_pipeline.py  → Pipeline principal
│   │   └── [otros managers...]
│   │
│   ├── fetchers/                → Obtención de datos
│   │   ├── orderbook_fetcher.py       → Order Book L2
│   │   ├── deribit_fetcher.py         → Opciones (GEX)
│   │   ├── liquidations_fetcher.py    → Liquidaciones
│   │   ├── defillama_fetcher.py       → TVL DeFi
│   │   └── sentiment_fetcher.py       → Sentiment news
│   │
│   └── storage/                 → Almacenamiento
│       └── questdb_connector.py       → QuestDB
│
├── 🧬 features/ - INGENIERÍA DE FEATURES
│   ├── microstructure/          → Order Book features
│   │   ├── order_book_processor.py    → OBI, spreads
│   │   ├── vpin_calculator.py         → Toxicidad flujo
│   │   ├── ofi_calculator.py          → Order Flow Imbalance
│   │   └── microprice_calculator.py   → Micro-precio Stoikov
│   │
│   ├── derivatives/             → Features derivados
│   │   ├── gex_calculator.py          → Gamma Exposure
│   │   ├── funding_features.py        → Funding rates
│   │   └── liquidation_features.py    → Liquidaciones
│   │
│   ├── statistical/             → Features estadísticos
│   │   ├── hurst_calculator.py        → Memoria de mercado
│   │   ├── entropy_calculator.py      → Complejidad
│   │   ├── kalman_filter.py           → Filtro Kalman
│   │   └── wavelet_features.py        → Wavelets
│   │
│   └── automated/               → Auto-generación
│       ├── tsfresh_engine.py          → Motor tsfresh
│       └── feature_selector.py        → Selección estadística
│
├── 🧪 tests/ - TESTING
│   ├── test_feature_engineering.py
│   ├── test_tsfresh.py
│   └── test_model_performance.py
│
└── 🔧 utils/ - UTILIDADES
    └── rate_limiter.py

OTROS ARCHIVOS ÚTILES (root):
├── coinglass_fetcher.py         → Fetcher Coinglass (OI, Funding)
├── ensemble_trainer.py          → Entrenamiento ensemble
├── collect_microstructure.py    → Script recolección microestructura
├── collect_derivatives.py       → Script recolección derivados
└── verify_questdb.py            → Verificar QuestDB funciona
```

---

## 📂 ARCHIVOS PRINCIPALES

### 🎯 start_system.py
**Qué hace:** Inicia TODO el sistema (trading en vivo)

**Cuándo usar:**
- Quieres hacer trading automático
- Ya tienes el modelo entrenado
- QuestDB corriendo

**Cómo funciona:**
```python
1. Carga configuración (config_loader.py)
2. Inicia main_orchestrator.py
3. Ejecuta ciclo de trading:
   - Recolecta datos cada 4h
   - Calcula features
   - Hace predicción con modelo
   - Ejecuta trade si confianza > umbral
```

**Ejecutar:**
```bash
python start_system.py
```

---

### 🎼 main_orchestrator.py
**Qué hace:** Orquestador principal del trading

**Componentes:**
- Lee datos históricos (Binance OHLCV cada 4h)
- Llama a `feature_engineering.py` para crear features
- Carga modelo entrenado
- Hace predicción (UP/DOWN)
- Llama a `execution_bot.py` si predicción fuerte

**No ejecutar directamente** (lo llama `start_system.py`)

---

### ⚙️ config_loader.py
**Qué hace:** Carga configuración desde `config.json`

**Configuración típica:**
```json
{
  "binance_api_key": "tu_api_key",
  "binance_api_secret": "tu_secret",
  "symbol": "ETHUSDT",
  "prediction_threshold": 0.65,
  "position_size": 0.1,
  "use_testnet": true
}
```

---

### 🤖 execution_bot.py
**Qué hace:** Ejecuta trades en Binance

**Funciones:**
- `place_market_order(side, quantity)` → Market order
- `place_limit_order(side, price, quantity)` → Limit order
- `cancel_order(order_id)` → Cancela orden
- `get_position()` → Posición actual

**No ejecutar directamente** (lo llama `main_orchestrator.py`)

---

### 🧬 feature_engineering.py
**Qué hace:** Crea TODAS las features para el modelo

**Features que genera (~460 total):**

#### 1. Features Base (~30)
- Precio: close, returns, volatility
- Volumen: volume, volume_ma, volume_surge
- Technical: RSI, MACD, Bollinger Bands

#### 2. Features DeFi (~10)
- TVL de protocolos (via defillama_fetcher.py)
- Stablecoin flows
- DEX volumes

#### 3. Features Derivados (~15)
- Open Interest (via coinglass_fetcher.py)
- Funding rate
- Long/Short ratio

#### 4. Features On-Chain (~10)
- Exchange flows
- Whale movements

#### 5. Sentiment (~5)
- News sentiment
- Social metrics

#### 6. Features Microestructura (~150)
```python
# Solo si tienes datos de QuestDB
from features.microstructure import (
    order_book_processor,
    vpin_calculator,
    ofi_calculator,
    microprice_calculator
)

# Genera:
- OBI_L1, OBI_L5, OBI_L10, OBI_L20
- VPIN (toxicidad)
- OFI (order flow imbalance)
- Microprice, spreads
```

#### 7. Features Derivados Avanzados (~80)
```python
from features.derivatives import (
    gex_calculator,
    funding_features,
    liquidation_features
)

# Genera:
- GEX por strike (25 features)
- Funding dynamics (18 features)
- Liquidation clusters (15 features)
```

#### 8. Features Estadísticos (~100)
```python
from features.statistical import (
    hurst_calculator,
    entropy_calculator,
    kalman_filter,
    wavelet_features
)

# Genera:
- Hurst exponent (memoria)
- Entropías (complejidad)
- Kalman residuales
- Coeficientes wavelet/FFT
```

#### 9. Features Auto-Generadas (~100)
```python
from features.automated import tsfresh_engine

# tsfresh genera 1750+ features
# Luego selecciona top 100 estadísticamente
```

**Ejecutar standalone:**
```bash
python feature_engineering.py
# Genera DataFrame con todas las features
```

---

### 🤖 model_pipeline.py
**Qué hace:** Entrena modelo XGBoost con todas las features

**Proceso:**
```python
1. Carga datos históricos
2. Llama feature_engineering.py para generar features
3. Llama target_labeling.py para crear targets
4. Llama weighting_logic.py para ponderar muestras
5. Optimiza hiperparámetros con Optuna (2000 trials)
6. Entrena modelo final
7. Guarda modelo en models/xgboost_model.pkl
8. Genera reporte de performance
```

**Ejecutar:**
```bash
python model_pipeline.py

# Salida esperada:
# ✓ Features: 460
# ✓ Samples: 5000
# ✓ Accuracy: 72.3%
# ✓ F1-Score: 0.71
# ✓ Model saved to models/xgboost_model.pkl
```

**Tiempo estimado:** 2-6 horas (depende de Optuna trials)

---

### 🎯 target_labeling.py
**Qué hace:** Define qué es "éxito" (target del modelo)

**Estrategias disponibles:**
```python
# 1. Fixed Horizon (default)
# Target = 1 si precio sube >0.5% en próximas 4h
target = (close.shift(-1) / close - 1) > 0.005

# 2. Triple Barrier
# Usa stop-loss y take-profit
target = triple_barrier_method(prices, sl=0.02, tp=0.05)

# 3. Trend Following
# Target = 1 si tendencia alcista en próximas 12h
target = trend_based_labeling(prices, horizon=12)
```

**No ejecutar directamente** (lo llama `model_pipeline.py`)

---

### ⚖️ weighting_logic.py
**Qué hace:** Pondera muestras de entrenamiento

**Técnicas:**
```python
# 1. Time Decay (más peso a datos recientes)
weights = exponential_decay(timestamps, half_life=30)

# 2. Volatility Weighting (más peso en alta volatilidad)
weights = volatility_adjusted(returns, volatility)

# 3. Balanced (más peso a clase minoritaria)
weights = class_balancing(targets)
```

**No ejecutar directamente** (lo llama `model_pipeline.py`)

---

## 🔄 FLUJO DE TRABAJO TÍPICO

### Escenario 1: Primera Vez (Setup Inicial)

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Levantar QuestDB
docker run -p 9000:9000 -p 9009:9009 -p 8812:8812 \
  -v "$(pwd)/questdb_data:/var/lib/questdb" \
  questdb/questdb

# 3. Verificar QuestDB funciona
python verify_questdb.py

# 4. Recolectar datos iniciales (opcional)
python collect_microstructure.py  # 30 min para 24h de datos

# 5. Entrenar modelo
python model_pipeline.py  # 2-6 horas

# 6. Configurar API keys en config.json
{
  "binance_api_key": "TU_KEY",
  "binance_api_secret": "TU_SECRET"
}

# 7. Iniciar trading
python start_system.py
```

---

### Escenario 2: Re-entrenar Modelo (cada semana)

```bash
# 1. Modelo ya existe, solo re-entrenar con datos nuevos
python model_pipeline.py

# 2. Sistema usará nuevo modelo automáticamente
```

---

### Escenario 3: Solo Recolección de Datos (investigación)

```bash
# Recolectar microestructura para análisis
python collect_microstructure.py

# Ver datos en QuestDB UI
# Abrir http://localhost:9000
# SELECT * FROM orderbook_snapshots LIMIT 100;
```

---

### Escenario 4: Backtest (sin trading real)

```python
# Modificar main_orchestrator.py:
# Cambiar execute=True a execute=False

# Ejecutar
python start_system.py

# Verás predicciones pero NO ejecutará trades
```

---

## ⚙️ CONFIGURACIÓN

### config.json (crear en root)
```json
{
  "binance": {
    "api_key": "tu_api_key_aqui",
    "api_secret": "tu_secret_aqui",
    "testnet": true
  },

  "trading": {
    "symbol": "ETHUSDT",
    "position_size_usd": 100,
    "prediction_threshold": 0.65,
    "max_positions": 1,
    "use_stop_loss": true,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.05
  },

  "data": {
    "questdb_host": "localhost",
    "questdb_port": 9000,
    "use_cache": true,
    "cache_ttl_seconds": 60
  },

  "features": {
    "use_microstructure": true,
    "use_derivatives": true,
    "use_statistical": true,
    "use_tsfresh": true,
    "tsfresh_top_n": 100
  },

  "model": {
    "type": "xgboost",
    "model_path": "models/xgboost_model.pkl",
    "retrain_every_days": 7,
    "optuna_trials": 2000
  }
}
```

---

## 🚀 EJECUCIÓN

### Sistema Completo (Trading Automático)

```bash
# Terminal 1: QuestDB
docker run -p 9000:9000 -p 9009:9009 -p 8812:8812 \
  -v "$(pwd)/questdb_data:/var/lib/questdb" \
  questdb/questdb

# Terminal 2: Sistema de Trading
python start_system.py

# OUTPUT ESPERADO:
# =====================================
# 🚀 SISTEMA INICIADO
# =====================================
# ⏰ [2025-12-17 10:00:00] Recolectando datos...
# 📊 Features calculadas: 460
# 🤖 Predicción: UP (confianza: 72.3%)
# 💰 Ejecutando BUY 0.05 ETH @ $1,950
# =====================================
```

---

### Solo Entrenamiento

```bash
python model_pipeline.py

# Archivos generados:
# - models/xgboost_model.pkl (modelo)
# - models/feature_importance.csv (importancias)
# - models/training_report.txt (métricas)
```

---

### Solo Recolección de Datos

```bash
# Microestructura (Order Book, VPIN, OFI)
python collect_microstructure.py --hours 24

# Derivados (GEX, Funding, Liquidaciones)
python collect_derivatives.py --hours 24

# Ver en QuestDB: http://localhost:9000
```

---

## 🔧 TROUBLESHOOTING

### Error: "QuestDB not running"

```bash
# Verificar QuestDB
docker ps | grep questdb

# Si no está corriendo, iniciar
docker run -p 9000:9000 -p 9009:9009 -p 8812:8812 \
  -v "$(pwd)/questdb_data:/var/lib/questdb" \
  questdb/questdb
```

---

### Error: "No module named 'features'"

```bash
# Agregar ETH al PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/home/user/ETH"

# O ejecutar desde directorio ETH
cd /home/user/ETH
python start_system.py
```

---

### Error: "Rate limit exceeded"

```python
# Editar data/managers/cache_manager.py
# Aumentar TTL de cache:

DEFAULT_TTLS = {
    'gex': 600,  # 10 min en vez de 5 min
    'funding_rate': 43200,  # 12h en vez de 8h
}
```

---

### Error: "WebSocket disconnected"

```bash
# Automático: websocket_manager.py reconecta solo
# Si persiste, verificar firewall/internet

# Ver logs:
tail -f logs/websocket.log
```

---

### Warning: "Low accuracy (< 60%)"

```bash
# Re-entrenar con más datos
python model_pipeline.py

# O ajustar hiperparámetros en model_pipeline.py:
optuna_trials = 5000  # En vez de 2000
```

---

## 📊 MONITOREO

### Ver Predicciones en Vivo

```bash
# Logs del sistema
tail -f logs/orchestrator.log

# Ver solo predicciones
tail -f logs/orchestrator.log | grep "Predicción"
```

### Ver Datos en QuestDB

```bash
# Abrir UI: http://localhost:9000

# Queries útiles:
SELECT * FROM orderbook_snapshots
ORDER BY timestamp DESC
LIMIT 100;

SELECT
  timestamp,
  bid_prices[0] as best_bid,
  ask_prices[0] as best_ask
FROM orderbook_snapshots
WHERE timestamp > systimestamp() - 3600000000  -- Última hora
```

### Ver Performance del Modelo

```bash
python tests/test_model_performance.py

# Genera:
# - Accuracy por período
# - Confusion matrix
# - Feature importance
# - Profit simulation
```

---

## 🎯 PRÓXIMOS PASOS

### Nivel Principiante
1. ✅ Ejecutar `python verify_questdb.py`
2. ✅ Ejecutar `python model_pipeline.py` (entrenar)
3. ✅ Ejecutar `python start_system.py` (testnet)

### Nivel Intermedio
1. ✅ Colectar 7 días de microestructura
2. ✅ Re-entrenar modelo semanalmente
3. ✅ Ajustar `config.json` según performance

### Nivel Avanzado
1. ✅ Crear features personalizadas
2. ✅ Optimizar Optuna trials
3. ✅ Implementar ensemble de modelos
4. ✅ Trading en producción (NO testnet)

---

## 📞 AYUDA

**Ver logs:**
```bash
ls -lh logs/
tail -f logs/orchestrator.log
```

**Verificar features generadas:**
```python
from feature_engineering import generate_features
df = generate_features(symbol='ETHUSDT')
print(df.columns)  # Ver todas las features
print(df.shape)    # (filas, features)
```

**Testear componentes:**
```bash
python tests/test_feature_engineering.py
python tests/test_tsfresh.py
python tests/test_model_performance.py
```

---

## ✅ CHECKLIST DE INICIO

- [ ] QuestDB corriendo (`docker ps`)
- [ ] `config.json` creado con API keys
- [ ] Modelo entrenado (`models/xgboost_model.pkl` existe)
- [ ] Dependencies instaladas (`pip install -r requirements.txt`)
- [ ] PYTHONPATH configurado
- [ ] Testnet habilitado para pruebas
- [ ] Logs funcionando (`logs/` existe)

**¿Todo OK? → `python start_system.py`** 🚀
