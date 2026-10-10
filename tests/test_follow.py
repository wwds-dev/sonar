"""Two SONARs, one book: the one without the lock follows the one with it.

The window and the launchd agent share a state file, and `enginelock` lets
only one of them drive. The loser used to sit beside the winner with nothing
to show — a window with an empty book, an agent that never drove once the
window quit. Now the loser *follows*: it mirrors the holder's state over the
holder's HTTP port, forwards every action that writes the book, and takes the
lock over the moment it is free.

These tests run a real `server.PaperServer` on a loopback port as the holder
(its `Live` stubbed — the engine has its own suite) and a real `core.Live` as
the follower. The lock file names PID 1, which always exists and is never us.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time

import pytest

from sonar import core, server
from sonar import risk as risk_mod
from sonar.core import Live
from sonar.engine import Engine
from sonar.portfolio import Portfolio


class FakeAgent:
    """The surface `server.Handler` reads and writes — the engine that holds
    the lock, as the follower sees it through the API."""

    def __init__(self):
        self.lock = threading.Lock()
        self.snapshot = {"status": "live", "now": 1, "candle": {"price": 83_000.0}}
        self.assets = {"generated": 7, "n": 2,
                       "assets": [{"symbol": "AAA", "price": 101.0},
                                  {"symbol": "BBB", "price": 49.0}]}
        self.positions = {"stats": {"equity": 10_050.0, "n_open": 1},
                          "open": [{"id": "p1", "symbol": "AAA"}], "closed": [],
                          "equity": [{"t": 1, "v": 10_000.0}, {"t": 2, "v": 10_050.0}]}
        self.calibration = {"verdict": "unproven"}
        self.protocol_on = True
        self.alerts = [{"symbol": "AAA", "message": "woke up", "stale": False,
                        "data_age_s": 0}]
        self.inst = {"n": 1, "recent": [], "pressure": {"level": "Light"}}
        self.risk_name, self.hz_name = "moderate", "week"
        self.trades, self.closes, self.configured, self.reads = [], [], [], []
        self.undos = []
        self.llm = {"available": False,
                    "detail": "anthropic SDK not installed (pip install anthropic)"}

    def config(self):
        return {"risk": {"name": self.risk_name}, "horizon": {"name": self.hz_name},
                "protocol": {"on": self.protocol_on}, "llm": dict(self.llm)}

    def configure(self, risk, hz, protocol=None):
        self.configured.append((risk, hz, protocol))
        self.risk_name = risk or self.risk_name
        self.hz_name = hz or self.hz_name
        if protocol is not None:
            self.protocol_on = bool(protocol)
        return self.config()

    def read(self, kind, ident):
        self.reads.append((kind, ident))
        return {"subject": ident or "BTC", "direction": "UNCLEAR", "conviction": 0}

    def trade(self, symbol, direction):
        self.trades.append((symbol, direction))
        return {"ok": True, "message": f"opened {direction} {symbol}", "position": {}}

    def close_position(self, pos_id):
        self.closes.append(pos_id)
        return {"ok": True, "message": "closed", "position": {}}

    def undo(self, pos_id, kind):
        self.undos.append((pos_id, kind))
        return {"ok": True, "message": "cancelled", "position": {}}


@pytest.fixture
def agent(loopback, monkeypatch):
    fake = FakeAgent()
    monkeypatch.setattr(server.Handler, "live", fake)
    srv = server.PaperServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=srv.serve_forever,
                              kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    host, port = srv.server_address[:2]
    try:
        yield f"http://{host}:{port}", fake
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


@pytest.fixture
def quick(monkeypatch):
    """The follower's cadences, shrunk from seconds to the test's patience."""
    monkeypatch.setattr(core, "FOLLOW_EVERY", 0.02)
    monkeypatch.setattr(core, "FOLLOW_SLOW_EVERY", 0.0)
    monkeypatch.setattr(core, "LOCK_RETRY_EVERY", 0.1)


def _lock_held_by(data_dir, pid: int, url: str | None = None) -> None:
    rec = {"pid": pid, "role": "agent", "since": time.time()}
    if url:
        rec["url"] = url
    (data_dir / "engine.lock").write_text(json.dumps(rec))


def _dead_pid() -> int:
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def _follower(tmp_path, monkeypatch) -> Live:
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    # Driving needs the market; waiting does not. Should a test hand the lock
    # over, the engine must not go to the network from here.
    live.warmup = lambda: None
    live._poll = lambda: None
    # The follower keeps the Wire's caches warm itself; not from a test.
    live.news.headlines = lambda: []
    live.events.payload = lambda: {}
    return live


def _wait(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def following(agent, quick, tmp_path, monkeypatch):
    url, fake = agent
    _lock_held_by(tmp_path, 1, url)
    live = _follower(tmp_path, monkeypatch)
    thread = threading.Thread(target=live.run, args=("app",), daemon=True)
    thread.start()
    assert _wait(lambda: live.snapshot.get("following") == url
                 and live.positions.get("open")), "never followed the agent"
    try:
        yield live, fake, url
    finally:
        live.stop()
        thread.join(timeout=5)
        assert not thread.is_alive(), "stop() did not end the follow loop"


# --------------------------------------------------------------------------- #
# Mirroring
# --------------------------------------------------------------------------- #
def test_the_follower_shows_the_holders_state(following):
    live, fake, url = following
    assert live.read_only is True and live.following == url
    assert live.snapshot["candle"] == fake.snapshot["candle"]
    assert live.snapshot["status"] == "live"
    assert live.assets == fake.assets
    assert live.positions == fake.positions
    assert live.calibration == fake.calibration
    assert live.alerts == fake.alerts and live.inst == fake.inst
    assert live.protocol_on is True
    assert "url" in json.loads((live.engine_lock.path).read_text())


def test_the_follower_wears_the_holders_knobs(following):
    live, fake, _ = following
    fake.risk_name, fake.hz_name = "aggressive", "month"
    assert _wait(lambda: live.risk.name == "aggressive" and live.horizon.name == "month")


def test_an_unanswering_holder_is_reported_not_hidden(following, monkeypatch):
    live, _fake, url = following
    monkeypatch.setattr(Live, "_fetch", staticmethod(
        lambda u, p: (_ for _ in ()).throw(OSError("connection refused"))))
    assert _wait(lambda: live.snapshot.get("status") == "read-only")
    assert "not answering" in live.snapshot["detail"]
    assert live.snapshot["following"] == url


# --------------------------------------------------------------------------- #
# Forwarding: the holder has the pen
# --------------------------------------------------------------------------- #
def test_a_trade_is_handed_to_the_holder_not_booked_here(following):
    live, fake, _ = following
    result = live.trade("BBB", "SHORT")
    assert result["ok"] and fake.trades == [("BBB", "SHORT")]
    assert live.book.open == [], "the follower's own book must stay untouched"


def test_a_close_is_handed_to_the_holder(following):
    live, fake, _ = following
    assert live.close_position("p1")["ok"]
    assert fake.closes == ["p1"]


def test_an_undo_is_handed_to_the_holder(following):
    live, fake, _ = following
    assert live.undo("p1", "trade")["ok"]
    assert fake.undos == [("p1", "trade")]


def test_the_knobs_are_handed_to_the_holder_and_mirrored_back(following):
    live, fake, _ = following
    live.configure("aggressive", "month")
    assert fake.configured[-1] == ("aggressive", "month", None)
    assert live.risk.name == "aggressive" and live.horizon.name == "month"


def test_the_protocol_switch_is_handed_to_the_holder(following):
    live, fake, _ = following
    live.set_protocol(False)
    assert fake.configured[-1] == (None, None, False)
    assert live.protocol_on is False


def test_an_llm_read_is_run_by_the_holder(following):
    live, fake, _ = following
    read = live.read("btc", "")
    assert fake.reads == [("btc", "")]
    assert live.last_read == read and read["direction"] == "UNCLEAR"


def test_a_refused_action_reads_as_a_sentence_not_a_traceback(following, monkeypatch):
    live, _fake, _ = following
    monkeypatch.setattr(Live, "_post", staticmethod(
        lambda u, p, b: (_ for _ in ()).throw(OSError("connection refused"))))
    result = live.trade("BBB", "SHORT")
    assert result["ok"] is False and "did not take it" in result["message"]


# --------------------------------------------------------------------------- #
# Taking over
# --------------------------------------------------------------------------- #
def test_the_follower_takes_over_when_the_holder_dies(following):
    live, _fake, _ = following
    _lock_held_by(live.engine_lock.path.parent, _dead_pid())   # the agent is gone
    # Holding the lock is not yet driving: read-only lifts once the book is re-read.
    assert _wait(lambda: live.engine_lock.held and not live.read_only)
    assert live.following is None and live.read_only is False and live.conflict == ""
    assert json.loads(live.engine_lock.path.read_text())["pid"] == os.getpid()


def test_a_holder_without_an_address_is_waited_for_then_replaced(quick, tmp_path, monkeypatch):
    """A second window holds the lock: nothing to follow, so this one waits
    with a plain message — and drives the moment the lock is gone."""
    _lock_held_by(tmp_path, 1)                       # no url: a window, not a daemon
    live = _follower(tmp_path, monkeypatch)
    thread = threading.Thread(target=live.run, args=("agent",), daemon=True)
    thread.start()
    try:
        assert _wait(lambda: live.snapshot.get("status") == "read-only")
        assert "waits for it to stop" in live.snapshot["detail"]
        assert live.following is None
        (tmp_path / "engine.lock").unlink()           # the window quit
        assert _wait(lambda: live.engine_lock.held and not live.read_only)
    finally:
        live.stop()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _holder_writes(data_dir, *, bankroll, scored, cash, risk_name="moderate"):
    """What the agent leaves on disk after hours of driving, written through
    the real classes so the follower reads it exactly as it would in use."""
    eng = Engine(data_dir / "state.json", risk=risk_mod.get(risk_name))
    eng.bankroll = bankroll
    eng.n_scored_total = scored
    eng.scorelog = [{"hour": h} for h in range(scored)]
    eng.save()
    book = Portfolio(data_dir / "portfolio.json")
    book.cash = cash
    book.equity_log = [{"t": 1, "v": 10_000.0}, {"t": 2, "v": cash}]
    book.save()


def test_a_takeover_keeps_what_the_holder_wrote(following):
    """The window loaded the book at launch, followed the agent for hours, and
    took over when it stopped. Its first save used to write that launch-time
    copy over everything the agent had done since: trades, scored hours, cash."""
    live, _fake, _ = following
    data = live.engine_lock.path.parent
    assert live.engine.n_scored_total == 0 and live.book.equity_log == []
    _holder_writes(data, bankroll=9_876.5, scored=7, cash=4_321.0)
    _lock_held_by(data, _dead_pid())                            # the agent stops
    assert _wait(lambda: live.engine_lock.held and not live.read_only)
    assert live.engine.bankroll == 9_876.5 and live.engine.n_scored_total == 7
    assert live.book.cash == 4_321.0 and len(live.book.equity_log) == 2
    assert live.positions["stats"]["cash"] == 4_321.0
    live.engine.save()                       # the first settle / scored hour / mark
    live.book.save()
    state = json.loads((data / "state.json").read_text())
    book = json.loads((data / "portfolio.json").read_text())
    assert state["bankroll"] == 9_876.5 and state["n_scored_total"] == 7
    assert len(state["scorelog"]) == 7
    assert book["cash"] == 4_321.0 and len(book["equity_log"]) == 2


def test_nothing_is_written_between_taking_the_lock_and_re_reading_the_book(
        following, monkeypatch):
    """The lock is ours a moment before the book on disk has been re-read. A
    trade taken in that moment would write the launch-time book, so it refuses."""
    live, fake, _ = following
    entered, release = threading.Event(), threading.Event()
    take = Live._take_the_book

    def slow_take(self):
        entered.set()
        release.wait(5)
        take(self)

    monkeypatch.setattr(Live, "_take_the_book", slow_take)
    _lock_held_by(live.engine_lock.path.parent, _dead_pid())
    try:
        assert entered.wait(5), "never took the lock"
        result = live.trade("AAA", "LONG")
        assert result["ok"] is False and "read-only" in result["message"]
        assert fake.trades == [], "forwarded to a holder that is gone"
    finally:
        release.set()
    assert _wait(lambda: not live.read_only)


def test_a_takeover_keeps_the_protocols_day_stamp(following):
    """The follower mirrors whether protocol mode is on, never the day it last
    ran. Without the re-read, the agent's batch for today and the window's
    launch-time stamp ("") would put a second day's entries in the same day."""
    live, _fake, _ = following
    data = live.engine_lock.path.parent
    today = time.strftime("%Y-%m-%d")
    assert live._protocol_last_day == ""
    (data / "protocol.json").write_text(json.dumps({"on": True, "last_day": today}))
    _lock_held_by(data, _dead_pid())
    assert _wait(lambda: live.engine_lock.held and not live.read_only)
    assert live._protocol_last_day == today and live.protocol_on is True


