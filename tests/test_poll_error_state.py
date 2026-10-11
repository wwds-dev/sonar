"""A failed bitcoin poll is shown as a failure, and freezes nothing else.

Closing UX review C-1: ``refresh()`` returned before the Screener and Big
picture unless the hourly snapshot was ``live``. A poll error printed
"error — first poll can take a moment", dropped the reason, and left the
Screener on "Fetching prices… about a minute" for as long as the feed was down.
"""
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget

from sonar import assets as assets_mod
from sonar.core import Live
from ui import app as ui_app
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


def _texts(layout):
    return [w.text() for i in range(layout.count())
            if (w := layout.itemAt(i).widget()) is not None and hasattr(w, "text")]


class FakeRow(QWidget):
    """Stands in for AssetRow: what is tested is that the board is rebuilt."""
    def __init__(self, a, *_):
        super().__init__()
        self.symbol = a["symbol"]

    def update_age(self, now):
        pass


@pytest.fixture(autouse=True)
def _fake_rows(monkeypatch):
    monkeypatch.setattr(ui_app, "AssetRow", FakeRow)


def _board():
    return {"status": "live", "generated": 1_700_000_000, "n": 1, "priced": 1,
            "assets": [{"symbol": "GS"}]}


# --------------------------------------------------------------------------- #
# refresh() with the poll failing
# --------------------------------------------------------------------------- #
def test_the_screener_draws_while_the_poll_errors(window):
    window.live.assets = _board()
    window.live.snapshot = {"status": "error", "detail": "no fresh BTC price"}
    window.refresh()
    assert len(window._asset_rows) == 1
    assert any(isinstance(w, FakeRow) for w in
               (window._assets_lay.itemAt(i).widget()
                for i in range(window._assets_lay.count())))


def test_the_error_and_its_reason_are_on_the_status_line(window):
    window.live.snapshot = {"status": "error", "detail": "Binance  timed\nout"}
    window.refresh()
    text = window.status.text()
    assert text.startswith("⚠") and "Binance timed out" in text
    assert "first poll can take a moment" not in text


def test_big_picture_refreshes_while_the_poll_errors(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window, "_refresh_macro", lambda snap: seen.append(snap))
    window.live.snapshot = {"status": "error", "detail": "x"}
    window.refresh()
    assert seen and seen[0]["status"] == "error"


def test_the_screener_draws_in_read_only_from_the_mirrored_board(window):
    window.live.assets = _board()
    window.live.snapshot = {"status": "read-only", "detail": "another engine"}
    window.refresh()
    assert len(window._asset_rows) == 1


def test_starting_still_says_first_poll(window):
    window.live.snapshot = {"status": "starting"}
    window.refresh()
    assert "first poll can take a moment" in window.status.text()


@pytest.mark.parametrize("macro,want", [(True, "Loading"), (False, "Switch to")])
def test_the_macro_note_uses_the_engine_horizon_when_the_snapshot_has_none(
        window, monkeypatch, macro, want):
    monkeypatch.setattr(window.live, "horizon", type("H", (), {"macro": macro})())
    window._refresh_macro({"status": "error"})
    assert want in window.macro_note.text()


# --------------------------------------------------------------------------- #
# what the empty Screener says
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("board,want", [
    ({"status": "starting", "assets": []}, "first scan takes about a minute"),
    ({"status": "starting", "assets": [], "error": "URLError: offline"},
     "The last scan failed (URLError: offline)"),
    # an old board's verdict is about a scan that is no longer the latest
    ({"generated": 1, "n": 0, "priced": 12, "assets": [], "error": "KeyError: x"},
     "The last scan failed (KeyError: x)"),
    ({"generated": 1, "n": 0, "priced": 0, "assets": []}, "No prices came back"),
    ({"generated": 1, "n": 0, "priced": 12, "assets": []}, "volatility filter"),
    ({"generated": 1, "n": 0, "assets": []}, "volatility filter"),   # older agent
])
def test_the_empty_screener_says_what_is_true(window, board, want):
    window._refresh_cards(board)
    assert any(want in t for t in _texts(window._assets_lay)), _texts(window._assets_lay)


def test_fetching_stops_being_claimed_after_three_minutes(window):
    window._refresh_cards({"status": "starting", "assets": []})
    window._assets_since = time.time() - ui_app.MainWindow.ASSETS_LATE_S - 61
    window._refresh_cards({"status": "starting", "assets": []})
    texts = _texts(window._assets_lay)
    assert any("Still no prices after 4 minutes" in t for t in texts), texts
    assert not any("about a minute" in t for t in texts)


def test_read_only_without_a_board_does_not_claim_a_scan(window):
    window._refresh_cards({"status": "starting", "assets": []}, read_only=True)
    texts = _texts(window._assets_lay)
    assert any("it is read-only" in t for t in texts), texts
    assert not any("about a minute" in t for t in texts)


