"""A delisted pair must not be mistaken for a live one.

Binance removed XMRUSDT in February 2024 but kept answering ``/klines`` for it,
returning the final candle from the day of delisting. Years later that endpoint
still reports ~$118 while Monero actually trades near $369 — a plausible number,
silently three years out of date, and never an error.

Anything computed from a candle like that is wrong without looking wrong, which
is the worst failure mode this project has. So freshness is checked, and a stale
candle is treated as no candle at all.
"""

import time

from sonar import feeds


def candle(age_hours: float) -> feeds.Candle:
    return feeds.Candle(open=100.0, price=101.0, high=102.0, low=99.0,
                        open_time=int(time.time() - age_hours * 3600),
                        source="test")


def test_current_candle_is_fresh():
    assert feeds.is_stale(candle(0.0)) is False
    assert feeds.is_stale(candle(0.5)) is False


def test_slightly_late_candle_is_tolerated():
    """A slow exchange or a little clock skew must not blank the terminal."""
    assert feeds.is_stale(candle(1.5)) is False


def test_yesterdays_candle_is_stale():
    assert feeds.is_stale(candle(24.0)) is True


def test_the_monero_case():
    """The real one: a candle frozen at delisting, ~900 days old."""
    assert feeds.is_stale(candle(899 * 24)) is True


def test_stale_feed_yields_no_candle(monkeypatch):
    """hourly_candle returns None rather than passing a stale price through."""
    monkeypatch.setattr(feeds, "_binance_hour", lambda symbol="X": candle(5000))
    assert feeds.hourly_candle("XMRUSDT") is None


def test_fresh_feed_passes_through(monkeypatch):
    fresh = candle(0.2)
    monkeypatch.setattr(feeds, "_binance_hour", lambda symbol="X": fresh)
    assert feeds.hourly_candle("ETHUSDT") is fresh


def test_btc_falls_back_to_coinbase_when_binance_is_stale(monkeypatch):
    """BTC has a second source, so staleness should reach for it."""
    backup = candle(0.1)
    monkeypatch.setattr(feeds, "_binance_hour", lambda symbol="X": candle(5000))
    monkeypatch.setattr(feeds, "_coinbase_hour", lambda: backup)
    assert feeds.hourly_candle("BTCUSDT") is backup


def test_monero_is_not_wired_to_the_hourly_model():
    """Monero is on the screener but must never reach the Binance-backed
    engine, because Binance no longer lists it."""
    from sonar import assets
    symbols = [s for s, _n, _c, _k in assets.WATCHLIST]
    assert "XMR-USD" in symbols
    assert "XMR-USD" not in assets.CRYPTO_BINANCE
