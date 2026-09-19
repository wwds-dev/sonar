"""Market data parsing — the shape everything downstream trusts.

`sonar/feeds.py` was 30% covered. It *looks* like network code and mostly is
not: under each fetch is a parser, and a parser that misreads a payload does not
raise — it hands back a plausible-looking wrong price that the model, the book
and the equity curve all take at face value.

The parsers are now split from the fetches, so none of this touches the network.

The test with the highest yield is `test_the_two_exchanges_agree_about_the_same
_candle`. Binance sends `[open_time_ms, open, high, low, close]` and Coinbase
sends `[time_s, low, high, open, close, volume]` — the same candle, a different
field order, and different time units. Each parser looks obviously correct on
its own. Only comparing them catches a transposition, which is exactly how the
lattice bug in `model.py` was found.
"""

import math
import time
from datetime import datetime

import pytest

from sonar import feeds

HOUR = 1_700_000_000 // 3600 * 3600


# --------------------------------------------------------------------------- #
# Candle arithmetic
# --------------------------------------------------------------------------- #
def candle(open_=100.0, price=102.0, high=105.0, low=95.0, t=HOUR):
    return feeds.Candle(open=open_, price=price, high=high, low=low,
                        open_time=t, source="test")


def test_change_and_change_pct():
    c = candle(open_=100.0, price=102.0)
    assert c.change == pytest.approx(2.0)
    assert c.change_pct == pytest.approx(2.0)


def test_a_fall_reads_negative():
    c = candle(open_=100.0, price=98.0)
    assert c.change < 0 and c.change_pct < 0


def test_a_zero_open_does_not_divide_by_zero():
    """A dead feed sends zeros, and this property is rendered on the Terminal
    tab every second."""
    assert candle(open_=0.0, price=100.0).change_pct == 0.0


def test_flat_counts_as_up():
    """Matching the market's own convention: closes *at or above* its open."""
    assert candle(open_=100.0, price=100.0).is_up is True
    assert candle(open_=100.0, price=99.99).is_up is False


# --------------------------------------------------------------------------- #
# Binance
# --------------------------------------------------------------------------- #
BINANCE_ROW = [HOUR * 1000, "100.0", "105.0", "95.0", "102.0", "12.3"]


def test_binance_klines_parse():
    c = feeds.parse_binance_klines([BINANCE_ROW])
    assert (c.open, c.high, c.low, c.price) == (100.0, 105.0, 95.0, 102.0)


def test_binance_milliseconds_become_seconds():
    """Off by a factor of 1000 and every candle looks 54,000 years stale."""
    assert feeds.parse_binance_klines([BINANCE_ROW]).open_time == HOUR


def test_binance_names_its_source():
    assert "Binance" in feeds.parse_binance_klines([BINANCE_ROW]).source
    assert "BTC/USDT" in feeds.parse_binance_klines([BINANCE_ROW], "BTCUSDT").source


@pytest.mark.parametrize("rows", [None, [], [[]], [["x", "y"]], [[HOUR, "a", "b", "c", "d"]]])
def test_a_payload_binance_cannot_parse_is_no_candle_rather_than_a_crash(rows):
    assert feeds.parse_binance_klines(rows) is None


# --------------------------------------------------------------------------- #
# Coinbase
# --------------------------------------------------------------------------- #
def coinbase_row(t=HOUR, low=95.0, high=105.0, open_=100.0, close=102.0):
    return [t, low, high, open_, close, 1.0]


def test_coinbase_candles_parse():
    c = feeds.parse_coinbase_candles([coinbase_row()], now=HOUR + 60)
    assert (c.open, c.high, c.low, c.price) == (100.0, 105.0, 95.0, 102.0)


def test_coinbase_picks_the_hour_in_progress():
    rows = [coinbase_row(t=HOUR + 3600, close=999.0), coinbase_row(t=HOUR, close=102.0)]
    assert feeds.parse_coinbase_candles(rows, now=HOUR + 60).price == 102.0


def test_coinbase_falls_back_to_the_newest_row():
    """Coinbase returns newest-first, and a gap is normal rather than fatal."""
    rows = [coinbase_row(t=HOUR - 7200, close=50.0)]
    assert feeds.parse_coinbase_candles(rows, now=HOUR + 60).price == 50.0


