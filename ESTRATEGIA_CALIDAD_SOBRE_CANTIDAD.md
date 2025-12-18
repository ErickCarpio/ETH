# Estrategia: CALIDAD sobre CANTIDAD

## Fecha: 2025-12-18

## Por Qué Cambiar de Nuevo

### Resultados del Experimento Anterior (Umbrales Laxos)

**Parámetros:**
- `forward_window: 32` (8 horas)
- `trend_threshold: 1.2%`
- `volatility_threshold_low: 1.0%`

**Resultado:**
```
✅ Balance mejorado: 55% NO_TRADE, 20% LONG, 24% SHORT
❌ Accuracy CATASTRÓFICA: 26% (antes 75%)
❌ Precision LONG: 17%
❌ Precision SHORT: 16%

Reporte de Clasificación:
              precision    recall  f1-score   support
           0       0.63      0.21      0.32       652
           1       0.17      0.11      0.13       141
           2       0.16      0.58      0.25       182
```

### Diagnóstico

**El problema NO era el balance de clases. Era la CALIDAD de las etiquetas.**

Con umbrales laxos (1.2%, 8h):
- Capturamos MUCHO ruido como "tendencias"
- ETH se mueve 1.2% en 8h constantemente sin ser una tendencia real
- El modelo aprende ruido, no patrones
- Resultado: 26% accuracy (peor que adivinar al azar)

**Lección aprendida:**
- Más datos != Mejor modelo
- CALIDAD de las etiquetas > CANTIDAD de señales

---

## Nueva Estrategia: Selectividad Extrema

### Filosofía

**"Prefiero tener 10 señales EXCELENTES que 100 señales MEDIOCRES"**

- Si el modelo dice LONG/SHORT → Debe ser una señal CONFIABLE
- Aceptar que 70-80% del tiempo el mejor trade es NO_TRADE
- Grid trading no requiere 100 señales/día, requiere señales BUENAS

---

## Nuevos Parámetros

```python
labeler = RegimeLabeler(
    forward_window=48,  # 12 horas (antes 32 = 8h)
    trend_threshold=0.025,  # 2.5% (antes 1.2%)
    volatility_threshold_low=0.018,  # 1.8% (antes 1.0%)
    volatility_threshold_high=0.055  # 5.5% (antes 4.5%)
)
```

### Justificación

| Parámetro | Valor | Razón |
|-----------|-------|-------|
| `forward_window` | 48 (12h) | Captura tendencias de medio día completo, no solo unas horas |
| `trend_threshold` | 2.5% | ETH moviéndose 2.5% en 12h es una tendencia REAL |
| `vol_threshold_low` | 1.8% | Muy selectivo - solo laterales muy claros |
| `vol_threshold_high` | 5.5% | Umbral para pánico/euforia extrema |

---

## Qué Esperar

### Distribución de Clases Esperada

```
Clase 0 (Lateral):  70-75%  (~3500 muestras)
Clase 1 (Alcista):  12-15%  (~600-750)
Clase 2 (Bajista):  12-15%  (~600-750)
```

**Comparación histórica:**

| Iteración | Balance | Accuracy | Precision LONG/SHORT |
|-----------|---------|----------|----------------------|
| **v1 (Conservador)** | 84/6/10 | 75% | 3% / 8% - Inútil |
| **v2 (Laxo)** | 55/20/24 | 26% | 17% / 16% - Terrible |
| **v3 (Selectivo)** | 70-75/12-15/12-15 | **60-70%** ⭐ | **50-60%** ⭐ |

---

## Performance Objetivo

### Escenario Realista:

```
Reporte de Clasificación (Validación):
              precision    recall  f1-score   support

           0       0.75      0.80      0.77       700  (Lateral)
           1       0.55      0.50      0.52       120  (LONG)
           2       0.60      0.55      0.57       155  (SHORT)

    accuracy                           0.70       975
   macro avg       0.63      0.62      0.62       975
weighted avg       0.70      0.70      0.70       975
```

**¿Por qué esto es mejor?**

