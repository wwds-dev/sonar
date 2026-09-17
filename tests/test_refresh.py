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


def test_the_wire_never_fetches_from_the_ui_thread(window, monkeypatch):
    """The blank-window bug, pinned down.

    With both caches aged out, rendering the Wire must still not go near the
    network. If it does, the event loop stops for up to half a minute and the
    window turns into a white rectangle that ignores the close button — which
    is what a user saw and reported.
    """
    from sonar.events import EventsCache
    from sonar.news import NewsCache

    attempts = []
    monkeypatch.setattr(NewsCache, "_refresh", lambda self: attempts.append("news"))
    monkeypatch.setattr(EventsCache, "refresh",
                        lambda self, *a, **k: attempts.append("events"))
    window.live.news._at = 0.0
    window.live.events._at = 0.0

    window._refresh_wire()

    assert attempts == [], f"the UI thread tried to fetch: {attempts}"


# --------------------------------------------------------------------------- #
# The Book tab's buttons — the last step of the trade path
# --------------------------------------------------------------------------- #
def _row(symbol="BTC-USD", price=100.0, vol=0.03):
    return {"symbol": symbol, "price": price, "volatility": vol,
            "name": symbol, "confidence": 70.0, "cls": "Crypto"}


def test_buying_from_the_board_reports_success(window):
    window.live.assets = {"assets": [_row()]}
    window._trade("BTC-USD", "LONG")
    assert "\u2713" in window.status.text()
    assert "paper money only" in window.status.text()


def test_a_refused_trade_says_so_rather_than_failing_silently(window):
    window.live.assets = {"assets": [_row()]}
    window._trade("NOPE", "LONG")
    assert "\u26a0" in window.status.text()
    assert "NOPE" in window.status.text()


def test_buying_forces_both_boards_to_redraw(window):
    """Without clearing the cached signatures the user clicks buy and nothing
    changes until the next 90-second tick — which is indistinguishable from the
    button being dead, and is exactly how the Assets read button once behaved."""
    window.live.assets = {"assets": [_row()]}
    window._assets_sig = "stale"
    window._book_sig = "stale"
    window._trade("BTC-USD", "LONG")
    assert window._assets_sig is None
    assert window._book_sig is None


def test_closing_from_the_book_reports_success_and_redraws(window):
    window.live.assets = {"assets": [_row()]}
    pos_id = window.live.trade("BTC-USD", "LONG")["position"]["id"]
    window._book_sig = "stale"
    window._close_position(pos_id)
    assert "\u2713" in window.status.text()
    assert window._book_sig is None


def test_closing_something_that_is_not_open_warns(window):
    window._close_position("not-a-real-id")
    assert "\u26a0" in window.status.text()