@pytest.mark.parametrize("rows", [None, [], [[]], [["a", "b", "c", "d", "e", "f"]]])
def test_a_payload_coinbase_cannot_parse_is_no_candle(rows):
    assert feeds.parse_coinbase_candles(rows, now=HOUR) is None


# --------------------------------------------------------------------------- #
# The cross-check
# --------------------------------------------------------------------------- #
def test_the_two_exchanges_agree_about_the_same_candle():
    """The same candle, in two different field orders and two time units.

    Binance: [open_time_ms, open, high, low, close]
    Coinbase: [time_s,      low,  high, open, close, volume]

    Both parsers look right in isolation. This is what catches a transposed
    high/low or open/close — the failure that produces a perfectly plausible
    wrong number and never raises.
    """
    binance = feeds.parse_binance_klines(
        [[HOUR * 1000, "100.0", "105.0", "95.0", "102.0", "1.0"]])
    coinbase = feeds.parse_coinbase_candles(
        [[HOUR, 95.0, 105.0, 100.0, 102.0, 1.0]], now=HOUR + 60)

    assert binance.open == coinbase.open
    assert binance.high == coinbase.high
    assert binance.low == coinbase.low
    assert binance.price == coinbase.price
    assert binance.open_time == coinbase.open_time
    assert binance.source != coinbase.source, "only the label should differ"


def test_both_parsers_agree_that_high_is_the_highest():
    """A transposition would usually break this invariant before anything else."""
    for c in (feeds.parse_binance_klines([[HOUR * 1000, "100", "105", "95", "102"]]),
              feeds.parse_coinbase_candles([[HOUR, 95.0, 105.0, 100.0, 102.0, 1.0]],
                                           now=HOUR)):
        assert c.high >= c.open and c.high >= c.price
        assert c.low <= c.open and c.low <= c.price


# --------------------------------------------------------------------------- #
# Staleness — the delisting trap
# --------------------------------------------------------------------------- #
def test_a_fresh_candle_is_not_stale():
    assert not feeds.is_stale(candle(t=int(time.time())))


def test_a_candle_from_years_ago_is_stale():
    """Binance kept answering /klines for XMRUSDT for years after delisting it,
    returning the final candle from the day it stopped trading. It never errors,
    so nothing downstream notices — this check is the only thing that does."""
    assert feeds.is_stale(candle(t=int(time.time()) - 3 * 365 * 86400))


def test_the_tolerance_is_hours_not_minutes():
    """A slow exchange or a clock skew must not blank the tab."""
    assert not feeds.is_stale(candle(t=int(time.time()) - 3000))
    assert feeds.is_stale(candle(t=int(time.time()) - 3 * 3600))


# --------------------------------------------------------------------------- #
# Volatility input
# --------------------------------------------------------------------------- #
def klines(closes):
    return [[HOUR * 1000 + i * 3_600_000, "0", "0", "0", str(c)]
            for i, c in enumerate(closes)]


def test_log_returns_are_hour_on_hour():
    got = feeds.log_returns_from_klines(klines([100.0, 110.0, 99.0]))
    assert got == pytest.approx([math.log(1.1), math.log(99 / 110)])


def test_a_flat_series_has_no_movement():
    assert feeds.log_returns_from_klines(klines([100.0] * 6)) == pytest.approx([0.0] * 5)


@pytest.mark.parametrize("rows", [None, [], klines([100.0]), klines([100.0, 101.0])])
def test_too_little_history_yields_nothing_rather_than_noise(rows):
    assert feeds.log_returns_from_klines(rows) == []


def test_a_zero_close_is_skipped_rather_than_taking_log_of_zero():
    """The shape a halted or delisted pair sends. `log(0)` here would take the
    volatility estimate — and every probability computed from it — with it."""
    got = feeds.log_returns_from_klines(klines([100.0, 0.0, 100.0, 101.0]))
    assert all(math.isfinite(x) for x in got)


def test_an_unparseable_payload_yields_nothing():
    assert feeds.log_returns_from_klines([["a"], ["b"], ["c"]]) == []


