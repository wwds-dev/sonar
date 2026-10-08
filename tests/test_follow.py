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
from sonar.core import Live


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

    def config(self):
        return {"risk": {"name": self.risk_name}, "horizon": {"name": self.hz_name},
                "protocol": {"on": self.protocol_on}}

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
    assert _wait(lambda: live.engine_lock.held)
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
        assert _wait(lambda: live.engine_lock.held)
        assert live.read_only is False
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
