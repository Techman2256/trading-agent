import pandas as pd

from strategy.rsi_strategy import TimeframeResult, calculate_support_resistance, get_mtf_signal


def create_ohlcv_df(highs, lows, closes):
    return pd.DataFrame(
        {
            "Open": [closes[0]] * len(highs),
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": [1000] * len(highs),
        }
    )


def test_calculate_support_resistance_returns_lowest_low_and_highest_high():
    highs = [10, 12, 11, 14, 13, 15, 14, 16, 12, 17, 13, 18, 14, 19, 13, 20, 15, 22, 21, 23]
    lows = [5, 4, 6, 5, 7, 8, 6, 7, 5, 9, 8, 6, 5, 7, 4, 8, 6, 9, 7, 10]
    df = create_ohlcv_df(highs, lows, closes=[9] * len(highs))

    support, resistance = calculate_support_resistance(df)

    assert support == 4.0
    assert resistance == 23.0


def test_get_mtf_signal_returns_strong_buy_when_all_timeframes_agree(monkeypatch):
    data_1h = create_ohlcv_df([22] * 20, [20] * 20, closes=[21] * 20)
    data_4h = create_ohlcv_df([32] * 20, [30] * 20, closes=[31] * 20)
    data_1d = create_ohlcv_df([42] * 20, [40] * 20, closes=[41] * 20)

    buy_result = TimeframeResult(
        rsi=40.0,
        ema_9=22.0,
        ema_21=20.0,
        ema_cross="ABOVE",
        current_price=20.4,
    )

    monkeypatch.setattr(
        "strategy.rsi_strategy.get_signal_details",
        lambda data: buy_result,
    )

    result = get_mtf_signal("AAPL", data_1h, data_4h, data_1d)

    assert result.signal == "STRONG BUY"
    assert result.tf_1h.ema_cross == "ABOVE"
    assert result.tf_4h.ema_cross == "ABOVE"
    assert result.tf_1d.ema_cross == "ABOVE"


def test_get_mtf_signal_returns_short_when_all_timeframes_agree(monkeypatch):
    data_1h = create_ohlcv_df([22] * 20, [20] * 20, closes=[21] * 20)
    data_4h = create_ohlcv_df([32] * 20, [30] * 20, closes=[31] * 20)
    data_1d = create_ohlcv_df([42] * 20, [40] * 20, closes=[41] * 20)

    short_result = TimeframeResult(
        rsi=60.0,
        ema_9=20.0,
        ema_21=22.0,
        ema_cross="BELOW",
        current_price=21.5,
    )

    monkeypatch.setattr(
        "strategy.rsi_strategy.get_signal_details",
        lambda data: short_result,
    )

    result = get_mtf_signal("AAPL", data_1h, data_4h, data_1d)

    assert result.signal == "SHORT"
    assert result.tf_1h.ema_cross == "BELOW"
    assert result.tf_4h.ema_cross == "BELOW"
    assert result.tf_1d.ema_cross == "BELOW"