# --------------------------------------------------------------------------- #
# The order book
# --------------------------------------------------------------------------- #
def test_bids_are_sorted_best_first_and_asks_too():
    """The engine reads bids[0] and asks[0] as the best price available. Sort
    either the wrong way and every entry is priced against the far side."""
    data = {"bids": [{"price": "0.40", "size": "10"},
                     {"price": "0.45", "size": "5"},
                     {"price": "0.30", "size": "99"}],
            "asks": [{"price": "0.60", "size": "10"},
                     {"price": "0.55", "size": "5"},
                     {"price": "0.70", "size": "99"}]}
    bids, asks = feeds.parse_order_book(data)
    assert [p for p, _ in bids] == [0.45, 0.40, 0.30], "best bid is the highest"
    assert [p for p, _ in asks] == [0.55, 0.60, 0.70], "best ask is the lowest"


def test_the_book_is_capped_at_the_depth_asked_for():
    data = {"bids": [{"price": str(0.5 - i / 100), "size": "1"} for i in range(30)],
            "asks": []}
    assert len(feeds.parse_order_book(data, depth=5)[0]) == 5


def test_an_empty_or_missing_book_is_empty_not_an_error():
    assert feeds.parse_order_book({}) == ([], [])
    assert feeds.parse_order_book({"bids": None, "asks": None}) == ([], [])


def test_a_level_with_a_missing_price_does_not_crash_the_book():
    bids, _ = feeds.parse_order_book({"bids": [{"size": "10"}], "asks": []})
    assert bids == [(0.0, 10.0)]


# --------------------------------------------------------------------------- #
# Small helpers that everything leans on
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw, expected", [
    ("1.5", 1.5), (2, 2.0), (None, 0.0), ("", 0.0), ("abc", 0.0), ([], 0.0),
])
def test_floats_from_an_api_never_raise(raw, expected):
    assert feeds._f(raw) == expected


def test_a_float_can_carry_its_own_default():
    assert feeds._f(None, default=0.5) == 0.5


def test_an_iso_timestamp_becomes_unix_seconds():
    assert feeds._iso_to_unix("2026-01-01T00:00:00Z") == 1767225600


def test_a_missing_end_date_assumes_the_next_hour_boundary():
    got = feeds._iso_to_unix(None)
    assert got % 3600 == 0
    assert got > time.time()


def test_an_unparseable_end_date_does_not_raise():
    assert feeds._iso_to_unix("not a date") > 0


def test_the_hour_slug_matches_polymarket_s_format():
    """Get this wrong and the market lookup silently falls back to 'soonest
    ending', which is usually — but not always — the same market."""
    assert feeds._hour_slug(datetime(2026, 1, 5, 19, 30)) == \
        "bitcoin-up-or-down-january-5-2026-7pm-et"


def test_the_hour_slug_uses_a_twelve_hour_clock():
    assert "12am" in feeds._hour_slug(datetime(2026, 3, 9, 0, 5))
    assert "12pm" in feeds._hour_slug(datetime(2026, 3, 9, 12, 5))


# --------------------------------------------------------------------------- #
# The fetch layer, with the network stubbed at `_get`
# --------------------------------------------------------------------------- #
@pytest.fixture
def api(monkeypatch):
    """Answer `_get` from a routing table keyed on a substring of the URL."""
    routes: dict[str, object] = {}

    def fake_get(url, timeout=8.0):
        for fragment, payload in routes.items():
            if fragment in url:
                return payload
        return None

    monkeypatch.setattr(feeds, "_get", fake_get)
    return routes


def test_a_fresh_binance_candle_is_used_directly(api):
    api["binance"] = [[int(time.time()) // 3600 * 3600 * 1000,
                       "100", "105", "95", "102"]]
    assert "Binance" in feeds.hourly_candle().source


