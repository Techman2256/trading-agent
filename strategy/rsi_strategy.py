from typing import Literal, NamedTuple

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

Signal = Literal["STRONG BUY", "STRONG SELL", "HOLD"]


class SignalResult(NamedTuple):
    signal: Signal
    rsi: float | None
    ema_9: float | None
    ema_21: float | None
    ema_cross: str
    support_level: float | None
    resistance_level: float | None
    current_price: float | None
    support_confirm: bool
    resistance_confirm: bool


def calculate_rsi(data: pd.DataFrame, window: int = 14) -> pd.Series:
    """Calculate the Relative Strength Index (RSI) for a data series."""
    if data.empty or "Close" not in data.columns:
        raise ValueError("Historical data must include a Close column")
    rsi_indicator = RSIIndicator(close=data["Close"], window=window)
    return rsi_indicator.rsi()


def calculate_ema(data: pd.DataFrame, window: int) -> pd.Series:
    """Calculate an exponential moving average for the Close price."""
    if data.empty or "Close" not in data.columns:
        raise ValueError("Historical data must include a Close column")
    ema_indicator = EMAIndicator(close=data["Close"], window=window)
    return ema_indicator.ema_indicator()


def get_signal_details(data: pd.DataFrame) -> SignalResult:
    """Return detailed signal information for the latest candle."""
    required_columns = {"Close", "High", "Low"}
    if data.empty or not required_columns.issubset(set(data.columns)):
        raise ValueError("Historical data must include Close, High, and Low columns")

    rsi_series = calculate_rsi(data)
    ema_9_series = calculate_ema(data, window=9)
    ema_21_series = calculate_ema(data, window=21)

    if rsi_series.empty or ema_9_series.empty or ema_21_series.empty:
        return SignalResult(
            signal="HOLD",
            rsi=None,
            ema_9=None,
            ema_21=None,
            ema_cross="NO",
            support_level=None,
            resistance_level=None,
            current_price=None,
            support_confirm=False,
            resistance_confirm=False,
        )

    current_price = float(data["Close"].iloc[-1])
    current_rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None
    current_ema_9 = float(ema_9_series.iloc[-1]) if not pd.isna(ema_9_series.iloc[-1]) else None
    current_ema_21 = float(ema_21_series.iloc[-1]) if not pd.isna(ema_21_series.iloc[-1]) else None

    ema_cross = "NO"
    cross_above = False
    cross_below = False
    if len(ema_9_series) >= 2 and len(ema_21_series) >= 2:
        prev_ema_9 = ema_9_series.iloc[-2]
        prev_ema_21 = ema_21_series.iloc[-2]
        if not pd.isna(prev_ema_9) and not pd.isna(prev_ema_21) and current_ema_9 is not None and current_ema_21 is not None:
            if prev_ema_9 <= prev_ema_21 and current_ema_9 > current_ema_21:
                ema_cross = "ABOVE"
                cross_above = True
            elif prev_ema_9 >= prev_ema_21 and current_ema_9 < current_ema_21:
                ema_cross = "BELOW"
                cross_below = True

    support_series = data["Low"].rolling(20).min()
    resistance_series = data["High"].rolling(20).max()
    support_level = float(support_series.iloc[-1]) if not pd.isna(support_series.iloc[-1]) else None
    resistance_level = float(resistance_series.iloc[-1]) if not pd.isna(resistance_series.iloc[-1]) else None

    support_confirm = (
        support_level is not None
        and support_level > 0
        and abs(current_price - support_level) / support_level <= 0.02
    )
    resistance_confirm = (
        resistance_level is not None
        and resistance_level > 0
        and abs(current_price - resistance_level) / resistance_level <= 0.02
    )

    signal: Signal = "HOLD"
    if (
        current_rsi is not None
        and current_ema_9 is not None
        and current_ema_21 is not None
        and current_rsi < 35
        and cross_above
        and support_confirm
    ):
        signal = "STRONG BUY"
    elif (
        current_rsi is not None
        and current_ema_9 is not None
        and current_ema_21 is not None
        and current_rsi > 65
        and cross_below
        and resistance_confirm
    ):
        signal = "STRONG SELL"

    return SignalResult(
        signal=signal,
        rsi=current_rsi,
        ema_9=current_ema_9,
        ema_21=current_ema_21,
        ema_cross=ema_cross,
        support_level=support_level,
        resistance_level=resistance_level,
        current_price=current_price,
        support_confirm=support_confirm,
        resistance_confirm=resistance_confirm,
    )
