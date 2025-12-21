# 📈 ETH Trading Bot - Dashboard Web

## 🎯 Características

✅ **Visualización en Tiempo Real**
- Gráfico de velas (candlestick) interactivo
- Marcas de entradas/salidas del bot
- P&L acumulado en tiempo real
- Auto-actualización configurable

✅ **Métricas de Performance**
- Win Rate
- Profit Factor
- Total P&L
- Mejor/Peor trade

✅ **Control del Bot**
- Iniciar/Detener trading
- Ajustar threshold, TP/SL en vivo
- Configuración de timeframe

✅ **Historial de Trades**
- Tabla completa de todos los trades
- Filtros y búsqueda
- Exportable

---

## 🚀 Instalación

### 1. Instalar Dependencias

```powershell
pip install -r requirements_dashboard.txt
```

O manualmente:

```powershell
pip install streamlit plotly pandas numpy
```

### 2. Ejecutar Dashboard

```powershell
streamlit run web_dashboard.py
```

El navegador se abrirá automáticamente en: **http://localhost:8501**

---

## 📊 Cómo Usar

### **Panel Principal**

- **Gráfico Superior:** Precio + Marcas de Trades
  - 🔺 Verde arriba = LONG ganador
  - 🔻 Rojo abajo = SHORT perdedor
  - Línea punteada = Duración del trade

- **Gráfico Inferior:** Curva de P&L acumulado
  - Verde = Ganancia acumulada
  - Por encima de 0 = Rentable

### **Sidebar (Izquierda)**

- **▶️ Iniciar / ⏸️ Detener:** Control del bot
- **Threshold:** Nivel de confianza mínimo para operar
- **Stop Loss / Take Profit:** Ajustar en tiempo real
- **Timeframe:** Cuántas horas mostrar en el gráfico
- **Auto-actualizar:** Refrescar automáticamente cada N segundos

### **Métricas Superiores**

- **💵 Precio ETH:** Precio actual + cambio 24h
- **📊 Trades Totales:** Cantidad + Win Rate
- **💰 P&L Total:** Ganancia/pérdida acumulada
- **📈 Profit Factor:** Ratio ganancias/pérdidas
- **🧠 Modelo:** Estado del modelo (actualizado o no)

### **Tabla de Trades**

- Muestra todos los trades históricos
- Ordenable por columna
- Scroll infinito

---

## 🔧 Configuración Avanzada

### **Cambiar Puerto**

```powershell
streamlit run web_dashboard.py --server.port 8080
```

### **Modo Headless (Sin Navegador)**

```powershell
streamlit run web_dashboard.py --server.headless true
```

### **Exponer a la Red Local**

```powershell
streamlit run web_dashboard.py --server.address 0.0.0.0
```

Luego accede desde otro dispositivo: `http://<tu-ip>:8501`

---

## 📱 Características por Implementar

### **Próximas Versiones:**

- [ ] **Integración con Trading Real**
  - Conectar con `start_system.py`
  - Mostrar posiciones abiertas en vivo
  - Logs del bot en tiempo real

- [ ] **Alertas**
  - Notificaciones de trades
  - Alertas de precio
  - Warnings de drawdown

- [ ] **Analytics Avanzados**
  - Heatmap de horarios rentables
  - Análisis de drawdown
  - Sharpe ratio

- [ ] **Backtesting Interactivo**
  - Ejecutar backtest desde el dashboard
  - Comparar estrategias
  - Optimización de parámetros

- [ ] **Multi-timeframe**
  - Ver 15min, 1H, 4H simultáneamente
  - Sincronización de señales

---

## 🐛 Troubleshooting

### **Error: "Cannot import streamlit"**

```powershell
pip install --upgrade streamlit
```

### **Error: "No se puede conectar a localhost:8501"**

- Verifica que no hay otro proceso en el puerto 8501
- Cambia el puerto: `streamlit run web_dashboard.py --server.port 8080`

### **Dashboard no actualiza**

- Activa "🔄 Auto-actualizar" en el sidebar
- Ajusta el intervalo de refresh

### **No hay datos de precio**

- Ejecuta primero: `python model_pipeline_complete.py`
- Verifica que existe `data/cache/ETHUSDT_1h_*.parquet`

---

## 📚 Documentación

- **Streamlit:** https://docs.streamlit.io
- **Plotly:** https://plotly.com/python/

---

## 🤝 Contribuir

Para agregar nuevas features al dashboard:

1. Edita `web_dashboard.py`
2. Reinicia Streamlit (Ctrl+C y vuelve a ejecutar)
3. El dashboard se recarga automáticamente al guardar cambios

---

## 📞 Soporte

Si tienes problemas:
1. Verifica los logs de Streamlit en la terminal
2. Revisa que todas las dependencias estén instaladas
3. Asegúrate de tener datos en `data/cache/`

---

**¡Disfruta tu Dashboard de Trading! 🚀**