def test_a_takeover_clears_the_dead_holders_mirror_from_the_screen(following):
    live, _fake, url = following
    assert live.snapshot.get("following") == url
    _lock_held_by(live.engine_lock.path.parent, _dead_pid())
    assert _wait(lambda: live.engine_lock.held and not live.read_only)
    assert live.snapshot == {"status": "starting"}, "still showing the gone holder"


def test_a_book_that_cannot_be_read_is_said_and_retried(following, monkeypatch):
    """Re-reading the book can fail (a disk error saving --risk). The engine
    used to vanish with the window stuck read-only and silent."""
    live, _fake, _ = following
    take, calls = Live._take_the_book, []

    def flaky(self):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("disk full")
        take(self)

    monkeypatch.setattr(Live, "_take_the_book", flaky)
    _lock_held_by(live.engine_lock.path.parent, _dead_pid())
    assert _wait(lambda: "could not read the book" in str(live.snapshot.get("detail")))
    assert live.read_only is True
    assert _wait(lambda: not live.read_only), "never retried"
    assert len(calls) == 2


def test_a_risk_asked_for_at_launch_is_saved_only_once_the_lock_is_ours(
        quick, tmp_path, monkeypatch):
    """`--risk` is persisted so the bankroll records what it is sized under —
    but a process waiting on the lock wrote the state file from __init__,
    over the book the holder was writing."""
    _holder_writes(tmp_path, bankroll=9_500.0, scored=3, cash=5_000.0,
                   risk_name="conservative")
    before = (tmp_path / "state.json").read_text()
    _lock_held_by(tmp_path, 1)
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live(risk_name="aggressive")
    assert (tmp_path / "state.json").read_text() == before, "wrote before holding the lock"
    assert live.risk.name == "aggressive"
    live.warmup = lambda: None
    live._poll = lambda: None
    thread = threading.Thread(target=live.run, args=("agent",), daemon=True)
    thread.start()
    try:
        assert _wait(lambda: live.snapshot.get("status") == "read-only")
        assert (tmp_path / "state.json").read_text() == before
        (tmp_path / "engine.lock").unlink()                     # the holder quit
        assert _wait(lambda: live.engine_lock.held and not live.read_only)
        state = json.loads((tmp_path / "state.json").read_text())
        assert state["risk_profile"] == "aggressive"
        assert state["bankroll"] == 9_500.0 and state["n_scored_total"] == 3
        assert live.risk.name == "aggressive" and live.engine.risk.name == "aggressive"
    finally:
        live.stop()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_a_window_with_no_holder_to_follow_does_not_write_the_book(
        quick, tmp_path, monkeypatch):
    """A second window: another engine drives and publishes nowhere this one
    can follow. Its trades, closes and knobs used to land in the shared files
    beside the holder's writes; now they refuse and say why."""
    _holder_writes(tmp_path, bankroll=9_500.0, scored=3, cash=5_000.0)
    files = {n: (tmp_path / n).read_text() for n in ("state.json", "portfolio.json")}
    _lock_held_by(tmp_path, 1)                                  # no url: a window
    live = _follower(tmp_path, monkeypatch)
    live.assets = {"assets": [{"symbol": "AAA", "price": 101.0}]}
    thread = threading.Thread(target=live.run, args=("app",), daemon=True)
    thread.start()
    try:
        assert _wait(lambda: live.snapshot.get("status") == "read-only")
        traded = live.trade("AAA", "LONG")
        assert traded["ok"] is False and "read-only" in traded["message"]
        assert traded["position"] is None
        closed = live.close_position("anything")
        assert closed["ok"] is False and "read-only" in closed["message"]
        live.configure("aggressive", None)
        assert live.risk.name == "moderate"
        live.set_protocol(True)
        assert live.protocol_on is False
        assert not (tmp_path / "protocol.json").exists()
        for name, text in files.items():
            assert (tmp_path / name).read_text() == text, f"{name} was written"
    finally:
        live.stop()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_stop_ends_the_wait(quick, tmp_path, monkeypatch):
    _lock_held_by(tmp_path, 1)
    live = _follower(tmp_path, monkeypatch)
    thread = threading.Thread(target=live.run, args=("app",), daemon=True)
    thread.start()
    assert _wait(lambda: live.snapshot.get("status") == "read-only")
    live.stop()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert not live.engine_lock.held


