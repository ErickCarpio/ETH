# Cambio de Timeframe: 15MIN → 1H

## Fecha: 2025-12-18

## Razón del Cambio

**15min es demasiado ruidoso para predecir con ML.**

Resultados con 15min:
- v1: Accuracy 75% (solo predice NO_TRADE)
- v2: Accuracy 26% (aprende ruido)
- v3: Accuracy 47%, precision LONG 4%, SHORT 13%

**Conclusión:** El problema no son los parámetros, es el timeframe.

---

## Nuevo Setup: 1H + 1D MACRO

### Timeframe de Trading: 1H

**Ventajas:**
- ✅ Menos ruido que 15min
- ✅ Patrones técnicos más claros (SMA, RSI, MACD)
- ✅ Aún suficientes señales para grid trading (~10-20/semana vs 100+/semana en 15min)
- ✅ Mejor para análisis técnico tradicional
- ✅ Swing trading en lugar de scalping

**Dataset:**
- 10,000 velas de 1H = 417 días ≈ 1.1 años
- 5-10x más datos que antes (5000 velas de 15min = 52 días)

### Timeframe Macro: 1D

**Ventajas:**
- ✅ SMA_50, SMA_200 en diario son MUY respetados por el mercado
- ✅ RSI diario más significativo
- ✅ Tendencias de largo plazo claras
- ✅ Menos ruido en indicadores macro

**Dataset:**
- 730 velas de 1D = 2 años
- Datos macro de alta calidad

---

## Parámetros Ajustados

### Forward Window

```python
# Antes (15min):
forward_window = 48  # 48 velas × 15min = 12 horas

# Ahora (1H):
forward_window = 12  # 12 velas × 1H = 12 horas (equivalente)
```

### Umbrales (sin cambio)

```python
labeler = RegimeLabeler(
    forward_window=12,  # 12 velas × 1H = 12h
    trend_threshold=0.025,  # 2.5% en 12h
    volatility_threshold_low=0.018,  # 1.8%
    volatility_threshold_high=0.055  # 5.5%
)
```

Los umbrales NO cambian porque son porcentuales y relativos al tiempo (12h en ambos casos).

---

## Cambios en Archivos

### model_pipeline_complete.py

1. **Descarga de datos:**
```python
# Antes:
df_15min = download_binance_data(symbol, timeframe='15m', limit=5000)
df_4h = download_binance_data(symbol, timeframe='4h', limit=1000)

# Ahora:
df_1h = download_binance_data(symbol, timeframe='1h', limit=10000)
df_1d = download_binance_data(symbol, timeframe='1d', limit=730)
```

2. **Features:**
```python
# Antes:
features_df = fe.build_full_features(
    crypto_df=df_15min,
    crypto_4h_df=df_4h
)

# Ahora:
features_df = fe.build_full_features(
    crypto_df=df_1h,
    crypto_4h_df=df_1d  # Usa param crypto_4h_df pero con datos 1D
)
```

3. **Labeling:**
```python
# Antes:
price_df = df_15min[['open', 'high', 'low', 'close']].copy()

# Ahora:
price_df = df_1h[['open', 'high', 'low', 'close']].copy()
```

### config_15min.json

```json
{
  "data": {
    "timeframe": "1h",  // antes "15m"
    "_comment_timeframe": "1H para trading, 1D para contexto macro"
  },
  "model": {
    "forward_window": 12,  // antes 48
    "_comment_forward": "12 velas × 1H = 12 horas"
  },
  "sentiment": {
    "aggregation_freq": "1h"  // antes "15min"
  }
}
```

---

## Performance Esperada

### Con 1H (menos ruido):

```
Distribución de Clases:
  Clase 0 (Lateral):  65-70%  (~6500-7000)
  Clase 1 (LONG):     15-17%  (~1500-1700)
  Clase 2 (SHORT):    15-17%  (~1500-1700)

Métricas Esperadas:
              precision    recall  f1-score   support

           0       ~0.75     ~0.80     ~0.77     ~2100
           1       ~0.60     ~0.55     ~0.57     ~500   ← MUCHO mejor que 4%
           2       ~0.65     ~0.60     ~0.62     ~500   ← MUCHO mejor que 13%

    accuracy                           ~0.70     3100
   macro avg       ~0.67     ~0.65     ~0.65     3100
```

**Mejora esperada vs 15min:**
- Accuracy: 47% → **70%** (+50%)
- Precision LONG: 4% → **60%** (+15x)
- Precision SHORT: 13% → **65%** (+5x)
- Macro F1: 0.27 → **0.65** (+2.4x)

---

## Ventajas para Grid Trading

### Más Datos Históricos

- 15min: 52 días de datos
- **1H: 417 días de datos (8x más)**

Con más datos:
- ✅ Mejor entrenamiento del modelo
- ✅ Más ciclos de mercado capturados
- ✅ Validación más robusta

### Señales de Mejor Calidad

| Timeframe | Señales/Semana | Calidad |
|-----------|----------------|---------|
| **15min** | 100-150 | Muy ruidosas, 4% precision |
| **1H** | 10-20 | Claras, 60%+ precision esperado |

**Para grid trading:**
- NO necesitas 100 señales/semana
- Necesitas 10-20 señales **BUENAS**
- Con 60% precision + reward/risk 2:1 = **muy rentable**

### Compatibilidad con Análisis Técnico

1H es el timeframe preferido para:
- ✅ Swing trading
- ✅ Análisis técnico tradicional
- ✅ Identificar soportes/resistencias
- ✅ Divergencias MACD
- ✅ Patrones de velas

---

## Testing

### Ejecutar Pipeline

```bash
git pull origin claude/review-code-errors-LsmkW
python model_pipeline_complete.py
```

### Validar Descarga

```
INFO:__main__:   ✓ Datos 1H: 10000 velas (417 días)  ✅
INFO:__main__:   ✓ Datos 1D: 730 velas (2.0 años)    ✅
```

### Validar Performance

**Mínimo aceptable:**
- Accuracy: >60%
- Precision LONG: >50%
- Precision SHORT: >50%

**Objetivo:**
- Accuracy: >70%
- Precision LONG: >60%
- Precision SHORT: >60%

---

## Si Esto No Funciona

Si con 1H la accuracy sigue <55%:

### Plan B: Timeframe 4H

Si 1H aún tiene ruido:
- Cambiar a 4H para trading
- Usar 1W para macro
- Menos señales pero MUY claras

### Plan C: Problema Fundamental

Si incluso 4H falla, el problema NO es el timeframe:
- Cambiar a regresión (predecir % de cambio)
- Usar ensemble de modelos
- Agregar features sofisticadas (microestructura, derivados, on-chain)

---

## Conclusión

**15min → 1H:**
- ✅ 8x más datos históricos (52 → 417 días)
- ✅ Menos ruido, patrones más claros
- ✅ Compatible con análisis técnico
- ✅ Perfecto para grid trading
- ✅ Performance esperada: 70% accuracy, 60% precision LONG/SHORT

**Si 1H no funciona, el problema es más profundo que el timeframe.**
