import pandas as pd

from strategy.rsi_strategy import TimeframeResult, get_mtf_signal


def make_test_df(highs, lows):
    return pd.DataFrame(
        {
            "Open": [100.0] * len(highs),
            "High": highs,
            "Low": lows,
            "Close": [100.0] * len(highs),
            "Volume": [1_000] * len(highs),
        }
    )


def test_get_mtf_signal_strong_buy(monkeypatch):
    data_1h = make_test_df([20.0] * 20, [10.0] * 20)
    data_4h = make_test_df([30.0] * 20, [20.0] * 20)
    data_1d = make_test_df([40.0] * 20, [30.0] * 20)

    buy_result = TimeframeResult(
        rsi=40.0,
        ema_9=15.0,
        ema_21=10.0,
        ema_cross="ABOVE",
        current_price=10.2,
    )

    monkeypatch.setattr(
        "strategy.rsi_strategy.get_signal_details",
        lambda data: buy_result,
    )

    result = get_mtf_signal("AAPL", data_1h, data_4h, data_1d)

    assert result.signal == "STRONG BUY"
    assert result.support == 10.0
    assert result.resistance == 20.0
    assert result.tf_1h.ema_cross == "ABOVE"
    assert result.tf_4h.ema_cross == "ABOVE"
    assert result.tf_1d.ema_cross == "ABOVE"


def test_get_mtf_signal_short(monkeypatch):
    data_1h = make_test_df([20.0] * 20, [10.0] * 20)
    data_4h = make_test_df([30.0] * 20, [20.0] * 20)
    data_1d = make_test_df([40.0] * 20, [30.0] * 20)

    short_result = TimeframeResult(
        rsi=60.0,
        ema_9=10.0,
        ema_21=15.0,
        ema_cross="BELOW",
        current_price=19.7,
    )

    monkeypatch.setattr(
        "strategy.rsi_strategy.get_signal_details",
        lambda data: short_result,
    )

    result = get_mtf_signal("AAPL", data_1h, data_4h, data_1d)

    assert result.signal == "SHORT"
    assert result.support == 10.0
    assert result.resistance == 20.0
    assert result.tf_1h.ema_cross == "BELOW"
    assert result.tf_4h.ema_cross == "BELOW"
    assert result.tf_1d.ema_cross == "BELOW"
