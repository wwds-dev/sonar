"""The watchlist, and the request rate it implies.

Grown from 26 instruments to 129 so that a cross-sectional statistic within an
asset class means something — at 26, Index, Forex and Commodity held 3, 3 and 2
members, and a median absolute deviation over two instruments is not a
standardisation.

The growth brought a problem with it that is worth a test rather than a comment:
refetching every row each cycle takes the request rate from ~13 a minute to
~64, and the source throttles well below that. It does not error when it does —
it returns fewer rows, and the screen quietly shrinks. So the scanner refreshes
in rotation, and these pin that down.
"""

import time

import pytest

from sonar import assets, horizon, risk


def test_the_watchlist_is_large_enough_to_rank_within_a_class():
    from collections import Counter
    counts = Counter(cls for _, _, cls, _ in assets.WATCHLIST)
    assert len(assets.WATCHLIST) >= 100
    for cls, n in counts.items():
        assert n >= 15, f"{cls} has only {n} — too few to standardise across"


def test_no_symbol_appears_twice():
    symbols = [s for s, _, _, _ in assets.WATCHLIST]
    assert len(symbols) == len(set(symbols))


def test_every_row_is_completely_described():
    for symbol, name, cls, kw in assets.WATCHLIST:
        assert symbol and name and cls
        assert isinstance(kw, set) and kw, f"{symbol} has no news keywords"


def test_the_rebranded_ticker_stays_out():
    """MATIC-USD returns nothing since the rebrand. It is the failure mode the
    list was verified against, and a silent re-add would put an empty row back
    on the screen."""
    assert "MATIC-USD" not in [s for s, *_ in assets.WATCHLIST]


# --------------------------------------------------------------------------- #
# The rotation
# --------------------------------------------------------------------------- #
class FakeClock:
    def __init__(self):
        self.calls = []

    def fetch(self, symbol, rng):
        self.calls.append(symbol)
        closes = [100.0 + i * 0.1 for i in range(300)]
        return (closes[-1], "USD", closes)


@pytest.fixture
def scanner(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(assets, "_fetch", fake.fetch)
    sc = assets.AssetScanner()
    return sc, fake


def test_a_cold_cache_is_filled_in_one_pass(scanner):
    """A half-empty screen at launch is worse than one burst of requests."""
    sc, fake = scanner
    sc.payload([], horizon.HORIZONS["week"], risk.get("moderate"))
    assert len(fake.calls) == len(assets.WATCHLIST)


def test_a_warm_cache_refreshes_only_a_batch(scanner):
    """This is what holds the request rate near where it was at 26 instruments.
    Without it, 129 rows every two minutes is ~64 requests a minute and the
    source throttles."""
    sc, fake = scanner
    hz, pr = horizon.HORIZONS["week"], risk.get("moderate")
    sc.payload([], hz, pr)
    fake.calls.clear()
    sc._at = 0.0
    sc.payload([], hz, pr)
    assert len(fake.calls) == assets.ROLL_BATCH


def test_every_row_still_appears_while_only_a_batch_refreshes(scanner):
    """The screen must not shrink to the batch size — the rest is scored from
    cache."""
    sc, fake = scanner
    hz, pr = horizon.HORIZONS["week"], risk.get("moderate")
    sc.payload([], hz, pr)
    sc._at = 0.0
    rows = sc.payload([], hz, pr)["assets"]
    assert len(rows) >= len(assets.WATCHLIST) - 5


def test_the_stalest_rows_are_the_ones_refreshed(scanner):
    """Otherwise a row could sit unrefreshed indefinitely while its neighbours
    cycle."""
    sc, fake = scanner
    hz, pr = horizon.HORIZONS["week"], risk.get("moderate")
    sc.payload([], hz, pr)
    # Age the first batch of symbols so they are clearly the stalest.
    stale = [w[0] for w in assets.WATCHLIST[:assets.ROLL_BATCH]]
    for sym in stale:
        ts, got = sc._bars[(sym, hz.chart_range)]
        sc._bars[(sym, hz.chart_range)] = (ts - 10_000, got)
    fake.calls.clear()
    sc._at = 0.0
    sc.payload([], hz, pr)
    assert set(fake.calls) == set(stale)


def test_each_row_reports_how_old_its_data_is(scanner):
    """Rows refresh in rotation, so ages differ across the screen. Reporting it
    is what stops a stale row looking exactly like a fresh one."""
    sc, fake = scanner
    hz, pr = horizon.HORIZONS["week"], risk.get("moderate")
    rows = sc.payload([], hz, pr)["assets"]
    assert all("data_age_s" in r for r in rows)
    assert all(r["data_age_s"] >= 0 for r in rows)


def test_a_symbol_that_fails_to_fetch_is_retried_rather_than_dropped(scanner):
    """A throttled request is the common case at this size, and it must not
    remove the instrument from the screen permanently."""
    sc, fake = scanner
    hz, pr = horizon.HORIZONS["week"], risk.get("moderate")
    dead = assets.WATCHLIST[0][0]

    def flaky(symbol, rng):
        if symbol == dead:
            return None
        return fake.fetch(symbol, rng)

    import sonar.assets as mod
    original = mod._fetch
    mod._fetch = flaky
    try:
        sc.payload([], hz, pr)
        assert (dead, hz.chart_range) not in sc._bars
        # Still cold, so the next pass tries everything again — including it.
        fake.calls.clear()
        sc._at = 0.0
        mod._fetch = fake.fetch
        sc.payload([], hz, pr)
        assert dead in fake.calls
    finally:
        mod._fetch = original


def test_the_batch_is_sized_to_the_old_request_rate():
    """26 was the whole watchlist before it grew; keeping the batch there keeps
    the sustained request rate where it has always been."""
    assert assets.ROLL_BATCH == 26
