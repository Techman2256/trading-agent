from __future__ import annotations

from typing import Dict, List

import pandas as pd
import yfinance as yf

SYMBOLS: List[str] = [
    "AAPL",
    "TSLA",
    "MSFT",
    "AMZN",
    "NVDA",
    "GOOGL",
    "META",
    "NFLX",
    "AMD",
    "COIN",
    "SPY",
    "QQQ",
    "JPM",
    "DIS",
    "BA",
]


def fetch_historical_data(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame:
    """Fetch historical OHLCV data for a symbol using yfinance."""
    data = yf.download(symbol, period=period, interval=interval, progress=False)
    if data.empty:
        raise ValueError(f"No historical data returned for {symbol}")
    
    # Handle MultiIndex columns from yfinance (auto_adjust=True creates nested structure)
    # MultiIndex format is (Price_Metric, Ticker), we need just the Price_Metric level
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    
    # Ensure we have the required columns
    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    if not all(col in data.columns for col in required_cols):
        raise ValueError(f"Missing required OHLCV columns for {symbol}")
    
    return data


def fetch_live_price(symbol: str) -> float:
    """Fetch the latest live price for a symbol using yfinance."""
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="1d", interval="1m")
    if data.empty:
        raise ValueError(f"Failed to fetch live price for {symbol}")
    return float(data["Close"].iloc[-1])


def fetch_historical_data_for_symbols(
    symbols: List[str],
    period: str = "1y",
    interval: str = "1d",
) -> Dict[str, pd.DataFrame]:
    """Fetch historical data for multiple symbols in a batch."""
    results: Dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        results[symbol] = fetch_historical_data(symbol, period=period, interval=interval)
    return results
