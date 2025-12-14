"""
Historical Microstructure Data Generator
Descarga snapshots del Order Book y calcula features microestructurales aproximadas

NOTA: Esto NO es tan preciso como el stream real (100ms updates), pero:
- Permite entrenar el modelo sin esperar horas
- Usa datos históricos reales de Binance
- Calcula OBI, spread, micro-price (no VPIN/OFI porque necesitan stream)
"""

import asyncio
import ccxt.async_support as ccxt
import pandas as pd
from datetime import datetime, timedelta
import logging
from pathlib import Path
import time

from microstructure.features import MicrostructureFeatures

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HistoricalMicrostructureGenerator:
    """
    Genera datos microestructurales históricos usando snapshots del Order Book

    Limitaciones:
    - VPIN: No se puede calcular (requiere stream de trades)
    - OFI: No se puede calcular con precisión (requiere deltas del OB)
    - Kyle's Lambda: No se puede calcular (requiere secuencia de trades)
    - Roll Spread: Aproximación simple

    Lo que SÍ podemos calcular:
    - OBI (5/10/20 levels) ✅
    - Spread absoluto y relativo ✅
    - Micro-price ✅
    - Weighted mid-price ✅
    - Depth statistics ✅
    """

    def __init__(self, symbol: str = "ETH/USDT"):
        self.symbol = symbol
        self.exchange = None
        self.data_dir = Path("./data")
        self.data_dir.mkdir(exist_ok=True)

    async def initialize(self):
        """Inicializa exchange"""
        self.exchange = ccxt.binance({'enableRateLimit': True})
        logger.info("✅ Exchange inicializado")

    async def close(self):
        """Cierra exchange"""
        if self.exchange:
            await self.exchange.close()

    async def fetch_orderbook_snapshot(self, symbol: str, limit: int = 1000):
        """
        Obtiene un snapshot del Order Book

        Args:
            symbol: Par de trading (ETH/USDT)
            limit: Niveles del order book (max 5000)

        Returns:
            Dict con bids, asks, timestamp
        """
        try:
            ob = await self.exchange.fetch_order_book(symbol, limit=limit)
            return {
                'bids': ob['bids'],  # [[price, qty], ...]
                'asks': ob['asks'],
                'timestamp': ob['timestamp'] if ob['timestamp'] else int(time.time() * 1000),
                'datetime': datetime.fromtimestamp(
                    (ob['timestamp'] if ob['timestamp'] else int(time.time() * 1000)) / 1000
                )
            }
        except Exception as e:
            logger.error(f"Error fetching order book: {e}")
            return None

    def calculate_features_from_snapshot(self, ob_snapshot: dict) -> dict:
        """
        Calcula features microestructurales desde un snapshot

        Args:
            ob_snapshot: Snapshot del order book

        Returns:
            Dict con features calculadas
        """
        bids = ob_snapshot['bids']
        asks = ob_snapshot['asks']

        if not bids or not asks:
            return None

        # Convertir a dict {price: qty}
        bids_dict = {price: qty for price, qty in bids}
        asks_dict = {price: qty for price, qty in asks}

        # Calcular features básicas
        best_bid = bids[0]  # (price, qty)
        best_ask = asks[0]

        mid_price = (best_bid[0] + best_ask[0]) / 2.0
        spread = best_ask[0] - best_bid[0]
        spread_bps = (spread / mid_price) * 10000 if mid_price > 0 else 0

        # Micro-price (volume-weighted)
        micro_price = (
            (best_bid[0] * best_ask[1] + best_ask[0] * best_bid[1]) /
            (best_bid[1] + best_ask[1])
        ) if (best_bid[1] + best_ask[1]) > 0 else mid_price

        # OBI en múltiples niveles
        def calc_obi(levels):
            bid_vol = sum(qty for _, qty in bids[:levels])
            ask_vol = sum(qty for _, qty in asks[:levels])
            total = bid_vol + ask_vol
            return (bid_vol - ask_vol) / total if total > 0 else 0

        obi_5 = calc_obi(5)
        obi_10 = calc_obi(10)
        obi_20 = calc_obi(20)

        # Weighted mid-price
        def calc_weighted_mid(levels):
            bid_items = bids[:levels]
            ask_items = asks[:levels]

            bid_weighted = sum(p * q for p, q in bid_items)
            ask_weighted = sum(p * q for p, q in ask_items)

            bid_total_qty = sum(q for _, q in bid_items)
            ask_total_qty = sum(q for _, q in ask_items)

            total_qty = bid_total_qty + ask_total_qty

            return (bid_weighted + ask_weighted) / total_qty if total_qty > 0 else mid_price

        weighted_mid_5 = calc_weighted_mid(5)

        # Depth statistics
        bid_volume_5 = sum(qty for _, qty in bids[:5])
        ask_volume_5 = sum(qty for _, qty in asks[:5])
        bid_volume_10 = sum(qty for _, qty in bids[:10])
        ask_volume_10 = sum(qty for _, qty in asks[:10])

        return {
            'timestamp': ob_snapshot['datetime'],
            'mid_price': mid_price,
            'micro_price': micro_price,
            'spread': spread,
            'spread_bps': spread_bps,
            'obi_5': obi_5,
            'obi_10': obi_10,
            'obi_20': obi_20,
            'weighted_mid_5': weighted_mid_5,
            'bid_volume_5': bid_volume_5,
            'ask_volume_5': ask_volume_5,
            'bid_volume_10': bid_volume_10,
            'ask_volume_10': ask_volume_10,
            'best_bid_price': best_bid[0],
            'best_bid_qty': best_bid[1],
            'best_ask_price': best_ask[0],
            'best_ask_qty': best_ask[1],
        }

    async def generate_historical_data(
        self,
        hours: int = 24,
        interval_seconds: int = 300  # 5 minutos por defecto
    ) -> pd.DataFrame:
        """
        Genera datos históricos recolectando snapshots periódicamente

        Args:
            hours: Horas de datos a simular
            interval_seconds: Intervalo entre snapshots (min 1 segundo)

        Returns:
            DataFrame con features microestructurales
        """
        logger.info(f"🔄 Generando datos históricos...")
        logger.info(f"   Duración: {hours} horas")
        logger.info(f"   Intervalo: {interval_seconds} segundos")
        logger.info(f"   Total snapshots: ~{int((hours * 3600) / interval_seconds)}")

        await self.initialize()

        snapshots_data = []
        total_snapshots = int((hours * 3600) / interval_seconds)

        try:
            for i in range(total_snapshots):
                # Fetch snapshot
                ob = await self.fetch_orderbook_snapshot(self.symbol, limit=100)

                if ob:
                    # Calcular features
                    features = self.calculate_features_from_snapshot(ob)

                    if features:
                        snapshots_data.append(features)

                        if (i + 1) % 10 == 0:
                            logger.info(f"   Progress: {i+1}/{total_snapshots} snapshots")

                # Rate limiting (Binance permite ~1200/min, usamos ~12/min para estar seguros)
                await asyncio.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("\n⚠️  Interrumpido por usuario")
        finally:
            await self.close()

        # Convertir a DataFrame
        if snapshots_data:
            df = pd.DataFrame(snapshots_data)
            df.set_index('timestamp', inplace=True)

            logger.info(f"\n✅ Datos generados: {len(df)} snapshots")
            logger.info(f"   Período: {df.index[0]} a {df.index[-1]}")

            return df
        else:
            logger.error("❌ No se generaron datos")
            return pd.DataFrame()

    async def generate_and_save(
        self,
        hours: int = 24,
        interval_seconds: int = 300
    ):
        """
        Genera y guarda datos históricos

        Args:
            hours: Horas de datos
            interval_seconds: Intervalo entre snapshots
        """
        df = await self.generate_historical_data(hours, interval_seconds)

        if not df.empty:
            # Guardar
            symbol_safe = self.symbol.replace('/', '_')
            filename = f"microstructure_historical_{symbol_safe}.parquet"
            filepath = self.data_dir / filename

            df.to_parquet(filepath)
            logger.info(f"💾 Datos guardados: {filepath}")

            # CSV de respaldo
            df.to_csv(str(filepath).replace('.parquet', '.csv'))

            # Mostrar muestra
            logger.info(f"\n📊 Muestra de datos:")
            logger.info(f"\n{df.head()}")

            return df

        return None


