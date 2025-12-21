# 🔧 Instrucciones para Actualizar el Código en Windows

Tu error dice que tienes cambios locales en `config_15min.json` que bloquean el pull. Vamos a actualizar sin perder tus cambios.

---

## ✅ Opción 1: PowerShell (Recomendado)

Abre **PowerShell** en tu carpeta del proyecto y ejecuta estos comandos **UNO POR UNO**:

### Paso 1: Guardar tus cambios locales
```powershell
git stash push -m "Mis cambios en config antes de actualizar"
```

### Paso 2: Descargar los últimos cambios
```powershell
git pull origin claude/review-code-errors-LsmkW
```

### Paso 3: Restaurar tus cambios
```powershell
git stash pop
```

---

## ⚠️ Si hay Conflictos en config_15min.json

Después del `git stash pop`, si ves un mensaje de conflicto:

1. **Abre `config_15min.json`** en tu editor
2. **Busca líneas** que empiecen con `<<<<<<<` y `>>>>>>>`
3. **Resuelve el conflicto** manualmente:
   - Líneas entre `<<<<<<< Updated upstream` y `=======` son la versión del repo
   - Líneas entre `=======` y `>>>>>>> Stashed changes` son tus cambios locales
4. **Elimina** los marcadores `<<<<<<<`, `=======`, `>>>>>>>`
5. **Guarda** el archivo

### Ejemplo de Conflicto:

```json
<<<<<<< Updated upstream
    "testnet": true,
    "paper_trading": false,
    "testnet_api_key": "",
    "testnet_api_secret": "",
=======
    "testnet": false,
    "paper_trading": true,
>>>>>>> Stashed changes
```

**Debes elegir una versión o combinar:**
```json
    "testnet": true,
    "paper_trading": false,
    "testnet_api_key": "TUS_KEYS_AQUI",
    "testnet_api_secret": "TU_SECRET_AQUI",
```

5. **Después de resolver**, ejecuta:
```powershell
git add config_15min.json
git stash drop
```

---

## ✅ Opción 2: Método Manual (Si lo anterior falla)

### Paso 1: Respaldar tu configuración
```powershell
copy config_15min.json config_15min_BACKUP.json
```

### Paso 2: Descartar cambios locales y actualizar
```powershell
git checkout -- config_15min.json
git pull origin claude/review-code-errors-LsmkW
```

### Paso 3: Copiar tus API keys del backup
1. Abre `config_15min_BACKUP.json`
2. Copia tus API keys si las tenías
3. Pégalas en el nuevo `config_15min.json` en la sección correcta:
   ```json
   "testnet_api_key": "TU_KEY_AQUI",
   "testnet_api_secret": "TU_SECRET_AQUI"
   ```

---

## 🎯 Después de Actualizar

### 1. Verificar que tienes los nuevos archivos:
```powershell
ls -Name COMO_CONFIGURAR_TESTNET.md, RESUMEN_TESTNET_IMPLEMENTADO.md
```

Deberías ver ambos archivos listados.

### 2. Verificar el código actualizado:

Abre `web_dashboard.py` y busca (Ctrl+F) la línea `109`. Deberías ver:

```python
# MODO 1: PAPER TRADING (Simulación Local)
if is_paper_trading:
    logger.info("🖥️ Modo PAPER TRADING (Simulación Local - Sin Riesgo)")
```

Si ves algo diferente, el código no se actualizó.

### 3. Reinicia el Dashboard:

1. **Detén** el dashboard (Ctrl+C en la terminal donde corre)
2. **Ejecuta** nuevamente:
   ```powershell
   python -m streamlit run web_dashboard.py
   ```

3. **Verás** la nueva interfaz con:
   - ✅ Radio selector de 3 modos (Testnet/Paper/Real)
   - ✅ Campos para API keys de Testnet
   - ✅ Configuración de Leverage y Margin visible

---

## 🔍 Verificar que Funcionó

### En el Sidebar del Dashboard, deberías ver:

```
⚙️ Configuración Futuros
────────────────────────

Modo de Trading:
○ Testnet Binance (Dinero Ficticio)  ← NUEVO
○ Paper Trading (Simulado Local)     ← NUEVO
○ Real Trading (Dinero Real)         ← NUEVO

Parámetros de Futuros:
Apalancamiento (Leverage): [1, 2, 3, 5, 10, 20, 50]
Tipo de Margen: [ISOLATED, CROSS]
Tamaño de Posición (USD): [10-1000]

🔑 API Keys Testnet    ← NUEVO (solo si seleccionas Testnet)
Testnet API Key: [campo de password]
Testnet API Secret: [campo de password]
```

Si NO ves esto, el código no se actualizó correctamente.

---

## 🆘 Si Nada Funciona

Como último recurso:

### 1. Guardar tus API keys
Abre `config_15min.json` y copia tus `testnet_api_key` y `testnet_api_secret` si las tienes.

### 2. Descargar todo de nuevo
```powershell
# Salir de la carpeta
cd ..

# Renombrar la carpeta actual
mv ETH ETH_OLD

# Clonar de nuevo
git clone https://github.com/ErickCarpio/ETH.git
cd ETH

# Cambiar a la branch correcta
git checkout claude/review-code-errors-LsmkW
```

### 3. Restaurar tus API keys
Pega tus API keys guardadas en el nuevo `config_15min.json`.

### 4. Instalar dependencias (por si acaso)
```powershell
pip install -r requirements.txt
```

---

## 📞 Si Sigues Teniendo Problemas

Mándame un screenshot de:
1. La salida del comando: `git status`
2. La salida del comando: `git log --oneline -5`
3. El sidebar del dashboard para ver si cambió

---

**Última actualización:** 2025-12-21
**Branch:** claude/review-code-errors-LsmkW
**Último commit:** 21b62aa
