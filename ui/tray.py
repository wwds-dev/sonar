"""Menu-bar presence — the bankroll at a glance, and a Quit that is always there.

SONAR is a daemon wearing an app. The equity curve only means something if
positions settle on the hours they were priced for, and the calibration table
only fills as trades resolve.

The close button used to **hide** for that reason, keeping the engine alive
behind a menu-bar icon. It was reported as a bug twice, which settles the
question of whether the notification explaining it was enough: on macOS the red
button closes, and an app that survives it reads as an app ignoring you. Close
now quits.

Uptime still has a door, and a better one — `sonar --headless` runs the same
engine with no Qt at all. That is what `sonar/core.py` was split out for.

So this icon is now a readout rather than a lifeline: it shows the bankroll
while the app runs, and carries a Quit for reaching the app when its window is
behind something.

The icon is drawn as a macOS *template* image — a monochrome mask the system
recolours for light and dark menu bars — because a coloured icon looks wrong in
half of them.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import theme


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

        quit_action = QAction("Quit SONAR", menu)
        # The engine stops here and only here.
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.setToolTip("SONAR — paper money only")
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.reveal()

    def reveal(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _quit(self) -> None:
        self.window.allow_close = True
        self.hide()
        self.app.quit()

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
        self.setToolTip(f"SONAR  ${bank:,.0f}{edge}  ·  paper money only")