async def quick_snapshot_demo():
    """
    Demo rápido: obtener UN snapshot y mostrar features
    """
    print("📸 DEMO: Snapshot actual del Order Book\n")

    generator = HistoricalMicrostructureGenerator("ETH/USDT")
    await generator.initialize()

    # Obtener snapshot
    ob = await generator.fetch_orderbook_snapshot("ETH/USDT", limit=20)

    if ob:
        # Calcular features
        features = generator.calculate_features_from_snapshot(ob)

        print(f"⏰ Timestamp: {features['timestamp']}")
        print(f"\n💰 PRECIOS:")
        print(f"   Mid Price:    ${features['mid_price']:.2f}")
        print(f"   Micro Price:  ${features['micro_price']:.2f}")
        print(f"   Spread:       ${features['spread']:.4f}")
        print(f"   Spread (bps): {features['spread_bps']:.2f}")

        print(f"\n📊 ORDER BOOK IMBALANCE:")
        print(f"   OBI (5):  {features['obi_5']:>7.4f}")
        print(f"   OBI (10): {features['obi_10']:>7.4f}")
        print(f"   OBI (20): {features['obi_20']:>7.4f}")

        if features['obi_5'] > 0.1:
            print(f"   → 🟢 Presión COMPRADORA")
        elif features['obi_5'] < -0.1:
            print(f"   → 🔴 Presión VENDEDORA")
        else:
            print(f"   → ⚖️  Equilibrado")

        print(f"\n📈 VOLUMEN (5 niveles):")
        print(f"   Bids: {features['bid_volume_5']:.2f} ETH")
        print(f"   Asks: {features['ask_volume_5']:.2f} ETH")

    await generator.close()


