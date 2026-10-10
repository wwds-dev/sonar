"""T1-10: status at any width, a way back from a misclick, a first-run card."""

from __future__ import annotations

import time

import pytest

from sonar.core import Live
from sonar.portfolio import Portfolio

ASSET = {"symbol": "AAA", "name": "Aaa", "price": 100.0, "volatility": 0.02,
         "confidence": 50.0, "cls": "Equity"}


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    lv = Live()
    lv.book = Portfolio(tmp_path / "portfolio.json")
    lv.assets = {"assets": [dict(ASSET)]}
    return lv


# --------------------------------------------------------------------------- #
# The book: cancel and reopen never reach the graded record
# --------------------------------------------------------------------------- #
def test_undoing_a_trade_removes_it_and_refunds_the_cash(live):
    cash = live.book.cash
    pos = live.trade("AAA", "LONG")["position"]
    assert live.book.cash < cash
    r = live.undo(pos["id"], "trade")
    assert r["ok"] and live.book.open == [] and live.book.closed == []
    assert live.book.cash == pytest.approx(cash)


def test_undoing_a_close_reopens_it_at_its_entry(live):
    pos = live.trade("AAA", "LONG")["position"]
    cash_open = live.book.cash
    live.assets = {"assets": [dict(ASSET, price=104.0)]}
    assert live.close_position(pos["id"])["ok"]
    r = live.undo(pos["id"], "close")
    assert r["ok"] and live.book.closed == [] and len(live.book.open) == 1
    back = live.book.open[0]
    assert back.entry == 100.0 and back.exit is None and back.outcome is None
    assert live.book.cash == pytest.approx(cash_open)


def test_too_late_is_too_late(live, monkeypatch):
    pos = live.trade("AAA", "LONG")["position"]
    live.book.open[0].opened_at = time.time() - live.UNDO_WINDOW - 1
    r = live.undo(pos["id"], "trade")
    assert r["ok"] is False and "time is up" in r["message"]
    assert len(live.book.open) == 1


def test_a_close_cannot_be_undone_once_the_price_has_moved(live):
    """Reopened after a move past its target, the next mark graded a hand
    close as a TARGET win picked with hindsight."""
    pos = live.trade("AAA", "LONG")["position"]
    live.assets = {"assets": [dict(ASSET, price=pos["target"] - 0.01)]}
    assert live.close_position(pos["id"])["ok"]
    live.assets = {"assets": [dict(ASSET, price=pos["target"] + 1.0)]}
    r = live.undo(pos["id"], "close")
    assert r["ok"] is False and "moved" in r["message"]
    assert [p.outcome for p in live.book.closed] == ["MANUAL"]


def test_a_trade_cannot_be_undone_once_the_price_has_moved(live):
    """Cancelling at entry after a drop would let a bad start vanish from the record."""
    pos = live.trade("AAA", "LONG")["position"]
    live.assets = {"assets": [dict(ASSET, price=99.0)]}
    assert live.undo(pos["id"], "trade")["ok"] is False
    assert len(live.book.open) == 1


def test_a_reopen_needs_the_cash_to_still_be_there(live):
    pos = live.trade("AAA", "LONG")["position"]
    assert live.close_position(pos["id"])["ok"]
    live.book.cash = 0.0                     # spent on something else meanwhile
    assert live.undo(pos["id"], "close")["ok"] is False
    assert live.book.cash == 0.0


def test_a_protocol_entry_cannot_be_undone(live):
    pos, _ = live.book.enter(dict(ASSET), "LONG", 5, "week", protocol=True)
    assert live.undo(pos.id, "trade")["ok"] is False


def test_a_trade_that_already_hit_a_barrier_says_so(live):
    pos = live.trade("AAA", "LONG")["position"]
    live._mark_book({"assets": [dict(ASSET, price=pos["stop"] * 0.99)]})
    r = live.undo(pos["id"], "trade")
    assert "already closed at its stop" in r["message"]


def test_a_barrier_exit_cannot_be_undone(live):
    pos = live.trade("AAA", "LONG")["position"]
    live._mark_book({"assets": [dict(ASSET, price=pos["stop"] * 0.99)]})
    assert live.book.closed[0].outcome == "STOP"
    assert live.undo(pos["id"], "close")["ok"] is False, "an outcome, not a misclick"


# --------------------------------------------------------------------------- #
# The window
# --------------------------------------------------------------------------- #
@pytest.fixture
def window(qapp_window):
    return qapp_window


@pytest.fixture
def qapp_window(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from ui.app import MainWindow
    QApplication.instance() or QApplication([])
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    win = MainWindow(Live())
    win.poll.live.stop()
    win.poll.quit(); win.poll.wait(3000)
    win.live.book = Portfolio(tmp_path / "portfolio.json")
    win.live.assets = {"assets": [dict(ASSET)]}
    yield win
    win.shutdown()


def test_the_status_line_is_on_screen_when_the_rail_folds(window):
    window.resize(1280, 800)
    window._sync_rail()
    window._set_status("⚠  another engine is running")
    assert window.tabs.is_collapsed()
    assert not window.statusBar().isHidden() and not window._bar_status.isHidden()
    assert "another engine" in window._bar_status.text()
    window.resize(1600, 900)
    window._sync_rail()
    assert window.statusBar().isHidden(), "the rail's own line shows it again"


def test_a_trade_offers_undo_and_undo_takes_it_back(window):
    cash = window.live.book.cash
    window._trade("AAA", "LONG")
    assert window._toast_target is not None and not window._toast_undo.isHidden()
    assert not window.statusBar().isHidden(), "the toast shows at any width"
    window._undo_clicked()
    assert window.live.book.open == [] and window.live.book.cash == pytest.approx(cash)
    assert window._toast_target is None and "cancelled" in window.status.text()


def test_the_toast_goes_away_on_its_own(window):
    window._trade("AAA", "LONG")
    window._toast_done()                      # what the 8 s timer calls
    assert window._toast_undo.isHidden() and window._toast_target is None


def test_the_start_card_shows_on_an_empty_book_until_dismissed(window):
    window._refresh_portfolio()
    assert not window.start_card.isHidden()
    window._dismiss_start_card()
    window._refresh_portfolio()
    assert window.start_card.isHidden()


def test_got_it_sticks_even_if_it_cannot_be_saved(window, monkeypatch):
    def fail(*a, **k):
        raise OSError("read-only disk")
    monkeypatch.setattr("sonar.paths.write_atomically", fail)
    window._refresh_portfolio()
    window._dismiss_start_card()
    window._refresh_portfolio()
    assert window.start_card.isHidden()


def test_the_start_card_leaves_once_there_is_a_book(window):
    window.live.trade("AAA", "LONG")
    window._refresh_portfolio()
    assert window.start_card.isHidden()


def test_every_page_has_a_keyboard_shortcut(window):
    from PySide6.QtGui import QShortcut
    keys = {s.key().toString() for s in window.findChildren(QShortcut)}
    assert {f"Ctrl+{i}" for i in range(1, window.tabs.count() + 1)} <= keys
