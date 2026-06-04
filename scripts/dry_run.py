"""Dry run script to simulate one trading cycle without network or Alpaca calls.

This script uses `strategy.get_signal_details` with synthetic price series
and a `MockExecutor` to emulate order placement. No real orders or network
requests are made.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import random
from typing import Dict

import pandas as pd

from strategy.rsi_strategy import get_signal_details
from risk.risk_manager import RiskManager
from data.market_data import fetch_historical_data, SYMBOLS
from pathlib import Path
import json


class MockOrder:
    def __init__(self, id: str):
        self.id = id


class MockPosition:
    def __init__(self, qty: int, unrealized_pl: float = 0.0):
        self.qty = qty
        self.unrealized_pl = unrealized_pl


class MockExecutor:
    def __init__(self, positions: Dict[str, int]):
        # positions map symbol -> qty (positive for long, negative for short)
        self.positions = positions

    def get_account(self):
        class Acc:
            equity = 100000.0
            last_equity = 100000.0

        return Acc()

    def list_positions(self):
        return [MockPosition(q) for q in self.positions.values() if q != 0]

    def get_position_qty(self, symbol: str) -> int:
        return int(self.positions.get(symbol, 0))

    def place_market_order(self, symbol: str, qty: int, side: str):
        print(f"[MOCK] place_market_order {side} {qty} {symbol}")
        # update mock positions
        if side == "buy":
            self.positions[symbol] = max(0, self.positions.get(symbol, 0) - qty)
        else:
            self.positions[symbol] = self.positions.get(symbol, 0) + qty
        return MockOrder(id=f"mock-{symbol}-{side}-{qty}")

    def place_short_market_order(self, symbol: str, qty: int):
        print(f"[MOCK] place_short_market_order sell(short) {qty} {symbol}")
        # opening a short reduces qty (negative)
        self.positions[symbol] = self.positions.get(symbol, 0) - qty
        return MockOrder(id=f"mock-{symbol}-short-{qty}")

    def get_position(self, symbol: str):
        qty = self.positions.get(symbol, 0)
        return MockPosition(qty, unrealized_pl=random.uniform(-50, 50))

    def count_short_positions(self) -> int:
        return sum(1 for q in self.positions.values() if q < 0)


def make_synthetic_data(days: int = 60, start_price: float = 100.0, trend: str = "flat") -> pd.DataFrame:
    dates = [datetime.now().date() - timedelta(days=(days - i)) for i in range(days)]
    prices = []
    price = start_price
    for i in range(days):
        move = random.uniform(-1.0, 1.0)
        if trend == "up":
            move += 0.5
        elif trend == "down":
            move -= 0.5
        price = max(1.0, price + move)
        prices.append(round(price, 2))

    df = pd.DataFrame({"Close": prices})
    df.index = pd.date_range(end=datetime.now(), periods=days)
    df["High"] = df["Close"] * 1.01
    df["Low"] = df["Close"] * 0.99
    return df


def run(use_live: bool = True, out_path: str | None = None):
    symbols = SYMBOLS
    out_path = out_path or "logs/dry_run_results.jsonl"
    Path(out_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    out_f = open(out_path, "a", encoding="utf-8")
    # simulate we are already short on TSLA with 50 shares
    mock_positions = {"AAPL": 0, "TSLA": -50, "MSFT": 0}
    executor = MockExecutor(mock_positions)
    risk_manager = RiskManager()

    for sym in symbols:
        # try to fetch live historical data when requested, otherwise fall back to synthetic
        hist = None
        if use_live:
            try:
                # fetch last 60 days daily data
                hist = fetch_historical_data(sym, period="60d", interval="1d")
            except Exception as e:
                print(f"[WARN] Failed to fetch live data for {sym}: {e}; falling back to synthetic")
                hist = None

        if hist is None:
            # choose a trend to exercise behavior
            trend = "down" if sym == "TSLA" else "up"
            hist = make_synthetic_data(start_price=100.0 + random.uniform(-20, 20), trend=trend)

        details = get_signal_details(hist)
        qty = executor.get_position_qty(sym)
        print(f"{sym} -> signal={details.signal} RSI={details.rsi:.1f} EMA_cross={details.ema_cross} qty={qty}")

        # prepare structured result
        result = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "symbol": sym,
            "signal": str(details.signal),
            "rsi": float(details.rsi) if details.rsi is not None else None,
            "ema_cross": details.ema_cross,
            "qty": int(qty),
            "action": None,
            "pl": None,
            "price": None,
            "order_id": None,
            "order_qty": None,
        }

        current_qty = executor.get_position_qty(sym)
        # cover short if RSI < 45
        if current_qty < 0 and risk_manager.should_cover_short(details.rsi):
            pos = executor.get_position(sym)
            pl = getattr(pos, "unrealized_pl", 0.0)
            cover_qty = abs(current_qty)
            order = executor.place_market_order(sym, cover_qty, side="buy")
            print(f"✅ SHORT COVERED - Stock: {sym} Profit/Loss: ${pl:.2f}")
            result["action"] = "cover_short"
            result["pl"] = float(pl)
            # record the cover order id and price
            result["order_id"] = getattr(order, "id", None)
            result["order_qty"] = int(cover_qty)
            try:
                result["price"] = float(hist["Close"].iloc[-1])
            except Exception:
                result["price"] = None
            out_f.write(json.dumps(result) + "\n")
            continue

        if details.signal == "SHORT":
            # open short
            nshorts = executor.count_short_positions()
            if not risk_manager.can_open_short_position(nshorts):
                print(f"Skipping short for {sym}: short limit reached ({nshorts})")
                continue
            live_price = hist["Close"].iloc[-1]
            qty = risk_manager.calculate_position_size(executor.get_account().equity, live_price)
            if qty <= 0:
                print(f"Calculated short qty zero for {sym}; skipping")
                continue
            order = executor.place_short_market_order(sym, qty)
            print(f"🔴 SHORT SELL - Stock: {sym} RSI: {details.rsi:.1f}")
            result["action"] = "short_sell"
            result["order_id"] = getattr(order, "id", None)
            result["order_qty"] = int(qty)
            try:
                result["price"] = float(live_price)
            except Exception:
                result["price"] = None
            out_f.write(json.dumps(result) + "\n")

        elif details.signal == "STRONG BUY":
            if current_qty > 0:
                print(f"Already holding {current_qty} shares of {sym}")
                continue
            live_price = hist["Close"].iloc[-1]
            qty = risk_manager.calculate_position_size(executor.get_account().equity, live_price)
            if qty <= 0:
                print(f"Calculated buy qty zero for {sym}; skipping")
                continue
            order = executor.place_market_order(sym, qty, side="buy")
            print(f"🟢 BUY EXECUTED - {sym} Shares: {qty} RSI: {details.rsi:.1f} EMA: {details.ema_cross}")
            result["action"] = "buy"
            result["order_id"] = getattr(order, "id", None)
            result["order_qty"] = int(qty)
            try:
                result["price"] = float(live_price)
            except Exception:
                result["price"] = None
            out_f.write(json.dumps(result) + "\n")

    out_f.close()


if __name__ == "__main__":
    run()
