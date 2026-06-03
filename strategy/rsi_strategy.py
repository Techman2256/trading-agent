from typing import Literal

import pandas as pd
from ta.momentum import RSIIndicator

Signal = Literal["BUY", "SELL", "HOLD"]


def calculate_rsi(data: pd.DataFrame, window: int = 14) -> pd.Series:
    """Calculate the Relative Strength Index (RSI) for a data series."""
    if data.empty or "Close" not in data.columns:
        raise ValueError("Historical data must include a Close column")
    rsi_indicator = RSIIndicator(close=data["Close"], window=window)
    return rsi_indicator.rsi()


def generate_signal(data: pd.DataFrame) -> Signal:
    """Generate a trading signal based on the current RSI value."""
    rsi = calculate_rsi(data)
    if rsi.empty:
        return "HOLD"

    current_rsi = rsi.iloc[-1]
    if pd.isna(current_rsi):
        return "HOLD"
    if current_rsi < 30:
        return "BUY"
    if current_rsi > 70:
        return "SELL"
    return "HOLD"