- **Precision LONG/SHORT ~55-60%:** Cuando dice "operar", hay 55-60% de probabilidad de acertar
- **Recall ~50%:** Captura la mitad de las oportunidades reales (pero las que captura son buenas)
- **Macro F1 ~0.62:** Balance razonable entre precision y recall

**Para trading:**
- Si modelo dice LONG → 55% chance de acertar
- Con reward/risk 2:1 → Profit esperado positivo
- Con grid trading → Aprovechar la volatilidad en ambos casos

---

## Si Esto No Funciona...

Si con estos parámetros la accuracy sigue <50%, entonces:

### Plan B: Clasificación Binaria

```python
# En lugar de 3 clases (LATERAL/LONG/SHORT)
# Usar 2 clasificadores:

# 1. Modelo TRADE vs NO_TRADE
#    Objetivo: 70% accuracy
#    Si dice TRADE → continuar

# 2. Modelo LONG vs SHORT (solo si hay TRADE)
#    Objetivo: 60% accuracy direccional
```

**Ventaja:**
- Cada modelo se especializa en una decisión más simple
- Menos confusión entre clases

### Plan C: Cambiar Timeframe

Si 15min es demasiado ruidoso:

| Timeframe | Pros | Contras |
|-----------|------|---------|
| **15min** | Muchas señales | Muy ruidoso |
| **1H** | Menos ruido, patrones más claros | Menos señales |
| **4H** | Tendencias claras | Muy pocas señales |

**Recomendación:** Si 15min no funciona, probar **1H**.

### Plan D: Features Más Sofisticadas

Si el problema son las features:

1. **Microestructura:** Order flow imbalance, VPIN
2. **Derivados:** Funding rate, Open Interest, GEX
3. **On-chain:** Exchange flows, whale movements
4. **Multi-timeframe:** Confirmar 15min con 1H y 4H

---

## Testing Instructions

### 1. Ejecutar Pipeline

```bash
python model_pipeline_complete.py
```

### 2. Validar Distribución

Debe mostrar:
```
INFO:target_labeling:DISTRIBUCIÓN DE RÉGIMEN:
  Clase 0 (Lateral):  ~3500-3700 (70-75%)  ✅
  Clase 1 (Alcista):  ~600-750   (12-15%)  ✅
  Clase 2 (Bajista):  ~600-750   (12-15%)  ✅
```

### 3. Validar Performance

**Mínimo aceptable:**
- Accuracy: >55%
- Precision LONG: >45%
- Precision SHORT: >45%
- Macro F1: >0.50

**Objetivo ideal:**
- Accuracy: >65%
- Precision LONG: >55%
- Precision SHORT: >55%
- Macro F1: >0.60

### 4. Si Falla

**Si Accuracy <50%:**
→ Implementar Plan B (clasificación binaria)

**Si Accuracy 50-55%:**
→ Ajustar umbrales: trend=3.0%, forward=64 (16h)

**Si Accuracy >55%:**
→ ¡ÉXITO! Proceder a backtesting

---

## Filosofía de Trading

**Recordatorio:**

Grid trading NO necesita predecir cada movimiento.

**Lo que SÍ necesita:**
1. Identificar cuando HAY una oportunidad (vs. ruido lateral)
2. Direccionalidad aproximada (no exacta)
3. No operar cuando el mercado es impredecible

**Con 55% de precision en señales selectivas:**
- 10 señales/semana × 55% accuracy = 5-6 trades ganadores
- Con risk/reward 2:1 y grid optimization → Rentable

**El modelo NO tiene que ser perfecto. Solo tiene que ser MEJOR que adivinar.**

---

## Conclusión

**Cambio de mentalidad:**

| ❌ Antes | ✅ Ahora |
|---------|----------|
| Capturar TODO | Capturar lo MEJOR |
| Más señales = mejor | Menos señales de mejor calidad |
| Balance 50/25/25 | Balance 75/12/12 OK |
| Precision 17% | Precision 55%+ |
| Accuracy 26% | Accuracy 65%+ |

**Si con esto no funciona, el problema no son los parámetros. Es el enfoque (15min multi-class classification).**
