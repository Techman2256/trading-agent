from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from data.market_data import SYMBOLS, fetch_historical_data
from strategy.rsi_strategy import calculate_rsi

INITIAL_CAPITAL = 100_000
RISK_PER_TRADE = 0.02


@dataclass
class TradeResult:
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    profit_loss: float


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    peak = equity_curve[0]
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def backtest_symbol(symbol: str) -> List[TradeResult]:
    """Backtest the RSI strategy for one symbol and return closed trades."""
    data = fetch_historical_data(symbol, period="1y", interval="1d")
    data = data.copy()
    data["rsi"] = calculate_rsi(data)
    data = data.dropna(subset=["rsi"]).reset_index()

    trades: List[TradeResult] = []
    position_qty = 0
    entry_price = 0.0
    entry_date = None
    capital_per_trade = INITIAL_CAPITAL * RISK_PER_TRADE

    for idx in range(len(data) - 1):
        today = data.loc[idx]
        tomorrow = data.loc[idx + 1]
        signal = "HOLD"
        if today["rsi"] < 30:
            signal = "BUY"
        elif today["rsi"] > 70:
            signal = "SELL"

        if signal == "BUY" and position_qty == 0:
            qty = math.floor(capital_per_trade / tomorrow["Close"])
            if qty > 0:
                position_qty = qty
                entry_price = float(tomorrow["Close"])
                entry_date = tomorrow["Date"]
        elif signal == "SELL" and position_qty > 0:
            exit_price = float(tomorrow["Close"])
            exit_date = tomorrow["Date"]
            profit_loss = position_qty * (exit_price - entry_price)
            trades.append(
                TradeResult(
                    symbol=symbol,
                    entry_date=entry_date,
                    exit_date=exit_date,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    profit_loss=profit_loss,
                )
            )
            position_qty = 0
            entry_price = 0.0
            entry_date = None

    if position_qty > 0 and entry_date is not None:
        exit_price = float(data.iloc[-1]["Close"])
        exit_date = data.iloc[-1]["Date"]
        profit_loss = position_qty * (exit_price - entry_price)
        trades.append(
            TradeResult(
                symbol=symbol,
                entry_date=entry_date,
                exit_date=exit_date,
                entry_price=entry_price,
                exit_price=exit_price,
                profit_loss=profit_loss,
            )
        )

    return trades


def run_backtest() -> None:
    """Run the RSI strategy backtest across all symbols and print performance summary."""
    equity = INITIAL_CAPITAL
    equity_curve = [equity]
    all_trades: List[TradeResult] = []

    for symbol in SYMBOLS:
        try:
            symbol_trades = backtest_symbol(symbol)
            all_trades.extend(symbol_trades)
            for trade in symbol_trades:
                equity += trade.profit_loss
                equity_curve.append(equity)
        except Exception as err:
            print(f"Skipping {symbol} due to error: {err}")

    total_return = (equity - INITIAL_CAPITAL) / INITIAL_CAPITAL if INITIAL_CAPITAL else 0.0
    wins = sum(1 for trade in all_trades if trade.profit_loss > 0)
    trade_count = len(all_trades)
    win_rate = (wins / trade_count) * 100 if trade_count else 0.0
    max_drawdown = calculate_max_drawdown(equity_curve)

    print("Backtest Results")
    print("---------------")
    print(f"Total return: {total_return:.2%}")
    print(f"Win rate: {win_rate:.2f}%")
    print(f"Number of trades: {trade_count}")
    print(f"Max drawdown: {max_drawdown:.2%}")


if __name__ == "__main__":
    run_backtest()
