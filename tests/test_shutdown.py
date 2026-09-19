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

import os
import pathlib
import threading
import time
from types import SimpleNamespace

import pytest

from sonar.core import Live


def test_stop_ends_the_run_loop(tmp_path, monkeypatch):
    """run() must return after stop() — the property the window relies on."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
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
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
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
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
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


def test_stop_before_run_is_harmless(tmp_path, monkeypatch):
    """stop() may arrive before the thread ever started — quitting during
    startup must not raise."""
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    live.stop()          # must not raise

@pytest.fixture
def bare_window():
    """`shutdown()` bound to a plain object, with no QApplication behind it.

    The logic under test is the wait loop and what it does with a thread that
    will not stop — none of which needs a window. Building a real MainWindow
    here would start a real poll thread, which is the thing these tests are
    about.
    """
    from ui.app import MainWindow

    class Bare:
        SHUTDOWN_GRACE_MS = MainWindow.SHUTDOWN_GRACE_MS
        shutdown = MainWindow.shutdown
        _owned_threads = MainWindow._owned_threads

        def __init__(self):
            self.timer = None
            self.live = SimpleNamespace(stop=lambda: None)
            self.poll = None
            self._read_thread = self._cfg_thread = None
            self._bt_thread = self._lab_thread = None
            self.playmaker_thread = None

    return Bare()



# --- the blank white window ------------------------------------------------ #
#
# Reported four times, misdiagnosed three: "SONAR doesn't quit", with a
# screenshot of an empty white rectangle. The close button was never the bug.
# The app is themed near-black (#080b11), so a *white* window is one Qt never
# painted — a dead event loop, not a refused close.
#
# It died in shutdown(). The last resort for a thread that would not stop was
# QThread.terminate(), which kills the thread wherever it stands; if it is
# running Python it holds the GIL, and terminate never gives it back. Every
# Python thread then blocks in take_gil forever, the event loop included, so
# nothing repaints and macOS shows the window's empty backing store.
#
# It was not a rare race. live.stop() only lands between fetches, so any quit
# during an in-flight request had to outlast a socket timeout of 8-30s inside a
# grace of 1.5s, and then terminated a thread that was by construction mid-read.

def test_nothing_in_the_ui_calls_qthread_terminate():
    """The one call that must not come back.

    Checked against the file with `ast`, for two reasons. Prose: this module and
    `ui/app.py` both discuss `QThread.terminate()` at length, so a substring
    search over the source would never pass. And patching: the first version of
    this test read `inspect.getsource(MainWindow._exit_now)`, which under the
    suite returns *conftest's* stub — `no_hard_exit` has replaced the attribute
    by then — so it read a function that could not contain the call and passed
    no matter what the app did. It survived a deliberate mutation that put
    terminate back, which is the only reason it was caught.

    An AST walk looks for the call itself, which neither problem touches.
    """
    import ast

    src = pathlib.Path(__file__).resolve().parents[1] / "ui" / "app.py"
    tree = ast.parse(src.read_text())
    offenders = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "terminate"
    ]
    assert not offenders, (
        f"ui/app.py calls .terminate() at line(s) {offenders}. On a thread "
        "running Python that deadlocks the interpreter and freezes the window "
        "— end the process with os._exit instead.")


def test_a_thread_that_will_not_stop_ends_the_process(bare_window):
    """A straggler must route to the hard exit, naming what it gave up on."""
    from ui.app import MainWindow

    class Stuck:
        def isRunning(self): return True
        def quit(self): pass
        def wait(self, ms): return False        # never finishes, like a socket

    win = bare_window
    win.poll = Stuck()
    calls = []
    win._exit_now = lambda stragglers: calls.append(list(stragglers))

    win.shutdown()

    assert calls == [["poll"]], (
        "shutdown() let a wedged thread through without ending the process; "
        "Qt aborts when it is destroyed still running")


def test_the_grace_is_a_budget_for_all_threads_not_each(bare_window):
    """Six threads x 4s each held the UI thread for 24s with nothing painting.

    That is the same white window as the deadlock, just self-healing, so the
    wait has to be bounded across the set rather than per thread.
    """
    from ui.app import MainWindow

    class Slow:
        def __init__(self): self.waited = []
        def isRunning(self): return True
        def quit(self): pass
        def wait(self, ms):
            self.waited.append(ms)
            time.sleep(ms / 1000.0)
            return False

    win = bare_window
    threads = [Slow() for _ in range(3)]
    win.poll, win._read_thread, win._cfg_thread = threads
    win._bt_thread = win._lab_thread = None
    win.playmaker_thread = None
    win._exit_now = lambda stragglers: None

    started = time.monotonic()
    win.shutdown()
    elapsed = time.monotonic() - started

    budget = MainWindow.SHUTDOWN_GRACE_MS / 1000.0
    assert elapsed < budget * 2, (
        f"shutdown took {elapsed:.2f}s against a {budget:.2f}s budget — the "
        "wait is per-thread again, and the window paints nothing throughout")
    assert sum(t.waited[0] for t in threads) <= MainWindow.SHUTDOWN_GRACE_MS + 50


CHILD = '''
import os, sys, time
from types import SimpleNamespace
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication
from ui.app import MainWindow

class Busy(QThread):
    """A poll thread mid-fetch: running Python, holding the GIL, ignoring stop."""
    def run(self):
        end = time.monotonic() + 120
        while time.monotonic() < end:
            sum(i * i for i in range(10000))

app = QApplication([])

class Bare:
    SHUTDOWN_GRACE_MS = MainWindow.SHUTDOWN_GRACE_MS
    shutdown = MainWindow.shutdown
    _owned_threads = MainWindow._owned_threads
    _exit_now = MainWindow._exit_now            # the real one: os._exit

win = Bare()
win.timer = None
win.live = SimpleNamespace(stop=lambda: None, engine_lock=None)
win.poll = Busy()
win._read_thread = win._cfg_thread = None
win._bt_thread = win._lab_thread = win.playmaker_thread = None
win.poll.start()
time.sleep(0.3)

win.shutdown()

# Only reached if shutdown() declined to exit. Either way the point is that the
# interpreter still works here -- under terminate() it never got this far.
sys.stdout.write("RETURNED\\n")
sys.stdout.flush()
os._exit(0)
'''


def test_quitting_during_a_fetch_does_not_freeze_the_process(tmp_path):
    """The regression test for the blank white window, end to end.

    A real subprocess, a real QThread running real Python, and the real
    `shutdown()`. Against the old `QThread.terminate()` this does not fail --
    it *hangs*, permanently, which is precisely what the user saw and why a
    timeout rather than an assertion is the thing being checked.
    """
    import subprocess
    import sys as _sys

    script = tmp_path / "quit_during_fetch.py"
    script.write_text(CHILD)

    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               PYTHONPATH=str(pathlib.Path(__file__).resolve().parents[1]))
    started = time.monotonic()
    try:
        done = subprocess.run([_sys.executable, str(script)], env=env,
                              capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        raise AssertionError(
            "shutdown() never returned: the process is wedged with a thread "
            "that would not stop. This is the blank white window — the event "
            "loop is blocked, so the window never repaints and the close "
            "button does nothing.")
    elapsed = time.monotonic() - started

    assert done.returncode == 0, f"exited {done.returncode}: {done.stderr[-800:]}"
    assert elapsed < 20, (
        f"quitting took {elapsed:.1f}s with one thread stuck; the user sees an "
        "unresponsive window for all of it")
    assert "still in flight" in done.stderr, (
        "the hard exit should say what it gave up on, so the next report of "
        f"this has something to go on. stderr was: {done.stderr!r}")
