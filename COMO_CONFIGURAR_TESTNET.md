# 🧪 Cómo Configurar Binance Testnet

El bot ahora soporta **3 modos de trading**. Esta guía te muestra cómo configurar **Testnet de Binance** (dinero ficticio).

---

## 🎯 Los 3 Modos de Trading

| Modo | Descripción | Conexión | Riesgo |
|------|-------------|----------|--------|
| **🧪 Testnet Binance** | Dinero ficticio de Binance | testnet.binancefuture.com | ✅ Sin riesgo |
| **🖥️ Paper Trading** | Simulación local | Solo lectura de precios | ✅ Sin riesgo |
| **🔥 Real Trading** | Dinero real | binance.com | ⚠️ RIESGO REAL |

---

## ✅ PASO 1: Obtener API Keys de Testnet

### 1.1 Ve a Binance Testnet Futures

Abre en tu navegador:
```
https://testnet.binancefuture.com
```

### 1.2 Crea una Cuenta (Gratis)

- No requiere verificación KYC
- No necesitas depositar dinero real
- Binance te da balance ficticio ilimitado

### 1.3 Genera API Keys

1. Click en tu perfil (esquina superior derecha)
2. Selecciona **"API Management"**
3. Click en **"Create API Key"**
4. Copia las keys generadas:
   - **API Key** (empieza con letras y números)
   - **Secret Key** (más larga, guárdala de forma segura)

⚠️ **IMPORTANTE**: Estas keys son SOLO para testnet. No funcionan en producción.

---

## ✅ PASO 2: Configurar las API Keys

Tienes **2 formas** de configurar las keys:

### Opción A: Desde el Dashboard (Recomendado)

1. Ejecuta el dashboard:
   ```bash
   streamlit run web_dashboard.py
   ```

2. En el **sidebar**, selecciona:
   - **Modo de Trading:** "Testnet Binance (Dinero Ficticio)"

3. Aparecerán campos para:
   - **Testnet API Key**
   - **Testnet API Secret**

4. Pega tus keys copiadas

5. Click en **"💾 Aplicar Cambios"**

### Opción B: Editar config_15min.json

Abre `config_15min.json` y edita:

```json
{
  "exchange": {
    "testnet": true,
    "paper_trading": false,

    "testnet_api_key": "TU_API_KEY_AQUI",
    "testnet_api_secret": "TU_SECRET_KEY_AQUI"
  }
}
```

---

## ✅ PASO 3: Verificar Configuración

### 3.1 Verifica el Balance en Testnet

Ve a https://testnet.binancefuture.com y revisa:
- **Wallet → Futures**: Debes ver balance ficticio (ej: 10,000 USDT)

### 3.2 Verifica Conexión del Bot

Inicia el dashboard y haz click en **"▶️ Iniciar"**.

En los **Logs del Bot** deberías ver:

```
🧪 Modo TESTNET BINANCE (Dinero Ficticio - Sin Riesgo)
   Conectando a testnet.binancefuture.com
✓ Conectado a Binance Testnet
✓ Margin Mode: ISOLATED
✓ Leverage configurado: 1x
✓ Balance Testnet USDT: $10000.00

==================================================
📊 CONFIGURACIÓN DE TRADING:
   Modo: TESTNET BINANCE (Dinero Ficticio)
   Mercado: FUTUROS (Futures)
   Símbolo: ETHUSDT
   Leverage: 1x
   Margin Mode: ISOLATED
   Tamaño por posición: $100 USD
   Stop Loss: 2.0%
   Take Profit: 5.0%
==================================================
```

Si ves esos mensajes, **¡felicidades! Estás conectado al testnet**.

---

## 🎓 Configuración de Leverage y Margen

### Configurar desde el Dashboard

En el sidebar puedes ajustar:

#### 1️⃣ Apalancamiento (Leverage)
- **1x**: Sin apalancamiento (RECOMENDADO para empezar)
- **2-3x**: Bajo riesgo
- **5-10x**: Riesgo medio (requiere experiencia)
- **20-50x**: Alto riesgo (solo para expertos)

⚠️ **Con leverage 20x, un movimiento del 5% = liquidación total**

#### 2️⃣ Tipo de Margen
- **ISOLATED** ✅ (Recomendado): Solo pierdes el margen de esa posición
- **CROSS** ⚠️ (Peligroso): Puedes perder todo tu balance

#### 3️⃣ Tamaño de Posición
- Default: $100 USD por trade
- Ajusta según tu estrategia y tolerancia al riesgo

---

