"""Every live data source still answers in the shape SONAR parses.

Opt-in: `./run-tests.sh -m network -q`. The default run never touches the
network (tests/conftest.py), which is right for a suite and leaves one
failure class uncaught — a third-party payload changing shape. The parsers
then return nothing, every fetch path treats nothing as "offline", and the
first sign is a panel quietly showing "—" (TESTING.md §5). Until 2026-10-10
the only checks of this kind were ESPN's leagues; these cover the sources the
app's numbers come from. Run them weekly, and before calling a build
installed.

Each test asks for real data and asserts on what only a working source
returns — a price in a plausible range, a timestamp near now, rows with the
fields the parser reads — not merely that something came back.
"""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.network


@pytest.fixture(autouse=True)
def own_cache(tmp_path, monkeypatch):
    """The macro and asset fetchers write caches; keep them out of the app's."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)


def test_binance_serves_the_hour_in_progress():
    from sonar import feeds
    c = feeds.hourly_candle()
    assert c is not None, "neither Binance nor the Coinbase fallback answered"
    assert 1_000 < c.price < 10_000_000
    assert abs(time.time() - c.open_time) < 2 * 3600
    assert not feeds.is_stale(c)


def test_binance_serves_enough_hourly_returns_for_sigma():
    from sonar import feeds
    rets = feeds.recent_hourly_returns(limit=72)
    assert len(rets) >= 70
    assert all(abs(r) < 0.5 for r in rets)


def test_binance_settles_a_closed_hour():
    from sonar import feeds
    hour = int(time.time() // 3600 - 3) * 3600
    close = feeds.hour_close(hour)
    assert close is not None and 1_000 < close < 10_000_000


def test_polymarket_lists_the_hourly_market_with_a_book():
    """The market the engine prices against. It must belong to the current
    hour (the alignment invariant refuses anything else) and carry a touch."""
    from sonar import feeds
    m = feeds.current_market()
    assert m is not None, "no hourly BTC up/down market found"
    assert 0.0 <= m.implied_up <= 1.0
    assert m.end_time > time.time() - 60
    assert m.end_time - time.time() <= 3600 + 60
    assert m.best_bid is None or 0.0 <= m.best_bid <= 1.0
    assert m.best_ask is None or 0.0 <= m.best_ask <= 1.0


def test_yahoo_serves_a_year_of_daily_closes():
    from sonar import assets
    bars = assets.fetch_bars("SPY")
    assert bars and len(bars) > 200, "the screener's main source is down or changed"
    t, close = bars[-1]
    assert time.time() - t < 7 * 86400
    assert 10 < close < 100_000


def test_fred_serves_every_series_the_macro_tab_reads():
    from sonar import macro
    snap = macro.snapshot(ttl=0)
    assert not snap.stale, "no FRED series answered"
    missing = [k for k in ("ten_year", "curve_spread", "fed_funds", "vix",
                           "real_10y", "cpi_yoy", "unemployment")
               if getattr(snap, k) is None]
    assert not missing, f"FRED returned nothing for {missing}"


def test_nasdaq_serves_an_earnings_calendar():
    from sonar import events
    cache = events.EventsCache()
    cache.refresh(lookahead=7)
    payload = cache.cached_payload()
    assert payload["n_earnings"] > 0, "a week of weekdays with no earnings at all"
    assert payload["generated"] > 0


def test_most_newswires_answer():
    """Twenty-four feeds across nine press blocs. A few being down is weather;
    most being down is the parser."""
    from sonar import news
    cache = news.NewsCache()
    per_feed = {name: cache._one(name, feed) for name, feed in news.FEEDS.items()}
    answering = [n for n, heads in per_feed.items() if heads]
    assert len(answering) >= len(news.FEEDS) * 0.75, \
        f"only {len(answering)} of {len(news.FEEDS)} answered; silent: " \
        f"{sorted(set(per_feed) - set(answering))}"
    dated = [h for heads in per_feed.values() for h in heads if h.dated]
    assert dated and min(h.age_hours for h in dated) < 24


def test_the_central_banks_answer():
    from sonar import institutions
    evs = institutions.InstitutionCache().events()
    assert evs, "no central-bank release, speech or calendar entry at all"
