"""The paper book is written from several threads; each write must be whole.

The engine thread marks the book and closes positions on barrier hits; the
window's thread and the HTTP handlers trade and close; a settings change
rescans on a thread of its own. None of it was locked. A manual close racing a
barrier hit credited the cash twice and raised `list.remove(x): x not in list`
on the loser; two saves of one file at once renamed each other's temporary
file away. These tests hold one writer inside the critical section with a gate
in the broker and send the other in, so the race is forced rather than hoped for.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

from sonar import paths
from sonar.core import Live
from sonar.engine import Engine
from sonar.portfolio import Portfolio, PaperBroker

ASSET = {"symbol": "AAA", "name": "Aaa", "price": 100.0, "volatility": 0.02,
         "confidence": 50.0, "cls": "equity"}


class GateBroker(PaperBroker):
    """Fills like the paper broker, but the first exit waits at a gate."""

    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        self.exits = 0

    def execute(self, symbol, direction, units, price):
        if direction in ("SELL", "COVER"):
            self.exits += 1
            if self.exits == 1:
                self.entered.set()
                self.release.wait(5)
        return super().execute(symbol, direction, units, price)


def _run(target, errors):
    def go():
        try:
            target()
        except Exception as exc:          # a race shows up here, in the loser
            errors.append(exc)
    t = threading.Thread(target=go, daemon=True)
    t.start()
    return t


def _book_with_a_long(path) -> tuple[Portfolio, GateBroker, object]:
    broker = GateBroker()
    book = Portfolio(path, broker=broker)
    pos, msg = book.enter(ASSET, "LONG", 5, "week")
    assert pos is not None, msg
    return book, broker, pos


def test_a_close_racing_a_barrier_hit_credits_once(tmp_path):
    book, broker, pos = _book_with_a_long(tmp_path / "portfolio.json")
    cash_before = book.cash
    errors: list[Exception] = []
    a = _run(lambda: book.close(pos.id, 105.0, "MANUAL"), errors)
    assert broker.entered.wait(5)
    b = _run(lambda: book.mark({"AAA": pos.stop - 1.0}), errors)   # the stop is hit
    time.sleep(0.1)                       # give the barrier pass its chance to cut in
    broker.release.set()
    a.join(5), b.join(5)
    assert not errors, errors
    assert len(book.closed) == 1 and book.open == []
    assert book.cash == pytest.approx(cash_before + pos.units * 105.0)
    assert broker.exits == 1, "closed twice"


def test_a_manual_close_after_a_barrier_closed_it_says_so(tmp_path, monkeypatch):
    """Found and closed under one lock in Live: the barrier pass holds the book,
    so the manual close waits, then finds nothing open rather than crashing on
    a close that returned None."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    live.book, broker, pos = _book_with_a_long(tmp_path / "portfolio.json")
    live.assets = {"assets": [dict(ASSET)]}
    cash_before = live.book.cash
    errors: list[Exception] = []
    results: list[dict] = []
    hit = {"assets": [dict(ASSET, price=pos.stop - 1.0)]}
    a = _run(lambda: live._mark_book(hit), errors)
    assert broker.entered.wait(5)
    b = _run(lambda: results.append(live.close_position(pos.id)), errors)
    time.sleep(0.1)
    broker.release.set()
    a.join(5), b.join(5)
    assert not errors, errors
    assert results and results[0]["ok"] is False
    assert results[0]["message"] == "no such open position"
    assert len(live.book.closed) == 1 and live.book.closed[0].outcome == "STOP"
    assert live.book.cash == pytest.approx(cash_before + pos.units * pos.stop)


def test_two_saves_of_one_file_at_once_both_land(tmp_path):
    errors: list[Exception] = []
    target = tmp_path / "state.json"

    def hammer(tag):
        for i in range(300):
            paths.write_atomically(target, f'{{"w": "{tag}", "i": {i}}}')

    threads = [_run(lambda t=t: hammer(t), errors) for t in ("a", "b")]
    for t in threads:
        t.join(10)
    assert not errors, errors[:3]
    assert not list(tmp_path.glob("*.tmp")), "a temporary file was left behind"


def test_the_engine_saves_from_two_threads_without_losing_a_write(tmp_path):
    eng = Engine(tmp_path / "state.json")
    errors: list[Exception] = []

    def hammer():
        for _ in range(200):
            eng.save()

    threads = [_run(hammer, errors) for _ in range(2)]
    for t in threads:
        t.join(10)
    assert not errors, errors[:3]


def test_rescans_run_one_at_a_time(tmp_path, monkeypatch):
    """The engine thread's rescan and a settings change's rescan used to run
    together and mark the book twice."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    inside, most = [0], [0]
    guard = threading.Lock()

    def slow_once():
        with guard:
            inside[0] += 1
            most[0] = max(most[0], inside[0])
        time.sleep(0.05)
        with guard:
            inside[0] -= 1

    live._rescan_once = slow_once
    errors: list[Exception] = []
    threads = [_run(live._rescan, errors) for _ in range(4)]
    for t in threads:
        t.join(5)
    assert not errors and most[0] == 1


def test_an_older_mark_pass_never_hides_a_newer_trade(tmp_path, monkeypatch):
    """The engine thread's mark pass used to publish after releasing the
    book's lock: a trade landing in that gap published one open position, then
    the older pass published none — hidden until the next rescan, 90s later."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    live.book = Portfolio(tmp_path / "portfolio.json")
    live.assets = {"assets": [dict(ASSET)]}
    entered, release = threading.Event(), threading.Event()
    real_lock, gated = live.lock, [True]

    class GatedLock:
        """self.lock as the engine thread meets it: the first time, it stops at
        the door — after the mark pass, before publishing."""
        def __enter__(self):
            if gated[0] and threading.current_thread().name == "marker":
                gated[0] = False
                entered.set()
                release.wait(5)
            return real_lock.__enter__()

        def __exit__(self, *exc):
            return real_lock.__exit__(*exc)

    live.lock = GatedLock()
    errors: list[Exception] = []
    marker = threading.Thread(target=lambda: live._mark_book({"assets": [dict(ASSET)]}),
                              name="marker", daemon=True)
    marker.start()
    assert entered.wait(5)
    trader = _run(lambda: live.trade("AAA", "LONG"), errors)
    time.sleep(0.1)                   # the trade gets its chance to publish first
    release.set()
    marker.join(5), trader.join(5)
    assert not errors, errors
    assert len(live.book.open) == 1
    assert len(live.positions["open"]) == 1, "the view lost a position the book holds"


def test_temp_files_a_killed_save_left_are_swept_when_old(tmp_path):
    target = tmp_path / "portfolio.json"
    target.write_text("{}")
    old = [tmp_path / "portfolio.json.111.222.tmp", tmp_path / "portfolio.tmp"]
    young = tmp_path / "portfolio.json.333.444.tmp"
    for f in (*old, young):
        f.write_text("x")
    long_ago = time.time() - paths.TEMP_FILE_MAX_AGE - 60
    for f in old:
        os.utime(f, (long_ago, long_ago))
    assert paths.read_state(target) == {}
    assert not any(f.exists() for f in old)
    assert young.exists(), "a save in flight must not be swept"