## 📊 Monitorear Trades en Testnet

### En el Dashboard

El dashboard muestra en tiempo real:
- 📈 Gráfico de precio con tus trades marcados
- 🎯 Posición abierta actual (LONG/SHORT)
- 💰 P&L acumulado
- 📊 Estadísticas (Win Rate, Profit Factor)
- 📝 Logs del bot

### En Binance Testnet

También puedes ver tus trades en:
```
https://testnet.binancefuture.com/futures/ETHUSDT
```

Verás:
- **Positions**: Posiciones abiertas
- **Open Orders**: Órdenes pendientes
- **Trade History**: Historial de trades

---

## 🔧 Solución de Problemas

### Error: "API keys de Testnet no configuradas"

**Solución:**
1. Verifica que las keys estén en `config_15min.json`
2. Asegúrate de que sean keys de **testnet**, no de producción
3. Confirma que `testnet: true` en el config

### Error: "Invalid API-key, IP, or permissions"

**Posibles causas:**
1. **Keys incorrectas**: Verifica que copiaste correctamente
2. **IP restriction**: En testnet, ve a API Management → Edit restrictions → Allow all IPs
3. **Permissions**: Asegúrate de que las keys tengan permisos de "Futures Trading"

### No aparecen trades en testnet

**Verificar:**
1. **Balance suficiente**: Debes tener al menos $100 USDT en testnet
2. **Threshold alto**: Baja el threshold de confianza en el dashboard
3. **No hay señales**: Es normal, espera a que el modelo detecte oportunidad

### Bot se conecta pero no ejecuta trades

**Revisar logs:**
- Busca el mensaje de confianza: "Confianza 65% < 70% - No operar"
- Si la confianza es menor al threshold, el bot no operará
- Ajusta el threshold en el dashboard (bájalo a 60-65% para más trades)

---

## 🎯 Primeros Pasos Recomendados

### 1. Configura Testnet con Valores Seguros

```json
{
  "trading": {
    "leverage": 1,              // Sin apalancamiento
    "margin_mode": "ISOLATED",  // Margen aislado
    "position_size_usd": 100,   // $100 por trade
    "prediction_threshold": 0.70 // 70% confianza mínima
  }
}
```

### 2. Deja el Bot Corriendo 24-48 Horas

- Monitorea el dashboard regularmente
- Revisa los logs para ver las predicciones
- Observa cómo se ejecutan los trades

### 3. Analiza Resultados

Después de 10-20 trades, revisa:
- **Win Rate**: ¿Más de 50%?
- **Profit Factor**: ¿Mayor a 1.5?
- **P&L Total**: ¿Positivo?

### 4. Ajusta Parámetros

Si los resultados son buenos:
- Puedes probar con leverage 2x-3x
- Ajustar SL/TP
- Modificar threshold

---

## ⚠️ Antes de Pasar a Dinero Real

Solo cambia a **Real Trading** cuando:

✅ **Win Rate > 55%** en testnet (mínimo 50 trades)
✅ **Profit Factor > 2.0** consistente
✅ **P&L positivo** durante 2+ semanas
✅ **Entiendes leverage y riesgos** completamente
✅ **Has probado diferentes condiciones de mercado** (alcista, bajista, lateral)

### Cómo Cambiar a Real Trading

1. En el dashboard, selecciona: **"Real Trading (Dinero Real)"**
2. Ingresa tus API keys de **producción** (binance.com)
3. **Reduce el tamaño de posición** inicialmente (ej: $20-50)
4. **Usa leverage 1x** siempre al principio
5. **Monitorea constantemente** - configura alertas

---

## 📚 Recursos

- **Testnet Binance Futures**: https://testnet.binancefuture.com
- **Documentación Binance API**: https://developers.binance.com/docs/derivatives/
- **Guía de Leverage**: Ver `EXPLICACION_FUTUROS_LEVERAGE.md`
- **Calculadora de Liquidación**: https://www.binance.com/en/futures/funding-history/perpetual/funding-fee-calculator

---

## 💡 Tips Finales

1. **Testnet es ilimitado**: Si pierdes todo el balance, Binance te recarga automáticamente
2. **Simula realismo**: Trata el dinero ficticio como si fuera real para aprender
3. **Practica gestión de riesgo**: No uses todo tu balance en un trade
4. **Documenta tus trades**: Anota qué funcionó y qué no
5. **Ten paciencia**: El trading algorítmico requiere tiempo y ajustes

---

**Última actualización:** 2025-12-21
**Configuración actual:** Testnet soportado con leverage configurable
