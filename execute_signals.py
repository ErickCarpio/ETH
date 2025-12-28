#!/usr/bin/env python3
"""
Execute Trading Signals
Ejecuta señales de trading desde un archivo CSV
"""

import asyncio
import pandas as pd
import json
import logging
from datetime import datetime
from pathlib import Path
import ccxt.async_support as ccxt

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SignalExecutor:
    """Ejecuta señales de trading en Binance Demo"""

    def __init__(self, config_path='config_15min.json'):
        self.config = self._load_config(config_path)
        self.exchange = None

    def _load_config(self, config_path):
        """Carga configuración"""
        with open(config_path, 'r') as f:
            return json.load(f)

    async def initialize(self):
        """Inicializa conexión con Binance Demo SPOT"""
        logger.info("🚀 Conectando a Binance Demo (SPOT)...")

        # Cargar API keys
        testnet_api_key = self.config['exchange']['testnet_api_key']
        testnet_api_secret = self.config['exchange']['testnet_api_secret']

        if not testnet_api_key or not testnet_api_secret:
            raise ValueError("API keys de testnet no configuradas en config_15min.json")

        # Inicializar exchange SPOT
        self.exchange = ccxt.binance({
            'apiKey': testnet_api_key,
            'secret': testnet_api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True,
            }
        })

        # Activar modo testnet (sandbox)
        self.exchange.set_sandbox_mode(True)

        # Override URLs a testnet SPOT
        self.exchange.urls['api'] = {
            'public': 'https://testnet.binance.vision/api/v3',
            'private': 'https://testnet.binance.vision/api/v3',
        }

        # Verificar conexión
        try:
            balance = await self.exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            logger.info(f"✓ Conectado a Binance Demo SPOT (Balance: ${usdt_balance:.2f} USDT)")
        except Exception as e:
            logger.error(f"❌ Error conectando a Binance Demo: {e}")
            raise

    def load_signals(self, filepath):
        """Carga señales desde CSV"""
        df = pd.read_csv(filepath)
        logger.info(f"📊 Cargadas {len(df)} señales desde {filepath}")
        return df

    async def execute_signal(self, signal, position_size_usd=100):
        """Ejecuta una señal individual"""
        try:
            symbol = signal['symbol']
            direction = signal['direction']
            entry = signal['entry']
            stop_loss = signal['stop_loss']
            take_profit = signal['take_profit']

            # Calcular cantidad
            quantity = position_size_usd / entry

            # Determinar side
            side = 'buy' if direction == 'LONG' else 'sell'

            logger.info(f"📈 Ejecutando {direction} en {symbol}:")
            logger.info(f"   Entrada: ${entry:.4f}")
            logger.info(f"   Stop Loss: ${stop_loss:.4f}")
            logger.info(f"   Take Profit: ${take_profit:.4f}")
            logger.info(f"   Cantidad: {quantity:.6f}")

            # Ejecutar orden de mercado
            order = await self.exchange.create_market_order(symbol, side, quantity)

            logger.info(f"✅ Orden ejecutada: {order['id']}")

            # TODO: Configurar TP/SL automáticos (requiere crear órdenes condicionales)
            logger.warning("⚠️ Recuerda configurar manualmente TP y SL en Binance")

            return order

        except Exception as e:
            logger.error(f"❌ Error ejecutando señal para {symbol}: {e}")
            return None

    async def execute_all(self, signals_df, min_confidence=0.70):
        """Ejecuta todas las señales que cumplan el threshold"""
        # Filtrar por confianza
        filtered = signals_df[signals_df['confidence'] >= min_confidence]

        if filtered.empty:
            logger.warning(f"⚠️ No hay señales con confianza >= {min_confidence:.0%}")
            return

        logger.info(f"🎯 Ejecutando {len(filtered)} señales con confianza >= {min_confidence:.0%}")

        executed = []
        for idx, signal in filtered.iterrows():
            order = await self.execute_signal(signal)
            if order:
                executed.append({
                    'symbol': signal['symbol'],
                    'direction': signal['direction'],
                    'order_id': order['id'],
                    'executed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })

            # Rate limiting
            await asyncio.sleep(1)

        # Guardar log de ejecución
        if executed:
            log_df = pd.DataFrame(executed)
            log_file = f"executed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            log_df.to_csv(f"signals/{log_file}", index=False)
            logger.info(f"📝 Log de ejecución guardado: signals/{log_file}")

    async def run(self, signals_file, min_confidence=0.70, dry_run=False):
        """Ejecuta el executor"""
        try:
            await self.initialize()

            # Cargar señales
            signals = self.load_signals(signals_file)

            if dry_run:
                logger.info("🧪 MODO DRY RUN - No se ejecutarán trades reales")
                filtered = signals[signals['confidence'] >= min_confidence]
                print("\n" + "="*80)
                print("📊 SEÑALES QUE SE EJECUTARÍAN:")
                print("="*80)
                print(filtered.to_string(index=False))
                print("="*80)
            else:
                # Confirmar
                filtered = signals[signals['confidence'] >= min_confidence]
                print(f"\n⚠️ Se ejecutarán {len(filtered)} trades en Binance Demo:")
                print(filtered[['symbol', 'direction', 'confidence', 'entry']].to_string(index=False))

                confirm = input("\n¿Continuar? (yes/no): ")
                if confirm.lower() == 'yes':
                    await self.execute_all(signals, min_confidence)
                else:
                    logger.info("❌ Ejecución cancelada")

        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            if self.exchange:
                await self.exchange.close()


async def main():
    """Función principal"""
    import argparse

    parser = argparse.ArgumentParser(description='Ejecutor de señales de trading')
    parser.add_argument('signals_file', type=str, help='Archivo CSV con señales')
    parser.add_argument('--min-confidence', type=float, default=0.70, help='Confianza mínima (default: 0.70)')
    parser.add_argument('--dry-run', action='store_true', help='Modo prueba (no ejecuta trades)')
    parser.add_argument('--config', type=str, default='config_15min.json', help='Archivo de configuración')

    args = parser.parse_args()

    executor = SignalExecutor(config_path=args.config)
    await executor.run(args.signals_file, args.min_confidence, args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
