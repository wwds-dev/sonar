"""Menu-bar presence — so closing the window does not stop the engine.

SONAR is a daemon wearing an app. The equity curve only means something if
positions settle on the hours they were priced for, and the calibration table
only fills as trades resolve. A window you close taking the engine with it
quietly destroys both.

So the close button **hides**. The poll thread keeps running, the menu bar shows
the bankroll, and quitting is a deliberate act with its own menu item. The first
close says so once, rather than leaving you wondering where the window went.

The icon is drawn as a macOS *template* image — a monochrome mask the system
recolours for light and dark menu bars — because a coloured icon looks wrong in
half of them.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from sonar import version

from . import theme


# How long after a menu-bar click an app activation is still attributed to it
# rather than to the Dock. The click, the activation and the menu appearing are
# one gesture arriving as three events, in an order the platform chooses.
TRAY_TOUCH_GRACE_MS = 1500


def _tray_icon() -> QIcon:
    """A small sonar sweep, as a template image.

    Drawn at 44px and marked ``setIsMask`` so macOS inverts it appropriately
    instead of leaving a dark glyph on a dark menu bar.
    """
    size = 44
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    centre = QPointF(size * 0.5, size * 0.52)
    p.setPen(QPen(Qt.black, size * 0.075, Qt.SolidLine, Qt.RoundCap))
    for frac in (0.16, 0.30):
        p.drawEllipse(centre, size * frac, size * frac)
    p.drawLine(centre, QPointF(centre.x() + size * 0.26, centre.y() - size * 0.26))
    p.end()
    pm.setDevicePixelRatio(2.0)
    icon = QIcon(pm)
    icon.setIsMask(True)          # template image: the system handles contrast
    return icon


class Tray(QSystemTrayIcon):
    """Menu-bar item showing live state, with the only real Quit."""

    def __init__(self, window, app) -> None:
        super().__init__(_tray_icon(), app)
        self.window = window
        self.app = app
        self._warned = False
        self._stalled = False

        menu = QMenu()
        self.state_action = QAction("starting…", menu)
        self.state_action.setEnabled(False)
        menu.addAction(self.state_action)
        self.pos_action = QAction("", menu)
        self.pos_action.setEnabled(False)
        self.pos_action.setVisible(False)
        menu.addAction(self.pos_action)
        menu.addSeparator()

        show = QAction("Open SONAR", menu)
        show.triggered.connect(self.reveal)
        menu.addAction(show)
        menu.addSeparator()

        # The menu bar is the one part of the app you can reach while the window
        # is hidden, which is most of the time -- so the version is reachable
        # there too, with the full build stamp as its tooltip.
        self.version_action = QAction(version.version_string(), menu)
        self.version_action.setEnabled(False)
        self.version_action.setToolTip(version.tooltip())
        menu.addAction(self.version_action)

        quit_action = QAction("Quit SONAR", menu)
        # The engine stops here and only here.
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.menu = menu
        self.setContextMenu(menu)
        self.setToolTip("SONAR — paper money only")

        # Clicking a menu-bar item opens its menu. That is all it does in every
        # Mac app that has one, and SONAR used to do more: the click revealed
        # the window as well, so asking what the bankroll was dragged the whole
        # app to the front over whatever you were working in. "Open SONAR" is
        # the item that opens SONAR.
        #
        # The click still has to be *recorded*, because macOS activates the app
        # to show the menu and main.py reads an activation as a Dock click. Both
        # signals are watched because their order is the platform's to decide.
        self._touched_at = 0.0
        self.activated.connect(self._note_touch)
        menu.aboutToShow.connect(self._note_touch)

    def _note_touch(self, *_) -> None:
        self._touched_at = time.monotonic()

    def menu_recently_used(self) -> bool:
        """Did this activation come from the menu bar rather than the Dock?

        Qt reports both as a bare ApplicationActivate. The menu being open is
        proof on its own; the timestamp covers the moment between the click
        landing and the menu appearing.
        """
        if self.menu.isVisible():
            return True
        return (time.monotonic() - self._touched_at) * 1000 < TRAY_TOUCH_GRACE_MS

    def reveal(self) -> None:
        # MainWindow.reveal, not showNormal: a close pressed in full screen
        # leaves a hide pending until the Space has collapsed, and reopening the
        # window has to call that off rather than race it.
        self.window.reveal()

    def _quit(self) -> None:
        self.window.allow_close = True
        self.hide()
        self.app.quit()

    def note_hidden(self) -> None:
        """Explain the first disappearing act, once."""
        if self._warned:
            return
        self._warned = True
        if self.supportsMessages():
            self.showMessage(
                "SONAR is still running",
                "The engine keeps settling hours in the background. "
                "Open it from the menu bar, or quit from there.",
                self.icon(), 6000)

    def update_state(self, snap: dict) -> None:
        """Refresh the menu-bar readout from the live snapshot."""
        stats = (snap.get("portfolio") or {}).get("stats") or {}
        if not stats:
            return
        bank = stats.get("bankroll")
        pnl = stats.get("total_pnl", 0.0)
        n = stats.get("n_trades", 0)
        self.state_action.setText(f"${bank:,.0f}   {pnl:+,.0f}   ·   {n} trades")

        op = (snap.get("portfolio") or {}).get("open_position")
        if op:
            self.pos_action.setText(
                f"open: {op['side']} {op['shares']:.2f} @ {op['entry_price']:.2f}")
            self.pos_action.setVisible(True)
        else:
            self.pos_action.setVisible(False)

        sig = snap.get("signal") or {}
        edge = f"  edge {sig['edge']*100:+.1f}¢" if sig else ""
        stalled = self._check_stalled(snap)
        warn = "  ⚠ STALLED" if stalled else ""
        self.setToolTip(f"SONAR  ${bank:,.0f}{edge}{warn}  ·  paper money only")

    def _check_stalled(self, snap: dict) -> bool:
        """Notify once when the run stops collecting, and re-arm on recovery.

        The app is designed to be invisible, which is exactly why a dead run
        looks identical to a healthy one: the window is hidden, the menu bar
        glyph never changes, and the equity curve simply stops growing where
        nobody is watching it. BTC settles around the clock, so two hours
        without a settlement always means the experiment has stalled.
        """
        rh = (snap.get("portfolio") or {}).get("run_health") or {}
        stalled = bool(rh.get("stale"))
        if stalled and not self._stalled and self.supportsMessages():
            self.showMessage(
                "SONAR has stopped collecting",
                "No hour has settled in over two hours. The feed, the "
                "network, or the engine has stalled — open SONAR to check.",
                self.icon(), 10_000)
        self._stalled = stalled
        return stalled
