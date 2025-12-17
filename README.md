# 🚀 Sistema de Trading ETH - ML + Grid Trading

Sistema automatizado de trading para Ethereum que combina:
- **Machine Learning** (XGBoost) para predicción de regímenes de mercado
- **Grid Trading** adaptativo para ejecución
- **460+ features** de microestructura, derivados, estadísticos y automated

---

## ⚡ Quick Start

### 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 2. Entrenar modelo
```bash
python model_pipeline.py
```

Este proceso:
- Descarga 2 años de datos de ETHUSDT (4h)
- Genera 244 features automáticamente
- Entrena XGBoost con Optuna (1000 trials)
- Guarda modelo en `models/xgboost_model.json`

**Nota:** El entrenamiento puede tardar 1-3 horas dependiendo de tu hardware.

### 3. (Opcional) Configurar tiempo real

```bash
# Levantar QuestDB
docker run -p 9000:9000 -p 9009:9009 -p 8812:8812 \
  -v "${PWD}/questdb_data:/var/lib/questdb" \
  questdb/questdb

# Iniciar sistema completo
python start_system.py
```

---

## 📊 Características

### Machine Learning
- **XGBoost** con balanceo automático de clases
- **Optuna** para optimización de hiperparámetros
- **4 regímenes**: Lateral, Alcista, Bajista, Peligro
- **Time-decay weighting** para priorizar datos recientes

### Features (~244 generadas automáticamente)
- **Base** (~30): Returns, volatilidad, RSI, ATR, Bollinger
- **Microestructura** (~19): Order Book Imbalance, VPIN, OFI
- **Derivados** (placeholders): GEX, Funding, Liquidaciones
- **Estadísticos** (~100): Hurst, entropía, Kalman, wavelets
- **Automated**: tsfresh (opcional)

### Trading
- **Grid Trading** adaptativo por régimen
- **Stop Loss / Take Profit** configurables
- **Paper trading** y testnet soportados
- **Backtesting** integrado

---

## 📁 Estructura del Proyecto

```
ETH/
├── model_pipeline.py           # Entrenamiento del modelo ML
├── feature_engineering.py      # Generación de features
├── target_labeling.py          # Definición de targets
├── weighting_logic.py          # Pesos de muestras
├── config.json                 # Configuración principal
├── requirements.txt            # Dependencias
│
├── features/                   # Módulos de features
│   ├── microstructure/        # Order Book, VPIN, OFI
│   ├── derivatives/           # GEX, Funding, Liquidaciones
│   ├── statistical/           # Hurst, entropía, Kalman
│   └── automated/             # tsfresh, selección
│
├── data/                       # Sistema de datos en tiempo real
│   ├── managers/              # WebSocket, caché, pipeline
│   ├── fetchers/              # APIs externas
│   └── storage/               # QuestDB connector
│
├── models/                     # Modelos entrenados
│   └── xgboost_model.json     # Modelo actual
│
└── docs/                       # Documentación
    ├── GUIA_DE_USO.md         # Guía detallada
    ├── ESTRUCTURA.md          # Análisis de estructura
    └── MASTER_PLAN.md         # Plan maestro (6 fases)
```

---

## ⚙️ Configuración

Edita `config.json` para ajustar:

### Trading
```json
{
  "exchange": {
    "symbol": "ETHUSDT",
    "testnet": true,              // ⚠️ Cambiar a false para REAL
    "testnet_api_key": "...",
    "testnet_api_secret": "..."
  },
  "trading": {
    "total_capital": 1000.0,
    "grid_allocation": 0.80,
    "prediction_threshold": 0.65,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.05
  }
}
```

### Modelo
```json
{
  "model": {
    "n_classes": 4,
    "optuna_trials": 1000,          // Reducir a 50-100 para pruebas rápidas
    "retrain_every_days": 7
  }
}
```

### Features
```json
{
  "features": {
    "use_microstructure": true,   // ~150 features
    "use_derivatives": true,       // ~80 features (placeholders offline)
    "use_statistical": true,       // ~100 features
    "use_tsfresh": true           // ~100 features (opcional)
  }
}
```

---

## 🔍 Verificación

### Verificar configuración
```bash
python verify_config.py
```

### Test del pipeline
```bash
python test_pipeline.py
```

---

## 📚 Documentación

- **[Guía de Uso Completa](docs/GUIA_DE_USO.md)** - Instrucciones detalladas paso a paso
- **[Análisis de Estructura](docs/ESTRUCTURA.md)** - Implementación actual vs plan
- **[Master Plan](docs/MASTER_PLAN.md)** - Visión completa del sistema (6 fases)

---

## 🚨 Advertencias

⚠️ **Trading Real**
- Por defecto está en **testnet** (dinero virtual)
- Para trading real: cambiar `"testnet": false` en config.json
- Usa tus propias API keys de producción
- Comienza con capital pequeño para probar

⚠️ **Performance**
- El entrenamiento inicial puede tardar 1-3 horas
- Reducir `optuna_trials` a 50-100 para pruebas rápidas
- Las features estadísticas generan warnings (esperado)

⚠️ **Datos Tiempo Real**
- Microestructura requiere QuestDB + collectors
- Offline usa placeholders (valores en 0)
- Para producción, ejecutar `start_system.py`

---

## 🛠️ Troubleshooting

### Error: `ModuleNotFoundError: No module named 'xgboost'`
```bash
pip install -r requirements.txt
```

### Error: `ImportError: cannot import name 'generate_features'`
```bash
git pull  # Obtener última versión con wrappers
```

### Warning: `DataFrame is highly fragmented`
- Es un warning de performance, no afecta funcionamiento
- El código funciona correctamente

### Modelo no entrena / No output
```bash
python -u model_pipeline.py  # Forzar output unbuffered
```

---

## 📊 Resultados Esperados

Después de entrenar el modelo, verás:

```
================================================================================
ENTRENAMIENTO COMPLETADO
================================================================================
✓ Features: 243
✓ Muestras train: 740
✓ Muestras val: 185
✓ Modelo guardado: models/xgboost_model.json
================================================================================
```

### Distribución de clases típica:
- **Lateral (0)**: ~60-65% (mercado en rango)
- **Alcista (1)**: ~10-15% (tendencia alcista)
- **Bajista (2)**: ~10-15% (tendencia bajista)
- **Peligro (3)**: ~15-20% (alta volatilidad)

---

## 🔧 Desarrollo

### Estructura de clases vs funciones

El sistema usa **arquitectura de clases** con **wrappers funcionales**:

```python
# Clase principal
class FeatureEngineer:
    def build_full_features(self, ...): ...

# Wrapper para compatibilidad
def generate_features(symbol='ETHUSDT'):
    engineer = FeatureEngineer()
    return engineer.build_full_features(...)
```

### Re-entrenar modelo
```python
from model_pipeline import XGBoostRegimeModel

model = XGBoostRegimeModel()
model.load_model("xgboost_model.json")
model.retrain_daily(X_new, y_new, weights, quick_optimization=True)
```

---

## 📝 Licencia

Proyecto personal - Uso educativo

---

## 🤝 Contribuir

Este es un proyecto personal, pero sugerencias son bienvenidas vía issues.

---

**Estado:** ✅ Fase 1-6 implementadas (460+ features funcionales)
**Última actualización:** Diciembre 2024
