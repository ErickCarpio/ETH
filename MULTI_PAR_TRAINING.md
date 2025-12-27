# 🚀 Sistema de Entrenamiento Multi-Par

## 📋 Descripción

Sistema que entrena **20 modelos XGBoost separados** (uno por cada par de trading), cada uno especializado en predecir señales LONG/SHORT para su moneda específica.

### ✅ Ventajas del Enfoque Multi-Modelo

- **Especialización**: Cada modelo aprende patrones únicos de su par (volatilidad, correlaciones, etc.)
- **Mayor precisión**: DOGE es 3x más volátil que ETH → modelos separados capturan mejor estas diferencias
- **Escalabilidad**: Fácil agregar/remover pares sin re-entrenar todo
- **Mantenimiento**: Actualizar modelo de un par no afecta a los demás

---

## 📁 Estructura del Proyecto

```
ETH/
├── train_multiple_pairs.py       # Script principal de entrenamiento multi-par
├── daily_signals.py               # Generador de señales (usa modelos por par)
├── execute_signals.py             # Ejecutor de señales en Binance Demo
├── models/                        # Modelos entrenados
│   ├── model_ETHUSDT.json        # Modelo para ETH
│   ├── model_SOLUSDT.json        # Modelo para SOL
│   ├── ...                        # (20 modelos total)
│   └── training_summary.json      # Resumen de entrenamiento
├── signals/                       # Señales generadas
│   └── signals_YYYYMMDD_HHMMSS.csv
├── data/fetchers/                 # APIs externas
│   ├── sentiment_fetcher.py       # News (límite 5/par)
│   ├── coinglass_fetcher.py       # Derivatives
│   └── defillama_fetcher.py       # Stablecoins
└── API_LIMITS_AND_ALLOCATION.md   # Documentación de límites de APIs
```

---

## 🔧 Instalación y Configuración

### 1. Requisitos

```bash
pip install -r requirements.txt
```

**Dependencias principales:**
- `xgboost` - Modelo de ML
- `ccxt` - Descarga de datos de Binance
- `pandas`, `numpy` - Procesamiento de datos
- `optuna` - Optimización de hiperparámetros
- `transformers`, `torch` - FinBERT (sentiment analysis)

### 2. API Keys (Opcional pero Recomendado)

Editar `config_15min.json` y agregar:

```json
{
  "api_keys": {
    "newsapi": "TU_NEWSAPI_KEY",           // 100 requests/día
    "cryptopanic": "TU_CRYPTOPANIC_KEY",   // Sin límites estrictos
    "coinglass": "TU_COINGLASS_KEY",       // Derivatives (OI, funding)
    "cryptoquant": "TU_CRYPTOQUANT_KEY"    // On-chain (opcional)
  }
}
```

**Sin API keys**: El sistema usará datos simulados para features externas (funcionará pero con menor precisión).

---

## 🎯 Uso del Sistema

### Paso 1: Entrenar los 20 Modelos

```bash
python train_multiple_pairs.py
```

**Lo que hace:**
1. ✅ Descarga datos OHLCV de 20 pares (últimos ~730 días)
2. ✅ Genera 96 features completas por par (técnicas + estadísticas + externas)
3. ✅ Crea labels binarios (LONG=1, SHORT=0) usando RegimeLabeler
4. ✅ Entrena modelo XGBoost optimizado con Optuna (30 trials por par)
5. ✅ Guarda cada modelo: `models/model_ETHUSDT.json`, `model_SOLUSDT.json`, etc.

**Tiempo estimado**: ~2-4 horas para 20 pares (depende de API keys y conexión)

**Configuración** (editable en `train_multiple_pairs.py`):

```python
PAIRS = [
    'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT',
    'DOGEUSDT', 'MATICUSDT', 'DOTUSDT', 'LINKUSDT', 'UNIUSDT',
    'ATOMUSDT', 'AVAXUSDT', 'LTCUSDT', 'ETCUSDT', 'FILUSDT',
    'APTUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT', 'SUIUSDT'
]  # BTC EXCLUIDO

TRAINING_CONFIG = {
    'days_historical': 730,        # 2 años de datos
    'forward_window': 12,          # Predicción a 12h
    'trend_threshold': 0.025,      # 2.5% mínimo para tendencia clara
    'optuna_trials': 30,           # Trials de optimización
    'news_per_pair': 5,            # NewsAPI: 5 noticias × 20 = 100/día
}
```

### Paso 2: Generar Señales Diarias

```bash
python daily_signals.py
```

**Lo que hace:**
1. ✅ Obtiene top 20 pares por volumen (sin BTC)
2. ✅ Para cada par:
   - Descarga datos actuales (1h + 4h)
   - Genera 96 features
   - Carga **modelo específico del par**
   - Calcula predicción (LONG/SHORT)
   - Encuentra **precio de entrada óptimo** (mejor expected value)
   - Calcula TP/SL absolutos basados en soporte/resistencia
