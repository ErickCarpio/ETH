# 🗄️ Instalación de QuestDB - FASE 0

**Estado:** QuestDB NO está instalado en el sistema
**Acción requerida:** Instalación manual

---

## 📥 OPCIÓN 1: Instalación Rápida con Docker (RECOMENDADO)

```bash
# 1. Instalar Docker (si no está instalado)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 2. Ejecutar QuestDB
docker run -d \
  --name questdb \
  -p 9000:9000 \
  -p 9009:9009 \
  -p 8812:8812 \
  -p 9003:9003 \
  -v $(pwd)/questdb_data:/var/lib/questdb \
  questdb/questdb:latest

# 3. Verificar que está corriendo
docker ps | grep questdb

# 4. Acceder a la UI web
# http://localhost:9000

# 5. Verificar conexión PostgreSQL (puerto 8812)
docker logs questdb
```

**Puertos:**
- `9000` - Web Console (UI)
- `8812` - PostgreSQL wire protocol (usado por Python)
- `9009` - InfluxDB line protocol
- `9003` - Min health server

---

## 📥 OPCIÓN 2: Instalación Sin Docker

### Para Linux:

```bash
# 1. Descargar QuestDB
cd /tmp
wget https://github.com/questdb/questdb/releases/download/7.3.10/questdb-7.3.10-no-jre-bin.tar.gz

# 2. Extraer
tar -xzf questdb-7.3.10-no-jre-bin.tar.gz
sudo mv questdb-7.3.10-no-jre-bin /opt/questdb

# 3. Iniciar QuestDB
cd /opt/questdb
./questdb.sh start

# 4. Verificar que está corriendo
./questdb.sh status

# 5. Logs
tail -f /opt/questdb/log/questdb.log
```

### Para Mac:

```bash
# Usar Homebrew
brew install questdb

# Iniciar
questdb start

# Verificar
questdb status
```

### Para Windows:

```powershell
# Descargar desde: https://github.com/questdb/questdb/releases
# Extraer el ZIP
# Ejecutar: questdb.exe start
```

---

## ✅ VERIFICACIÓN POST-INSTALACIÓN

Una vez que QuestDB esté corriendo, ejecutar:

```bash
# 1. Verificar conexión
python verify_questdb.py

# 2. Inicializar tablas
python -c "
from data.storage.questdb_storage import QuestDBStorage
storage = QuestDBStorage()
storage.initialize_tables()
print('✅ Tablas creadas')
"

# 3. Verificar tablas en Web Console
# Ir a: http://localhost:9000
# Ejecutar SQL:
SHOW TABLES;

# Deberías ver:
# - orderbook_snapshots
# - microstructure_features
# - trades
# - funding_rates
# - liquidations
# - open_interest
```

---

## 🚀 SIGUIENTE PASO: Ejecutar Collectors

Una vez QuestDB esté corriendo y las tablas creadas:

```bash
# Terminal 1: Collector de Microestructura
python collect_microstructure.py

# Terminal 2: Collector de Derivatives
python collect_derivatives.py

# Esperar 10-60 minutos para acumular datos

# Verificar datos:
python verify_questdb.py
```

---

## 🔧 TROUBLESHOOTING

### Error: "Connection refused on port 8812"
**Causa:** QuestDB no está corriendo
**Solución:** Iniciar QuestDB (ver opciones arriba)

### Error: "psycopg2 not installed"
**Causa:** Librería Python faltante
**Solución:**
```bash
pip install psycopg2-binary
```

### Error: "Permission denied"
**Causa:** QuestDB necesita permisos para escribir
**Solución:**
```bash
# Docker:
sudo chown -R $(whoami):$(whoami) ./questdb_data

# Sin Docker:
sudo chown -R $(whoami):$(whoami) /opt/questdb
```

### QuestDB consume mucha RAM
**Solución:** Limitar memoria en Docker
```bash
docker run -d \
  --name questdb \
  --memory="2g" \
  --memory-swap="2g" \
  -p 9000:9000 -p 8812:8812 -p 9009:9009 \
  questdb/questdb:latest
```

---

## 📊 CONFIGURACIÓN RECOMENDADA

Editar `questdb_data/conf/server.conf`:

```properties
# Performance
cairo.max.uncommitted.rows=500000
cairo.commit.lag=5000

# PostgreSQL wire protocol
pg.enabled=true
pg.net.bind.to=0.0.0.0:8812

# Web Console
http.enabled=true
http.bind.to=0.0.0.0:9000

# Memory
shared.worker.count=4
```

---

## 🎯 CRITERIOS DE ÉXITO

QuestDB está listo cuando:

- ✅ `docker ps` muestra contenedor corriendo (o `questdb.sh status`)
- ✅ Web Console accesible en http://localhost:9000
- ✅ `python verify_questdb.py` conecta sin errores
- ✅ Comando `SHOW TABLES` muestra 6 tablas
- ✅ Collectors pueden escribir datos sin errores

---

**Estado actual:**
- ❌ QuestDB NO instalado
- ✅ psycopg2-binary instalado
- ✅ Collectors configurados (collect_microstructure.py, collect_derivatives.py)
- ✅ Script de verificación creado (verify_questdb.py)

**Acción inmediata:** Instalar QuestDB usando una de las opciones arriba
