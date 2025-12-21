# 🚀 Cómo Usar el Dashboard Integrado

El dashboard ahora tiene **TODO integrado** en un solo archivo. No necesitas ejecutar múltiples scripts.

## ✅ Requisitos Previos

1. **Modelo entrenado**: Debe existir `models/xgboost_model.json`
   ```bash
   python model_pipeline_complete.py  # Solo si no tienes el modelo
   ```

2. **API Keys de Binance Testnet**: Configuradas en `config_15min.json`
   - Ve a: https://testnet.binancefuture.com
   - Crea cuenta (gratis, dinero ficticio)
   - API Management → Crear API Key
   - Copia las keys a `config_15min.json`:
     ```json
     "testnet_api_key": "tu_key_aqui",
     "testnet_api_secret": "tu_secret_aqui"
     ```

## 🎯 Uso del Dashboard

### 1️⃣ Iniciar el Dashboard

```bash
streamlit run web_dashboard.py
```

### 2️⃣ Iniciar el Bot de Trading

En el dashboard:
1. Verifica que el modelo existe (indicador en dashboard)
2. Haz clic en **▶️ Iniciar**
3. El bot automáticamente:
   - ✅ Carga el modelo XGBoost
   - ✅ Se conecta a Binance Testnet
   - ✅ Descarga datos en vivo (ETH/USDT 1h)
   - ✅ Calcula features (RSI, MACD, Bollinger, etc)
   - ✅ Hace predicciones LONG/SHORT
   - ✅ Ejecuta trades si confianza >= 70%
   - ✅ Monitorea Stop Loss y Take Profit
   - ✅ Guarda trades en `logs/live_trades.csv`

### 3️⃣ Monitorear en Tiempo Real

El dashboard muestra:
- 📈 Gráfico de precio con trades marcados
- 🎯 Posición abierta actual (si hay)
- 💰 P&L acumulado
- 📊 Estadísticas (Win Rate, Profit Factor)
- 📝 Logs del bot en vivo
- 🔄 Auto-refresco cada 10 segundos

### 4️⃣ Detener el Bot

Haz clic en **⏸️ Detener** cuando quieras parar el bot.

---

## ⚙️ Configuración

### Ajustar Parámetros desde el Dashboard

En la barra lateral puedes modificar:
- **Threshold de Confianza**: 50% - 95% (default: 70%)
- **Stop Loss**: 1% - 5% (default: 2%)
- **Take Profit**: 2% - 10% (default: 5%)
- **Timeframe de Visualización**: 6h hasta "Todo"

### Editar Configuración Avanzada

Abre `config_15min.json`:

```json
{
  "trading": {
    "prediction_threshold": 0.70,    // Confianza mínima para operar
    "stop_loss_pct": 0.02,           // 2% Stop Loss
    "take_profit_pct": 0.05,         // 5% Take Profit
    "position_size_usd": 100,        // Tamaño por trade
    "max_positions": 1               // Máximo 1 posición a la vez
  },

  "exchange": {
    "testnet": true,                 // SIEMPRE true para testnet
    "symbol": "ETHUSDT"
  }
}
```

---

## 📊 Interpretación de Resultados

### Métricas Clave

| Métrica | Qué Significa | Valor Bueno |
|---------|---------------|-------------|
| **Win Rate** | % de trades ganadores | > 50% |
| **Profit Factor** | Ganancias / Pérdidas | > 2.0 |
| **P&L Total** | Ganancia/pérdida acumulada | Positivo |
| **Sharpe Ratio** | Retorno ajustado por riesgo | > 1.5 |

### Estados del Bot

- 🟢 **Bot Iniciado**: Operando en vivo
- 🔴 **Bot Detenido**: No está operando
- 🎯 **Posición Abierta**: Trade activo (muestra SL/TP)
- 🤖 **Esperando señal**: Sin posición, buscando oportunidad

---

## 🔍 Solución de Problemas

### Error: "Modelo no encontrado"
**Solución**: Ejecuta `python model_pipeline_complete.py` para entrenar el modelo.

### Error: "AuthenticationError"
**Solución**: Verifica que las API keys en `config_15min.json` sean correctas.

### No aparecen trades
**Posible causa**:
1. Confianza < threshold (70% default) → Baja el threshold en el dashboard
2. No hay señales claras en el mercado → Es normal, espera
3. Balance insuficiente en testnet → Verifica balance en https://testnet.binancefuture.com

### Bot se detiene solo
**Revisa los logs** en el dashboard. Posibles causas:
- Error de conexión → Reintentar
- Balance insuficiente → Recargar testnet
- Error en predicción → Verifica que el modelo sea compatible

---

## 📝 Archivos Generados

El bot crea automáticamente:

| Archivo | Descripción |
|---------|-------------|
| `logs/live_trades.csv` | Trades ejecutados en vivo |
| `logs/trading_bot.log` | Logs detallados del bot |

El dashboard los lee automáticamente.

---

## ⚠️ Notas Importantes

1. **Testnet = Dinero Ficticio**
   - No pierdes dinero real
   - Perfecto para probar estrategias
   - Binance te da balance ilimitado

2. **Timeframe = 1 hora**
   - El bot analiza velas de 1 hora
   - Espera ~1 hora entre señales
   - Para timeframes menores, modifica `config_15min.json`

3. **Threshold Alto = Pocos Trades**
   - Threshold 70% → Muy selectivo (pocas señales)
   - Threshold 60% → Más trades, menos confianza
   - Encuentra el balance óptimo

4. **Pasar a Dinero Real**
   - Solo cuando tengas:
     - Win Rate > 50% consistente (2+ semanas)
     - Profit Factor > 2.0
     - Balance positivo en testnet
   - Cambia `testnet: false` en config
   - **¡MUCHA PRECAUCIÓN!**

---

## 🎓 Próximos Pasos

1. **Optimizar el modelo**:
   ```bash
   python model_pipeline_complete.py  # Re-entrena con datos nuevos
   ```

2. **Analizar resultados**:
   - Revisa trades en `logs/live_trades.csv`
   - Identifica patrones de éxito/fracaso
   - Ajusta threshold y SL/TP

3. **Cuando estés listo para dinero real**:
   - Cambia `testnet: false`
   - Usa API keys de producción
   - Reduce position_size_usd inicialmente
   - Monitorea constantemente

---

## 💡 Tips

- Deja el dashboard abierto con auto-refresh activado
- Verifica los logs regularmente
- Ajusta parámetros según los resultados
- No hagas cambios drásticos sin probar en testnet
- Ten paciencia: el trading algorítmico requiere tiempo

---

¿Dudas? Revisa los logs en el dashboard o el archivo `logs/trading_bot.log`.