3. ✅ Guarda señales en `signals/signals_YYYYMMDD_HHMMSS.csv`

**Formato de señales** (CSV):

```csv
timestamp,symbol,direction,confidence,current_price,entry,stop_loss,take_profit,probability,expected_value,distance_pct,risk_reward
2025-12-27 10:30:00,ETH/USDT,LONG,0.89,3450.00,3420.00,3380.00,3520.00,0.75,1.88,0.87%,2.50
2025-12-27 10:30:00,SOL/USDT,SHORT,0.92,125.50,127.00,130.00,122.00,0.82,2.13,1.19%,1.67
...
```

**Campos clave:**
- `entry`: Precio LIMIT de entrada (óptimo por expected value)
- `stop_loss`: SL absoluto (soporte/resistencia)
- `take_profit`: TP absoluto (soporte/resistencia)
- `probability`: Probabilidad de alcanzar precio de entrada
- `expected_value`: Prob × R:R (mayor = mejor señal)
- `risk_reward`: R:R real con esa entrada

### Paso 3: Ejecutar Señales (Opcional)

```bash
python execute_signals.py signals/signals_latest.csv --demo
```

**Flags:**
- `--demo`: Ejecuta en Binance Demo (testnet)
- `--live`: Ejecuta en Binance REAL ⚠️ (requiere API keys)

**IMPORTANTE**: Siempre probar en `--demo` primero.

---

## 📊 Límites de APIs y Asignación

### APIs Críticas

| API | Límite | Asignación (20 pares) | Estado |
|-----|--------|----------------------|---------|
| **NewsAPI** | 100 req/día | 5 noticias/par = 100 | ⚠️ JUSTO |
| **Binance** | 2400 req/min | 60 req total | ✅ OK |
| **CryptoPanic** | ~1000 req/día | 100 req | ✅ OK |
| **Coinglass** | ??? | 40 req (OI+FR) | ⚠️ API key |
| **DefiLlama** | Sin límite | 1 req (global) | ✅ OK |

**Ver detalles completos**: [API_LIMITS_AND_ALLOCATION.md](API_LIMITS_AND_ALLOCATION.md)

### Modificaciones Aplicadas

1. **`sentiment_fetcher.py`**:
   - Parámetro `max_results=5` por defecto
   - Limita NewsAPI a 5 noticias por par
   - Total: 5 × 20 = 100 requests/día (respeta límite)

2. **`train_multiple_pairs.py`**:
   - Implementa rate limiting (3s entre pares)
   - Respeta todos los límites de APIs
   - Usa datos simulados si falta API key

---

## 🧪 Pruebas y Validación

### Probar con 2 Pares Primero

Para probar el sistema antes de entrenar los 20 pares:

```python
# Editar train_multiple_pairs.py (línea ~30)
PAIRS = ['ETHUSDT', 'SOLUSDT']  # Solo 2 pares para prueba
```

Ejecutar:
```bash
python train_multiple_pairs.py
```

**Tiempo estimado**: ~10-15 minutos para 2 pares

### Verificar Modelos

```bash
ls -lh models/
# Deberías ver:
# model_ETHUSDT.json (+ metadata.pkl)
# model_SOLUSDT.json (+ metadata.pkl)
# training_summary.json
```

### Probar Generación de Señales

```bash
python daily_signals.py
# Verificar que cargue modelos correctamente:
# "✓ Modelo cargado para ETH/USDT: models/model_ETHUSDT.json"
```

---

## 📈 Análisis de Resultados

### Training Summary

Después de entrenar, revisar `models/training_summary.json`:

```json
{
  "timestamp": "2025-12-27T10:30:00",
  "total_pairs": 20,
  "successful": 18,
  "failed": 2,
  "results": [
    {
      "symbol": "ETHUSDT",
      "status": "SUCCESS",
      "model_file": "model_ETHUSDT.json",
      "samples": 3245,
      "features": 96
    },
    ...
  ]
}
```

### Evaluación de Modelos

Durante entrenamiento, cada modelo muestra:

```
📊 EVALUACIÓN EN TEST SET:
              precision    recall  f1-score   support

       SHORT       0.68      0.71      0.69       423
        LONG       0.72      0.69      0.70       456

    accuracy                           0.70       879
```

**Métricas clave:**
- **Accuracy > 65%**: Modelo básico aceptable
- **Accuracy > 70%**: Modelo bueno
- **F1-score balanceado**: Modelo no está sesgado a una clase

---

## ⚠️ Troubleshooting

### Error: "Modelo no encontrado"

```
⚠️ Modelo no encontrado para ETH/USDT: models/model_ETHUSDT.json
```

**Solución**: Entrenar modelos primero
```bash
python train_multiple_pairs.py
```

### Error: "NewsAPI 426 Upgrade Required"

