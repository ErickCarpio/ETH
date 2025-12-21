# 🚨 CONFIGURACIÓN CRÍTICA: Futuros, Leverage y Margen

## ⚠️ PROBLEMA DETECTADO

Tu bot estaba operando en **Binance Futures** sin configuración explícita de:
- ❌ **Leverage** (apalancamiento)
- ❌ **Margin Mode** (tipo de margen)

Esto es **EXTREMADAMENTE PELIGROSO** porque Binance usa valores por defecto que pueden liquidar tu cuenta rápidamente.

---

## 📊 QUÉ ESTABA PASANDO (ANTES)

### Configuración por Defecto de Binance Testnet:
- **Leverage:** 20x (20 veces tu capital)
- **Margin Mode:** CROSS (puedes perder TODO tu balance)
- **Posición:** $100 USD

### Ejemplo de RIESGO:
```
Tu configuración: $100 USD por trade
Leverage 20x: Controlas $2,000 de ETH (20 veces más)

Si ETH se mueve 5% EN TU CONTRA:
- Pérdida: $2,000 × 5% = $100
- Resultado: LIQUIDACIÓN TOTAL (pierdes todo el margen)

Con leverage 20x, un movimiento del 5% = pérdida del 100%
```

---

## ✅ QUÉ SE ARREGLÓ (AHORA)

### Nueva Configuración en `config_15min.json`:

```json
"trading": {
  "leverage": 1,              // 1x = SIN apalancamiento (SEGURO)
  "margin_mode": "ISOLATED",  // Solo pierdes el margen de ESA posición
  "position_size_usd": 100    // $100 por trade
}
```

### Ahora con Leverage 1x:
```
Tu configuración: $100 USD por trade
Leverage 1x: Controlas $100 de ETH (sin apalancamiento)

Si ETH se mueve 5% EN TU CONTRA:
- Pérdida: $100 × 5% = $5
- Resultado: Pérdida controlada (solo -$5)

Con leverage 1x, un movimiento del 5% = pérdida del 5%
```

---

## 🎓 EXPLICACIÓN: Leverage (Apalancamiento)

### ¿Qué es el Leverage?

El leverage multiplica tu exposición al mercado:

| Leverage | Posición $100 | Controlas | Riesgo/Beneficio |
|----------|---------------|-----------|------------------|
| **1x** | $100 | $100 | **Normal** (recomendado) |
| **5x** | $100 | $500 | 5 veces más |
| **10x** | $100 | $1,000 | 10 veces más |
| **20x** | $100 | $2,000 | 20 veces más (PELIGROSO) |
| **50x** | $100 | $5,000 | 50 veces más (EXTREMO) |

### Ejemplos Reales:

#### Con Leverage 1x (SIN apalancamiento):
```
Precio ETH: $3,500
Posición: $100
Cantidad ETH: 0.0286 ETH

ETH sube a $3,675 (+5%):
- Ganancia: $5 (5%)

ETH baja a $3,325 (-5%):
- Pérdida: -$5 (5%)
```

#### Con Leverage 20x:
```
Precio ETH: $3,500
Posición: $100
Controlas: $2,000 de ETH (20x)
Cantidad ETH: 0.5714 ETH

ETH sube a $3,675 (+5%):
- Ganancia: $100 (100%) ← EXCELENTE
- Pero...

ETH baja a $3,325 (-5%):
- Pérdida: -$100 (100%) ← LIQUIDACIÓN TOTAL
```

### ⚠️ Liquidación:

Con leverage alto, si el precio se mueve en tu contra, **Binance cierra automáticamente tu posición** (liquidación) para protegerse.

**Precio de liquidación (aproximado):**
- Leverage 1x: Nunca (necesitas -100% para liquidar)
- Leverage 5x: -20% del precio
- Leverage 10x: -10% del precio
- Leverage 20x: **-5% del precio** ← MUY PELIGROSO

---

## 🎓 EXPLICACIÓN: Margin Mode (Tipo de Margen)

### ISOLATED vs CROSS:

| Característica | ISOLATED (✅ Recomendado) | CROSS (⚠️ Peligroso) |
|----------------|---------------------------|----------------------|
| **Margen usado** | Solo el de ESA posición | TODO tu balance |
| **Liquidación** | Pierdes solo esa posición | Pierdes TODO |
| **Riesgo** | Controlado | Extremo |
| **Ejemplo** | Trade malo = -$100 | Trade malo = -$1,000 (todo) |

### Ejemplo ISOLATED (SEGURO):

```
Balance total: $1,000
Trade 1: $100 en LONG ETH (ISOLATED)
Trade 2: $100 en LONG BTC (ISOLATED)

Si Trade 1 se liquida:
- Pierdes: Solo $100 (el margen de ese trade)
- Balance restante: $900
- Trade 2: Sigue activo sin afectarse
```

### Ejemplo CROSS (PELIGROSO):

```
Balance total: $1,000
Trade 1: $100 en LONG ETH (CROSS)
Trade 2: $100 en LONG BTC (CROSS)

Si Trade 1 va mal:
- Binance usa TODO tu balance para evitar liquidación
- Si no alcanza, LIQUIDA AMBOS TRADES
- Pierdes: Potencialmente TODO tu balance ($1,000)
```

---

## 📊 CONFIGURACIÓN ACTUAL DEL BOT

### En `config_15min.json`:

```json
{
  "exchange": {
    "testnet": true,           // ✅ Testnet (dinero ficticio)
    "symbol": "ETHUSDT"
  },

  "trading": {
    "leverage": 1,             // ✅ 1x = Sin apalancamiento
    "margin_mode": "ISOLATED", // ✅ Solo pierdes esa posición
    "position_size_usd": 100,  // $100 por trade
    "stop_loss_pct": 0.02,     // 2% Stop Loss
    "take_profit_pct": 0.05    // 5% Take Profit
  }
}
```

