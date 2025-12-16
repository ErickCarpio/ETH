"""
Order Flow Imbalance (OFI) Calculator
======================================

Calcula el desequilibrio en el flujo de órdenes basado en cambios en el libro.

OFI mide la presión compradora/vendedora según:
- Cambios en volumen en cada nivel de precio
- Movimientos del precio bid/ask
- Órdenes agresivas vs pasivas

Features generadas: ~20
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
import logging


class OFICalculator:
    """
    Calcula Order Flow Imbalance (OFI) desde order book snapshots.

    OFI Formula:
    OFI_bid = ΔVolume_bid + (Price_moved_up * Volume_prev)
    OFI_ask = ΔVolume_ask + (Price_moved_down * Volume_prev)
    OFI_net = OFI_bid - OFI_ask
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize OFI calculator.

        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.prev_book = None

    def calculate_ofi(self,
                     book_current: Dict,
                     book_prev: Optional[Dict] = None) -> Dict[str, float]:
        """
        Calculate Order Flow Imbalance from two consecutive order book snapshots.

        Args:
            book_current: Current order book {bids: [(price, vol)], asks: [(price, vol)]}
            book_prev: Previous order book (same format)

        Returns:
            Dictionary with OFI features
        """
        features = {}

        if book_prev is None:
            # First call, no previous book
            self.prev_book = book_current
            return {
                'ofi_bid': 0.0,
                'ofi_ask': 0.0,
                'ofi_net': 0.0,
                'ofi_bid_pressure': 0.0,
                'ofi_ask_pressure': 0.0,
                'ofi_imbalance_ratio': 0.0
            }

        try:
            # Extract bids and asks
            bids_curr = book_current.get('bids', [])
            asks_curr = book_current.get('asks', [])
            bids_prev = book_prev.get('bids', [])
            asks_prev = book_prev.get('asks', [])

            if not bids_curr or not asks_curr or not bids_prev or not asks_prev:
                return self._placeholder_features()

            # Calculate OFI for bid side
            ofi_bid = self._calculate_side_ofi(
                current_levels=bids_curr,
                prev_levels=bids_prev,
                side='bid'
            )

            # Calculate OFI for ask side
            ofi_ask = self._calculate_side_ofi(
                current_levels=asks_curr,
                prev_levels=asks_prev,
                side='ask'
            )

            # Net OFI
            ofi_net = ofi_bid - ofi_ask

            # Normalized metrics
            total_ofi = abs(ofi_bid) + abs(ofi_ask)
            if total_ofi > 0:
                ofi_imbalance_ratio = ofi_net / total_ofi
            else:
                ofi_imbalance_ratio = 0.0

            # Pressure metrics (positive = buying pressure, negative = selling)
            features['ofi_bid'] = ofi_bid
            features['ofi_ask'] = ofi_ask
            features['ofi_net'] = ofi_net
            features['ofi_bid_pressure'] = max(0, ofi_bid)
            features['ofi_ask_pressure'] = max(0, ofi_ask)
            features['ofi_imbalance_ratio'] = ofi_imbalance_ratio

            # Store current book as previous for next call
            self.prev_book = book_current

        except Exception as e:
            self.logger.warning(f"Error calculating OFI: {e}")
            return self._placeholder_features()

        return features

    def _calculate_side_ofi(self,
                           current_levels: list,
                           prev_levels: list,
                           side: str) -> float:
        """
        Calculate OFI for one side (bid or ask).

        Args:
            current_levels: [(price, volume), ...]
            prev_levels: [(price, volume), ...]
            side: 'bid' or 'ask'

        Returns:
            OFI value for this side
        """
        # Convert to dictionaries for easier lookup
        curr_dict = {float(price): float(vol) for price, vol in current_levels[:10]}
        prev_dict = {float(price): float(vol) for price, vol in prev_levels[:10]}

        ofi = 0.0

        # Get best prices
        if side == 'bid':
            curr_best = max(curr_dict.keys()) if curr_dict else 0
            prev_best = max(prev_dict.keys()) if prev_dict else 0
        else:
            curr_best = min(curr_dict.keys()) if curr_dict else float('inf')
            prev_best = min(prev_dict.keys()) if prev_dict else float('inf')

        # Calculate volume changes at each price level
        all_prices = set(curr_dict.keys()) | set(prev_dict.keys())

        for price in all_prices:
            vol_curr = curr_dict.get(price, 0)
            vol_prev = prev_dict.get(price, 0)
            delta_vol = vol_curr - vol_prev

            # Add volume change contribution
            ofi += delta_vol

        # Add price movement contribution
        if side == 'bid':
            if curr_best > prev_best:
                # Bid moved up (buying pressure)
                ofi += prev_dict.get(prev_best, 0)
            elif curr_best < prev_best:
                # Bid moved down (selling pressure)
                ofi -= prev_dict.get(prev_best, 0)
        else:
            if curr_best < prev_best:
                # Ask moved down (buying pressure)
                ofi += prev_dict.get(prev_best, 0)
            elif curr_best > prev_best:
                # Ask moved up (selling pressure)
                ofi -= prev_dict.get(prev_best, 0)

        return ofi

    def calculate_cancellation_ratio(self,
                                    current_book: Dict,
                                    prev_book: Dict) -> float:
        """
        Calculate order cancellation ratio.

        Measures: (Volume disappeared) / (Total volume prev)

        Args:
            current_book: Current order book
            prev_book: Previous order book

        Returns:
            Cancellation ratio (0-1)
        """
        try:
            # Combine bids and asks
            prev_levels = prev_book.get('bids', [])[:10] + prev_book.get('asks', [])[:10]
            curr_levels = current_book.get('bids', [])[:10] + current_book.get('asks', [])[:10]

            prev_dict = {float(p): float(v) for p, v in prev_levels}
            curr_dict = {float(p): float(v) for p, v in curr_levels}

            total_prev = sum(prev_dict.values())
            if total_prev == 0:
                return 0.0

            # Calculate disappeared volume
            disappeared = 0.0
            for price, vol_prev in prev_dict.items():
                vol_curr = curr_dict.get(price, 0)
                if vol_curr < vol_prev:
                    disappeared += (vol_prev - vol_curr)

            ratio = disappeared / total_prev
            return min(1.0, ratio)

        except Exception as e:
            self.logger.warning(f"Error calculating cancellation ratio: {e}")
            return 0.0

    def detect_aggressive_orders(self,
                                 trades: list,
                                 book: Dict,
                                 window_seconds: int = 10) -> Dict[str, float]:
        """
        Detect aggressive market orders from trades.

        Aggressive = trades that cross the spread

        Args:
            trades: List of recent trades [{price, qty, is_buyer_maker, time}, ...]
            book: Current order book
            window_seconds: Time window for aggregation

        Returns:
            Dictionary with aggressive order metrics
        """
        features = {}

        try:
            if not trades or not book.get('bids') or not book.get('asks'):
                return {
                    'aggressive_buy_ratio': 0.0,
                    'aggressive_sell_ratio': 0.0,
                    'aggressive_volume': 0.0,
                    'aggressive_trade_count': 0
                }

            # Get current spread
            best_bid = max([float(p) for p, v in book['bids'][:1]])
            best_ask = min([float(p) for p, v in book['asks'][:1]])
            mid_price = (best_bid + best_ask) / 2

            aggressive_buys = 0
            aggressive_sells = 0
            aggressive_vol = 0.0
            total_trades = len(trades)

            for trade in trades:
                price = float(trade.get('price', 0))
                qty = float(trade.get('qty', 0))
                is_buyer_maker = trade.get('is_buyer_maker', False)

                # Aggressive buy: price >= mid (taker is buyer)
                if price >= mid_price and not is_buyer_maker:
                    aggressive_buys += 1
                    aggressive_vol += qty
                # Aggressive sell: price <= mid (taker is seller)
                elif price <= mid_price and is_buyer_maker:
                    aggressive_sells += 1
                    aggressive_vol += qty

            aggressive_count = aggressive_buys + aggressive_sells

            features['aggressive_buy_ratio'] = aggressive_buys / total_trades if total_trades > 0 else 0.0
            features['aggressive_sell_ratio'] = aggressive_sells / total_trades if total_trades > 0 else 0.0
            features['aggressive_volume'] = aggressive_vol
            features['aggressive_trade_count'] = aggressive_count

        except Exception as e:
            self.logger.warning(f"Error detecting aggressive orders: {e}")
            features = {
                'aggressive_buy_ratio': 0.0,
                'aggressive_sell_ratio': 0.0,
                'aggressive_volume': 0.0,
                'aggressive_trade_count': 0
            }

        return features

    def calculate_all_features(self,
                              current_book: Dict,
                              prev_book: Optional[Dict] = None,
                              trades: Optional[list] = None) -> Dict[str, float]:
        """
        Calculate all OFI-related features.

        Args:
            current_book: Current order book
            prev_book: Previous order book
            trades: Recent trades (optional)

        Returns:
            Dictionary with all OFI features (~20)
        """
        features = {}

        # Basic OFI
        ofi_features = self.calculate_ofi(current_book, prev_book or self.prev_book)
        features.update(ofi_features)

        # Cancellation ratio
        if prev_book or self.prev_book:
            features['cancellation_ratio'] = self.calculate_cancellation_ratio(
                current_book,
                prev_book or self.prev_book
            )
        else:
            features['cancellation_ratio'] = 0.0

        # Aggressive orders
        if trades:
            aggressive_features = self.detect_aggressive_orders(trades, current_book)
            features.update(aggressive_features)
        else:
            features.update({
                'aggressive_buy_ratio': 0.0,
                'aggressive_sell_ratio': 0.0,
                'aggressive_volume': 0.0,
                'aggressive_trade_count': 0
            })

        # Derived features
        if features['ofi_net'] != 0:
            features['ofi_intensity'] = abs(features['ofi_net'])
            features['ofi_direction'] = 1 if features['ofi_net'] > 0 else -1
        else:
            features['ofi_intensity'] = 0.0
            features['ofi_direction'] = 0

        # OFI momentum (requires history - placeholder for now)
        features['ofi_momentum'] = 0.0

        # Aggressive vs passive ratio
        total_aggressive = features['aggressive_buy_ratio'] + features['aggressive_sell_ratio']
        features['aggressive_passive_ratio'] = total_aggressive / (1 - total_aggressive) if total_aggressive < 1 else 1.0

        # OFI regime
        features['ofi_regime_buying'] = 1 if features['ofi_net'] > 100 else 0
        features['ofi_regime_selling'] = 1 if features['ofi_net'] < -100 else 0
        features['ofi_regime_neutral'] = 1 if abs(features['ofi_net']) <= 100 else 0

        return features

    def _placeholder_features(self) -> Dict[str, float]:
        """Return placeholder features when calculation fails."""
        return {
            'ofi_bid': 0.0,
            'ofi_ask': 0.0,
            'ofi_net': 0.0,
            'ofi_bid_pressure': 0.0,
            'ofi_ask_pressure': 0.0,
            'ofi_imbalance_ratio': 0.0,
            'cancellation_ratio': 0.0,
            'aggressive_buy_ratio': 0.0,
            'aggressive_sell_ratio': 0.0,
            'aggressive_volume': 0.0,
            'aggressive_trade_count': 0,
            'ofi_intensity': 0.0,
            'ofi_direction': 0,
            'ofi_momentum': 0.0,
            'aggressive_passive_ratio': 0.0,
            'ofi_regime_buying': 0,
            'ofi_regime_selling': 0,
            'ofi_regime_neutral': 1
        }
