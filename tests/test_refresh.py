"""The UI refresh loop must survive contact with a real Live object.

This exists because of a bug that shipped: removing the Polymarket board
deleted ``Live.scan``, but ``MainWindow.refresh()`` still read it. Every timer
tick then raised AttributeError on its first line — before a single label was
written — so the whole window sat on "starting…" with every field showing "—".

Nothing caught it. The unit tests never build a window, and ``--selftest``
checks packaging rather than rendering. The app looked fine in source, passed
271 tests, built cleanly, and was broken the moment it was launched.

So: build the real window against a real Live and call the real refresh, for
each status it can encounter. Any attribute the UI reads and the engine no
longer publishes fails here instead of on someone's desktop.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from sonar.core import Live
from ui.app import MainWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    win = MainWindow(Live())
    win.poll.live.stop()             # no network from a unit test
    win.poll.quit(); win.poll.wait(2000)
    yield win
    win.shutdown()


def test_refresh_before_the_first_poll(window):
    """The state the app is in for its first second: snapshot says 'starting'."""
    window.refresh()


def test_refresh_when_read_only(window):
    """Another SONAR holds the engine lock."""
    window.live.snapshot = {"status": "read-only", "detail": "another engine"}
    window.refresh()


def test_refresh_when_the_engine_errors(window):
    window.live.snapshot = {"status": "error", "detail": "boom"}
    window.refresh()


def test_refresh_with_a_live_snapshot(window):
    """The path that renders everything — and the one that was broken.

    A minimal but complete snapshot: whatever refresh() reaches for here has to
    be something Live actually publishes.
    """
    window.live.snapshot = {
        "status": "live",
        "candle": {"price": 60000.0, "change_pct": 0.5, "is_up": True},
        "signal": {"model_up": 0.55, "market_up": 0.52, "edge": 0.03,
                   "side": "UP", "tau": 0.4},
        "lattice": {},
        "market": {"bids": [], "asks": []},
        "portfolio": {"stats": {}},
    }
    window.refresh()
    assert "paper money only" in window.status.text(), \
        "refresh() bailed out before writing the status line"


def test_repeated_refresh_is_stable(window):
    """The timer calls this several times a second for the life of the app."""
    window.live.snapshot = {"status": "live", "candle": None, "signal": None,
                            "lattice": {}, "market": {}, "portfolio": {}}
    for _ in range(5):
        window.refresh()
