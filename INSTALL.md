# Guía de Instalación - Fase 1

## Instalación Rápida

```bash
# Instalar dependencias básicas
pip install -r requirements.txt
```

## Instalación por Componentes

### 1. Dependencias Core (Obligatorias)

```bash
pip install ccxt>=4.0.0 xgboost>=2.0.0 optuna>=3.5.0 pandas>=2.0.0 numpy>=1.24.0 scikit-learn>=1.3.0
```

### 2. WebSocket & Async (Fase 1 - Obligatorias)

```bash
pip install websockets>=12.0 aiohttp>=3.9.0 asyncio-throttle>=1.0.0
```

### 3. QuestDB Storage (Opcional)

**Solo si quieres almacenar datos históricos:**

```bash
pip install psycopg2-binary>=2.9.0
```

**Nota:** Si no instalas `psycopg2-binary`, el sistema funcionará igual pero **sin storage** (datos solo en memoria).

### 4. ML & NLP (Opcional - Solo si usas FinBERT)

```bash
pip install transformers>=4.35.0 torch>=2.1.0 sentencepiece>=0.1.99
```

## Verificación de Instalación

```python
# Verificar componentes instalados
python -c "
import websockets
import aiohttp
print('✅ WebSocket dependencies OK')

try:
    import psycopg2
    print('✅ QuestDB storage available')
except ImportError:
    print('⚠️  QuestDB storage not available (optional)')

try:
    import torch
    from transformers import AutoTokenizer
    print('✅ FinBERT available')
except ImportError:
    print('⚠️  FinBERT not available (optional)')
"
```

## Configuración de QuestDB (Opcional)

### Opción A: Docker (Recomendado)

```bash
# Ya tienes docker-compose.yml en el repo
docker-compose up -d questdb

# Verificar que está corriendo
curl http://localhost:9000
```

QuestDB UI disponible en: http://localhost:9000

### Opción B: Instalación Manual

```bash
# Descargar QuestDB
wget https://github.com/questdb/questdb/releases/download/7.3.0/questdb-7.3.0-rt-linux-amd64.tar.gz
tar -xvf questdb-7.3.0-rt-linux-amd64.tar.gz
cd questdb-7.3.0-rt-linux-amd64

# Iniciar
./bin/questdb.sh start
```

## Testing sin QuestDB

El test funciona **sin QuestDB**:

```bash
python test_phase1.py
```

Esto ejecutará el sistema completo en modo **memoria solo** (sin persistencia).

## Testing con QuestDB

```bash
# 1. Iniciar QuestDB
docker-compose up -d questdb

# 2. Ejecutar test completo
python test_phase1.py

# El test detectará QuestDB automáticamente y guardará datos
```

## Troubleshooting

### Error: `ModuleNotFoundError: No module named 'psycopg2'`

**Solución 1 (Recomendada):** Instalar psycopg2-binary
```bash
pip install psycopg2-binary>=2.9.0
```

**Solución 2:** Ejecutar sin storage
- El sistema funcionará igual, solo que los datos no se guardarán en QuestDB
- Todas las features microestructurales se calculan en memoria

### Error: `ModuleNotFoundError: No module named 'websockets'`

```bash
pip install websockets>=12.0 aiohttp>=3.9.0
```

### Error: PyTorch DLL en Windows

```bash
# Instalar versión CPU-only (más ligera)
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

O simplemente deshabilitar FinBERT en `config.yaml`.

## Configuración Mínima (Sin Opcionales)

Si solo quieres probar el sistema básico:

```bash
# Solo lo esencial
pip install ccxt pandas numpy scikit-learn xgboost websockets aiohttp
```

Esto te permitirá:
- ✅ Trading básico
- ✅ WebSocket en tiempo real
- ✅ Order Book reconstruction
- ✅ Features microestructurales
- ❌ No FinBERT sentiment
- ❌ No QuestDB storage

## Verificación Final

```bash
# Test rápido (30 segundos)
python -c "
import asyncio
from data.managers.realtime_data_manager import RealtimeDataManager

async def test():
    mgr = RealtimeDataManager('ETHUSDT', enable_storage=False, enable_trades=False)
    await mgr.start()
    await asyncio.sleep(5)
    print('✅ Sistema funcionando')
    print(mgr.get_stats())
    await mgr.stop()

asyncio.run(test())
"
```

Si esto ejecuta sin errores, **tu instalación está completa** ✅