# --------------------------------------------------------------------------- #
# The read runs on the holder, so the holder decides whether it can run
# --------------------------------------------------------------------------- #
def test_whether_a_read_can_run_is_the_holders_answer(following, monkeypatch):
    """The launchd agent runs the checkout's venv and the window the bundle;
    they need not have the same SDK. This process being able to run a read
    says nothing about the process that will."""
    live, fake, url = following
    monkeypatch.setattr("sonar.llm.available", lambda: (True, "ready"))
    ok, why = live.llm_available()
    assert ok is False, "the follower's own SDK answered for the holder"
    assert "anthropic SDK not installed" in why
    assert url.split("//")[-1] in why, "a refusal must say where the read runs"
    assert live.config()["llm"]["available"] is False


def test_a_holder_that_can_read_lets_a_follower_without_the_sdk_ask(following, monkeypatch):
    live, fake, _ = following
    monkeypatch.setattr("sonar.llm.available",
                        lambda: (False, "anthropic SDK not installed"))
    fake.llm = {"available": True, "detail": "ready"}
    assert _wait(lambda: live.llm_available() == (True, "ready"))


def test_an_engine_that_drives_answers_for_itself(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    monkeypatch.setattr("sonar.llm.available", lambda: (False, "no key here"))
    assert live.following is None
    assert live.llm_available() == (False, "no key here")
