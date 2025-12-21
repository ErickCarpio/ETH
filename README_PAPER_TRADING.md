# 📊 Paper Trading - Guía de Uso

Sistema de trading simulado en tiempo real para probar el bot sin riesgo.

## 🎯 ¿Qué es Paper Trading?

Opera con **datos reales de Binance** pero sin dinero real:
- Usa el modelo entrenado para generar señales
- Ejecuta trades simulados (LONG/SHORT)
- Aplica TP/SL configurados
- Guarda historial en `logs/trades_history.csv`
- El dashboard se actualiza automáticamente

## 🚀 Inicio Rápido

### 1. Entrenar el modelo primero

```bash
python model_pipeline_complete.py
```

Esto generará `models/xgboost_model.json`

### 2. Ejecutar el Paper Trading Bot

```bash
python paper_trading_bot.py
```

Verás output como:

```
🤖 Inicializando Paper Trading Bot...
✓ Symbol: ETHUSDT
✓ Timeframe: 1h
✓ Threshold: 70%
✓ SL: 2.0% | TP: 5.0%
✓ Balance inicial: $10000.00

🚀 Paper Trading Bot iniciado
⏱️ Comprobando mercado cada 60s

============================================================
🔄 Iteración #1 - 2025-12-21 12:00:00
============================================================
📊 Precio actual: $3500.00
🔮 Señal: 1 (confianza: 75.2%)
📈 LONG abierto @ $3500.00 (confianza: 75.2%)
```

### 3. Visualizar en el Dashboard

En otra terminal:

```bash
streamlit run web_dashboard.py
```

El dashboard mostrará:
- Trades en tiempo real conforme se ejecutan
- Gráfico con marcas de entrada/salida
- Estadísticas actualizadas cada 10 segundos

## ⚙️ Configuración

Edita `config_15min.json` para ajustar:

```json
{
  "trading": {
    "prediction_threshold": 0.70,    // Confianza mínima (70%)
    "stop_loss_pct": 0.02,           // Stop Loss 2%
    "take_profit_pct": 0.05,         // Take Profit 5%
    "position_size_usd": 100         // Tamaño de posición
  }
}
```

## 📊 Archivos Generados

- `logs/trades_history.csv`: Historial de todos los trades
  - Columnas: entry_time, exit_time, direction, entry_price, exit_price, pnl_pct, exit_reason

## 🛑 Detener el Bot

Presiona `Ctrl+C` para detener el bot de forma segura.

El bot cerrará cualquier posición abierta y mostrará un resumen final:

```
📊 RESUMEN FINAL
Total trades: 15
Win rate: 53.3%
Balance final: $10,245.00
P&L total: +$245.00
```

## ⚡ Modo Avanzado

### Cambiar intervalo de comprobación

Por defecto el bot comprueba el mercado cada 60 segundos. Para timeframe 1h puedes aumentarlo:

```python
# Comprobar cada 5 minutos
bot.run(interval_seconds=300)
```

### Balance inicial personalizado

Modifica `paper_trading_bot.py`:

```python
self.balance = 50000  # $50,000 inicial
```

## 📈 Mejores Prácticas

1. **Déjalo correr 24-48h**: Necesitas varios trades para evaluar performance
2. **Ajusta threshold**: Si hay muy pocos trades, baja el threshold (ej: 0.65)
3. **Optimiza TP/SL**: Usa los resultados del pipeline para encontrar mejores valores
4. **Monitorea win rate**: Apunta a 50%+ para rentabilidad con TP=5%, SL=2%

## 🔍 Troubleshooting

**Error: "Modelo no encontrado"**
- Ejecuta `python model_pipeline_complete.py` primero

**Sin señales generadas**
- Threshold muy alto → Bájalo a 0.65 o 0.60
- Mercado lateral → Normal, esperar volatilidad

**Dashboard no muestra trades**
- Verifica que `logs/trades_history.csv` existe
- Refresca el dashboard (Ctrl+C y reiniciar)

## ⏭️ Próximos Pasos

Una vez tengas buenos resultados en paper trading (Win Rate 50%+, Profit Factor >2):

1. **Testnet de Binance**: Opera en testnet con API keys de prueba
2. **Trading Real**: Usa cantidades pequeñas ($10-50) primero
3. **Diversificación**: Prueba otros pares (BTC, SOL, etc.)

---

💡 **Recuerda**: Paper trading es simulación. Los resultados reales pueden variar por slippage, fees y liquidez.
