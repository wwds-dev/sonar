"""The engine gives the account-value curve its past — carefully.

`Live._seed_account_history` runs on the engine thread right after a scan
that fetched 129 charts, which is exactly when Yahoo throttles the next burst.
A history built on part of the book would value the missing instruments at
entry and draw a flatter past than happened, so a short answer is refused and
retried later rather than used. These tests pin that policy, with the fetch
replaced by a stub: what comes back is the variable under test.
"""

from __future__ import annotations

import time
from datetime import datetime

import pytest

from sonar import core

ASSET = {"symbol": "AAA", "name": "Alpha", "price": 100.0, "volatility": 0.02,
         "confidence": 60.0, "cls": "Equity"}
OTHER = {**ASSET, "symbol": "BBB", "name": "Beta"}


def _day(y, m, d, h=0) -> float:
    return datetime(y, m, d, h).timestamp()


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    lv = core.Live()
    for row in (ASSET, OTHER):
        pos, _ = lv.book.enter(row, "LONG", 4, "week")
        pos.opened_at = _day(2026, 9, 1, 10)           # a week of history to rebuild
    lv.book.save()
    return lv


def _bars(symbols):
    return {s: [(_day(2026, 9, d, 9), 100.0 + d) for d in range(1, 9)] for s in symbols}


def test_a_complete_answer_seeds_the_history_and_publishes_it(live, monkeypatch):
    monkeypatch.setattr(core.assets, "fetch_bars", lambda s, rng=None: _bars([s])[s])
    monkeypatch.setattr(core.time, "time", lambda: _day(2026, 9, 8, 12))
    live._seed_account_history()
    assert len(live.book.equity_log) == 7                   # 1–7 Sep, full days
    assert live.positions["equity"] == live.book.equity_log
    assert live._seed_tries == 0                            # a success costs nothing


def test_a_partial_answer_is_refused_and_costs_a_try(live, monkeypatch):
    monkeypatch.setattr(core.assets, "fetch_bars",
                        lambda s, rng=None: _bars([s])[s] if s == "AAA" else None)
    live._seed_account_history()
    assert live.book.equity_log == []
    assert live._seed_tries == 1


def test_no_answer_at_all_costs_nothing(live, monkeypatch):
    """Offline is not a reason to give up: the attempt is free and comes back."""
    monkeypatch.setattr(core.assets, "fetch_bars", lambda s, rng=None: None)
    live._seed_account_history()
    assert live.book.equity_log == []
    assert live._seed_tries == 0
    assert live._seed_at > 0                                # but it did wait


def test_attempts_are_spaced_out(live, monkeypatch):
    calls = []
    monkeypatch.setattr(core.assets, "fetch_bars",
                        lambda s, rng=None: calls.append(s) or None)
    now = [1_000_000.0]
    monkeypatch.setattr(core.time, "time", lambda: now[0])
    live._seed_account_history()
    n = len(calls)
    assert n == 2
    now[0] += core.SEED_RETRY_EVERY - 1
    live._seed_account_history()
    assert len(calls) == n                                  # too soon
    now[0] += 2
    live._seed_account_history()
    assert len(calls) == 2 * n


def test_it_gives_up_after_enough_partial_answers(live, monkeypatch):
    monkeypatch.setattr(core.assets, "fetch_bars",
                        lambda s, rng=None: _bars([s])[s] if s == "AAA" else None)
    now = [1_000_000.0]
    monkeypatch.setattr(core.time, "time", lambda: now[0])
    for _ in range(core.SEED_MAX_TRIES + 2):
        live._seed_account_history()
        now[0] += core.SEED_RETRY_EVERY + 1
    assert live._seed_tries == core.SEED_MAX_TRIES


def test_nothing_is_fetched_once_the_log_reaches_back_to_the_first_entry(live, monkeypatch):
    live.book.equity_log = [{"t": int(_day(2026, 9, 1, 12)), "v": 10_000.0}]
    monkeypatch.setattr(core.assets, "fetch_bars",
                        lambda s, rng=None: pytest.fail("fetched with nothing to fill"))
    live._seed_account_history()
    assert live._seed_at == 0.0


def test_the_scan_runs_the_seed_after_marking_the_book(live, monkeypatch):
    """The order matters: the first live point may land first, and the seed
    must fill the days before it rather than stand down."""
    monkeypatch.setattr(core.assets, "fetch_bars", lambda s, rng=None: _bars([s])[s])
    now = _day(2026, 9, 8, 12)
    monkeypatch.setattr(core.time, "time", lambda: now)
    rows = [dict(ASSET, price=108.0), dict(OTHER, price=108.0)]
    live._mark_book({"assets": rows})
    assert len(live.book.equity_log) == 1                   # the live point
    live._seed_account_history()
    assert len(live.book.equity_log) == 8                   # 7 days before it, then it
    assert live.book.equity_log[-1]["t"] == int(now)
    assert all(a["t"] < b["t"] for a, b in zip(live.book.equity_log, live.book.equity_log[1:]))
