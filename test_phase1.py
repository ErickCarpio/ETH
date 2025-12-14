"""
Test script para Fase 1 - Infraestructura de Tiempo Real

Demuestra el funcionamiento de todos los componentes:
- WebSocket Manager
- Order Book Reconstructor
- Microstructure Features
- Realtime Data Manager

NO requiere QuestDB instalado (storage deshabilitado por defecto)
"""

import asyncio
import logging
from data.managers.realtime_data_manager import RealtimeDataManager

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def on_features_update(features: dict):
    """
    Callback que se ejecuta cada vez que se calculan nuevas features
    (aproximadamente cada 1 segundo)
    """
    print("\n" + "="*70)
    print("📊 MICROSTRUCTURE FEATURES UPDATE")
    print("="*70)

    # Features básicas
    print(f"\n🎯 PRECIOS:")
    print(f"   Mid Price:    ${features.get('mid_price', 0):>10.2f}")
    print(f"   Micro Price:  ${features.get('micro_price', 0):>10.2f}")
    print(f"   Spread:       ${features.get('spread', 0):>10.4f}")

    spread_bps = None
    if features.get('spread') and features.get('mid_price'):
        spread_bps = (features['spread'] / features['mid_price']) * 10000
    print(f"   Spread (bps): {spread_bps:>10.2f}" if spread_bps else "   Spread (bps):        N/A")

    # Order Book Imbalance
    print(f"\n📈 ORDER BOOK IMBALANCE (OBI):")
    print(f"   OBI (5 levels):  {features.get('obi_5', 0):>8.4f}")
    print(f"   OBI (10 levels): {features.get('obi_10', 0):>8.4f}")
    print(f"   OBI (20 levels): {features.get('obi_20', 0):>8.4f}")

    # Interpretar OBI
    obi = features.get('obi_5', 0)
    if obi > 0.1:
        interpretation = "🟢 PRESIÓN COMPRADORA (más bids)"
    elif obi < -0.1:
        interpretation = "🔴 PRESIÓN VENDEDORA (más asks)"
    else:
        interpretation = "⚖️  EQUILIBRADO"
    print(f"   Interpretación: {interpretation}")

    # Order Flow Imbalance
    print(f"\n💹 ORDER FLOW IMBALANCE (OFI):")
    ofi = features.get('ofi', 0)
    print(f"   OFI: {ofi:>8.4f}")
    if ofi > 0:
        print(f"   Interpretación: 🟢 Flujo de COMPRA dominante")
    elif ofi < 0:
        print(f"   Interpretación: 🔴 Flujo de VENTA dominante")
    else:
        print(f"   Interpretación: ⚖️  Sin flujo neto")

    # VPIN
    vpin = features.get('vpin', 0)
    if vpin > 0:
        print(f"\n🎲 VPIN (Informed Trading Probability):")
        print(f"   VPIN: {vpin:>8.4f}")

        if vpin > 0.5:
            print(f"   Interpretación: ⚠️  ALTA probabilidad de trading informado")
        elif vpin > 0.3:
            print(f"   Interpretación: ⚠️  MEDIA probabilidad de trading informado")
        else:
            print(f"   Interpretación: ✅ Trading normal")

    # Kyle's Lambda
    kyle = features.get('kyle_lambda', 0)
    if kyle and abs(kyle) > 0:
        print(f"\n🔬 KYLE'S LAMBDA (Price Impact):")
        print(f"   Lambda: {kyle:>8.6f}")
        print(f"   Interpretación: Por cada 1 ETH comprado, el precio sube ~${abs(kyle):.6f}")

    # Roll Spread
    roll = features.get('roll_spread', 0)
    if roll and roll > 0:
        print(f"\n📏 ROLL SPREAD (Bid-Ask Bounce):")
        print(f"   Roll Spread: ${roll:>8.4f}")

    print("\n" + "="*70 + "\n")


