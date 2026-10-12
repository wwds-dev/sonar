"""The holder engine works out the time-stop shadow; a follower only shows it.

`Live._shadow_pass` runs on the engine thread after each scan's mark
(docs/specs/shadow-time-stop.md, V-15). It copies the book under the book's
lock, lets go, fetches daily closes for the entries that need them — at most
once per symbol per UTC day — and assigns the pure function's result under
`self.lock` alone. Synthetic books only; conftest keeps every test out of the
real data directory and off the network, and the fetch is a stub here.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from sonar import calibration, core

DAY = 86_400.0
ROW = {"symbol": "AAA", "name": "Alpha", "price": 100.0, "volatility": 0.02,
       "confidence": 60.0, "cls": "Equity"}


def _utc(y, m, d, h=12) -> float:
    return datetime(y, m, d, h, tzinfo=timezone.utc).timestamp()


NOW = _utc(2026, 10, 12)


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    return core.Live()


def _enter(lv, symbol, age_days, protocol=True, **closed):
    pos, _ = lv.book.enter({**ROW, "symbol": symbol}, "LONG", 5, "week",
                           risk_fraction=0.0025, protocol=protocol)
    pos.opened_at = NOW - age_days * DAY
    for k, v in closed.items():
        setattr(pos, k, v)
    if closed:
        lv.book.open.remove(pos)
        lv.book.closed.append(pos)
    return pos


def _twin(lv, pos, age_days):
    """A second entry in the same symbol. The book holds one position per
    symbol at a time, but a closed one and a new one share a symbol daily."""
    twin = replace(pos, id=pos.id + "-2", opened_at=NOW - age_days * DAY)
    lv.book.open.append(twin)
    return twin


def _bars(first_ts, days=400):
    return [(first_ts + i * DAY, 100.0) for i in range(days)]


class FetchLog:
    """A stub for `assets.fetch_bars` that records each call and checks, from
    the worker thread, that neither the book's lock nor the engine's is held.
    An RLock held by the engine thread cannot be taken from another thread,
    so a fetch made inside `with book.lock:` fails the check."""

    def __init__(self, live, answer="bars"):
        self.live, self.answer, self.calls, self.locked = live, answer, [], []

    def __call__(self, symbol, rng=None):
        self.calls.append((symbol, rng))
        for name, lock in (("book", self.live.book.lock), ("engine", self.live.lock)):
            if lock.acquire(blocking=False):
                lock.release()
            else:
                self.locked.append(name)
        if self.answer == "raise":
            raise OSError("offline")
        if self.answer is None:
            return None
        return _bars(NOW - 300 * DAY)


def test_before_the_first_pass_the_readout_is_loading(live):
    """D3: "loading" until the holder's first computation — not a readout of
    an empty bar set."""
    assert live.shadow is None


def test_the_fetch_happens_outside_both_locks(live, monkeypatch):
    """V-15. Kills: a fetch under `book.lock` or `self.lock`."""
    _enter(live, "AAA", 40)
    log = FetchLog(live)
    monkeypatch.setattr(core.assets, "fetch_bars", log)
    live._shadow_pass(NOW)
    assert log.calls and log.locked == []
    assert isinstance(live.shadow, dict) and live.shadow["n_time"] == 1


def test_only_entries_past_t_without_an_earlier_barrier_are_fetched(live, monkeypatch):
    _enter(live, "OLD", 40)                                         # needs a close
    _enter(live, "HIT", 40, closed_at=NOW - 30 * DAY, outcome="TARGET",
           exit=101.0, pnl=1.0)                                     # settled before T
    _enter(live, "NEW", 10)                                         # not at T yet
    _enter(live, "MINE", 40, protocol=False)                        # a person's pick
    log = FetchLog(live)
    monkeypatch.setattr(core.assets, "fetch_bars", log)
    live._shadow_pass(NOW)
    assert [s for s, _r in log.calls] == ["OLD"]
    assert live.shadow["n_target"] == 1 and live.shadow["n_nonprotocol"] == 1


@pytest.mark.parametrize("answer", ["bars", None, "raise"])
def test_one_request_per_symbol_per_utc_day_failures_included(live, monkeypatch, answer):
    """Kills: a request per scan (every 90 s), or a failure retried at once.
    Once the closes have decided both entries, nothing more is asked for."""
    _twin(live, _enter(live, "AAA", 40), 41)
    log = FetchLog(live, answer)
    monkeypatch.setattr(core.assets, "fetch_bars", log)
    live._shadow_pass(NOW)
    live._shadow_pass(NOW + 3600)
    assert len(log.calls) == 1
    live._shadow_pass(_utc(2026, 10, 13, 0) + 60)                 # the next UTC day
    assert len(log.calls) == (1 if answer == "bars" else 2)
    if answer != "bars":
        # 12 days past T with no close: left out and counted, never guessed.
        assert live.shadow["n_no_price"] == 2 and live.shadow["n_reached"] == 0


@pytest.mark.parametrize("age,rng", [(40, "3mo"), (83, "3mo"), (85, "6mo"), (100, "6mo"), (300, "1y"), (700, "2y"),
                                     (1500, "5y"), (4000, "5y")])
def test_the_range_reaches_back_past_the_oldest_entry(live, monkeypatch, age, rng):
    _twin(live, _enter(live, "AAA", 35), age)
    log = FetchLog(live)
    monkeypatch.setattr(core.assets, "fetch_bars", log)
    live._shadow_pass(NOW)
    assert log.calls == [("AAA", rng)]


def test_a_failure_keeps_the_last_readout_and_says_why(live, monkeypatch):
    """D3 error state. Kills: dropping the readout, or showing a stale one as
    current."""
    _enter(live, "AAA", 40)
    monkeypatch.setattr(core.assets, "fetch_bars", FetchLog(live))
    live._shadow_pass(NOW)
    good = live.shadow

    def boom(*a, **k):
        raise RuntimeError("bad book")

    monkeypatch.setattr(calibration, "shadow_time_stop", boom)
    live._shadow_pass(NOW + 60)
    assert live.shadow["error"] == "RuntimeError"
    assert {k: v for k, v in live.shadow.items() if k != "error"} == \
        {k: v for k, v in good.items() if k != "error"}
    monkeypatch.undo()


def test_a_failure_before_any_readout_is_an_error_alone(live, monkeypatch):
    monkeypatch.setattr(calibration, "shadow_time_stop",
                        lambda *a: (_ for _ in ()).throw(ValueError("x")))
    live._shadow_pass(NOW)
    assert live.shadow == {"error": "ValueError"}


def test_the_pass_reads_copies_and_writes_nothing(live, monkeypatch):
    """V-11 at the engine: the book's positions are copied under its lock and
    the pure function never sees the originals."""
    pos = _enter(live, "AAA", 40)
    seen = []
    real = calibration.shadow_time_stop

    def spy(held, done, bars, now, decided=None):
        seen.extend(held + done)
        return real(held, done, bars, now, decided)

    monkeypatch.setattr(calibration, "shadow_time_stop", spy)
    monkeypatch.setattr(core.assets, "fetch_bars", FetchLog(live))
    live._shadow_pass(NOW)
    assert seen and all(p is not pos for p in seen) and seen[0] == pos
    assert pos.outcome is None and pos.closed_at is None


def test_a_follower_never_fetches_or_computes(live, monkeypatch):
    """V-15. Kills: a follower fetching bars."""
    _enter(live, "AAA", 40)
    log = FetchLog(live)
    monkeypatch.setattr(core.assets, "fetch_bars", log)
    live.following = "http://127.0.0.1:1"
    live.shadow = {"n_entered": 7}
    live._shadow_pass(NOW)
    assert log.calls == [] and live.shadow == {"n_entered": 7}


@pytest.mark.parametrize("payload,want", [
    ({"positions": {}, "calibration": {}}, core.SHADOW_UNAVAILABLE),
    ({"shadow": None}, None),
    ({"shadow": {"n_entered": 3}}, {"n_entered": 3}),
], ids=["older holder: no key", "holder still working", "holder's readout"])
def test_the_follower_mirrors_the_holders_shadow(live, payload, want, monkeypatch):
    """V-15 / D3 (e): a payload without the key is "not available", which is
    not the same as the holder still working it out."""
    monkeypatch.setattr(core.Live, "_fetch", staticmethod(lambda url, path: payload))
    live._mirror_book("http://holder")
    assert live.shadow == want


@pytest.mark.parametrize("junk", ["<b>hi</b>", 42, ["n_entered"]])
def test_a_mirrored_shadow_that_is_not_a_dict_is_ignored(live, junk, monkeypatch):
    live.shadow = {"n_entered": 1}
    monkeypatch.setattr(core.Live, "_fetch",
                        staticmethod(lambda url, path: {"shadow": junk}))
    live._mirror_book("http://holder")
    assert live.shadow == {"n_entered": 1}


def test_the_scan_works_it_out_after_marking_the_book(live, monkeypatch):
    """Placement: after `_mark_book` (and the history seed) in the scan, so
    the readout sees the closes that mark just made."""
    order = []
    monkeypatch.setattr(live.news, "headlines", lambda: [])
    monkeypatch.setattr(live.events, "payload", lambda: {})
    monkeypatch.setattr(live.institutions, "payload", lambda: None)
    monkeypatch.setattr(live.asset_scanner, "payload",
                        lambda heads, hz=None, profile=None: {"assets": [dict(ROW)]})
    monkeypatch.setattr(live, "_mark_book", lambda ap: order.append("mark"))
    monkeypatch.setattr(live, "_seed_account_history", lambda: order.append("seed"))
    monkeypatch.setattr(live, "_shadow_pass", lambda: order.append("shadow"))
    live._rescan()
    assert order == ["mark", "seed", "shadow"]


def test_taking_the_book_forgets_the_holders_shadow(live):
    live.shadow = {"n_entered": 9}
    live._take_the_book()
    assert live.shadow is None


def test_the_readout_is_served_with_the_book(live, monkeypatch):
    """/api/book carries `shadow` beside `calibration`."""
    from sonar import server
    live.shadow = {"n_entered": 2}
    got = {}

    class H:
        def __init__(self):
            self.live, self.path = live, "/api/book"

        def _refused(self, write):
            return False

        def _json(self, obj):
            got.update(obj)

    server.Handler.do_GET(H())
    assert got["shadow"] == {"n_entered": 2} and "calibration" in got


def test_the_engine_never_holds_the_engine_lock_while_computing(live, monkeypatch):
    """`self.lock` covers the assignment only: the window takes it every
    second, and a computation under it would freeze the window."""
    _enter(live, "AAA", 40)
    monkeypatch.setattr(core.assets, "fetch_bars", FetchLog(live))
    held = []
    real = calibration.shadow_time_stop

    def spy(*a):
        if live.lock.acquire(blocking=False):
            live.lock.release()
        else:
            held.append(True)
        return real(*a)

    monkeypatch.setattr(calibration, "shadow_time_stop", spy)
    t = threading.Thread(target=live._shadow_pass, args=(NOW,))
    t.start()
    t.join(5)
    assert held == [] and isinstance(live.shadow, dict)


# --------------------------------------------------------------------------- #
# Fix loop 1 (code review P1-1): a decided outcome never changes in-process
# --------------------------------------------------------------------------- #
def _wavy(first_ts, days=120, scale=1.0):
    """Closes that differ day to day, inside both barriers."""
    return [(first_ts + i * DAY, scale * (100.0 + ((i * 7) % 11 - 5) * 0.3))
            for i in range(days)]


def _cohort(lv, n=45, symbols=("AAA",)):
    """``n`` protocol entries 31-75 days old, one score each, spread over
    ``symbols``: every one past T with a final T bar."""
    model = _enter(lv, symbols[0], 75)               # one real entry; the rest are copies
    lv.book.open.remove(model)
    for i in range(n):
        pos = replace(model, id=f"{symbols[i % len(symbols)]}-{i:02d}",
                      symbol=symbols[i % len(symbols)], opened_at=NOW - (75 - i) * DAY,
                      confidence=1.5 * i)
        lv.book.open.append(pos)


class Days:
    """A fetch stub that answers by UTC day: ``plan[day](symbol)``."""

    def __init__(self, plan):
        self.plan, self.calls = plan, []

    def __call__(self, symbol, rng=None):
        self.calls.append(symbol)
        return self.plan[self.day](symbol)


def _readout_without_time(shadow):
    return {k: v for k, v in shadow.items() if k != "computed_at"}


def test_a_failed_day_after_a_good_one_changes_nothing(live, monkeypatch):
    """P1-1. A good fetch, then a failed one: the readout and look 1 are as
    they were. Kills: dropping the memo of decided outcomes, with the
    failure then taking the closes away."""
    _cohort(live)
    stub = Days({1: lambda s: _wavy(NOW - 100 * DAY), 2: lambda s: None})
    monkeypatch.setattr(core.assets, "fetch_bars", stub)
    stub.day = 1
    live._shadow_pass(NOW)
    before = live.shadow
    assert before["looks"][0]["evaluated"] is True and before["n_reached"] == 45
    stub.day = 2
    live._shadow_pass(NOW + DAY)
    assert _readout_without_time(live.shadow) == _readout_without_time(before)


def test_rewritten_closes_do_not_regrade_a_decided_entry(live, monkeypatch):
    """P1-1 / P2-1: Yahoo rescales old closes after a split. An entry
    already graded keeps its outcome; it is not asked about again. Kills:
    dropping the memo."""
    _cohort(live)
    stub = Days({1: lambda s: _wavy(NOW - 100 * DAY),
                 2: lambda s: _wavy(NOW - 100 * DAY, scale=0.5)})
    monkeypatch.setattr(core.assets, "fetch_bars", stub)
    stub.day = 1
    live._shadow_pass(NOW)
    before = live.shadow
    assert {e["state"] for e in before["entries"]} == {"time"}
    stub.day = 2
    live._shadow_pass(NOW + DAY)
    assert _readout_without_time(live.shadow) == _readout_without_time(before)
    assert stub.calls == ["AAA"]                     # decided: no second request
    # Undecided, the same rescaled series is refused, not graded.
    fresh = calibration.shadow_time_stop(live.book.open, [], {"AAA": _wavy(NOW - 100 * DAY,
                                                                           scale=0.5)}, NOW)
    assert fresh["n_reached"] == 0 and fresh["n_no_price"] + fresh["n_wait_price"] == 45


def test_one_symbol_failing_leaves_an_evaluated_look_alone(live, monkeypatch):
    """P1-1, reproduced by the reviewer: two symbols, one failing for a day,
    used to re-evaluate look 1 on a different subset (used 45 → 22)."""
    _cohort(live, symbols=("AAA", "BBB"))
    stub = Days({1: lambda s: _wavy(NOW - 100 * DAY),
                 2: lambda s: None if s == "BBB" else _wavy(NOW - 100 * DAY)})
    monkeypatch.setattr(core.assets, "fetch_bars", stub)
    stub.day = 1
    live._shadow_pass(NOW)
    look = live.shadow["looks"][0]
    assert look["evaluated"] is True and look["used"] == 45
    stub.day = 2
    live._shadow_pass(NOW + DAY)
    assert live.shadow["looks"][0] == look


def test_a_failed_request_keeps_the_series_already_held(live, monkeypatch):
    """P1-1, the cache itself. Kills: a failure overwriting yesterday's
    good closes with nothing."""
    pos = _enter(live, "AAA", 40)
    good = _wavy(NOW - 100 * DAY)
    stub = Days({1: lambda s: good, 2: lambda s: None})
    monkeypatch.setattr(core.assets, "fetch_bars", stub)
    stub.day = 1
    assert live._shadow_fetch([pos], NOW) == {"AAA": good}
    stub.day = 2
    assert live._shadow_fetch([pos], NOW + DAY) == {"AAA": good}
    assert len(stub.calls) == 2                     # still one request a day


def test_the_memo_lives_in_memory_and_keeps_the_first_decision(live, monkeypatch):
    _cohort(live, n=3)
    monkeypatch.setattr(core.assets, "fetch_bars", lambda s, rng=None: _wavy(NOW - 100 * DAY))
    live._shadow_pass(NOW)
    assert set(live._shadow_decided) == {e["id"] for e in live.shadow["entries"]}
    first = {k: dict(v) for k, v in live._shadow_decided.items()}
    live._shadow_pass(NOW + DAY)
    assert live._shadow_decided == first
    assert not any(p.name.startswith("shadow") for p in live.book.path.parent.iterdir())


def test_qa_c03_a_waiting_window_never_computes(live, monkeypatch):
    """QA C03: read-only with no holder to follow (a second window, or the
    moment before the book is re-read), a settings change's rescan must not
    compute or fetch. Kills: dropping the read_only guard."""
    _enter(live, "AAA", 40)
    log = FetchLog(live)
    monkeypatch.setattr(core.assets, "fetch_bars", log)
    live.read_only, live.following = True, None
    live._shadow_pass(NOW)
    assert log.calls == [] and live.shadow is None


@pytest.mark.parametrize("failing", ["all", "every third"])
def test_mv_s1a_failed_fetches_leave_look_1_as_evaluated(live, monkeypatch, failing):
    """Model-validator P1-1, s1 part A: 45 entries on 45 symbols, some closed
    at a barrier before T and the rest graded at T. When today's fetches all
    fail, or one symbol in three does, look 1 keeps its 45 members and its z
    (it used to drop to the 22 quick resolvers, z −0.36 → −0.98)."""
    _cohort(live, symbols=tuple(f"S{i}" for i in range(45)))
    for i, pos in enumerate(list(live.book.open)):
        if i % 2:                                  # half settled by the book before T
            live.book.open.remove(pos)
            live.book.closed.append(replace(pos, closed_at=pos.opened_at + 3 * DAY,
                                            outcome="TARGET" if i % 4 == 1 else "STOP",
                                            exit=pos.target, pnl=1.0))
    fails = (lambda s: True) if failing == "all" else (lambda s: int(s[1:]) % 3 == 0)
    stub = Days({1: lambda s: _wavy(NOW - 100 * DAY),
                 2: lambda s: None if fails(s) else _wavy(NOW - 100 * DAY)})
    monkeypatch.setattr(core.assets, "fetch_bars", stub)
    stub.day = 1
    live._shadow_pass(NOW)
    look = live.shadow["looks"][0]
    assert look["evaluated"] is True and look["used"] == 45 and look["n_excluded"] == 0
    stub.day = 2
    live._shadow_pass(NOW + DAY)
    assert live.shadow["looks"][0] == look
