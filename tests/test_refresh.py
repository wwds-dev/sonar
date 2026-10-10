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


def test_refresh_while_following_the_agent(window):
    """The launchd agent holds the lock and this window mirrors it: every
    page renders from the mirrored snapshot, and the status line says whose
    figures these are."""
    window.live.snapshot = {"status": "live", "now": 1,
                            "following": "http://127.0.0.1:8787"}
    window.refresh()
    assert window.status.text().startswith("following the engine at 127.0.0.1:8787")
    assert window.read_btn.isEnabled()


def test_a_refused_setting_does_not_stay_shown(window):
    """A window that may not write the book (another engine drives, nothing to
    follow) refuses the protocol switch and a risk change. The widgets the user
    touched must go back to what the engine runs, not keep claiming the change."""
    live = window.live
    live.read_only, live.following = True, None
    live.snapshot = {"status": "read-only", "detail": "another engine"}
    window.protocol_box.setChecked(True)            # refused by set_protocol
    other = next(i for i in range(window.risk_box.count())
                 if window.risk_box.itemData(i) != live.risk.name)
    window.risk_box.blockSignals(True)              # as if a refused ConfigThread ran
    window.risk_box.setCurrentIndex(other)
    window.risk_box.blockSignals(False)
    window.refresh()
    assert live.protocol_on is False and window.protocol_box.isChecked() is False
    assert window.risk_box.currentData() == live.risk.name


def test_the_macro_panel_says_loading_on_a_long_horizon(window):
    """Before the first macro fetch it told a user already on "This quarter"
    to switch to "This quarter"."""
    window._refresh_macro({"horizon": {"macro": True}})
    assert "Loading" in window.macro_note.text()
    window._refresh_macro({"horizon": {"macro": False}})
    assert "Switch to" in window.macro_note.text()


# --------------------------------------------------------------------------- #
# UX U-2 and U-5
# --------------------------------------------------------------------------- #
def _texts(layout):
    out = []
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is not None and hasattr(w, "text"):
            out.append(w.text())
    return out


def test_the_screener_says_it_is_loading_before_the_first_scan(window):
    assert any("first scan takes about a minute" in t for t in _texts(window._assets_lay))
    window._refresh_cards({"status": "starting", "assets": []})
    assert any("first scan" in t for t in _texts(window._assets_lay))
    window._refresh_cards({"generated": 1.0, "n": 0, "assets": []})
    assert any("volatility filter" in t for t in _texts(window._assets_lay)), \
        "after a scan, empty means filtered"


def test_practice_money_is_always_said_in_the_header(window):
    from PySide6.QtWidgets import QLabel
    assert any(l.text() == "Practice money only" for l in window.findChildren(QLabel))


def test_the_edge_figure_is_neutral_until_the_model_beats_the_market(window):
    from ui import theme
    sig = {"model_up": 0.6, "market_up": 0.5, "edge": 0.1, "side": "UP", "tau": 0.5}
    snap = {"status": "live", "signal": sig, "lattice": {}, "market": {},
            "portfolio": {"model_vs_market": {"model_better": False}}}
    window._refresh_terminal(snap)
    assert window.stats["edge"].val.palette().color(
        window.stats["edge"].val.foregroundRole()).name() == theme.MUTED.name() \
        or theme.MUTED.name() in window.stats["edge"].val.styleSheet()
    snap["portfolio"]["model_vs_market"]["model_better"] = True
    window._refresh_terminal(snap)
    assert theme.MUTED.name() not in window.stats["edge"].val.styleSheet()
