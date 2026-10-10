"""Follow mode across two real processes.

`test_follow.py` runs the holder as a thread of the test's own interpreter,
which is the right place for the protocol — but the engine lock is per *pid*,
and the thing it exists to arbitrate is the launchd agent and the window: two
interpreters, two venvs, one directory. These tests start a real daemon with
`server.main` in a child process on a spare loopback port, against the test's
own data directory, and put an in-process `Live` beside it.

The child never reaches the internet: before `server.main` runs it replaces
the poll body and warm-up with no-ops and makes `urlopen` refuse, exactly as
the suite's own guards do. It still takes the lock, writes its address into
it, serves the API and hands the lock over — which is all these tests ask of
it.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from sonar import core
from sonar.core import Live

ROOT = Path(__file__).resolve().parent.parent

CHILD = textwrap.dedent("""
    import sys, urllib.request
    sys.path.insert(0, sys.argv[3])
    from sonar import core, server

    def refuse(*a, **k):
        raise OSError("the test's agent does not go to the network")

    urllib.request.urlopen = refuse

    def warmup(self):
        # One row on the board, so a forwarded trade has something to book.
        with self.lock:
            self.assets = {"status": "live", "generated": 1, "assets": [
                {"symbol": "AAA", "name": "Alpha", "price": 100.0,
                 "volatility": 0.02, "confidence": 55.0, "cls": "Equity"}]}

    core.Live.warmup = warmup
    core.Live._poll = lambda self: None
    core.LOCK_RETRY_EVERY = 0.1
    core.FOLLOW_EVERY = 0.05
    core.FOLLOW_SLOW_EVERY = 0.0
    server.main("127.0.0.1", int(sys.argv[1]), role="agent")
""")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(cond, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


def _lock(data: Path) -> dict:
    try:
        return json.loads((data / "engine.lock").read_text())
    except (OSError, ValueError):
        return {}


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(core, "FOLLOW_EVERY", 0.05)
    monkeypatch.setattr(core, "FOLLOW_SLOW_EVERY", 0.0)
    monkeypatch.setattr(core, "LOCK_RETRY_EVERY", 0.1)


@pytest.fixture
def start_agent(tmp_path):
    """Start the daemon as its own process on this test's data directory."""
    children: list[subprocess.Popen] = []

    def start() -> tuple[subprocess.Popen, str]:
        port = _free_port()
        env = {**os.environ, "SONAR_DATA": str(tmp_path)}
        env.pop("QT_QPA_PLATFORM", None)
        child = subprocess.Popen(
            [sys.executable, "-c", CHILD, str(port), str(tmp_path), str(ROOT)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        children.append(child)
        return child, f"http://127.0.0.1:{port}"

    yield start
    for child in children:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)


def _window(tmp_path, monkeypatch) -> Live:
    """The in-process engine: the window's half, without the window."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    live.warmup = lambda: None
    live._poll = lambda: None
    live.news.headlines = lambda: []
    live.events.payload = lambda: {}
    return live


def _run(live: Live) -> threading.Thread:
    thread = threading.Thread(target=live.run, args=("app",), daemon=True)
    thread.start()
    return thread


def _stop(live: Live, thread: threading.Thread) -> None:
    live.stop()
    thread.join(timeout=5)
    assert not thread.is_alive(), "stop() did not end the engine's loop"


def test_a_window_follows_an_agent_in_another_process(
        loopback, quick, start_agent, tmp_path, monkeypatch):
    agent, url = start_agent()
    assert _wait(lambda: _lock(tmp_path).get("pid") == agent.pid), "agent never took the lock"
    assert _lock(tmp_path).get("url") == url

    live = _window(tmp_path, monkeypatch)
    thread = _run(live)
    try:
        assert _wait(lambda: live.following == url), "the window never followed"
        assert live.read_only is True
        assert _lock(tmp_path)["pid"] == agent.pid, "the follower took a held lock"
        # A trade goes to the agent and is booked there: the window's own
        # book stays empty, and the window shows the agent's.
        assert _wait(lambda: any(a.get("symbol") == "AAA"
                                 for a in live.assets.get("assets", [])))
        reply = live.trade("AAA", "LONG")
        assert reply["ok"] is True, reply["message"]
        assert live.book.open == [], "booked by the follower, not the holder"
        assert [p["symbol"] for p in live.positions.get("open", [])] == ["AAA"]
        # And refused twice, by the agent's book, in its words.
        again = live.trade("AAA", "LONG")
        assert again["ok"] is False and "already holding" in again["message"]
    finally:
        _stop(live, thread)


@pytest.mark.parametrize("how", [signal.SIGTERM, signal.SIGKILL],
                         ids=["agent stopped", "agent killed"])
def test_the_window_drives_once_the_agent_process_is_gone(
        loopback, quick, start_agent, tmp_path, monkeypatch, how):
    """`launchctl bootout` sends SIGTERM; a crash leaves a lock behind with a
    dead pid in it. Either way the window takes the book over, without a
    restart, and the lock then names the window."""
    agent, url = start_agent()
    assert _wait(lambda: _lock(tmp_path).get("pid") == agent.pid)
    live = _window(tmp_path, monkeypatch)
    thread = _run(live)
    try:
        assert _wait(lambda: live.following == url)
        agent.send_signal(how)
        agent.wait(timeout=10)
        assert _wait(lambda: live.engine_lock.held), "the window never took over"
        assert _lock(tmp_path)["pid"] == os.getpid()
        assert live.following is None and live.read_only is False
    finally:
        _stop(live, thread)


def test_an_agent_started_beside_a_window_waits_then_drives(
        loopback, quick, start_agent, tmp_path, monkeypatch):
    """`install_agent.sh` with the window open: the window publishes no
    address, so the agent cannot follow it — it waits, and drives the night
    the moment the window quits."""
    live = _window(tmp_path, monkeypatch)
    thread = _run(live)
    try:
        assert _wait(lambda: live.engine_lock is not None and live.engine_lock.held)
        agent, url = start_agent()
        time.sleep(1.0)                              # several of its retries
        assert agent.poll() is None, agent.stdout.read() if agent.stdout else ""
        assert _lock(tmp_path)["pid"] == os.getpid(), "the agent took a held lock"
    finally:
        _stop(live, thread)                          # the window quits
    live.engine_lock.release()
    assert _wait(lambda: _lock(tmp_path).get("pid") == agent.pid), \
        "the agent never took over from the window"
    assert _lock(tmp_path).get("url") == url, "the agent must publish its address"
