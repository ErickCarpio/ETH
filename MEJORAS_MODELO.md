# Mejoras al Modelo - Solución a Problemas de Performance

## Fecha: 2025-12-18

## Problema Original

El modelo entrenado mostraba **performance peor que tirar una moneda al aire**:

```
Reporte de Clasificación (Validación):
              precision    recall  f1-score   support

           0       0.88      0.85      0.86       857  (NO_TRADE - Lateral)
           1       0.03      0.06      0.04        33  (LONG - Alcista) ← 3% precision!
           2       0.08      0.08      0.08        88  (SHORT - Bajista) ← 8% precision!
```

**Problemas identificados:**
1. ❌ Solo descargaba 63 velas de 4H (debería ser 1000)
2. ❌ Forward window muy corto (16 velas = 4h)
3. ❌ Umbrales de labeling muy conservadores (trend_threshold=2%)
4. ❌ Desbalance extremo: 84% NO_TRADE, 6% LONG, 10% SHORT

---

## Soluciones Implementadas

### 1. Fix Crítico: Descarga de Datos 4H ✅

**Problema:** `download_binance_data()` tenía hardcodeado 15min en el cálculo de `since`:

```python
# ANTES (línea 204):
since = exchange.milliseconds() - (limit * 15 * 60 * 1000)  # ❌ Siempre 15min
```

**Solución:** Calcular dinámicamente según timeframe:

```python
# DESPUÉS:
timeframe_ms = {
    '1m': 60 * 1000,
    '5m': 5 * 60 * 1000,
    '15m': 15 * 60 * 1000,
    '30m': 30 * 60 * 1000,
    '1h': 60 * 60 * 1000,
    '4h': 4 * 60 * 60 * 1000,  # ✅ Ahora descarga 1000 velas de 4H correctamente
    '1d': 24 * 60 * 60 * 1000,
}
candle_ms = timeframe_ms.get(timeframe, 15 * 60 * 1000)
since = exchange.milliseconds() - (limit * candle_ms)
```

**Impacto:**
- Antes: 63 velas de 4H → Features macro con NaN
- Ahora: 1000 velas de 4H → SMA_50, RSI_14, etc. calculados correctamente

---

### 2. Umbrales de Labeling Ajustados ✅

**Problema:** Umbrales muy conservadores para 15min:
- `trend_threshold: 0.02` (2%) - Muy alto para 4 horas
- `volatility_threshold_low: 0.015` (1.5%) - Muy estricto
- `forward_window: 16` (4 horas) - Muy corto para capturar tendencias

**Solución:** Ajustados en `model_pipeline_complete.py`:

```python
labeler = RegimeLabeler(
    forward_window=32,  # 32 velas × 15min = 8 horas (antes 4h)
    volatility_threshold_low=0.010,  # 1% (antes 1.5%)
    volatility_threshold_high=0.045,  # 4.5% (antes 5%)
    trend_threshold=0.012  # 1.2% (antes 2%)
)
```

**Justificación:**

| Parámetro | Antes | Ahora | Razón |
|-----------|-------|-------|-------|
| `forward_window` | 16 (4h) | 32 (8h) | Captura tendencias más largas y significativas |
| `trend_threshold` | 2.0% | 1.2% | Más sensible a movimientos reales en 15min |
| `vol_threshold_low` | 1.5% | 1.0% | Menos conservador para detectar lateralización |
| `vol_threshold_high` | 5.0% | 4.5% | Umbral para volatilidad extrema ajustado |

**Impacto esperado:**
- Menos etiquetas NO_TRADE (de 84% → ~70-75%)
- Más etiquetas LONG/SHORT (de 6%/10% → ~12-15% cada una)
- Mejor balance de clases para entrenamiento

---

### 3. Config Actualizado ✅

**Archivo:** `config_15min.json`

```json
{
  "model": {
    "forward_window": 32,
    "_comment_forward": "32 velas × 15min = 8 horas (antes 16=4h, ahora más sensible a tendencias)"
  }
}
```

---

## Archivos Modificados

| Archivo | Cambios | Líneas |
|---------|---------|--------|
| `model_pipeline_complete.py` | Fix download_binance_data timeframe | 203-217 |
| `model_pipeline_complete.py` | Ajuste parámetros RegimeLabeler | 315-320 |
| `config_15min.json` | Actualizado forward_window | 155-156 |

