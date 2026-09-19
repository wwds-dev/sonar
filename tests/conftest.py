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


@pytest.fixture(scope="session", autouse=True)
def session_guards(tmp_path_factory):
    """Install the guards before *any* fixture a test can ask for.

    The rest of this file patched the network, the data directory and the poll
    body from `autouse=True` function-scoped fixtures, and that is too late.
    pytest instantiates fixtures highest-scope-first, so a **module**-scoped
    `window` fixture — which is what `test_lab_tab`, `test_layout` and
    `test_refresh` all use — is built *before* any function-scoped autouse
    fixture runs.

    So for the three tests this file was written to protect, none of it was in
    force at the moment it mattered. `MainWindow.__init__` started the poll
    thread into the real `Live.run()`, which took the engine lock in the user's
    own `~/Library/Application Support/SONAR` and went to the network — while
    the user's app might be running against the same state file. The loop then
    never finished, so the window fixture's `shutdown()` found it still running
    at teardown: the straggler that used to reach `QThread.terminate()`, which
    is the wedge described above. It was masked because terminate either hung
    (blamed on the network) or, later, left by `os._exit` with **exit code 0**.

    This fixture is the same set of patches at session scope, so they are up
    before the first module fixture is built. The function-scoped versions below
    stay: they give each test its own `tmp_path` and name the test in the
    network error, which a session-wide patch cannot do.
    """
    mp = pytest.MonkeyPatch()
    mp.setattr("sonar.paths.user_data_base",
               lambda: tmp_path_factory.mktemp("sonar-session"))
    mp.setattr("ui.worker.PollThread.run", lambda self: None, raising=False)
    mp.setattr("sonar.core.Live.warmup", lambda self: None)
    mp.setattr("sonar.core.Live._poll", lambda self: None)

    def blocked(*args, **kwargs):
        raise NetworkUsedInTest(
            "a fixture opened a network connection before any test ran "
            "(likely a module- or session-scoped fixture). Patch the provider "
            "it uses, or build it inside a test that is marked `network`.")

    mp.setattr(urllib.request, "urlopen", blocked)
    mp.setattr(socket.socket, "connect", blocked)
    mp.setattr(socket.socket, "connect_ex", blocked)
    yield
    mp.undo()


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
        # session_guards blocked these before this test was reached, so opting
        # in means putting the real ones back, not merely declining to patch.
        monkeypatch.setattr(socket.socket, "connect", _REAL_CONNECT)
        monkeypatch.setattr(socket.socket, "connect_ex", _REAL_CONNECT_EX)
        monkeypatch.setattr(urllib.request, "urlopen", _REAL_URLOPEN)
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

    If it has not finished by teardown, `MainWindow.shutdown()` gives up on it
    and ends the process. That used to be `QThread.terminate()`, which on a
    thread running Python leaves whatever it held — the GIL, or a plain pthread
    mutex — locked forever, with the main thread blocked in `take_gil` or
    `PyThread_release_lock`; both stacks were sampled out of hung runs here, and
    the same call shipped in the app, where it showed as a window that stopped
    repainting. It is now an `os._exit`, which is right for the app and fatal
    for a test run, so `no_hard_exit` below intercepts it.

    So the poll body never runs in tests. `Live.run()` and `stop()` are left
    real — `test_shutdown` pins down that the loop honours stop, patching its
    own instance — but the thread the *window* owns does nothing and finishes
    at once.
    """
    monkeypatch.setattr("ui.worker.PollThread.run", lambda self: None, raising=False)
    monkeypatch.setattr("sonar.core.Live.warmup", lambda self: None)
    monkeypatch.setattr("sonar.core.Live._poll", lambda self: None)


@pytest.fixture(scope="session", autouse=True)
def no_hard_exit():
    """Keep `shutdown()`'s last resort from taking the test runner with it.

    Leaving by `os._exit` is the correct end for the app and a silent disaster
    for pytest: the run stops with no summary and **exit code 0**, which every
    CI in the world reads as a pass. That is what happened on the first run
    after the fix landed — thirteen tests ran, one failed, and the process
    vanished before it could say so.

    Session-scoped because the thing that reaches it is a *teardown*. The window
    fixtures are module-scoped and call `shutdown()` when they expire, which is
    after any function-scoped patch has been undone — so a function-scoped guard
    is unpatched at exactly the moment it is needed. The earlier
    `QThread.terminate()` had the same hole, and that is the missing half of the
    teardown hang this file already describes: neutralising the poll body kept
    the *tests* off the network, but the fixture's own teardown still fell
    through to terminate with a thread running, which is a wedge on a good day
    and a silent exit 0 on this one.
    """
    import pytest as _pytest
    mp = _pytest.MonkeyPatch()

    def refuse(self, stragglers):
        raise AssertionError(
            f"shutdown() gave up on {', '.join(stragglers)} and would have "
            "ended the process. Stop the thread cooperatively in the test "
            "instead — the app cannot afford to wait for a socket, so this "
            "path is real, and it must stay unreachable from tests.")

    mp.setattr("ui.app.MainWindow._exit_now", refuse, raising=False)
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def no_thread_termination(monkeypatch):
    """Keep `QThread.terminate()` from coming back.

    It was `shutdown()`'s last resort until it was found to be the cause of the
    blank-window reports, and it is unsafe for any thread running Python. This
    fixture is now a regression guard rather than a hang-catcher: nothing in the
    app calls it, and anything that starts to, fails here by name.
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
