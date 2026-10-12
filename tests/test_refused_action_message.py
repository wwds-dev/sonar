"""A refused trade says so where the user will see it, for long enough.

Closing UX review C-2: ``_trade`` wrote "⚠ ..." to the status line and made a
toast only on success; ``refresh()`` rewrites the status line every second,
so the warning was gone before a user who clicked Buy and looked away could
read it. The same held for a failed Close and for "applying — rescanning…".
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget

from sonar.core import Live
from sonar.portfolio import Portfolio
from ui import app as ui_app
from ui.app import MainWindow

ASSET = {"symbol": "AAA", "name": "Aaa", "price": 100.0, "volatility": 0.02,
         "confidence": 50.0, "cls": "Equity"}


class FakeRow(QWidget):
    """The board is not under test; refresh() draws it in every state."""
    def __init__(self, a, *_):
        super().__init__()

    def update_age(self, now):
        pass


@pytest.fixture
def window(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    monkeypatch.setattr(ui_app, "AssetRow", FakeRow)
    win = MainWindow(Live())
    win.poll.live.stop()
    win.poll.quit(); win.poll.wait(3000)
    win.live.book = Portfolio(tmp_path / "portfolio.json")
    win.live.assets = {"assets": [dict(ASSET)]}
    win.live.snapshot = {"status": "starting"}
    win.resize(1600, 900)            # wide: the rail's own status line, no bar
    win._sync_rail()
    yield win
    win.shutdown()


@pytest.fixture
def clock(monkeypatch):
    """The hold's clock, moved by hand (ui_app._now, not the process's time)."""
    now = [1000.0]
    monkeypatch.setattr(ui_app, "_now", lambda: now[0])
    return now


def _shown(window) -> bool:
    return not window.statusBar().isHidden() and not window._toast_label.isHidden()


# --------------------------------------------------------------------------- #
# a refused trade
# --------------------------------------------------------------------------- #
def test_a_refused_trade_gets_a_warning_toast_without_undo(window, clock):
    window._trade("NOPE", "LONG")
    assert _shown(window), "the toast shows at any width"
    assert window._toast_timer.isActive(), "and goes away on its own"
    assert window._toast_timer.remainingTime() > window.TOAST_MS - 1000
    text = window._toast_label.text()
    assert text.startswith("⚠") and "Not traded" in text and "NOPE" in text
    assert window._toast_undo.isHidden() and window._toast_target is None


def test_the_refusal_survives_the_next_refreshes(window, clock):
    window._trade("NOPE", "LONG")
    held = window.status.text()
    assert held.startswith("⚠") and "NOPE" in held
    for _ in range(3):
        clock[0] += 1.0
        window.refresh()
    assert window.status.text() == held
    assert window._bar_status.text() == held


def test_refresh_writes_again_once_the_hold_is_over(window, clock):
    window._trade("NOPE", "LONG")
    clock[0] += window.TOAST_MS / 1000 + 0.1
    window.refresh()
    assert "first poll can take a moment" in window.status.text()


def test_the_warning_toast_goes_away_on_its_own(window, clock):
    window._trade("NOPE", "LONG")
    window._toast_done()                      # what the 8 s timer calls
    assert window._toast_label.isHidden() and window.statusBar().isHidden()


def test_undo_does_nothing_on_a_warning(window, clock):
    window._trade("NOPE", "LONG")
    calls = []
    window.live.undo = lambda *a: calls.append(a) or {"ok": True, "message": "x"}
    window._undo_clicked()
    assert calls == []


# --------------------------------------------------------------------------- #
# the other paths the review named
# --------------------------------------------------------------------------- #
def test_a_successful_trade_is_held_too(window, clock):
    window._trade("AAA", "LONG")
    held = window.status.text()
    assert held.startswith("✓")
    clock[0] += 1.0
    window.refresh()
    assert window.status.text() == held
    assert not window._toast_undo.isHidden(), "success keeps its Undo"


def test_a_failed_close_is_warned_and_held(window, clock):
    window._close_position("not-a-real-id")
    assert "Not closed" in window._toast_label.text() and _shown(window)
    held = window.status.text()
    clock[0] += 1.0
    window.refresh()
    assert window.status.text() == held and held.startswith("⚠")


def test_a_failed_undo_is_warned(window, clock):
    window._trade("AAA", "LONG")
    window.live.undo = lambda *a: {"ok": False, "message": "too late to undo"}
    window._undo_clicked()
    assert "Not undone: too late to undo" in window._toast_label.text()
    assert window.status.text().startswith("⚠")


def test_a_newer_message_replaces_a_held_one_at_once(window, clock):
    window._trade("NOPE", "LONG")
    window._trade("AAA", "LONG")
    assert window.status.text().startswith("✓")
    assert window._toast_target is not None, "the newer toast is the success's"


class NeverDone:
    """A ConfigThread whose rescan is still running."""
    def __init__(self, *a):
        pass
    done = type("Sig", (), {"connect": lambda self, f: None})()
    def start(self): pass
    def isRunning(self): return False


@pytest.mark.parametrize("snap", [{"status": "starting"},
                                  {"status": "live", "now": 1}])
def test_applying_a_setting_is_said_until_it_is_done(window, clock, monkeypatch, snap):
    monkeypatch.setattr(ui_app, "ConfigThread", NeverDone)
    window.live.snapshot = snap
    window._apply_config()
    clock[0] += 120.0
    window.refresh()
    assert window.status.text().startswith("applying")
    window._config_done(window.live.config())
    window.refresh()
    assert not window.status.text().startswith("applying")


def test_a_warning_gets_through_a_long_rescan(window, clock, monkeypatch):
    monkeypatch.setattr(ui_app, "ConfigThread", NeverDone)
    window._apply_config()
    clock[0] += window.TOAST_MS / 1000 + 1
    window.live.snapshot = {"status": "read-only", "detail": "another engine"}
    window.refresh()
    assert window.status.text().startswith("⚠  another engine")


def test_a_finished_setting_does_not_cut_a_refusal_short(window, clock, monkeypatch):
    monkeypatch.setattr(ui_app, "ConfigThread", NeverDone)
    window._apply_config()
    window._trade("NOPE", "LONG")
    held = window.status.text()
    window._config_done(window.live.config())
    clock[0] += 1.0
    window.refresh()
    assert window.status.text() == held


def test_a_refused_setting_says_so_through_the_real_engine(window, clock):
    live = window.live
    live.read_only, live.following = True, None       # nothing to follow
    window._config_done(live.configure("aggressive", None))
    assert "Setting not applied" in window._toast_label.text()
    assert "read-only" in window._toast_label.text()
    clock[0] += 1.0
    window.refresh()
    assert window.status.text().startswith("⚠")


def test_a_setting_error_keeps_a_live_undo(window, clock):
    window._trade("AAA", "LONG")
    target = window._toast_target
    window._config_done({"error": "rescan failed"})
    assert window._toast_target == target and not window._toast_undo.isHidden()
    assert "setting not applied: rescan failed" in window.status.text()


def test_a_refused_horizon_goes_back_to_the_engines(window):
    live = window.live
    other = next(i for i in range(window.hz_box.count())
                 if window.hz_box.itemData(i) != live.horizon.name)
    window.hz_box.blockSignals(True)
    window.hz_box.setCurrentIndex(other)
    window.hz_box.blockSignals(False)
    window._sync_knobs()
    assert window.hz_box.currentData() == live.horizon.name


def test_a_missing_page_is_held(window, clock, monkeypatch, tmp_path):
    monkeypatch.setattr("sonar.paths.resource_base", lambda: tmp_path)
    window._open_page("nope.html", "documentation")
    clock[0] += 1.0
    window.refresh()
    assert "documentation not found" in window.status.text()


# --------------------------------------------------------------------------- #
# what the engine tells the window
# --------------------------------------------------------------------------- #
def test_configure_says_when_it_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    live.read_only, live.following = True, None
    out = live.configure("aggressive", None)
    assert "read-only" in out["refused"] and out["risk"]


def test_configure_says_when_the_followed_engine_did_not_confirm(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    live = Live()
    live.following = "http://127.0.0.1:8787"

    def down(*a, **k):
        raise ConnectionError("refused")

    monkeypatch.setattr(live, "_post", down)
    out = live.configure("aggressive", None)
    assert "127.0.0.1:8787 did not confirm it (ConnectionError: refused)" in out["error"]


def test_a_warning_drops_the_previous_toasts_undo(window, clock):
    # Undo acts on what the toast shows; once it shows a refusal, the earlier
    # trade is no longer what a click would take back.
    window._trade("AAA", "LONG")
    window._trade("NOPE", "LONG")
    calls = []
    window.live.undo = lambda *a: calls.append(a) or {"ok": True, "message": "x"}
    window._undo_clicked()
    assert calls == [] and len(window.live.book.open) == 1
