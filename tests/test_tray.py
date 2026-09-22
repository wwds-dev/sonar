"""The menu-bar item: the only part of the app visible most of the time.

`ui/tray.py` sat at 0%, and it carries two things worth pinning. The readout —
`update_state` turning a snapshot into the bankroll line, the open-position
row and the tooltip — is pure formatting, and formatting that nothing checks
is how "TAU" ends up on screen. And the STALLED alarm has once-per-stall
semantics: notify when the run stops collecting, stay quiet while it stays
stopped, and re-arm when it recovers — a nagging alarm teaches people to
ignore the feature, which is worse than no alarm.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from ui.tray import Tray, _tray_icon


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeWindow:
    allow_close = False

    def __init__(self):
        self.revealed = 0

    def showNormal(self):
        self.revealed += 1

    def raise_(self):
        pass

    def activateWindow(self):
        pass

    def reveal(self):
        self.revealed += 1


@pytest.fixture
def tray(app):
    t = Tray(FakeWindow(), app)
    t.messages = []
    t.supportsMessages = lambda: True
    t.showMessage = lambda title, *a, **k: t.messages.append(title)
    yield t
    t.hide()
    t.deleteLater()


def snap(bankroll=10_250.0, pnl=250.0, n=7, stale=False, position=None,
         edge=None):
    portfolio = {"stats": {"bankroll": bankroll, "total_pnl": pnl,
                           "n_trades": n},
                 "open_position": position,
                 "run_health": {"stale": stale}}
    signal = {"edge": edge} if edge is not None else {}
    return {"portfolio": portfolio, "signal": signal}


def test_the_icon_is_a_template_image(app):
    """macOS recolours a mask for light and dark menu bars; a coloured icon
    is wrong in one of them."""
    assert _tray_icon().isMask()


def test_the_readout_carries_bankroll_pnl_and_trades(tray):
    tray.update_state(snap())
    assert tray.state_action.text() == "$10,250   +250   ·   7 trades"


def test_an_empty_snapshot_changes_nothing(tray):
    tray.update_state(snap())
    before = tray.state_action.text()
    tray.update_state({})
    assert tray.state_action.text() == before


def test_an_open_position_appears_and_disappears(tray):
    tray.update_state(snap(position={"side": "UP", "shares": 12.3456,
                                     "entry_price": 0.4321}))
    assert tray.pos_action.isVisible()
    assert tray.pos_action.text() == "open: UP 12.35 @ 0.43"
    tray.update_state(snap())
    assert not tray.pos_action.isVisible()


def test_the_tooltip_names_the_edge_and_the_paper_money_line(tray):
    tray.update_state(snap(edge=0.0234))
    assert "edge +2.3¢" in tray.toolTip()
    assert "paper money only" in tray.toolTip()


def test_a_stall_notifies_once_and_marks_the_tooltip(tray):
    tray.update_state(snap(stale=True))
    tray.update_state(snap(stale=True))
    tray.update_state(snap(stale=True))
    assert tray.messages == ["SONAR has stopped collecting"], \
        "one stall, one notification — a nagging alarm gets ignored"
    assert "⚠ STALLED" in tray.toolTip()


def test_recovery_clears_the_flag_and_rearms_the_alarm(tray):
    tray.update_state(snap(stale=True))
    tray.update_state(snap(stale=False))
    assert "STALLED" not in tray.toolTip()
    tray.update_state(snap(stale=True))
    assert tray.messages == ["SONAR has stopped collecting"] * 2, \
        "a second stall after recovery is news again"


def test_the_first_hide_is_explained_once(tray):
    tray.note_hidden()
    tray.note_hidden()
    assert tray.messages == ["SONAR is still running"]


def test_activation_reveals_the_window(tray):
    from PySide6.QtWidgets import QSystemTrayIcon
    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert tray.window.revealed == 1
    tray._on_activated(QSystemTrayIcon.ActivationReason.Context)
    assert tray.window.revealed == 1, "the context menu is not a reveal"


def test_the_version_sits_in_the_menu(tray):
    from sonar import version
    assert tray.version_action.text() == version.version_string()