async def main():
    """
    Función principal que ejecuta el test
    """
    symbol = "ETHUSDT"
    duration = 60  # segundos

    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║               FASE 1 - TEST DE INFRAESTRUCTURA                    ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print()
    print(f"📡 Symbol: {symbol}")
    print(f"⏱️  Duration: {duration} segundos")
    print(f"🔌 WebSocket: Binance depth@100ms + aggTrade")
    print(f"💾 Storage: Deshabilitado (no requiere QuestDB)")
    print()
    print("Iniciando en 3 segundos...")
    print()

    await asyncio.sleep(3)

    # Crear Realtime Data Manager
    manager = RealtimeDataManager(
        symbol=symbol,
        enable_storage=False,  # Deshabilitar storage para el test
        enable_trades=True,    # Habilitar trades para VPIN
        storage_batch_interval=10
    )

    # Registrar callback
    manager.register_feature_callback(on_features_update)

    # Iniciar manager
    logger.info("🚀 Iniciando Realtime Data Manager...")
    await manager.start()

    # Monitorear durante `duration` segundos
    print(f"\n⏳ Monitoreando por {duration} segundos...\n")

    for i in range(duration):
        await asyncio.sleep(1)

        # Cada 10 segundos, mostrar stats
        if (i + 1) % 10 == 0:
            stats = manager.get_stats()
            print("\n" + "-"*70)
            print(f"📊 ESTADÍSTICAS (t={i+1}s)")
            print("-"*70)
            print(f"   Depth Updates:     {stats['total_depth_updates']:>6}")
            print(f"   Trades:            {stats['total_trades']:>6}")
            print(f"   Features Calc:     {stats['total_features_calculated']:>6}")
            print(f"   Updates/sec:       {stats['depth_updates_per_sec']:>6.1f}")
            print(f"   Trades/sec:        {stats['trades_per_sec']:>6.2f}")

            ob_stats = stats['orderbook_stats']
            print(f"\n   Order Book:")
            print(f"     - Sincronizado:  {ob_stats['is_synchronized']}")
            print(f"     - Total updates: {ob_stats['total_updates']}")
            print(f"     - Desync count:  {ob_stats['desync_count']}")

            # Mostrar current order book
            orderbook = manager.get_orderbook()
            best_bid = orderbook.get_best_bid()
            best_ask = orderbook.get_best_ask()

            if best_bid and best_ask:
                print(f"\n   Best Levels:")
                print(f"     - Bid: ${best_bid[0]:.2f} x {best_bid[1]:.2f} ETH")
                print(f"     - Ask: ${best_ask[0]:.2f} x {best_ask[1]:.2f} ETH")

            print("-"*70 + "\n")

    # Detener manager
    logger.info("🛑 Deteniendo Realtime Data Manager...")
    await manager.stop()

    # Estadísticas finales
    print("\n" + "="*70)
    print("📊 ESTADÍSTICAS FINALES")
    print("="*70)

    final_stats = manager.get_stats()

    print(f"\n⏱️  UPTIME:")
    print(f"   Total: {final_stats['uptime_seconds']:.1f} segundos")

    print(f"\n📈 THROUGHPUT:")
    print(f"   Depth Updates:     {final_stats['total_depth_updates']}")
    print(f"   Trades:            {final_stats['total_trades']}")
    print(f"   Features Calc:     {final_stats['total_features_calculated']}")
    print(f"   Updates/sec:       {final_stats['depth_updates_per_sec']:.2f}")
    print(f"   Trades/sec:        {final_stats['trades_per_sec']:.2f}")

    print(f"\n📊 ORDER BOOK:")
    ob_stats = final_stats['orderbook_stats']
    print(f"   Sincronizado:      {ob_stats['is_synchronized']}")
    print(f"   Total snapshots:   {ob_stats['total_snapshots']}")
    print(f"   Total updates:     {ob_stats['total_updates']}")
    print(f"   Desync events:     {ob_stats['desync_count']}")

    print(f"\n✅ FEATURES ACTUALES:")
    current_features = manager.get_current_features()
    if current_features:
        print(f"   Mid Price:         ${current_features.get('mid_price', 0):.2f}")
        print(f"   OBI (5):           {current_features.get('obi_5', 0):.4f}")
        print(f"   OFI:               {current_features.get('ofi', 0):.4f}")
        vpin = current_features.get('vpin', 0)
        print(f"   VPIN:              {vpin:.4f}" if vpin > 0 else "   VPIN:              N/A (calculando...)")

    print("\n" + "="*70)
    print("✅ Test completado exitosamente!")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrumpido por el usuario")
    except Exception as e:
        logger.error(f"❌ Error en test: {e}", exc_info=True)
