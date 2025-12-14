import asyncio
from data.managers.realtime_data_manager import RealtimeDataManager

async def collect_data():
    print("🔄 Iniciando recolección de datos microestructurales...")
    print("📊 Guardando en QuestDB cada 10 segundos")
    print("⏱️  Déjalo corriendo al menos 1 hora (ideal: 24 horas)")
    print("⏹️  Presiona Ctrl+C para detener\n")
    
    manager = RealtimeDataManager(
        symbol='ETHUSDT',
        enable_storage=True,      # ← Ahora SÍ guardamos en QuestDB
        enable_trades=True,
        storage_batch_interval=10
    )
    
    await manager.start()
    
    try:
        # Correr indefinidamente hasta Ctrl+C
        while True:
            await asyncio.sleep(60)
            stats = manager.get_stats()
            print(f"\n⏱️  Uptime: {stats['uptime_seconds']/3600:.1f} horas")
            print(f"   Depth Updates: {stats['total_depth_updates']}")
            print(f"   Trades: {stats['total_trades']}")
            print(f"   Features Calc: {stats['total_features_calculated']}")
    
    except KeyboardInterrupt:
        print("\n\n🛑 Deteniendo recolección...")
        await manager.stop()
        print("✅ Datos guardados en QuestDB")

if __name__ == "__main__":
    asyncio.run(collect_data())