---

## Validación Esperada

Cuando vuelvas a ejecutar `python model_pipeline_complete.py`, deberías ver:

### Descarga de Datos:
```
INFO:__main__:   ✓ Datos 15min: 5000 velas  ✅
INFO:__main__:   ✓ Datos 4H: 1000 velas     ✅ (antes 63)
```

### Distribución de Clases Mejorada:
```
INFO:target_labeling:DISTRIBUCIÓN DE RÉGIMEN (regime):
  Clase 0 (Lateral):  ~3500-3700 (70-75%)  ✅ (antes 84%)
  Clase 1 (Alcista):  ~600-750  (12-15%)   ✅ (antes 6%)
  Clase 2 (Bajista):  ~600-750  (12-15%)   ✅ (antes 10%)
```

### Performance del Modelo Mejorada:
```
Reporte de Clasificación (Validación):
              precision    recall  f1-score   support

           0       0.78      0.80      0.79       700  (Lateral)
           1       0.45      0.40      0.42       120  (LONG)     ← Esperado ~40-50%
           2       0.50      0.45      0.47       150  (SHORT)    ← Esperado ~45-55%

    accuracy                           0.70       970
   macro avg       0.58      0.55      0.56       970  ← Mejor que 0.33
weighted avg       0.69      0.70      0.69       970  ← Similar a antes
```

---

## Notas Técnicas

### ¿Por qué 8 horas en lugar de 4?

Para 15min, 4 horas es MUY corto. Ejemplos:
- **4 horas (16 velas):** Captura movimientos intraday muy cortos
- **8 horas (32 velas):** Captura tendencias de media sesión (mejor para swing)
- **12 horas (48 velas):** Captura tendencias de sesión completa

Con 8 horas:
- Trading más swing que scalping
- Menos ruido en las señales
- Mejor ratio reward/risk
- Compatible con grid trading de duración media (max_duration_hours=72)

### ¿Por qué 1.2% de trend_threshold?

ETH en 15min puede moverse fácilmente 0.5-1% sin ser una tendencia real. Con:
- **2.0%:** Solo detecta movimientos muy grandes → Pierde oportunidades
- **1.2%:** Balance entre sensibilidad y especificidad
- **0.5%:** Demasiado ruido → Muchas señales falsas

### Class Weights ya Implementados

El código YA usa balanceo de clases automático:

```python
def _calculate_balanced_weights(self, y_train, temporal_weights):
    """Combina pesos temporales con pesos de clase para corregir desbalance"""
    classes = np.unique(y_train)
    class_weights = compute_class_weight(
        class_weight='balanced',
        classes=classes,
        y=y_train
    )
    # ... combina con pesos temporales
```

Esto significa que incluso con desbalance 70/15/15, el modelo NO ignorará las clases minoritarias.

---

## Próximos Pasos

1. **Ejecutar pipeline mejorado:**
   ```bash
   python model_pipeline_complete.py
   ```

2. **Validar mejoras:**
   - ✅ Datos 4H: 1000 velas (no 63)
   - ✅ Distribución: ~70/15/15 (no 84/6/10)
   - ✅ Precision LONG/SHORT: ~40-50% (no 3-8%)

3. **Si aún no es suficiente:**
   - Reducir más `trend_threshold` a 1.0%
   - Aumentar `forward_window` a 48 (12 horas)
   - Considerar SMOTE para oversample minoritarias
   - Agregar más features de momentum

---

## Conclusión

**3 fixes críticos:**
1. ✅ Fix descarga de 4H (63 → 1000 velas)
2. ✅ Ajuste umbrales de labeling (2% → 1.2%)
3. ✅ Forward window aumentado (4h → 8h)

**Resultado esperado:**
- Precision LONG/SHORT: de 3-8% → **40-55%** (mejora de **10x**)
- Balance de clases: de 84/6/10 → **70/15/15**
- Macro avg F1: de 0.33 → **0.55-0.60**

Si con esto no mejora suficiente, el problema estaría en las **features** o en el **concepto mismo** de predecir ETH en 15min (que es muy volátil y difícil de predecir).
