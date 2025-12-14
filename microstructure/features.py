"""
Microstructure Features Calculator
Fase 2: Features de Market Microstructure

Calcula features institucionales avanzadas:
- OBI (Order Book Imbalance)
- VPIN (Volume-Synchronized Probability of Informed Trading)
- OFI (Order Flow Imbalance)
- Micro-price
- Price impact estimations
- Roll spread (bid-ask bounce measure)
- Kyle's Lambda (permanent price impact)

Referencias:
- Easley et al. (2012) - "Flow Toxicity and Liquidity in a High Frequency World"
- Cont et al. (2014) - "The Price Impact of Order Book Events"
- Kyle (1985) - "Continuous Auctions and Insider Trading"
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class VPINConfig:
    """Configuración para VPIN calculation"""
    bucket_size: float = 50.0  # Volumen por bucket (ETH)
    num_buckets: int = 50      # Número de buckets para el cálculo


class MicrostructureFeatures:
    """
    Calculador de features microestructurales en tiempo real

    Mantiene estado histórico necesario para cálculos
    """

    def __init__(self, symbol: str):
        self.symbol = symbol

        # Historial de order book snapshots
        self.ob_history: deque = deque(maxlen=1000)

        # Historial de trades
        self.trade_history: deque = deque(maxlen=5000)

        # VPIN calculation state
        self.vpin_config = VPINConfig()
        self.volume_buckets: deque = deque(maxlen=self.vpin_config.num_buckets)
        self.current_bucket_volume = 0.0
        self.current_bucket_buy_volume = 0.0

        # OFI calculation state
        self.last_bid_levels: Dict[float, float] = {}  # price -> qty
        self.last_ask_levels: Dict[float, float] = {}

        # Kyle's Lambda estimation
        self.price_changes: deque = deque(maxlen=100)
        self.signed_volumes: deque = deque(maxlen=100)

    def calculate_obi(
        self,
        bids: Dict[float, float],
        asks: Dict[float, float],
        levels: int = 5
    ) -> float:
        """
        Calcula Order Book Imbalance (OBI)

        OBI = (bid_volume - ask_volume) / (bid_volume + ask_volume)

        Args:
            bids: Dict {price: qty} ordenado descendente
            asks: Dict {price: qty} ordenado ascendente
            levels: Número de niveles a considerar

        Returns:
            OBI en [-1, 1]
        """
        bid_items = list(bids.items())[:levels]
        ask_items = list(asks.items())[:levels]

        bid_volume = sum(qty for _, qty in bid_items)
        ask_volume = sum(qty for _, qty in ask_items)

        total_volume = bid_volume + ask_volume

        if total_volume > 0:
            return (bid_volume - ask_volume) / total_volume

        return 0.0

    def calculate_ofi(
        self,
        current_bids: Dict[float, float],
        current_asks: Dict[float, float],
        levels: int = 5
    ) -> float:
        """
        Calcula Order Flow Imbalance (OFI)

        OFI mide el flujo neto de órdenes (cambios en volumen) en el order book

        OFI = Σ(ΔBid_volume) - Σ(ΔAsk_volume)

        Valores positivos indican presión compradora
        Valores negativos indican presión vendedora

        Args:
            current_bids: Bids actuales
            current_asks: Asks actuales
            levels: Número de niveles a considerar

        Returns:
            OFI (cambio neto en volumen)
        """
        if not self.last_bid_levels or not self.last_ask_levels:
            # Primer snapshot, inicializar y retornar 0
            self.last_bid_levels = dict(list(current_bids.items())[:levels])
            self.last_ask_levels = dict(list(current_asks.items())[:levels])
            return 0.0

        # Calcular cambios en bids
        bid_flow = 0.0
        current_bid_items = list(current_bids.items())[:levels]

        for price, qty in current_bid_items:
            old_qty = self.last_bid_levels.get(price, 0.0)
            bid_flow += (qty - old_qty)

        # Calcular cambios en asks
        ask_flow = 0.0
        current_ask_items = list(current_asks.items())[:levels]

        for price, qty in current_ask_items:
            old_qty = self.last_ask_levels.get(price, 0.0)
            ask_flow += (qty - old_qty)

        # Actualizar estado
        self.last_bid_levels = dict(current_bid_items)
        self.last_ask_levels = dict(current_ask_items)

        # OFI = flujo de compra - flujo de venta
        return bid_flow - ask_flow

    def update_vpin_with_trade(
        self,
        price: float,
        quantity: float,
        is_buy: bool
    ):
        """
        Actualiza buckets de volumen para cálculo de VPIN

        Args:
            price: Precio del trade
            quantity: Cantidad traded
            is_buy: True si es compra (aggressor buy)
        """
        # Agregar volumen al bucket actual
        self.current_bucket_volume += quantity

        if is_buy:
            self.current_bucket_buy_volume += quantity

        # Si el bucket está completo, cerrarlo
        if self.current_bucket_volume >= self.vpin_config.bucket_size:
            # Calcular |buy_volume - sell_volume| para este bucket
            sell_volume = self.current_bucket_volume - self.current_bucket_buy_volume
            volume_imbalance = abs(self.current_bucket_buy_volume - sell_volume)

            # Guardar bucket
            self.volume_buckets.append({
                "total_volume": self.current_bucket_volume,
                "buy_volume": self.current_bucket_buy_volume,
                "sell_volume": sell_volume,
                "imbalance": volume_imbalance
            })

            # Resetear bucket actual
            self.current_bucket_volume = 0.0
            self.current_bucket_buy_volume = 0.0

    def calculate_vpin(self) -> Optional[float]:
        """
        Calcula VPIN (Volume-Synchronized Probability of Informed Trading)

        VPIN = Σ|V_buy - V_sell| / Σ V_total

        Donde la suma es sobre los últimos N buckets de volumen

        VPIN alto (> 0.5) sugiere mayor probabilidad de trading informado
        (i.e., alguien con información privada está trading)

        Returns:
            VPIN en [0, 1], o None si no hay suficientes buckets
        """
        if len(self.volume_buckets) < self.vpin_config.num_buckets:
            return None

        total_imbalance = sum(b["imbalance"] for b in self.volume_buckets)
        total_volume = sum(b["total_volume"] for b in self.volume_buckets)

        if total_volume > 0:
            return total_imbalance / total_volume

        return None

    def calculate_micro_price(
        self,
        best_bid: Tuple[float, float],
        best_ask: Tuple[float, float]
    ) -> float:
        """
        Calcula micro-price (precio ponderado por volumen en L1)

        micro_price = (bid_price * ask_qty + ask_price * bid_qty) / (bid_qty + ask_qty)

        El micro-price da más peso al lado con menor volumen,
        reflejando la dirección esperada del próximo trade

        Args:
            best_bid: (price, qty)
            best_ask: (price, qty)

        Returns:
            Micro-price
        """
        bid_price, bid_qty = best_bid
        ask_price, ask_qty = best_ask

        total_qty = bid_qty + ask_qty

        if total_qty > 0:
            return (bid_price * ask_qty + ask_price * bid_qty) / total_qty

        return (bid_price + ask_price) / 2.0

    def calculate_roll_spread(self, window: int = 20) -> Optional[float]:
        """
        Calcula Roll spread (medida de bid-ask bounce)

        Roll spread = 2 * sqrt(-Cov(ΔP_t, ΔP_{t-1}))

        Donde ΔP es el cambio en precio mid

        Roll (1984) mostró que el spread efectivo puede estimarse
        desde la covarianza negativa de cambios de precio

        Args:
            window: Número de observaciones para calcular covarianza

        Returns:
            Roll spread estimate, o None si no hay suficientes datos
        """
        if len(self.ob_history) < window + 1:
            return None

        # Extraer mid prices
        mid_prices = []
        for ob_snapshot in list(self.ob_history)[-window-1:]:
            mid_price = ob_snapshot.get("mid_price")
            if mid_price:
                mid_prices.append(mid_price)

        if len(mid_prices) < window + 1:
            return None

        # Calcular cambios de precio
        price_changes = np.diff(mid_prices)

        # Calcular covarianza de cambios consecutivos
        if len(price_changes) > 1:
            cov = np.cov(price_changes[:-1], price_changes[1:])[0, 1]

            # Roll spread = 2 * sqrt(-cov)
            if cov < 0:
                return 2.0 * np.sqrt(-cov)

        return None

    def update_kyle_lambda(self, price_change: float, signed_volume: float):
        """
        Actualiza estimación de Kyle's Lambda

        Lambda mide el price impact permanente de un trade

        ΔP = λ * V_signed

        Donde V_signed es positivo para compras, negativo para ventas

        Args:
            price_change: Cambio en mid price
            signed_volume: Volumen signed (+ buy, - sell)
        """
        self.price_changes.append(price_change)
        self.signed_volumes.append(signed_volume)

    def calculate_kyle_lambda(self) -> Optional[float]:
        """
        Estima Kyle's Lambda mediante regresión simple

        λ = Cov(ΔP, V_signed) / Var(V_signed)

        Returns:
            Lambda (price impact per unit volume), o None si no hay suficientes datos
        """
        if len(self.price_changes) < 30:
            return None

        price_changes = np.array(list(self.price_changes))
        signed_volumes = np.array(list(self.signed_volumes))

        # Evitar división por cero
        var_volume = np.var(signed_volumes)

        if var_volume > 0:
            cov = np.cov(price_changes, signed_volumes)[0, 1]
            return cov / var_volume

        return None

    def calculate_effective_spread(
        self,
        trade_price: float,
        mid_price: float,
        is_buy: bool
    ) -> float:
        """
        Calcula effective spread para un trade

        Effective spread = 2 * |trade_price - mid_price|

        O en términos de side:
        - Buy: 2 * (trade_price - mid_price)
        - Sell: 2 * (mid_price - trade_price)

        Args:
            trade_price: Precio del trade
            mid_price: Mid price en el momento del trade
            is_buy: True si es compra

        Returns:
            Effective spread
        """
        if is_buy:
            return 2.0 * (trade_price - mid_price)
        else:
            return 2.0 * (mid_price - trade_price)

    def add_orderbook_snapshot(self, snapshot: Dict):
        """
        Agrega un snapshot del order book al historial

        Args:
            snapshot: Dict con datos del order book
        """
        self.ob_history.append(snapshot)

    def add_trade(self, trade: Dict):
        """
        Agrega un trade al historial y actualiza métricas

        Args:
            trade: Dict con datos del trade
                   {price, quantity, is_buy, timestamp}
        """
        self.trade_history.append(trade)

        # Actualizar VPIN
        self.update_vpin_with_trade(
            trade["price"],
            trade["quantity"],
            trade["is_buy"]
        )

    def calculate_trade_flow_toxicity(self, window: int = 50) -> Optional[float]:
        """
        Calcula Trade Flow Toxicity (Easley et al. 2012)

        Toxicity mide cuánto revierte el precio después de un trade,
        indicando si el trade contenía información adversa

        Returns:
            Toxicity score, o None si no hay suficientes datos
        """
        if len(self.trade_history) < window + 10:
            return None

        recent_trades = list(self.trade_history)[-window-10:]

        toxicities = []
        for i in range(len(recent_trades) - 10):
            trade = recent_trades[i]

            # Medir reversión de precio en próximos 10 trades
            future_prices = [t["price"] for t in recent_trades[i+1:i+11]]
            if not future_prices:
                continue

            avg_future_price = np.mean(future_prices)

            # Toxicity = (future_price - trade_price) * direction
            # Si compro y el precio baja después -> tóxico (perdí)
            direction = 1 if trade["is_buy"] else -1
            toxicity = (avg_future_price - trade["price"]) * direction

            toxicities.append(toxicity)

        if toxicities:
            return np.mean(toxicities)

        return None

    def calculate_realized_spread(self, window: int = 20) -> Optional[float]:
        """
        Calcula Realized Spread

        Realized spread mide cuánto del effective spread se debe a
        adverse selection vs. liquidity provision

        Returns:
            Realized spread promedio, o None si no hay suficientes datos
        """
        if len(self.trade_history) < window + 5:
            return None

        recent_trades = list(self.trade_history)[-window-5:]

        realized_spreads = []
        for i in range(len(recent_trades) - 5):
            trade = recent_trades[i]

            # Precio mid 5 trades después
            future_prices = [t["price"] for t in recent_trades[i+1:i+6]]
            if not future_prices:
                continue

            future_mid = np.mean(future_prices)

            # Realized spread
            if trade["is_buy"]:
                rs = 2 * (trade["price"] - future_mid)
            else:
                rs = 2 * (future_mid - trade["price"])

            realized_spreads.append(rs)

        if realized_spreads:
            return np.mean(realized_spreads)

        return None

    def calculate_quote_intensity(self, window_seconds: int = 60) -> float:
        """
        Calcula Quote Intensity (actualizaciones del order book por segundo)

        High quote intensity puede indicar:
        - Alta actividad de market makers
        - Quote stuffing (manipulación)
        - Alta volatilidad esperada

        Args:
            window_seconds: Ventana de tiempo para calcular intensidad

        Returns:
            Quotes por segundo
        """
        if len(self.ob_history) < 2:
            return 0.0

        recent_obs = list(self.ob_history)[-100:]  # Últimos 100 snapshots

        if len(recent_obs) < 2:
            return 0.0

        # Calcular tiempo transcurrido
        first_time = recent_obs[0].get("timestamp")
        last_time = recent_obs[-1].get("timestamp")

        if not first_time or not last_time:
            return 0.0

        from datetime import datetime
        if isinstance(first_time, datetime):
            elapsed = (last_time - first_time).total_seconds()
        else:
            elapsed = (last_time - first_time) / 1000.0  # milisegundos

        if elapsed > 0:
            return len(recent_obs) / elapsed

        return 0.0

    def calculate_order_arrival_rate(self, window: int = 50) -> float:
        """
        Calcula Order Arrival Rate (trades por minuto)

        High arrival rate indica:
        - Alta actividad / liquidez
        - Posible evento de noticias
        - Aumenta probabilidad de informed trading

        Args:
            window: Número de trades para calcular rate

        Returns:
            Trades por minuto
        """
        if len(self.trade_history) < 2:
            return 0.0

        recent_trades = list(self.trade_history)[-window:]

        if len(recent_trades) < 2:
            return 0.0

        first_time = recent_trades[0].get("timestamp")
        last_time = recent_trades[-1].get("timestamp")

        if not first_time or not last_time:
            return 0.0

        from datetime import datetime
        if isinstance(first_time, datetime):
            elapsed_minutes = (last_time - first_time).total_seconds() / 60.0
        else:
            elapsed_minutes = (last_time - first_time) / 60000.0  # milisegundos

        if elapsed_minutes > 0:
            return len(recent_trades) / elapsed_minutes

        return 0.0

    def calculate_price_impact(self, trade_size: float, levels: int = 10) -> float:
        """
        Estima price impact para un trade de cierto tamaño

        Simula ejecutar un market order y calcula cuánto se movería el precio

        Args:
            trade_size: Tamaño del trade hipotético
            levels: Niveles del order book a considerar

        Returns:
            Price impact estimado (bps)
        """
        if not self.ob_history:
            return 0.0

        latest_ob = self.ob_history[-1]

        if "bids" not in latest_ob or "asks" not in latest_ob:
            return 0.0

        mid_price = latest_ob.get("mid_price", 0)
        if mid_price == 0:
            return 0.0

        # Simular sell (walk down the bids)
        bids = latest_ob["bids"][:levels]
        remaining = trade_size
        total_cost = 0.0

        for price, qty in bids:
            if remaining <= 0:
                break

            fill_qty = min(remaining, qty)
            total_cost += fill_qty * price
            remaining -= fill_qty

        if trade_size > 0 and total_cost > 0:
            avg_price = total_cost / (trade_size - remaining)
            impact_bps = abs(avg_price - mid_price) / mid_price * 10000
            return impact_bps

        return 0.0

    def get_all_features(
        self,
        current_orderbook: Dict,
        last_trade: Optional[Dict] = None
    ) -> Dict:
        """
        Calcula todas las features microestructurales

        Args:
            current_orderbook: Snapshot actual del order book
            last_trade: Último trade (opcional)

        Returns:
            Dict con todas las features
        """
        features = {}

        # OBI en múltiples niveles
        if "bids" in current_orderbook and "asks" in current_orderbook:
            bids_dict = dict(current_orderbook["bids"])
            asks_dict = dict(current_orderbook["asks"])

            features["obi_5"] = self.calculate_obi(bids_dict, asks_dict, 5)
            features["obi_10"] = self.calculate_obi(bids_dict, asks_dict, 10)
            features["obi_20"] = self.calculate_obi(bids_dict, asks_dict, 20)

            # OFI
            features["ofi"] = self.calculate_ofi(bids_dict, asks_dict, 5)

        # Micro-price
        if "best_bid" in current_orderbook and "best_ask" in current_orderbook:
            features["micro_price"] = self.calculate_micro_price(
                current_orderbook["best_bid"],
                current_orderbook["best_ask"]
            )

        # VPIN
        vpin = self.calculate_vpin()
        features["vpin"] = vpin if vpin is not None else 0.0

        # Roll spread
        roll = self.calculate_roll_spread()
        features["roll_spread"] = roll if roll is not None else 0.0

        # Kyle's Lambda
        lambda_est = self.calculate_kyle_lambda()
        features["kyle_lambda"] = lambda_est if lambda_est is not None else 0.0

        # Effective spread (si hay trade)
        if last_trade and "mid_price" in current_orderbook:
            features["effective_spread"] = self.calculate_effective_spread(
                last_trade["price"],
                current_orderbook["mid_price"],
                last_trade["is_buy"]
            )

        # Advanced features
        toxicity = self.calculate_trade_flow_toxicity()
        features["trade_flow_toxicity"] = toxicity if toxicity is not None else 0.0

        realized_spread = self.calculate_realized_spread()
        features["realized_spread"] = realized_spread if realized_spread is not None else 0.0

        features["quote_intensity"] = self.calculate_quote_intensity()
        features["order_arrival_rate"] = self.calculate_order_arrival_rate()

        # Price impact para trade de tamaño estándar (1 ETH)
        features["price_impact_1eth"] = self.calculate_price_impact(1.0)

        return features


# Ejemplo de uso
if __name__ == "__main__":
    # Crear calculator
    calc = MicrostructureFeatures("ETHUSDT")

    # Simular order book
    orderbook = {
        "bids": [[2000.0, 10.5], [1999.0, 8.2], [1998.0, 12.1]],
        "asks": [[2001.0, 9.3], [2002.0, 7.8], [2003.0, 11.2]],
        "best_bid": (2000.0, 10.5),
        "best_ask": (2001.0, 9.3),
        "mid_price": 2000.5
    }

    # Simular trades para VPIN
    for i in range(100):
        trade = {
            "price": 2000.0 + np.random.randn(),
            "quantity": 1.0 + abs(np.random.randn() * 0.5),
            "is_buy": np.random.rand() > 0.5,
            "timestamp": i
        }
        calc.add_trade(trade)

    # Calcular features
    features = calc.get_all_features(orderbook)

    print("📊 Microstructure Features:")
    for key, value in features.items():
        if isinstance(value, float):
            print(f"   {key}: {value:.6f}")
        else:
            print(f"   {key}: {value}")
