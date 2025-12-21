# 🎯 Guía: Cómo Usar el Sistema Completo

El sistema YA tiene todo listo. Solo necesitas ejecutar los componentes en orden.

## 📋 Archivos que SÍ se Usan

### 🟢 PRINCIPALES (Usar estos):
1. **`config_15min.json`** - Configuración completa (API keys, parámetros)
2. **`start_system.py`** - Sistema principal (ejecuta el bot)
3. **`execution_bot.py`** - Bot de ejecución (conecta con Binance Testnet)
4. **`model_pipeline_complete.py`** - Entrena el modelo
5. **`web_dashboard.py`** - Dashboard de visualización

### 🔴 Archivos a IGNORAR:
- `model_pipeline.py` (viejo)
- `test_statistical_features.py` (pruebas)
- Otros archivos en root son componentes internos

---

## 🚀 Paso a Paso: Operando en Binance Testnet

### 1️⃣ Entrenar el Modelo (Solo una vez)

```powershell
python model_pipeline_complete.py
```

Esto genera: `models/xgboost_model.json`

---

### 2️⃣ Verificar API Keys de Testnet

Abre `config_15min.json` y verifica:

```json
{
  "exchange": {
    "testnet": true,
    "testnet_api_key": "tu_key_aqui",
    "testnet_api_secret": "tu_secret_aqui"
  }
}
```

**¿Cómo obtener keys de testnet?**
1. Ve a: https://testnet.binancefuture.com
2. Crea cuenta (es gratis, dinero ficticio)
3. API Management → Crear API Key
4. Copia Key + Secret al config

---

### 3️⃣ Ejecutar el Bot (Terminal 1)

```powershell
python start_system.py
```

**El bot automáticamente:**
- ✅ Se conecta a Binance Testnet
- ✅ Descarga datos en vivo
- ✅ Genera predicciones cada hora
- ✅ Ejecuta trades (LONG/SHORT)
- ✅ Guarda trades en `logs/predictions.csv`

---

### 4️⃣ Abrir Dashboard (Terminal 2)

```powershell
streamlit run web_dashboard.py
```

**El dashboard muestra:**
- 📈 Gráfico de precio en vivo
- 🎯 Trades ejecutados por el bot
- 💰 P&L en tiempo real
- 📊 Estadísticas (Win Rate, Profit Factor)

---

## ⚙️ Configuración Importante

### Editar `config_15min.json`:

```json
{
  "trading": {
    "prediction_threshold": 0.70,    // Baja a 0.65 si hay pocas señales
    "stop_loss_pct": 0.02,           // 2% SL
    "take_profit_pct": 0.05,         // 5% TP
    "position_size_usd": 100         // Tamaño de cada trade
  },

  "exchange": {
    "testnet": true                  // SIEMPRE true para testnet
  }
}
```

---

## 📊 Archivos que Genera el Bot

El bot guardará:
- `logs/predictions.csv` - Predicciones del modelo
- `logs/system.log` - Logs del sistema
- `logs/trades_history.csv` - Historial de trades

El dashboard los lee automáticamente.

---

## 🔧 Integración Dashboard + Bot

**Próxima tarea**: Modificar `web_dashboard.py` para que:

1. **Botón "Iniciar"** → Ejecuta `python start_system.py` como subproceso
2. **Botón "Detener"** → Para el proceso
3. **Auto-refresco** → Lee trades de `logs/` cada 10 segundos

¿Quieres que implemente esta integración ahora? Será UNA SOLA modificación al dashboard para controlar `start_system.py`.

---

## ❓ Preguntas Frecuentes

**P: ¿Cuánto dinero ficticio tengo en testnet?**
R: Binance Testnet te da dinero ilimitado. Es solo para pruebas.

**P: ¿Los trades son reales?**
R: NO. Testnet es simulación completa. No pierdes dinero real.

**P: ¿Cuándo usar dinero real?**
R: Solo cuando tengas:
   - Win Rate consistente >50% por 2+ semanas
   - Profit Factor >2.0
   - Balance positivo en testnet

**P: ¿Cómo paso a dinero real?**
R: Cambias en config:
```json
{
  "exchange": {
    "testnet": false,
    "api_key": "tu_key_real",
    "api_secret": "tu_secret_real"
  }
}
```
⚠️ **SOLO cuando estés 100% seguro**

---

## ✅ Próximo Paso

¿Quiero que modifique `web_dashboard.py` para que el botón "Iniciar" lance `start_system.py` automáticamente?

Sería una sola modificación limpia sin crear archivos nuevos.