def test_a_stale_binance_candle_falls_through_to_coinbase(api):
    """The delisting case. Binance answers happily with a three-year-old candle,
    so 'it returned something' is not the same as 'it returned a price'."""
    api["binance"] = [[(int(time.time()) - 3 * 365 * 86400) * 1000,
                       "100", "105", "95", "102"]]
    api["coinbase"] = [[int(time.time()) // 3600 * 3600, 95.0, 105.0, 100.0, 102.0, 1.0]]
    assert "Coinbase" in feeds.hourly_candle().source


def test_both_feeds_down_is_no_candle_rather_than_a_stale_one(api):
    """A missing signal is a visible problem; a stale one silently poisons every
    number computed from it."""
    assert feeds.hourly_candle() is None


def test_only_bitcoin_has_a_second_source(api):
    """Coinbase is wired for BTC-USD only — another symbol must not silently
    receive Bitcoin's price."""
    api["coinbase"] = [[int(time.time()) // 3600 * 3600, 95.0, 105.0, 100.0, 102.0, 1.0]]
    assert feeds.hourly_candle("ETHUSDT") is None


def test_a_dead_feed_yields_no_volatility_samples(api):
    assert feeds.recent_hourly_returns() == []


# --------------------------------------------------------------------------- #
# hour_close — the gap-settlement lookup
# --------------------------------------------------------------------------- #
def past_hour() -> int:
    return int(time.time()) // 3600 * 3600 - 7200


def test_hour_close_returns_the_requested_hours_close(api):
    t = past_hour()
    api["binance"] = [[t * 1000, "100", "105", "95", "101.5"]]
    assert feeds.hour_close(t) == pytest.approx(101.5)


def test_hour_close_refuses_an_hour_still_in_progress(api):
    """An in-progress candle's close is a live price wearing a close's name.
    Settling a position against it is the exact bug this function exists to
    prevent, one layer down."""
    api["binance"] = [[int(time.time()) // 3600 * 3600 * 1000,
                       "100", "105", "95", "102"]]
    assert feeds.hour_close(int(time.time()) // 3600 * 3600) is None


def test_hour_close_refuses_a_candle_for_a_different_hour(api):
    """Binance answers a startTime it has no candle for with the next candle it
    does have — a delisted or gappy pair must yield None, not a neighbour's
    price."""
    t = past_hour()
    api["binance"] = [[(t + 3600) * 1000, "100", "105", "95", "102"]]
    assert feeds.hour_close(t) is None


def test_hour_close_survives_a_dead_feed(api):
    assert feeds.hour_close(past_hour()) is None


def test_hour_close_survives_a_malformed_payload(api):
    api["binance"] = [["not-a-time", "x"]]
    assert feeds.hour_close(past_hour()) is None


def test_the_market_is_read_from_the_hour_slug(api):
    api["events?slug="] = [{
        "slug": "bitcoin-up-or-down-january-5-2026-7pm-et",
        "title": "Bitcoin Up or Down",
        "endDate": "2026-01-05T20:00:00Z",
        "markets": [{"clobTokenIds": '["tok-up", "tok-down"]',
                     "bestBid": "0.48", "bestAsk": "0.52",
                     "outcomePrices": '["0.50", "0.50"]', "volumeNum": "1234"}],
    }]
    api["midpoint?token_id="] = {"mid": "0.51"}
    api["book?token_id="] = {"bids": [{"price": "0.48", "size": "100"}],
                             "asks": [{"price": "0.52", "size": "100"}]}
    book = feeds.current_market()
    assert book.implied_up == pytest.approx(0.51)
    assert book.best_bid == pytest.approx(0.48)
    assert book.up_token == "tok-up", "the Up token is the first of the pair"
    assert book.bids and book.asks


def test_a_market_with_no_midpoint_falls_back_to_the_outcome_price(api):
    api["events?slug="] = [{"slug": "s", "title": "t",
                            "markets": [{"clobTokenIds": '["tok-up","tok-down"]',
                                         "outcomePrices": '["0.63", "0.37"]'}]}]
    assert feeds.current_market().implied_up == pytest.approx(0.63)


def test_a_market_with_nothing_to_price_is_an_even_split(api):
    api["events?slug="] = [{"slug": "s", "title": "t", "markets": [{}]}]
    assert feeds.current_market().implied_up == 0.5


def test_no_market_for_this_hour_falls_back_to_the_series(api):
    """Polymarket's slug format has changed before; the series query is what
    keeps the tab alive when it does."""
    api["series_slug="] = [{"slug": "fallback", "title": "t",
                            "markets": [{"outcomePrices": '["0.55","0.45"]'}]}]
    assert feeds.current_market().slug == "fallback"


def test_no_market_at_all_is_none(api):
    assert feeds.current_market() is None


def test_an_event_with_no_markets_is_none(api):
    api["events?slug="] = [{"slug": "s", "title": "t", "markets": []}]
    assert feeds.current_market() is None


def test_a_malformed_token_list_does_not_lose_the_market(api):
    """Without a token there is no order book, but the price is still worth
    having — degrading to less rather than to nothing."""
    api["events?slug="] = [{"slug": "s", "title": "t",
                            "markets": [{"clobTokenIds": "not json",
                                         "outcomePrices": '["0.6","0.4"]'}]}]
    book = feeds.current_market()
    assert book is not None and book.up_token == "" and book.bids == []


# --------------------------------------------------------------------------- #
# The warm-up's decision points — where a lookahead bug would hide
# --------------------------------------------------------------------------- #
def _hourly(n, start=HOUR, base=100.0):
    return [{"t": start + i * 3600, "open": base + i, "close": base + i + 1}
            for i in range(n)]


def _minutes(hourly, minute=40):
    return {h["t"] + minute * 60: h["open"] + 0.5 for h in hourly}


def test_one_row_per_hour_asked_for():
    hourly = _hourly(40)
    rows = feeds.assemble_decision_points(hourly, _minutes(hourly), hours=10)
    assert len(rows) == 10
    assert rows[-1]["open_time"] == hourly[-1]["t"]


def test_the_decision_price_comes_from_the_right_minute():
    hourly = _hourly(30)
    minutes = {h["t"] + 40 * 60: 555.0 for h in hourly}
    rows = feeds.assemble_decision_points(hourly, minutes, hours=5)
    assert all(r["price"] == 555.0 for r in rows)


def test_tau_is_the_hour_that_is_left():
    hourly = _hourly(30)
    rows = feeds.assemble_decision_points(hourly, _minutes(hourly, 40), hours=5,
                                          decision_minute=40)
    assert rows[0]["tau"] == pytest.approx(1 - 40 / 60)


def test_an_hour_with_no_minute_price_is_skipped_not_invented():
    """A made-up price is worse than a shorter curve."""
    hourly = _hourly(30)
    minutes = _minutes(hourly)
    del minutes[hourly[-1]["t"] + 40 * 60]
    rows = feeds.assemble_decision_points(hourly, minutes, hours=5)
    assert len(rows) == 4
    assert all(r["open_time"] != hourly[-1]["t"] for r in rows)


def test_sigma_is_causal():
    """The lookahead bug this split exists to make testable.

    Volatility for an hour must come only from hours *before* it. Feed a series
    that is dead flat until a violent hour, and that hour's own sigma must still
    be the calm one — if it sees itself, the backtest is being told the answer.
    """
    hourly = [{"t": HOUR + i * 3600, "open": 100.0, "close": 100.0}
              for i in range(30)]
    hourly[-1] = {"t": hourly[-1]["t"], "open": 100.0, "close": 400.0}
    rows = feeds.assemble_decision_points(hourly, _minutes(hourly), hours=3,
                                          vol_window=24)
    assert rows[-1]["sigma"] < 0.001, "the violent hour leaked into its own sigma"


def test_sigma_does_pick_up_a_move_on_the_following_hour():
    """The other half — causal must not mean blind."""
    hourly = [{"t": HOUR + i * 3600, "open": 100.0, "close": 100.0}
              for i in range(30)]
    hourly[-2] = {"t": hourly[-2]["t"], "open": 100.0, "close": 400.0}
    rows = feeds.assemble_decision_points(hourly, _minutes(hourly), hours=3,
                                          vol_window=24)
    assert rows[-1]["sigma"] > rows[0]["sigma"]


def test_too_little_history_falls_back_to_a_default_sigma():
    hourly = _hourly(3)
    rows = feeds.assemble_decision_points(hourly, _minutes(hourly), hours=3)
    assert rows[0]["sigma"] == 0.0045


def test_a_zero_close_in_the_window_does_not_break_sigma():
    hourly = _hourly(30)
    hourly[5] = {"t": hourly[5]["t"], "open": 100.0, "close": 0.0}
    rows = feeds.assemble_decision_points(hourly, _minutes(hourly), hours=5)
    assert all(math.isfinite(r["sigma"]) for r in rows)


def test_asking_for_more_hours_than_exist_is_not_an_error():
    hourly = _hourly(4)
    assert len(feeds.assemble_decision_points(hourly, _minutes(hourly), hours=50)) == 4
