from __future__ import annotations

import os
from typing import List, Optional

import alpaca_trade_api as tradeapi

from config import ALPACA_API_KEY, ALPACA_BASE_URL, ALPACA_SECRET_KEY


class OrderExecutor:
    """Place market orders through Alpaca paper trading."""

    def __init__(self) -> None:
        self.client = self._create_client()

    def _create_client(self) -> tradeapi.REST:
        if not ALPACA_API_KEY or not ALPACA_SECRET_KEY or not ALPACA_BASE_URL:
            raise EnvironmentError(
                "ALPACA_API_KEY, ALPACA_SECRET_KEY, and ALPACA_BASE_URL must be set"
            )
        # Normalize ALPACA_BASE_URL: remove any trailing slash and any trailing '/v2'
        # because `alpaca_trade_api.REST(..., api_version='v2')` will append the API
        # version path itself. Passing a base URL that already contains '/v2'
        # results in a duplicated '/v2/v2' in requests.
        base = ALPACA_BASE_URL.rstrip('/')
        if base.endswith("/v2"):
            base = base[:-3]

        return tradeapi.REST(
            ALPACA_API_KEY,
            ALPACA_SECRET_KEY,
            base,
            api_version="v2",
        )

    def get_account(self) -> tradeapi.entity.Account:
        """Return the current Alpaca account object."""
        return self.client.get_account()

    def list_positions(self) -> List[tradeapi.entity.Position]:
        """Return a list of currently open Alpaca positions."""
        return self.client.list_positions()

    def get_position_qty(self, symbol: str) -> int:
        """Return the current quantity held for a symbol, or 0 if not held."""
        try:
            position = self.client.get_position(symbol)
            return int(position.qty)
        except Exception:
            return 0

    def place_market_order(self, symbol: str, qty: int, side: str) -> tradeapi.entity.Order:
        """Place a market order to buy or sell the requested quantity."""
        if qty <= 0:
            raise ValueError("Order quantity must be greater than zero")
        return self.client.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type="market",
            time_in_force="day",
        )
