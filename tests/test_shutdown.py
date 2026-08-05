"""Tests for clean shutdown.

The failure these prevent is loud and confusing: Qt calls ``qFatal()`` when a
QThread is destroyed while still running, and qFatal *aborts*. The process dies
with SIGABRT and macOS pops "Python quit unexpectedly" — so quitting SONAR
looked like a crash, and the launch log recorded only::

    QThread: Destroyed while thread '' is still running

The poll thread is parented to the main window, so interpreter shutdown destroys
it. That is only safe if the loop it runs can actually be asked to finish, which
is what these tests pin down.
"""

import threading
import time

from sonar.core import Live


def test_stop_ends_the_run_loop(tmp_path, monkeypatch):
    """run() must return after stop() — the property the window relies on."""
    monkeypatch.setattr("sonar.paths.state_file", lambda: tmp_path / "state.json")
    live = Live()
    monkeypatch.setattr(live, "warmup", lambda: None)
    monkeypatch.setattr(live, "_poll", lambda: None)

    thread = threading.Thread(target=live.run, args=("test",), daemon=True)
    thread.start()
    time.sleep(0.2)                      # let it get into the loop
    assert thread.is_alive()

    live.stop()
    thread.join(timeout=5)
    assert not thread.is_alive(), "run() ignored stop() — teardown would abort"


def test_stop_does_not_wait_out_the_poll_interval(tmp_path, monkeypatch):
    """Shutdown must be prompt.

    The loop sleeps between polls. If it used time.sleep() a quit would block
    for the rest of that interval; an Event.wait() returns the moment it is set.
    """
    monkeypatch.setattr("sonar.paths.state_file", lambda: tmp_path / "state.json")
    monkeypatch.setattr("sonar.core.PRICE_EVERY", 30.0)
    live = Live()
    monkeypatch.setattr(live, "warmup", lambda: None)
    monkeypatch.setattr(live, "_poll", lambda: None)

    thread = threading.Thread(target=live.run, args=("test",), daemon=True)
    thread.start()
    time.sleep(0.2)

    started = time.monotonic()
    live.stop()
    thread.join(timeout=10)
    elapsed = time.monotonic() - started

    assert not thread.is_alive()
    assert elapsed < 5, f"stop() took {elapsed:.1f}s against a 30s interval"


def test_run_releases_the_engine_lock(tmp_path, monkeypatch):
    """A clean exit hands the lock back.

    SIGABRT never could, which left a stale holder on disk and sent the *next*
    launch into read-only mode for no reason a user could see.
    """
    monkeypatch.setattr("sonar.paths.state_file", lambda: tmp_path / "state.json")
    live = Live()
    monkeypatch.setattr(live, "warmup", lambda: None)
    monkeypatch.setattr(live, "_poll", lambda: None)

    thread = threading.Thread(target=live.run, args=("test",), daemon=True)
    thread.start()
    time.sleep(0.2)
    live.stop()
    thread.join(timeout=5)

    assert live.engine_lock is not None
    assert live.engine_lock.holder() is None, "lock still held after a clean exit"


def test_stop_before_run_is_harmless():
    """stop() may arrive before the thread ever started — quitting during
    startup must not raise."""
    live = Live()
    live.stop()          # must not raise
