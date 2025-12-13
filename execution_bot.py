"""
Execution Bot - Lógica de Grid Trading Dinámico (Versión Completa)
Incluye conexión segura y gestión de estado del Grid.
"""

import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GridExecutionBot:
    """
    Bot que ejecuta estrategia de Grid Trading.
    Maneja conexión, cálculo de niveles y ejecución de órdenes.
    """
    
    def __init__(self,
                 symbol: str = "ETH/USDT",
                 total_capital: float = 1000,
                 grid_allocation: float = 0.8,
                 min_grid_spacing: float = 0.005,
                 max_grid_spacing: float = 0.03,
                 min_order_value: float = 20.0):
        
        self.symbol = symbol
        self.total_capital = total_capital
        self.grid_allocation = grid_allocation
        self.min_spacing = min_grid_spacing
        self.max_spacing = max_grid_spacing
        self.min_order_value = min_order_value
        
        # Estado del Bot (Restaurado para evitar errores de atributo)
        self.exchange = None
        self.current_grid = None        # DataFrame con los niveles
        self.current_regime = None      # Último régimen predicho
        self.grid_start_time = None     # Fecha de inicio del grid actual
        self.open_orders = []           # Lista de órdenes vivas
        
    async def initialize_exchange(self, api_key: str = None, secret: str = None, testnet: bool = True):
        """Inicializa conexión limpiando espacios y forzando URLs"""
        
        if api_key: api_key = str(api_key).strip()
        if secret: secret = str(secret).strip()
        
        options = {'defaultType': 'future'}
        
        try:
            self.exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': options
            })
            
            if testnet:
                self.exchange.set_sandbox_mode(True)
                logger.info("🔧 Configurado modo TESTNET (Sandbox Futures)")
            else:
                logger.info("🔥 Configurado modo PRODUCCIÓN (Dinero Real)")

            if api_key and secret:
                await self.exchange.load_markets()
                logger.info("✓ Autenticación exitosa con Binance Futures")
            else:
                logger.warning("⚠️ Sin credenciales válidas. Modo solo lectura.")

        except Exception as e:
            logger.error(f"❌ Error crítico de conexión: {e}")

    async def close_exchange(self):
        if self.exchange:
            await self.exchange.close()
    
    # --- Lógica Matemática del Grid ---
    
    def calculate_grid_parameters(self, regime: int, current_price: float, volatility: float) -> Dict:
        """Define la geometría del grid según el régimen"""
        available_capital = self.total_capital * self.grid_allocation
        max_possible_orders = int(available_capital / self.min_order_value)
        
        # El espaciado se adapta a la volatilidad del mercado
        adaptive_spacing = np.clip(volatility * 2, self.min_spacing, self.max_spacing)
        
        params = {'current_price': current_price}

        if regime == 0:  # LATERAL
            n_levels = min(30, max_possible_orders)
            params.update({
                'type': 'NEUTRAL', 'n_levels': n_levels, 'spacing': adaptive_spacing,
                'range_multiplier': 1.5, 'long_bias': 0.5, 'short_bias': 0.5
            })
        elif regime == 1:  # ALCISTA
            n_levels = min(20, max_possible_orders)
            params.update({
                'type': 'LONG_BIASED', 'n_levels': n_levels, 'spacing': adaptive_spacing * 1.2,
                'range_multiplier': 1.3, 'long_bias': 0.7, 'short_bias': 0.3
            })
        elif regime == 2:  # BAJISTA
            n_levels = min(20, max_possible_orders)
            params.update({
                'type': 'SHORT_BIASED', 'n_levels': n_levels, 'spacing': adaptive_spacing * 1.2,
                'range_multiplier': 1.3, 'long_bias': 0.3, 'short_bias': 0.7
            })
        else:  # PELIGRO
            return {'type': 'CASH', 'n_levels': 0}
        
        # Calcular techo y piso del grid
        grid_range = current_price * params['spacing'] * params['n_levels']
        params['upper_bound'] = current_price + (grid_range * params['range_multiplier'])
        params['lower_bound'] = current_price - (grid_range * params['range_multiplier'])
        
        return params
    
    def generate_grid_levels(self, params: Dict) -> pd.DataFrame:
        """Genera la tabla de órdenes"""
        if params['type'] == 'CASH':
            return pd.DataFrame()
        
        n_levels = params['n_levels']
        levels = np.linspace(params['lower_bound'], params['upper_bound'], n_levels)
        
        grid_df = pd.DataFrame({'price': levels})
        # Determinar si es compra o venta según precio actual
        grid_df['side'] = grid_df['price'].apply(lambda p: 'buy' if p < params['current_price'] else 'sell')
        
        # Asignar capital por nivel
        capital_total = self.total_capital * self.grid_allocation
        capital_per_level = capital_total / n_levels
        
        # Calcular cantidad de ETH por orden
        grid_df['quantity'] = grid_df.apply(lambda row: self._calculate_order_size(
            capital_per_level, row['price'], row['side'], params['long_bias'], params['short_bias']), axis=1)
            
        # Filtro de seguridad: Eliminar órdenes menores a $20
        grid_df['value_usd'] = grid_df['quantity'] * grid_df['price']
        grid_df = grid_df[grid_df['value_usd'] >= self.min_order_value].copy()
        
        return grid_df
    
    @staticmethod
    def _calculate_order_size(capital, price, side, long_bias, short_bias):
        qty = capital / price
        # Aplicar sesgo (bias) según estrategia
        if side == 'buy':
            return qty * long_bias * 2  # Normalizar x2 porque bias suma 1.0
        else:
            return qty * short_bias * 2

    async def place_grid_orders(self, grid_levels: pd.DataFrame) -> List[Dict]:
        """Envía (o simula) las órdenes"""
        orders = []
        logger.info(f"---- COLOCANDO {len(grid_levels)} ÓRDENES ----")
        
        for _, row in grid_levels.iterrows():
            # Aquí iría la llamada real: await self.exchange.create_order(...)
            # Por seguridad en paper trading, solo logueamos:
            logger.info(f"🛒 {row['side'].upper()} {row['quantity']:.4f} ETH @ ${row['price']:.2f} (Total: ${row['value_usd']:.2f})")
            
            # Guardamos orden simulada
            orders.append({
                'id': f"sim_{np.random.randint(10000,99999)}",
                'side': row['side'],
                'price': row['price'],
                'quantity': row['quantity'],
                'status': 'open'
            })
            
        return orders

    async def cancel_all_orders(self):
        """Cancela todo (Simulado)"""
        if self.open_orders:
            logger.info(f"🗑️ Cancelando {len(self.open_orders)} órdenes activas...")
            self.open_orders = []

    async def execute_regime_strategy(self, predicted_regime, current_price, volatility):
        """
        Ejecuta la lógica completa: Cierra lo anterior -> Calcula nuevo -> Abre nuevo
        """
        regime_names = {0: 'LATERAL', 1: 'ALCISTA', 2: 'BAJISTA', 3: 'PELIGRO'}
        r_name = regime_names.get(predicted_regime, 'UNKNOWN')
        
        logger.info(f"🚀 EJECUTANDO ESTRATEGIA PARA: {r_name}")
        
        # 1. Limpiar mesa
        await self.cancel_all_orders()
        
        # 2. Calcular nueva estrategia
        params = self.calculate_grid_parameters(predicted_regime, current_price, volatility)
        
        if params['type'] == 'CASH':
            logger.warning("🛑 MODO CASH ACTIVADO. No se colocan órdenes.")
            self.current_grid = None
            self.current_regime = predicted_regime
            return

        logger.info(f"📊 Config: {params['type']} | Rangos: ${params['lower_bound']:.2f} - ${params['upper_bound']:.2f}")

        # 3. Generar órdenes
        grid_df = self.generate_grid_levels(params)
        
        if grid_df.empty:
            logger.warning("⚠️ El grid generado está vacío (posiblemente por capital insuficiente).")
            return

        # 4. Enviar órdenes
        placed_orders = await self.place_grid_orders(grid_df)
        
        # 5. Guardar estado
        self.current_grid = grid_df
        self.current_regime = predicted_regime
        self.grid_start_time = datetime.now()
        self.open_orders = placed_orders
        logger.info(f"✅ Grid iniciado con éxito. {len(placed_orders)} órdenes activas.")