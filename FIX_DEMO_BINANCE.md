# ✅ Fix Implementado: Conexión a Binance Demo Trading

## 🎯 Problema Resuelto

El bot intentaba conectarse al antiguo sistema de testnet de Binance usando `ccxt.binance()` con URLs manuales, pero las API keys de `demo.binance.com` no funcionaban con ese método.

**Error anterior:**
```
binance {"code":-2008,"msg":"Invalid Api-Key ID."}
```

## 🔧 Solución Implementada

Actualizado el código para usar el método correcto según la documentación de CCXT:

```python
# ❌ ANTES (Incorrecto)
self.exchange = ccxt.binance({
    'apiKey': testnet_api_key,
    'secret': testnet_api_secret,
    'urls': {
        'api': {
            'fapiPublic': 'https://demo-fapi.binance.com/fapi/v1',
            # ... más URLs manuales
        }
    }
})

# ✅ AHORA (Correcto)
self.exchange = ccxt.binanceusdm({
    'apiKey': testnet_api_key,
    'secret': testnet_api_secret,
    'enableRateLimit': True,
})
self.exchange.set_sandbox_mode(True)
```

## 📝 Cambios Realizados

### 1. `web_dashboard.py` (líneas 127-162)
- Cambiado `ccxt.binance()` → `ccxt.binanceusdm()`
- Agregado `set_sandbox_mode(True)` para activar modo demo
- Eliminadas configuraciones manuales de URLs
- Actualizados mensajes de log: "DEMO BINANCE" en lugar de "TESTNET BINANCE"

### 2. `verificar_testnet.py`
- Misma actualización que web_dashboard.py
- Eliminada PRUEBA 2 (antiguo endpoint testnet.binancefuture.com)
- Simplificado el script a una sola prueba con el método correcto
- Actualizados mensajes de error y diagnóstico

### 3. `config_15min.json`
- Actualizado comentario: `demo.binance.com` en lugar de `testnet.binancefuture.com`

## 🧪 Cómo Probar

### 1. Asegúrate de tener tus API keys configuradas

En `config_15min.json`:
```json
{
  "exchange": {
    "testnet": true,
    "paper_trading": false,
    "testnet_api_key": "TU_API_KEY_DE_DEMO_BINANCE",
    "testnet_api_secret": "TU_SECRET_KEY_DE_DEMO_BINANCE"
  }
}
```

### 2. Verifica la conexión con el script de diagnóstico

```bash
python verificar_testnet.py
```

**Salida esperada si funciona:**
```
======================================================================
🔍 VERIFICADOR DE CONEXIÓN BINANCE DEMO TRADING
======================================================================

📋 CONFIGURACIÓN ACTUAL:
   testnet: True
   paper_trading: False

🔑 VERIFICACIÓN DE API KEYS:
   ✓ testnet_api_key: xxxxxxxxxx...xxxxxxxxxx
   ✓ testnet_secret: yyyyyyyyyy...yyyyyyyyyy

🧪 PRUEBA 1: Conexión a demo.binance.com (USDT-Margined Futures)
----------------------------------------------------------------------
   Conectando y obteniendo balance...

   ✅ CONEXIÓN EXITOSA a demo.binance.com
   💰 Balance USDT: $100000.00
```

### 3. Ejecuta el bot

```bash
streamlit run web_dashboard.py
```

En el dashboard:
1. Selecciona: **"Testnet Binance (Dinero Ficticio)"**
2. Ingresa tus API keys de demo.binance.com (si no las guardaste en config)
3. Click **"💾 Aplicar Cambios"**
4. Click **"▶️ Iniciar"**

**Logs esperados:**
```
INFO: 🧪 Modo DEMO BINANCE (Dinero Ficticio - Sin Riesgo)
INFO:    Conectando a demo.binance.com
INFO: ✓ Conectado a Binance Demo Trading
INFO: ✓ Balance Demo USDT: $100000.00
INFO: ✓ Margin Mode: ISOLATED
INFO: ✓ Leverage configurado: 1x
```

## 📚 Referencias

- **CCXT Manual - Sandbox Mode**: https://github.com/ccxt/ccxt/wiki/Manual#sandbox-mode
- **CCXT Issue #26487**: https://github.com/ccxt/ccxt/issues/26487
- **Binance Demo Trading**: https://demo.binance.com
- **Binance Derivatives Docs**: https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info

## ⚠️ Importante

- Las API keys de **demo.binance.com** solo funcionan en modo demo
- Las API keys de **binance.com** (producción) NO funcionan en demo
- El método `ccxt.binanceusdm()` es específico para **USDT-Margined Futures**
- `set_sandbox_mode(True)` es NECESARIO para activar el modo demo

## 🎉 Resultado

Ahora el bot puede conectarse correctamente a Binance Demo Trading usando tus API keys de `demo.binance.com` y ejecutar trades con dinero ficticio.

---

**Última actualización:** 2025-12-22
**Commit:** 345a921
**Branch:** claude/review-code-errors-LsmkW
