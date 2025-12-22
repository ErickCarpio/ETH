# 🔑 Guía Rápida: Obtener API Keys de Binance Testnet

## 🎯 URL Correcta Actualizada

Binance cambió los endpoints de testnet:

| Tipo de Futures | Obtener API Keys | Endpoint del Bot |
|-----------------|------------------|------------------|
| **USDS-Margined** (ETHUSDT) | https://testnet.binancefuture.com | demo-fapi.binance.com ✅ |
| **Coin-Margined** (ETHUSD_PERP) | https://testnet.binancefuture.com | testnet.binancefuture.com |

**Tu bot usa ETHUSDT (USDS-Margined), así que se conecta automáticamente a `demo-fapi.binance.com`.**

---

## ✅ PASO 1: Crear Cuenta en Testnet (1 minuto)

### 1. Ve a:
```
https://testnet.binancefuture.com
```

### 2. Registrarse:
- Click en **"Register"** (esquina superior derecha)
- Ingresa un email (puede ser cualquiera, no se verifica)
- Crea una contraseña
- Click **"Create Account"**

### 3. Login:
- Ingresa tu email y contraseña
- Verás el trading interface de Binance Futures

---

## ✅ PASO 2: Obtener API Keys (2 minutos)

### 1. Ir a API Management:
- Click en tu **email** (esquina superior derecha)
- Selecciona **"API Management"** del menú

### 2. Crear API Key:
- Click en **"Create API"** o **"Generate HMAC_SHA256 Key"**
- Aparecerá un modal

### 3. Copiar las Keys:
```
API Key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Secret Key: yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
```

⚠️ **IMPORTANTE**:
- La **Secret Key** solo se muestra UNA VEZ
- Cópiala inmediatamente
- Si la pierdes, deberás crear un nuevo API key

### 4. Configurar Permisos (Opcional):
- Por defecto, las keys tienen permisos completos en testnet
- No necesitas configurar IP whitelist para testnet

---

## ✅ PASO 3: Configurar en el Bot

### Opción A: Desde el Dashboard (Recomendado)

1. **Ejecuta el dashboard:**
   ```powershell
   python -m streamlit run web_dashboard.py
   ```

2. **En el sidebar:**
   - Selecciona: **"Testnet Binance (Dinero Ficticio)"**

3. **Verás campos para API Keys:**
   ```
   🔑 API Keys Testnet
   Testnet API Key: [pega tu API Key aquí]
   Testnet API Secret: [pega tu Secret Key aquí]
   ```

4. **Pega tus keys** (las que copiaste en PASO 2)

5. **Click "💾 Aplicar Cambios"**

6. **Reinicia el bot:**
   - Detén el dashboard (Ctrl+C)
   - Ejecuta de nuevo: `python -m streamlit run web_dashboard.py`

### Opción B: Editar config_15min.json Manualmente

Abre `config_15min.json` y edita:

```json
{
  "exchange": {
    "testnet": true,
    "paper_trading": false,

    "testnet_api_key": "PEGA_TU_API_KEY_AQUI",
    "testnet_api_secret": "PEGA_TU_SECRET_KEY_AQUI"
  }
}
```

**Guarda** y **reinicia el dashboard**.

---

## ✅ PASO 4: Verificar Conexión

### Ejecuta el dashboard:
```powershell
python -m streamlit run web_dashboard.py
```

### Click "▶️ Iniciar"

### En los LOGS verás:

#### ✅ CORRECTO (Conexión exitosa):
```
INFO:__main__:🧪 Modo TESTNET BINANCE (Dinero Ficticio - Sin Riesgo)
INFO:__main__:   Conectando a testnet.binancefuture.com
INFO:__main__:✓ Conectado a Binance Testnet (demo-fapi.binance.com)
INFO:__main__:✓ Margin Mode: ISOLATED
INFO:__main__:✓ Leverage configurado: 1x
INFO:__main__:✓ Balance Testnet USDT: $100000.00
```

#### ❌ ERROR: Keys vacías
```
ERROR:__main__:❌ Error conectando exchange: binance {"code":-2008,"msg":"Invalid Api-Key ID."}
```
**Solución:** Las keys están vacías o incorrectas. Verifica que las pegaste correctamente en `config_15min.json`.

