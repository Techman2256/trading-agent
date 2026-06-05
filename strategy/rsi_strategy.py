from typing import Literal, NamedTuple

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

Signal = Literal["STRONG BUY", "STRONG SELL", "SHORT", "HOLD"]


class SignalResult(NamedTuple):
    signal: Signal
    rsi: float | None
    ema_9: float | None
    ema_21: float | None
    ema_cross: str
    current_price: float | None


class TimeframeResult(NamedTuple):
    rsi: float | None
    ema_9: float | None
    ema_21: float | None
    ema_cross: str
    current_price: float | None


class MTFSignalResult(NamedTuple):
    signal: Signal
    tf_1h: TimeframeResult
    tf_4h: TimeframeResult
    tf_1d: TimeframeResult
    support: float | None
    resistance: float | None


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
    required_columns = {"Close"}
    if data.empty or not required_columns.issubset(set(data.columns)):
        raise ValueError("Historical data must include a Close column")

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
            current_price=None,
        )

    current_price = float(data["Close"].iloc[-1])
    current_rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None
    current_ema_9 = float(ema_9_series.iloc[-1]) if not pd.isna(ema_9_series.iloc[-1]) else None
    current_ema_21 = float(ema_21_series.iloc[-1]) if not pd.isna(ema_21_series.iloc[-1]) else None

    ema_cross = "NO"
    ema_above = False
    ema_below = False
    if current_ema_9 is not None and current_ema_21 is not None:
        if current_ema_9 > current_ema_21:
            ema_cross = "ABOVE"
            ema_above = True
        elif current_ema_9 < current_ema_21:
            ema_cross = "BELOW"
            ema_below = True

    signal: Signal = "HOLD"
    if (
        current_rsi is not None
        and current_ema_9 is not None
        and current_ema_21 is not None
        and current_rsi < 45
        and ema_above
    ):
        signal = "STRONG BUY"
    elif (
        current_rsi is not None
        and current_ema_9 is not None
        and current_ema_21 is not None
        and current_rsi > 55
        and ema_below
    ):
        # Return a SHORT signal for initiating a short position
        signal = "SHORT"

    return SignalResult(
        signal=signal,
        rsi=current_rsi,
        ema_9=current_ema_9,
        ema_21=current_ema_21,
        ema_cross=ema_cross,
        current_price=current_price,
    )


def calculate_support_resistance(data: pd.DataFrame) -> tuple[float, float]:
    """Return support and resistance based on the last 20 candles."""
    if data.empty or "Low" not in data.columns or "High" not in data.columns:
        raise ValueError("Historical data must include High/Low columns")

    recent = data.tail(20)
    support = float(recent["Low"].min())
    resistance = float(recent["High"].max())
    return support, resistance


def _get_timeframe_result(data: pd.DataFrame) -> TimeframeResult:
    signal_details = get_signal_details(data)
    return TimeframeResult(
        rsi=signal_details.rsi,
        ema_9=signal_details.ema_9,
        ema_21=signal_details.ema_21,
        ema_cross=signal_details.ema_cross,
        current_price=signal_details.current_price,
    )


def get_mtf_signal(
    symbol: str,
    data_1h: pd.DataFrame,
    data_4h: pd.DataFrame,
    data_1d: pd.DataFrame,
) -> MTFSignalResult:
    """Return a multi-timeframe signal result for the given symbol."""
    tf_1h = _get_timeframe_result(data_1h)
    tf_4h = _get_timeframe_result(data_4h)
    tf_1d = _get_timeframe_result(data_1d)
    support, resistance = calculate_support_resistance(data_1h)

    is_buy = all(
        tf.rsi is not None and tf.ema_cross == "ABOVE" and tf.rsi < 45
        for tf in (tf_1h, tf_4h, tf_1d)
    ) and tf_1h.current_price is not None and tf_1h.current_price <= support * 1.03

    is_sell = all(
        tf.rsi is not None and tf.ema_cross == "BELOW" and tf.rsi > 55
        for tf in (tf_1h, tf_4h, tf_1d)
    ) and tf_1h.current_price is not None and tf_1h.current_price >= resistance * 0.97

    signal: Signal = "HOLD"
    if is_buy:
        signal = "STRONG BUY"
    elif is_sell:
        signal = "SHORT"

    return MTFSignalResult(
        signal=signal,
        tf_1h=tf_1h,
        tf_4h=tf_4h,
        tf_1d=tf_1d,
        support=support,
        resistance=resistance,
    )
