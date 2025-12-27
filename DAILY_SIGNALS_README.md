# 📊 Sistema de Señales Diarias

Sistema automatizado para generar señales de trading diarias en múltiples pares de criptomonedas.

## 🎯 Ventajas

- ✅ **No requiere PC encendida 24/7** - Ejecuta 1 vez al día
- ✅ **Múltiples pares** - Analiza los 20 pares con más volumen de Binance
- ✅ **Revisión manual** - Tú decides qué señales ejecutar
- ✅ **Gestión de riesgo** - Calcula automáticamente TP y SL
- ✅ **Sin riesgo** - Funciona con Binance Demo (dinero ficticio)

---

## 📋 Uso Diario (Recomendado)

### 1. Generar Señales (1 vez al día)

```bash
python daily_signals.py
```

Esto analiza los **20 pares más líquidos** y genera un archivo CSV con las señales.

**Ejemplo de salida:**
```
📊 SEÑALES DIARIAS - 2025-01-15 08:00:00
================================================================================

🎯 SEÑALES DE ALTA CONFIANZA (>=70%):
timestamp            symbol      direction  confidence  current_price  entry     stop_loss  take_profit  risk_reward
2025-01-15 08:00:00  BTC/USDT   LONG       0.82        43500.00       43500.00  42630.00   45675.00     2.5
2025-01-15 08:00:00  ETH/USDT   SHORT      0.75        3050.00        3050.00   3111.00    2897.50      2.5

📈 TODAS LAS SEÑALES (20):
... (lista completa)

📁 Archivo guardado: signals/signals_20250115_080000.csv
```

### 2. Revisar Señales

Abre el archivo CSV generado en `signals/` y revisa:
- **Confianza** - Solo ejecuta señales con >70% de confianza
- **Dirección** - LONG o SHORT
- **Precio de entrada** - Precio actual del mercado
- **Stop Loss** - Nivel de pérdida máxima
- **Take Profit** - Objetivo de ganancia

### 3. Ejecutar Señales (Opcional - Manual)

Tienes 2 opciones:

#### Opción A: Ejecutar Manualmente en Binance
1. Ve a [Binance Demo](https://testnet.binancefuture.com/)
2. Crea las órdenes manualmente según las señales
3. Configura TP y SL

#### Opción B: Ejecutar con Script (Automático)

```bash
# Ver qué se ejecutaría (sin ejecutar)
python execute_signals.py signals/signals_20250115_080000.csv --dry-run

# Ejecutar solo señales con confianza >= 70%
python execute_signals.py signals/signals_20250115_080000.csv --min-confidence 0.70

# Ejecutar solo señales con confianza >= 80%
python execute_signals.py signals/signals_20250115_080000.csv --min-confidence 0.80
```

---

## 🔧 Opciones Avanzadas

### Analizar Solo N Pares

```bash
# Top 10 pares
python daily_signals.py --pairs 10

# Top 50 pares
python daily_signals.py --pairs 50
```

### Usar Configuración Personalizada

```bash
python daily_signals.py --config mi_config.json
```

---

## 📁 Estructura de Archivos

```
ETH/
├── daily_signals.py          # Generador de señales
├── execute_signals.py        # Ejecutor de señales (opcional)
├── signals/                  # Directorio de señales generadas
│   ├── signals_20250115_080000.csv
│   ├── signals_20250116_080000.csv
│   └── executed_20250115_090000.csv  # Log de ejecuciones
├── config_15min.json         # Configuración
└── models/
    └── xgboost_model.pkl     # Modelo ML
```

---

## 📊 Formato del CSV de Señales

| Columna       | Descripción                          |
|---------------|--------------------------------------|
| timestamp     | Fecha y hora de la señal             |
| symbol        | Par de trading (ej: BTC/USDT)        |
| direction     | LONG o SHORT                         |
| confidence    | Confianza del modelo (0.0 - 1.0)     |
| current_price | Precio actual del mercado            |
| entry         | Precio de entrada sugerido           |
| stop_loss     | Nivel de Stop Loss                   |
| take_profit   | Nivel de Take Profit                 |
| risk_reward   | Ratio Riesgo/Beneficio               |

---

## 🎓 Workflow Recomendado

### Cada Mañana (8:00 AM):

1. **Generar señales:**
   ```bash
   python daily_signals.py
   ```

2. **Revisar señales de alta confianza** (>70%)

3. **Analizar contexto del mercado:**
   - Noticias importantes
   - Tendencia general del mercado
   - Correlaciones entre pares

4. **Seleccionar 3-5 mejores señales**

5. **Ejecutar trades** (manual o con script)

6. **Configurar alertas de TP/SL** en Binance

### Durante el Día:

- Monitorear posiciones abiertas
- Ajustar SL si es necesario (trailing stop)
- Cerrar parcialmente en niveles intermedios

### Antes de Dormir:

- Revisar estado de posiciones
- Asegurar que todos los SL estén configurados

---

## ⚠️ Importante

1. **Modo Demo por Defecto**: El sistema usa Binance Demo (testnet) con dinero ficticio
2. **Diversificación**: No pongas todo tu capital en un solo par
3. **Gestión de Riesgo**: Nunca arriesgues más del 1-2% de tu capital por trade
4. **Threshold de Confianza**: Solo ejecuta señales con confianza >= 70%
5. **Stop Loss Obligatorio**: SIEMPRE configura el SL antes de ejecutar

---

## 🔮 Próximas Mejoras

### Fase 2: Re-entrenar con Múltiples Pares

Para mejorar las predicciones en todos los pares:

1. Descargar datos históricos de los 20 pares
2. Re-entrenar el modelo con todos los pares
3. Agregar features específicas por par (correlaciones, dominancia BTC, etc.)

**¿Quieres implementar esto?** El modelo actual funciona, pero entrenar con múltiples pares mejorará las predicciones.

---

## 🆘 Troubleshooting

**Error: "No hay señales con confianza >= 70%"**
- Es normal, el mercado no siempre tiene oportunidades claras
- Puedes bajar el threshold a 60% temporalmente
- Considera esperar al día siguiente

**Error: "API keys inválidas"**
- Verifica que uses las keys de Binance Demo (testnet)
- Regenera las keys en https://testnet.binancefuture.com/

**Error: "Modelo no encontrado"**
- Verifica que existe `models/xgboost_model.pkl`
- Ajusta la ruta en `config_15min.json`

---

## 📞 Soporte

Si tienes problemas, revisa:
1. Logs en la consola
2. Archivos generados en `signals/`
3. Configuración en `config_15min.json`

---

**Happy Trading! 🚀**
