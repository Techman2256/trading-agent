from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from config import ALPACA_API_KEY, ALPACA_BASE_URL, ALPACA_SECRET_KEY


class OptionsExecutor:
    """Place options orders through Alpaca paper trading."""

    def __init__(self) -> None:
        if not ALPACA_API_KEY or not ALPACA_SECRET_KEY or not ALPACA_BASE_URL:
            raise EnvironmentError(
                "ALPACA_API_KEY, ALPACA_SECRET_KEY, and ALPACA_BASE_URL must be set"
            )
        base = ALPACA_BASE_URL.rstrip("/")
        if base.endswith("/v2"):
            base = base[:-3]
        self.base_url = base
        self.headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
            "Content-Type": "application/json",
        }

    def _get_target_expiry(self) -> str:
        candidate = date.today() + timedelta(days=14)
        return candidate.isoformat()

    def _fetch_option_contracts(
        self,
        symbol: str,
        option_type: str,
        expiry: str,
    ) -> list[Dict[str, Any]]:
        url = f"{self.base_url}/v2/options/contracts"
        params = {
            "underlying_symbol": symbol,
            "expiry": expiry,
            "option_type": option_type,
            "sort": "strike",
            "direction": "asc" if option_type == "call" else "desc",
            "limit": 100,
        }
        response = requests.get(url, headers=self.headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        if isinstance(data, list):
            return data
        raise RuntimeError("Unexpected options contract response format")

    def _select_contract(
        self,
        symbol: str,
        price: float,
        option_type: str,
    ) -> Dict[str, Any]:
        expiry = self._get_target_expiry()
        contracts = self._fetch_option_contracts(symbol, option_type, expiry)
        if not contracts:
            raise RuntimeError(
                f"No {option_type.upper()} option contracts found for {symbol} expiry {expiry}"
            )

        if option_type == "call":
            for contract in contracts:
                if float(contract.get("strike_price", contract.get("strike", 0))) >= price:
                    return contract
            return contracts[-1]

        for contract in contracts:
            if float(contract.get("strike_price", contract.get("strike", 0))) <= price:
                return contract
        return contracts[-1]

    def _place_option_order(
        self,
        option_symbol: str,
        qty: int,
        side: str,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/v2/options/orders"
        payload = {
            "order_class": "simple",
            "symbol": option_symbol,
            "qty": qty,
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        response = requests.post(url, headers=self.headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def buy_call_option(self, symbol: str, price: float) -> Dict[str, Any]:
        contract = self._select_contract(symbol, price, option_type="call")
        option_symbol = contract.get("symbol") or contract.get("option_symbol")
        if not option_symbol:
            raise RuntimeError("Option contract symbol not available")
        order = self._place_option_order(option_symbol, qty=1, side="buy")
        return {
            "contract": contract,
            "order": order,
        }

    def buy_put_option(self, symbol: str, price: float) -> Dict[str, Any]:
        contract = self._select_contract(symbol, price, option_type="put")
        option_symbol = contract.get("symbol") or contract.get("option_symbol")
        if not option_symbol:
            raise RuntimeError("Option contract symbol not available")
        order = self._place_option_order(option_symbol, qty=1, side="buy")
        return {
            "contract": contract,
            "order": order,
        }
