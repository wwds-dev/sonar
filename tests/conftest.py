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


class NetworkUsedInTest(RuntimeError):
    """Raised instead of opening a socket. Names the test that tried."""


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
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path,
                        raising=False)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "network: test genuinely needs a live network connection")
