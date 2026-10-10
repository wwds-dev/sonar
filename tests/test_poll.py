"""One engine poll, with the feeds stubbed: what reaches the screen."""

from __future__ import annotations

from sonar import feeds
from sonar.core import Live

HOUR = 1_700_000_000 // 3600 * 3600


def _candle(open_time: int, price: float) -> feeds.Candle:
    return feeds.Candle(open=100.0, price=price, high=price, low=100.0,
                        open_time=open_time, source="Coinbase BTC-USD")


def test_a_candle_from_an_earlier_hour_never_reaches_the_screen(tmp_path, monkeypatch,
                                                                 real_poll):
    """The engine ignores a past hour's candle (a lagging fallback, a clock a
    few seconds behind the exchange); the terminal showed its price beside the
    current hour's signal and put it on the spark line anyway."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    live._sigma = lambda: 0.0045
    live._rescan = lambda: None
    monkeypatch.setattr(feeds, "current_market", lambda: None)
    monkeypatch.setattr(feeds, "hour_close", lambda t: None)
    monkeypatch.setattr(feeds, "hourly_candle", lambda symbol="BTCUSDT": _candle(HOUR, 101.0))
    real_poll(live)
    assert live.engine.current_hour == HOUR
    assert [p["p"] for p in live.spark] == [101.0]
    monkeypatch.setattr(feeds, "hourly_candle",
                        lambda symbol="BTCUSDT": _candle(HOUR - 3600, 55.0))
    real_poll(live)
    assert [p["p"] for p in live.spark] == [101.0], "an old price reached the spark line"
    assert live.snapshot.get("candle") is None, "an old candle reached the snapshot"
    assert live.engine.current_hour == HOUR