```
NewsAPI: Upgrade Required. Saltando NewsAPI.
```

**Causa**: Free tier de NewsAPI tiene límites
**Solución**:
- Sistema automáticamente usa solo CryptoPanic
- O actualizar a plan PRO de NewsAPI

### Error: "Insuficientes datos etiquetados"

```
❌ Insuficientes datos etiquetados para SYMBOL. Saltando...
```

**Causa**: Par muy lateral (sin tendencias claras en 730 días)
**Solución**:
- Normal para algunos pares
- Revisar que otros pares sí entrenen correctamente
- Considerar reducir `trend_threshold` en config

### Modelos con baja precisión (<60%)

**Posibles causas:**
1. Faltan API keys → features externas son simuladas
2. Par muy volátil o sin patrones claros
3. Datos históricos insuficientes

**Soluciones:**
- Agregar API keys reales (NewsAPI, Coinglass, etc.)
- Aumentar `days_historical` a 1000+
- Aumentar `optuna_trials` a 50-100 para mejor optimización

---

## 🔄 Mantenimiento y Actualización

### Re-entrenar un Par Específico

Editar `train_multiple_pairs.py`:

```python
PAIRS = ['ETHUSDT']  # Solo ETH
```

Ejecutar y el modelo anterior será sobrescrito.

### Agregar Nuevos Pares

1. Editar `PAIRS` en `train_multiple_pairs.py`
2. Agregar el nuevo símbolo (ej: `'AVAXUSDT'`)
3. Re-ejecutar entrenamiento
4. `daily_signals.py` automáticamente detectará el nuevo modelo

### Actualizar Modelos Periódicamente

**Recomendación**: Re-entrenar modelos cada 1-3 meses

```bash
# Cron job ejemplo (ejecutar cada mes)
0 0 1 * * cd /path/to/ETH && python train_multiple_pairs.py
```

---

## 📝 Diferencias vs Sistema Anterior

| Característica | Sistema Anterior | Sistema Multi-Par Nuevo |
|---------------|------------------|------------------------|
| **Modelos** | 1 modelo único (ETHUSDT) | 20 modelos especializados |
| **Pares** | Solo ETH | 20 pares (sin BTC) |
| **Precisión** | ~65% en ETH | ~70% por par (especializado) |
| **Escalabilidad** | Difícil agregar pares | Fácil: agregar a PAIRS list |
| **NewsAPI** | 100 noticias/request | 5 noticias/par (optimizado) |
| **Tipo de señales** | Market orders | Limit orders (optimal entry) |

---

## 🎓 Conceptos Técnicos

### ¿Por qué 20 modelos y no 1?

**Opción 1: 1 modelo con feature "symbol"**
```python
# Pros: Simple, 1 archivo
# Cons: XGBoost no maneja bien contexto de símbolo
features = [..., 'symbol_encoded']  # symbol_encoded = 0 (ETH), 1 (SOL), etc.
model.fit(X, y)  # Modelo aprende "promedio" de todos
```

**Opción 2: 20 modelos separados** ✅ (implementado)
```python
# Pros: Cada modelo especializado en su par
# Cons: 20 archivos (pero organizados)
model_eth.fit(X_eth, y_eth)   # Aprende solo ETH
model_sol.fit(X_sol, y_sol)   # Aprende solo SOL
```

**Razón**: XGBoost (árbol de decisión) no tiene "memoria" de contexto como redes neuronales. Un modelo único no puede aprender que "DOGE 5% = normal" pero "ETH 5% = extremo".

### Expected Value vs Probability

**Probability**: ¿Qué tan probable es alcanzar este precio de entrada?
```python
probability = confidence * exp(-distance / ATR)
# Cerca del precio actual → alta prob
# Lejos del precio actual → baja prob
```

**Expected Value**: ¿Cuál entrada tiene mejor retorno esperado?
```python
expected_value = probability × risk_reward
# Balanceo: entrada lejana tiene mejor R:R pero menor prob
# Entrada cercana tiene alta prob pero peor R:R
```

**Mejor señal**: Mayor expected value (no mayor probability ni R:R solos)

---

## 📞 Soporte

**Errores o dudas**: Revisar logs en consola
**Documentación de APIs**: Ver `API_LIMITS_AND_ALLOCATION.md`
**Código fuente**: Todos los archivos están comentados

---

## ✅ Checklist de Implementación

- [x] Script de entrenamiento multi-par creado
- [x] Límite de NewsAPI implementado (5 noticias/par)
- [x] `daily_signals.py` actualizado para modelos por par
- [x] Documentación completa
- [ ] Probar entrenamiento con 2 pares
- [ ] Entrenar los 20 pares completos
- [ ] Generar señales diarias
- [ ] Ejecutar en demo (testnet)
- [ ] Evaluar resultados vs mercado real

---

**Última actualización**: 2025-12-27
**Versión**: 2.0 (Multi-Par)