### Configuración SEGURA:
- ✅ **Testnet:** No es dinero real
- ✅ **Leverage 1x:** Sin apalancamiento
- ✅ **ISOLATED:** Solo arriesgas $100 por trade
- ✅ **SL 2%:** Pérdida máxima $2 por trade
- ✅ **TP 5%:** Ganancia objetivo $5 por trade

---

## 🛠️ CÓMO CAMBIAR EL LEVERAGE (Si lo necesitas)

### ⚠️ SOLO CAMBIA ESTO SI ENTIENDES LOS RIESGOS

Edita `config_15min.json`:

```json
"trading": {
  "leverage": 1,  // Cambia a 2, 3, 5, 10, 20, etc
  "margin_mode": "ISOLATED"  // SIEMPRE deja ISOLATED
}
```

### Recomendaciones por Experiencia:

| Experiencia | Leverage Recomendado | Razón |
|-------------|----------------------|-------|
| **Principiante** | 1x | Aprende sin riesgos grandes |
| **Intermedio** | 2-3x | Balance entre ganancia y riesgo |
| **Avanzado** | 5x | Requiere gestión de riesgo estricta |
| **Experto** | 10x+ | Solo si sabes lo que haces |

### ⚠️ NUNCA uses más de 5x si:
- Es dinero real
- No tienes experiencia
- No monitoreas 24/7
- No tienes Stop Loss estrictos

---

## 🔍 CÓMO VERIFICAR TU CONFIGURACIÓN

### En el Dashboard:

Cuando ejecutes `streamlit run web_dashboard.py`, verás en el **sidebar**:

```
⚙️ Configuración Futuros
────────────────────────
🧪 Testnet (Dinero Ficticio)

Mercado: Futuros (Futures)
Símbolo: ETHUSDT
Apalancamiento: 1x
Margen: ISOLATED
Posición: $100 USD
```

### En los Logs:

Cuando el bot inicie, verás:

```
==================================================
📊 CONFIGURACIÓN DE TRADING:
   Mercado: FUTUROS (Futures)
   Símbolo: ETHUSDT
   Leverage: 1x
   Margin Mode: ISOLATED
   Tamaño por posición: $100 USD
   Stop Loss: 2.0%
   Take Profit: 5.0%
   Threshold: 70%
==================================================
```

### Cuando Ejecute un Trade:

```
============================================================
🚀 TRADE EJECUTADO
   Dirección: LONG
   Precio: $3,500.00
   Cantidad ETH: 0.0286
   Margen usado: $100.00
   Leverage: 1x
   Valor nocional: $100.00 (controlando $100.00 de ETH)
   Stop Loss: $3,430.00 (2.0%)
   Take Profit: $3,675.00 (5.0%)
   Confianza ML: 75.0%
   Order ID: 12345678
============================================================
```

---

## 🚀 PASOS SIGUIENTES

### 1. Pull los cambios:
```bash
git pull origin claude/review-code-errors-LsmkW
```

### 2. **DETÉN** el bot si está corriendo:
- En el dashboard: Click "⏸️ Detener"
- O cierra completamente el dashboard

### 3. Verifica `config_15min.json`:
```bash
cat config_15min.json | grep -A 5 '"trading"'
```

Deberías ver:
```json
"leverage": 1,
"margin_mode": "ISOLATED",
```

### 4. Reinicia el dashboard:
```bash
streamlit run web_dashboard.py
```

### 5. Verifica en el sidebar:
- Debe decir **"Apalancamiento: 1x"**
- Debe decir **"Margen: ISOLATED"**

### 6. Inicia el bot:
- Click "▶️ Iniciar"
- Revisa los logs (sección "Logs del Bot" en el dashboard)
- Confirma que veas la configuración correcta

---

## ⚠️ ADVERTENCIAS FINALES

### SI VAS A USAR DINERO REAL:

1. **Testea primero en Testnet** durante al menos 1-2 semanas
2. **NUNCA** uses leverage > 3x con dinero real
3. **SIEMPRE** usa margin mode ISOLATED
4. **Empieza con posiciones pequeñas** ($10-$20)
5. **Monitorea constantemente** (alertas, logs, dashboard)

### SI QUIERES MÁS LEVERAGE:

1. **Entiende que puedes perder TODO** muy rápido
2. **Calcula tu precio de liquidación** antes de abrir trades
3. **Usa Stop Loss MUY ajustados** (1-2%)
4. **Monitorea 24/7** o usa bots especializados
5. **No inviertas más del 1-2% de tu capital** por trade

---

## 📚 RECURSOS

- [Binance: Qué es el Leverage](https://www.binance.com/en/support/faq/leverage-and-margin-in-futures-trading-360033162972)
- [Binance: ISOLATED vs CROSS](https://www.binance.com/en/support/faq/what-is-the-difference-between-isolated-margin-and-cross-margin-in-binance-futures-360033395152)
- [Calculadora de Liquidación](https://www.binance.com/en/futures/funding-history/perpetual/funding-fee-calculator)

---

## 🆘 SOPORTE

Si tienes dudas:
1. Lee esta guía completa
2. Prueba en Testnet primero
3. Revisa los logs del bot
4. Consulta la documentación de Binance

**NUNCA arriesges dinero que no puedes perder.**

---

**Última actualización:** 2025-12-21
**Configuración actual:** Leverage 1x + ISOLATED (SEGURO)