#### ❌ ERROR: Keys de producción
```
ERROR:__main__:❌ Error conectando exchange: binance {"code":-2015,"msg":"Invalid API-key, IP, or permissions for action."}
```
**Solución:** Estás usando API keys de **producción** (binance.com) en lugar de testnet. Debes crear keys en https://testnet.binancefuture.com.

---

## 🔍 Verificar Balance en Testnet

### En el Dashboard:
- Una vez conectado, verás tu balance en los logs: `✓ Balance Testnet USDT: $100000.00`

### En la Web de Testnet:
1. Ve a: https://testnet.binancefuture.com/en/futures/ETHUSDT
2. Login con tu cuenta
3. Click en **"Wallet"** → **"Futures"**
4. Deberías ver tu balance ficticio (generalmente $100,000 USDT)

---

## 🎓 Endpoints Técnicos (Para Desarrolladores)

Si necesitas conocer los endpoints exactos que usa el bot:

```python
# USDS-Margined Futures Testnet (ETHUSDT, BTCUSDT, etc)
BASE_URL = "https://demo-fapi.binance.com"

# Endpoints comunes:
MARKET_DATA = "https://demo-fapi.binance.com/fapi/v1/ticker/price"
ACCOUNT_INFO = "https://demo-fapi.binance.com/fapi/v2/account"
NEW_ORDER = "https://demo-fapi.binance.com/fapi/v1/order"
LEVERAGE = "https://demo-fapi.binance.com/fapi/v1/leverage"
MARGIN_TYPE = "https://demo-fapi.binance.com/fapi/v1/marginType"

# WebSocket (si se implementa en el futuro):
WS_URL = "wss://fstream.binancefuture.com/ws"
```

---

## 📊 Diferencias Testnet vs Producción

| Característica | Testnet | Producción |
|---------------|---------|------------|
| **Dinero** | Ficticio ilimitado | Real (tu dinero) |
| **API Keys** | De testnet.binancefuture.com | De binance.com |
| **Endpoint** | demo-fapi.binance.com | fapi.binance.com |
| **Recarga balance** | Automática si llegas a $0 | No, pierdes tu dinero |
| **Liquidez** | Limitada (puede haber menos órdenes) | Alta (mercado real) |
| **Slippage** | Puede ser diferente | Real del mercado |
| **Fees** | Simulados (0.04% maker, 0.04% taker) | Reales (0.02%-0.04%) |
| **Riesgo** | ✅ Cero | ⚠️ Alto |

---

## 🔐 Seguridad de API Keys

### Para Testnet (dinero ficticio):
- ✅ No necesitas IP whitelist
- ✅ Puedes compartir keys si necesitas ayuda (es dinero ficticio)
- ✅ No hay riesgo financiero

### Para Producción (dinero real):
- ⚠️ **NUNCA** compartas tus API keys
- ⚠️ **SIEMPRE** usa IP whitelist
- ⚠️ **SOLO** habilita permisos necesarios (trading, no withdrawal)
- ⚠️ Usa 2FA en tu cuenta de Binance

---

## 🆘 Solución de Problemas

### "Invalid Api-Key ID"
- **Causa:** Keys vacías o incorrectas
- **Solución:** Verifica que copiaste las keys correctamente

### "Invalid API-key, IP, or permissions"
- **Causa:** Usando keys de producción en testnet (o viceversa)
- **Solución:** Las keys de testnet SOLO funcionan en testnet

### "Unable to load markets"
- **Causa:** Problema de conexión a internet o endpoint incorrecto
- **Solución:** Verifica tu conexión y que el código esté actualizado

### Balance muestra $0
- **Causa:** Primera vez en testnet, balance no cargado
- **Solución:** Espera 1-2 minutos, Binance recarga automáticamente

---

## 📚 Referencias

- **Testnet Futures UI**: https://testnet.binancefuture.com
- **Documentación Oficial**: https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
- **Spot Testnet FAQ**: https://developers.binance.com/docs/binance-spot-api-docs/faqs/testnet
- **Quick Start Guide**: https://developers.binance.com/docs/derivatives/quick-start

---

**Última actualización:** 2025-12-21
**Endpoint correcto:** demo-fapi.binance.com ✅
**Commit:** 0a076c9