async def generate_training_data():
    """
    Genera datos para entrenar el modelo

    Opciones:
    1. Rápido: 1 hora, snapshot cada 5 min = 12 puntos
    2. Normal: 6 horas, snapshot cada 5 min = 72 puntos
    3. Completo: 24 horas, snapshot cada 5 min = 288 puntos
    """
    print("🎯 GENERAR DATOS HISTÓRICOS PARA ENTRENAMIENTO\n")
    print("Opciones:")
    print("1. Rápido    - 1 hora  (12 snapshots)   - ~1 minuto")
    print("2. Normal    - 6 horas (72 snapshots)   - ~6 minutos")
    print("3. Completo  - 24 horas (288 snapshots) - ~24 minutos")
    print("4. Extenso   - 7 días (2016 snapshots)  - ~3 horas")

    choice = input("\nElige opción (1-4): ").strip()

    hours_map = {'1': 1, '2': 6, '3': 24, '4': 168}
    hours = hours_map.get(choice, 6)

    print(f"\n🔄 Generando datos de {hours} horas...")
    print("⚠️  Esto va a tardar. Puedes presionar Ctrl+C para detener en cualquier momento.\n")

    generator = HistoricalMicrostructureGenerator("ETH/USDT")
    df = await generator.generate_and_save(
        hours=hours,
        interval_seconds=300  # 5 minutos
    )

    if df is not None:
        print(f"\n✅ COMPLETADO!")
        print(f"   Archivo: data/microstructure_historical_ETH_USDT.parquet")
        print(f"   Registros: {len(df)}")
        print(f"\n🎯 Ahora puedes ejecutar: python start_system.py")
    else:
        print(f"\n❌ Error generando datos")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        # Demo rápido
        asyncio.run(quick_snapshot_demo())
    else:
        # Generar datos para entrenamiento
        asyncio.run(generate_training_data())
