"""A tab bar that says what a tab is for, and what it used to be called.

Renaming "Assets" to "Screener" makes the app readable for someone new and makes
every sentence in the manual wrong — `static/docs.html` refers to these tabs by
name forty times, and so does the README, and so does the person who has been
using the app for a month. Both names, stacked, costs one line of pixels and
settles the argument: the plain name leads, the original sits underneath in the
small caps it is written in everywhere else.

Qt will not do this on its own. A ``\\n`` in ``setTabText`` round-trips through
the API and is then drawn on one line and clipped, so the bar is painted here.
That means painting *everything* — a QTabBar that overrides ``paintEvent`` gets
no stylesheet background, no selected state, nothing — which is why the colours
below come from :mod:`ui.theme` rather than from the stylesheet.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QTabBar, QTabWidget

from . import theme

PAD_X = 15          # left/right inside one tab
HEIGHT = 48
UNDERLINE = 2


class PlainTabBar(QTabBar):
    """Two lines per tab: the plain name, and the name the docs use."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDrawBase(False)
        self.setMouseTracking(True)
        self._subtitles: dict[int, str] = {}
        self._hover = -1

    def set_subtitle(self, index: int, subtitle: str) -> None:
        self._subtitles[index] = subtitle.upper()
        self.updateGeometry()
        self.update()

    # -- geometry ---------------------------------------------------------- #
    def tabSizeHint(self, index: int):
        """Measured with the fonts `paintEvent` actually uses — and with the
        *selected* weight, because a tab sized for its unselected width loses
        its last letter the moment it is clicked."""
        size = super().tabSizeHint(index)
        title = QFontMetrics(theme.text(12, True)).horizontalAdvance(
            self.tabText(index))
        sub = QFontMetrics(theme.text(8)).horizontalAdvance(
            self._subtitles.get(index, ""))
        size.setWidth(max(title, sub) + 2 * PAD_X)
        size.setHeight(HEIGHT)
        return size

    # -- painting ---------------------------------------------------------- #
    def mouseMoveEvent(self, event) -> None:
        hover = self.tabAt(event.position().toPoint())
        if hover != self._hover:
            self._hover = hover
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        for i in range(self.count()):
            rect = self.tabRect(i)
            selected = i == self.currentIndex()

            p.setFont(theme.text(12, selected))
            p.setPen(theme.INK if selected
                     else (theme.MUTED if i == self._hover else theme.FAINT))
            title = QRect(rect.x() + PAD_X, rect.y() + 7,
                          rect.width() - 2 * PAD_X, 18)
            p.drawText(title, Qt.AlignLeft | Qt.AlignVCenter, self.tabText(i))

            subtitle = self._subtitles.get(i)
            if subtitle:
                p.setFont(theme.text(8))
                p.setPen(theme.FAINT)
                below = QRect(rect.x() + PAD_X, rect.y() + 24,
                              rect.width() - 2 * PAD_X, 14)
                p.drawText(below, Qt.AlignLeft | Qt.AlignVCenter, subtitle)

            if selected:
                p.fillRect(QRect(rect.x() + PAD_X - 3, rect.bottom() - UNDERLINE,
                                 rect.width() - 2 * PAD_X + 6, UNDERLINE),
                           theme.UP)


class PlainTabs(QTabWidget):
    """A QTabWidget wearing the bar above. ``addTab`` takes the pair."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bar = PlainTabBar(self)
        self.setTabBar(self._bar)

    def add(self, widget, name: str, was: str = "", tip: str = "") -> int:
        index = self.addTab(widget, name)
        if was:
            self._bar.set_subtitle(index, was)
        if tip:
            self.setTabToolTip(index, tip)
        return index
