"""The EDGAR earnings backfill — the catalyst weight's day in court.

The catalyst component is 0.20 of the confidence score and was the only one
attribution could not grade: "not measured" is honest, but a fifth of the
score resting on an untested claim is not a resting state. These pin down the
parsing (an Item-2.02 8-K is an earnings release; everything else is not),
the point-in-time lookup, and that the backtest actually computes the same
catalyst number the live screen does.
"""

import datetime as dt

from sonar import events
from sonar.research import earnings


def submissions(rows):
    forms, dates, items = zip(*rows) if rows else ([], [], [])
    return {"filings": {"recent": {"form": list(forms),
                                   "filingDate": list(dates),
                                   "items": list(items)}}}


def test_only_result_8ks_are_earnings():
    d = submissions([
        ("8-K", "2024-01-25", "2.02,9.01"),       # the earnings release
        ("8-K", "2024-02-02", "5.02,9.01"),       # a board change is not one
        ("10-Q", "2024-02-06", ""),               # the quarterly itself: no items
        ("8-K", "2024-04-25", "2.02"),
    ])
    assert earnings.earnings_dates_from_submissions(d) == \
        ["2024-01-25", "2024-04-25"]


def test_amended_duplicates_collapse_to_one_date():
    d = submissions([("8-K", "2024-01-25", "2.02"),
                     ("8-K", "2024-01-25", "2.02,9.01")])
    assert earnings.earnings_dates_from_submissions(d) == ["2024-01-25"]


def test_a_filer_with_no_item_column_yields_nothing():
    """Foreign filers report on 20-F and 6-K, which carry no item numbers —
    they must come back empty, not wrong."""
    d = {"filings": {"recent": {"form": ["6-K", "20-F"],
                                "filingDate": ["2024-01-01", "2024-03-01"],
                                "items": ["", ""]}}}
    assert earnings.earnings_dates_from_submissions(d) == []


def test_a_malformed_payload_is_empty_not_an_error():
    assert earnings.earnings_dates_from_submissions({}) == []
    assert earnings.earnings_dates_from_submissions({"filings": {}}) == []


def test_days_to_next_is_point_in_time():
    dates = ["2024-01-25", "2024-04-25", "2024-07-25"]
    assert earnings.days_to_next(dates, dt.date(2024, 4, 20)) == 5
    assert earnings.days_to_next(dates, dt.date(2024, 4, 25)) == 0, \
        "announcement day is a catalyst, not history"
    assert earnings.days_to_next(dates, dt.date(2024, 4, 26)) == 90
    assert earnings.days_to_next(dates, dt.date(2024, 8, 1)) is None, \
        "nothing scheduled is None, not a large number"


def test_far_future_dates_are_not_on_anyones_calendar_yet():
    assert earnings.days_to_next(["2025-01-01"], dt.date(2024, 1, 1)) is None


# --------------------------------------------------------------------------- #
# The wiring: the replay computes the same number the live screen does
# --------------------------------------------------------------------------- #
def test_the_replay_scores_catalyst_like_the_live_screen():
    from sonar import backtest

    n = 60
    bars = backtest.Bars(
        symbol="X",
        time=[int(dt.datetime(2024, 1, 1).timestamp()) + i * 86400
              for i in range(n)],
        open=[100.0] * n,
        high=[100.0 + (i % 7) for i in range(n)],
        low=[100.0 - (i % 5) for i in range(n)],
        close=[100.0 + ((i * 37) % 11 - 5) * 0.4 for i in range(n)])
    dates = ["2024-02-15"]
    trials = backtest.run_symbol(bars, horizon_days=5, step=2, earnings=dates)
    assert trials, "the synthetic series must resolve some setups"
    for t in trials:
        day = dt.datetime.utcfromtimestamp(t["t"]).date()
        away = earnings.days_to_next(dates, day)
        assert t["c_catalyst"] == events.catalyst_score(away, 5), \
            "attribution must measure the shipped formula, not a reconstruction"
    assert any(t["c_catalyst"] > 0 for t in trials), \
        "some decision points sit inside the event window"


def test_without_a_series_the_component_is_absent_not_zero():
    from sonar import backtest

    n = 60
    bars = backtest.Bars(
        symbol="X",
        time=[i * 86400 for i in range(n)], open=[100.0] * n,
        high=[101.0] * n, low=[99.0] * n,
        close=[100.0 + (i % 3) for i in range(n)])
    trials = backtest.run_symbol(bars, horizon_days=5, step=2)
    assert all(t["c_catalyst"] is None for t in trials), \
        "None is 'untested'; 0.0 would be a claim that no event was near"


def test_history_caches_misses_and_serves_from_disk(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        if "company_tickers" in url:
            return {"0": {"ticker": "AAPL", "cik_str": 320193}}
        return submissions([("8-K", "2024-01-25", "2.02")])

    monkeypatch.setattr(earnings, "_get", fake_get)
    first = earnings.history(["AAPL", "UNKNOWN"], refresh=True)
    assert first == {"AAPL": ["2024-01-25"], "UNKNOWN": []}
    n_calls = len(calls)
    assert earnings.history(["AAPL", "UNKNOWN"]) == first
    assert len(calls) == n_calls, "the second ask is answered from disk"
