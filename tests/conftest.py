"""Session-wide guards: no test may reach the network or the real data directory.

Three tests — `test_layout`, `test_lab_tab`, `test_refresh` — build a real
`MainWindow`, and `MainWindow.__init__` starts its poll thread immediately.
Calling `win.poll.live.stop()` afterwards, which is what they all did, stops the
*next* fetch; the first one is already in flight. When that fetch stalls the
thread never finishes and teardown waits on it forever.

That is not hypothetical. It is what left a pytest process blocked for five
hours and fifty minutes at 0.9% CPU — a socket in CLOSE_WAIT to a CDN and every
worker parked on a lock. It passes whenever the network happens to answer, which
is why it went unnoticed.

So the network is closed off here rather than in each test, before any window is
built. A test that wants a fetch to succeed has to say so by patching the layer
it is exercising, which is what the provider tests already do.
"""

import socket
import urllib.request

import pytest


#: Captured before anything patches them, so a test that genuinely needs a
#: socket can ask for one back. See the `loopback` fixture.
_REAL_CONNECT = socket.socket.connect
_REAL_CONNECT_EX = socket.socket.connect_ex
_REAL_URLOPEN = urllib.request.urlopen


@pytest.fixture
def loopback(monkeypatch):
    """Restore real sockets, for talking to a server this test started itself.

    The blanket ban exists to stop tests reaching the *internet* — someone
    else's uptime, someone else's rate limit, and a hang with no timeout. A
    server bound to 127.0.0.1 by the test that is about to query it is none of
    those things, and faking the handler plumbing to avoid it would test the
    fake rather than the server.

    Narrow on purpose: ask for it by name, and only where it is warranted.
    """
    monkeypatch.setattr(socket.socket, "connect", _REAL_CONNECT)
    monkeypatch.setattr(socket.socket, "connect_ex", _REAL_CONNECT_EX)
    monkeypatch.setattr(urllib.request, "urlopen", _REAL_URLOPEN)


class NetworkUsedInTest(OSError):
    """Raised instead of opening a socket. Names the test that tried.

    An OSError on purpose. Every fetch path in SONAR already treats a failed
    connection as an expected state — being offline is supported — so raising
    into that handling leaves the engine in a state it knows, rather than
    throwing an unfamiliar exception through a loop that was not written for it.
    """


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    """Fail fast instead of hanging when a test reaches for the network."""
    def blocked(*args, **kwargs):
        raise NetworkUsedInTest(
            f"{request.node.nodeid} tried to open a network connection. "
            "Patch the provider you are exercising, or mark the test "
            "`@pytest.mark.network` if it genuinely needs one.")

    if "network" in request.keywords:
        return
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    """Keep every test out of ~/Library/Application Support/SONAR.

    Only `test_refresh` and `test_enginelock` did this for themselves, so the
    other window tests were writing to — and taking the engine lock in — the
    real application directory while the user's own app might be running.
    """
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)


@pytest.fixture(autouse=True)
def idle_engine(monkeypatch):
    """Stop the window tests from ever starting a real poll.

    `MainWindow.__init__` starts `PollThread` immediately, and `PollThread.run()`
    calls `Live.run()`, which holds the engine lock and loops until `stop()`.
    The three window tests each build a window and *then* call
    `win.poll.live.stop()` — by which point the thread is already inside
    `acquire()` or `warmup()`.

    If it has not finished by teardown, `MainWindow.shutdown()` waits four
    seconds and then calls `QThread.terminate()`. Terminating a thread running
    Python leaves whatever it held — the GIL, or a plain pthread mutex — locked
    forever, and the main thread then blocks in `take_gil` or in
    `PyThread_release_lock`. Both stacks have been sampled out of hung runs
    here. Whether a given run hangs depends only on timing, which is why the
    suite could pass and then wedge on the next invocation.

    So the poll body never runs in tests. `Live.run()` and `stop()` are left
    real — `test_shutdown` pins down that the loop honours stop, patching its
    own instance — but the thread the *window* owns does nothing and finishes
    at once.
    """
    monkeypatch.setattr("ui.worker.PollThread.run", lambda self: None, raising=False)
    monkeypatch.setattr("sonar.core.Live.warmup", lambda self: None)
    monkeypatch.setattr("sonar.core.Live._poll", lambda self: None)


@pytest.fixture(autouse=True)
def no_thread_termination(monkeypatch):
    """Turn a deadlock into a test failure.

    `QThread.terminate()` is `shutdown()`'s last resort and is unsafe for a
    thread running Python. Reaching it in a test used to mean an eternal hang;
    now it means a named failure, so the next thread left running at teardown
    is found in seconds rather than hours.
    """
    try:
        from PySide6.QtCore import QThread
    except ImportError:
        return

    def refuse(self):
        raise AssertionError(
            f"{type(self).__name__} was still running at teardown and "
            "shutdown() fell through to terminate(). Stop the thread "
            "cooperatively instead — terminate() deadlocks the interpreter.")

    monkeypatch.setattr(QThread, "terminate", refuse)


#: The `network` marker is declared in pyproject.toml, which also deselects it
#: by default. Opt in with `pytest -m network`.


#: The hang guard is `faulthandler_timeout` in pyproject.toml, not here. Setting
#: it from `pytest_configure` with `faulthandler.dump_traceback_later()` looks
#: equivalent and is not: pytest's own faulthandler plugin cancels any pending
#: dump around each test and in `pytest_exception_interact`, so a session-wide
#: timer set that way is disarmed the first time anything raises. It fired
#: correctly on a one-test reproduction and then failed to fire on the full
#: suite, which is exactly the shape of bug a guard must not have.