def test_the_late_clock_starts_when_read_only_ends(window):
    window._assets_since = time.time() - 3600          # waited an hour read-only
    window._refresh_cards({"status": "starting", "assets": []}, read_only=True)
    window._refresh_cards({"status": "starting", "assets": []})
    texts = _texts(window._assets_lay)
    assert any("about a minute" in t for t in texts), texts


def test_a_steady_board_is_not_rebuilt_every_tick(window):
    window.live.assets = _board()
    window.live.snapshot = {"status": "error", "detail": "x"}
    window.refresh()
    first = list(window._asset_rows)
    window.refresh()
    window.refresh()
    assert window._asset_rows == first


def test_the_empty_text_wraps(window):
    window._refresh_cards({"status": "starting", "assets": [], "error": "E" * 140})
    from PySide6.QtWidgets import QLabel
    lbs = [window._assets_lay.itemAt(i).widget() for i in range(window._assets_lay.count())]
    assert any(isinstance(w, QLabel) and w.wordWrap() for w in lbs)


def test_a_followed_engines_failure_is_named_as_its(window):
    window.live.snapshot = {"status": "error", "detail": "x",
                            "following": "http://127.0.0.1:8787"}
    window.refresh()
    assert "the engine at 127.0.0.1:8787" in window.status.text()


# --------------------------------------------------------------------------- #
# Big picture without a regime
# --------------------------------------------------------------------------- #
def test_read_only_big_picture_says_it_cannot_load(window):
    window._refresh_macro({"status": "read-only", "detail": "another engine"})
    text = window.macro_note.text()
    assert "not available in this window" in text
    assert "Loading" not in text and "Switch to" not in text


def test_old_macro_figures_are_cleared_with_the_regime(window):
    window.macro_stats["VIX"].set("17.3")
    window.regime_bar.set_parts({"rates": 0.5}, {"rates": 1.0})
    window._refresh_macro({"status": "read-only"})
    assert window.macro_stats["VIX"].val.text() == "—"
    assert window.regime_bar.parts == []


# --------------------------------------------------------------------------- #
# what the engine publishes for it
# --------------------------------------------------------------------------- #
@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    return Live()


def test_an_error_snapshot_carries_the_horizon_and_macro(live, monkeypatch):
    class Macro:
        def as_dict(self):
            return {"regime": "neutral"}

    def boom():
        raise RuntimeError("feed down")

    monkeypatch.setattr(live, "_poll", boom)
    live._macro_snap = Macro()
    live.horizon = type("H", (), {"macro": True, "as_dict": lambda self: {"macro": True}})()
    live._poll_once()
    snap = live.snapshot
    assert snap["status"] == "error" and snap["detail"] == "feed down"
    assert snap["horizon"] == {"macro": True} and snap["macro"] == {"regime": "neutral"}


def test_an_error_snapshot_without_a_macro_has_none(live, monkeypatch):
    def boom():
        raise RuntimeError("feed down")

    monkeypatch.setattr(live, "_poll", boom)
    live._macro_snap = None
    live._poll_once()
    assert "macro" not in live.snapshot and "horizon" in live.snapshot


def test_a_good_scan_after_a_failed_one_clears_the_error(live, monkeypatch):
    monkeypatch.setattr(live.news, "headlines", lambda: [])
    monkeypatch.setattr(live.institutions, "payload", lambda: None)
    monkeypatch.setattr(live.events, "payload", lambda: {})
    monkeypatch.setattr(live, "_mark_book", lambda ap: None)
    monkeypatch.setattr(live, "_seed_account_history", lambda: None)

    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(live.asset_scanner, "payload", boom)
    live._rescan_once()
    assert "error" in live.assets
    monkeypatch.setattr(live.asset_scanner, "payload",
                        lambda *a, **k: {"generated": 1, "n": 0, "priced": 3, "assets": []})
    live._rescan_once()
    assert "error" not in live.assets


def test_a_failed_scan_is_recorded_on_the_board(live, monkeypatch):
    monkeypatch.setattr(live.news, "headlines", lambda: [])
    monkeypatch.setattr(live.institutions, "payload", lambda: None)
    monkeypatch.setattr(live.events, "payload", lambda: {})

    def boom(*a, **k):
        raise ConnectionError("source  down")

    monkeypatch.setattr(live.asset_scanner, "payload", boom)
    live._rescan_once()
    assert live.assets["error"] == "ConnectionError: source down"
    assert live.assets["assets"] == []          # the old board, untouched


def test_the_board_counts_priced_rows_before_the_filter(monkeypatch):
    scanner = assets_mod.AssetScanner()
    monkeypatch.setattr(assets_mod, "_fetch", lambda *a: None)    # source sends nothing
    p = scanner.payload([])
    assert p["priced"] == 0 and p["n"] == 0
