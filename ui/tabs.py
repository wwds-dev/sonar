"""The navigation rail: what a destination is for, and what it used to be called.

Until 2026-09-29 this module drew the same two-line names across a horizontal
tab bar. The Cockpit shell moved navigation to a **left rail** — eight
destinations with two-line names fit a column far more naturally than a row,
the old toolbar and the 48px bar both fold into it, and every screen gets the
height back. The rules carried over unchanged:

* **Both names, always.** Renaming "Assets" to "Screener" makes the app
  readable for someone new and makes every sentence in the manual wrong —
  `static/docs.html` refers to these tabs by name forty times. The plain name
  leads; the original sits underneath in small caps. `set_wording` keeps the
  expert behaviour: only the original names, one line each.
* **`addTab` is ``PlainTabs.add(widget, plain, was)``** and the docs test
  greps for that call, so every destination the window builds has a row in the
  manual's tabs table.

One new behaviour: **the rail collapses to icons** below a width the full rail
would crowd (the window decides when — see ``MainWindow.resizeEvent``). The
tested 1280×775 minimum is exactly the case: the board's columns already need
the width, so the rail yields it. Names survive as tooltips, and the subtitle
data stays put — collapse changes painting, never state.

``PlainTabs`` is no longer a QTabWidget — a QTabBar docked West draws vertical
text, and overriding enough of it to draw horizontally is fighting the widget —
but it keeps the QTabWidget surface the rest of the app and the tests use:
``count``, ``widget``, ``tabText``, ``setCurrentIndex``, ``currentIndex``,
``tabBar``. It also owns the **page header**: the current destination's name
over one sentence saying what the screen is, with a slot on the right for the
two knobs the whole app depends on, so they stay visible everywhere.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QStackedWidget,
                               QToolTip, QVBoxLayout, QWidget)

from . import icons, theme

ITEM_H = 46         # one destination's row — enough for both names
ITEM_GAP = 2
PAD_X = 10          # inside an item
TEXT_X = 40         # icon at 12, text after it
ACCENT_W = 3        # the selected item's left bar
GROUP_GAP = 26      # the room a group label takes between two groups


class PlainTabBar(QWidget):
    """The rail's item list: icon, plain name, and the name the docs use.

    Painted by hand for the same reason the old horizontal bar was — Qt will
    not stack two differently-sized lines in a tab label — plus one more: a
    QTabBar docked West rotates its text 90°, which is exactly the unreadable
    thing a rail exists to avoid.
    """

    clicked = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self._titles: list[str] = []
        self._subtitles: dict[int, str] = {}
        self._icons: dict[int, str] = {}
        self._tips: dict[int, str] = {}
        self._current = 0
        self._hover = -1
        self._collapsed = False
        self._group_at: int | None = None       # first item of the trailing group
        self._group_name = ""

    # -- model ------------------------------------------------------------- #
    def append(self, title: str, icon_key: str) -> int:
        self._titles.append(title)
        index = len(self._titles) - 1
        self._icons[index] = icon_key
        self.updateGeometry()
        return index

    def count(self) -> int:
        return len(self._titles)

    def set_group(self, first_index: int, name: str) -> None:
        """Items from ``first_index`` on form a labelled group: the experiments,
        kept off the main path by a gap and a small heading, never hidden."""
        self._group_at, self._group_name = first_index, name.upper()
        self.updateGeometry()
        self.update()

    def _top(self, index: int) -> int:
        gap = GROUP_GAP if self._group_at is not None and index >= self._group_at else 0
        return index * (ITEM_H + ITEM_GAP) + gap

    def setTabText(self, index: int, text: str) -> None:
        self._titles[index] = text
        self.update()

    def tabText(self, index: int) -> str:
        return self._titles[index]

    def set_subtitle(self, index: int, subtitle: str) -> None:
        if subtitle:
            self._subtitles[index] = subtitle.upper()
        else:
            self._subtitles.pop(index, None)
        self.update()

    def set_tip(self, index: int, tip: str) -> None:
        self._tips[index] = tip

    def set_current(self, index: int) -> None:
        self._current = index
        self.update()

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed != self._collapsed:
            self._collapsed = collapsed
            self.update()

    # -- geometry ---------------------------------------------------------- #
    def tabRect(self, index: int) -> QRect:
        return QRect(0, self._top(index), self.width(), ITEM_H)

    def sizeHint(self) -> QSize:
        rows = max(1, self.count())
        gap = GROUP_GAP if self._group_at is not None and self._group_at < rows else 0
        return QSize(50, rows * ITEM_H + (rows - 1) * ITEM_GAP + gap)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _index_at(self, pos) -> int:
        for row in range(self.count()):
            if self.tabRect(row).contains(pos):
                return row
        return -1

    # -- interaction ------------------------------------------------------- #
    def mousePressEvent(self, e) -> None:
        index = self._index_at(e.position().toPoint())
        if index >= 0:
            self.clicked.emit(index)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        hover = self._index_at(e.position().toPoint())
        if hover != self._hover:
            self._hover = hover
            self.update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = -1
        self.update()
        super().leaveEvent(e)

    def event(self, e) -> bool:
        # Names collapse away with the rail, so the tooltip has to carry them:
        # plain name, original name, and the sentence the header shows.
        if e.type() == QEvent.Type.ToolTip:
            index = self._index_at(e.pos())
            if index >= 0:
                lines = [self._titles[index]]
                sub = self._subtitles.get(index)
                if sub:
                    lines[0] += f"  ·  {sub}"
                tip = self._tips.get(index)
                if tip:
                    lines.append(tip)
                QToolTip.showText(e.globalPos(), "\n".join(lines), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    # -- painting ---------------------------------------------------------- #
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        ratio = self.devicePixelRatioF() or 2.0
        if self._group_at is not None and self._group_at < self.count():
            top = self._top(self._group_at) - GROUP_GAP
            if self._collapsed:
                p.setPen(theme.GRID)
                p.drawLine(10, top + GROUP_GAP // 2, self.width() - 10, top + GROUP_GAP // 2)
            else:
                p.setFont(theme.text(8))
                p.setPen(theme.FAINT)
                p.drawText(QRect(PAD_X + 4, top, self.width() - 2 * PAD_X, GROUP_GAP),
                           Qt.AlignLeft | Qt.AlignBottom, self._group_name)
        for i in range(self.count()):
            rect = self.tabRect(i)
            selected = i == self._current
            hovered = i == self._hover

            if selected:
                p.setPen(Qt.NoPen)
                p.setBrush(theme.PANEL_HI)
                p.drawRoundedRect(rect, 8, 8)
                p.setBrush(theme.UP)
                p.drawRoundedRect(
                    QRect(rect.x(), rect.y() + 8, ACCENT_W, ITEM_H - 16), 1, 1)

            ink = (theme.UP if selected
                   else theme.MUTED if hovered else theme.FAINT)
            pm = icons.pixmap(self._icons.get(i, ""), ink, 16, ratio)
            if self._collapsed:
                p.drawPixmap(rect.x() + (rect.width() - 16) // 2,
                             rect.y() + (ITEM_H - 16) // 2, pm)
                continue
            p.drawPixmap(rect.x() + 14, rect.y() + (ITEM_H - 16) // 2, pm)

            subtitle = self._subtitles.get(i)
            p.setFont(theme.text(12, selected))
            p.setPen(theme.INK if selected
                     else (theme.MUTED if hovered else theme.FAINT))
            # Centred when it is the only line — expert wording drops the
            # second one, and a title still sitting at the top of the row
            # reads as a rendering bug rather than as a setting.
            title = (QRect(rect.x() + TEXT_X, rect.y() + 7,
                           rect.width() - TEXT_X - PAD_X, 18) if subtitle
                     else QRect(rect.x() + TEXT_X, rect.y(),
                                rect.width() - TEXT_X - PAD_X, ITEM_H))
            p.drawText(title, Qt.AlignLeft | Qt.AlignVCenter, self._titles[i])

            if subtitle:
                p.setFont(theme.text(8))
                p.setPen(theme.FAINT)
                below = QRect(rect.x() + TEXT_X, rect.y() + 25,
                              rect.width() - TEXT_X - PAD_X, 14)
                p.drawText(below, Qt.AlignLeft | Qt.AlignVCenter, subtitle)


class PlainTabs(QWidget):
    """The rail, the page header and the pages — one widget, QTabWidget shaped.

    ``add`` takes the pair of names plus the sentence that becomes both the
    page header's subtitle and the destination's tooltip. The rail's top and
    bottom chrome (wordmark, buttons, status) belong to the window, which
    hands them over through :meth:`set_rail_header` / :meth:`set_rail_footer`;
    the knobs land in the page header through :meth:`set_header_widget`.
    """

    # The expanded width is budgeted, not chosen: the Screener's fixed columns
    # plus this must stay under RAIL_COLLAPSE_BELOW, or a user dragging the
    # window narrower hits the layout minimum before the fold can trigger and
    # the rail can never collapse interactively. test_layout holds the line.
    #
    # It is a floor, not the width. The budget is in the Mac's 72-dpi points,
    # and "My investments" fits it there with room to spare — but a 96-dpi
    # platform (CI's offscreen Ubuntu, DejaVu Sans) needs 143px for the same
    # bold-12 label and clipped it, which is how CI went red for two days
    # after the landing page landed. So `add` measures each name in the font
    # the rail paints it with and widens the rail when the font asks for it;
    # on this Mac nothing changes, and test_layout still says whether the
    # result fits under the fold.
    RAIL_W = 188
    RAIL_COLLAPSED_W = 56

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._names: dict[int, tuple[str, str]] = {}
        self._tips: dict[int, str] = {}
        self._plain = True
        self._collapsed = False
        self._rail_chrome: list[QWidget] = []
        self._rail_w = self.RAIL_W

        self._bar = PlainTabBar(self)
        self._bar.clicked.connect(self.setCurrentIndex)

        self._rail = QFrame()
        self._rail.setObjectName("rail")
        self._rail.setFixedWidth(self._rail_w)
        rail_lay = QVBoxLayout(self._rail)
        rail_lay.setContentsMargins(10, 14, 10, 12)
        rail_lay.setSpacing(12)
        self._rail_lay = rail_lay
        rail_lay.addWidget(self._bar)
        rail_lay.addStretch(1)

        # -- page header ---------------------------------------------------- #
        self._title = QLabel()
        self._title.setFont(theme.text(17, True))
        self._was = QLabel()
        f = theme.text(8)
        f.setLetterSpacing(f.SpacingType.PercentageSpacing, 112)
        self._was.setFont(f)
        self._was.setObjectName("faint")
        self._sub = QLabel()
        self._sub.setFont(theme.text(10))
        self._sub.setObjectName("muted")
        self._sub.setWordWrap(True)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(self._title)
        title_row.addWidget(self._was, 0, Qt.AlignBottom)
        title_row.addStretch(1)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addLayout(title_row)
        title_col.addWidget(self._sub)

        self._header = QWidget()
        self._header.setObjectName("cell")
        header_lay = QHBoxLayout(self._header)
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(16)
        header_lay.addLayout(title_col, 1)
        self._header_lay = header_lay

        self._stack = QStackedWidget()

        content = QVBoxLayout()
        content.setContentsMargins(12, 10, 10, 8)
        content.setSpacing(4)
        content.addWidget(self._header)
        content.addWidget(self._stack, 1)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._rail)
        outer.addLayout(content, 1)

    # -- rail chrome -------------------------------------------------------- #
    def set_rail_header(self, widget: QWidget) -> None:
        widget.setObjectName(widget.objectName() or "cell")
        self._rail_lay.insertWidget(0, widget)
        self._rail_chrome.append(widget)

    def set_rail_footer(self, widget: QWidget) -> None:
        widget.setObjectName(widget.objectName() or "cell")
        self._rail_lay.addWidget(widget)
        self._rail_chrome.append(widget)

    def set_header_widget(self, widget: QWidget) -> None:
        """The knobs. Top-aligned so a wrapped subtitle grows down, not out."""
        self._header_lay.addWidget(widget, 0, Qt.AlignTop)

    # -- QTabWidget surface -------------------------------------------------- #
    def set_group(self, first_index: int, name: str) -> None:
        self._bar.set_group(first_index, name)

    def add(self, widget, name: str, was: str = "", tip: str = "") -> int:
        index = self._stack.addWidget(widget)
        self._names[index] = (name, was)
        self._tips[index] = tip
        self._bar.append(name, (was or name).lower())
        if was:
            self._bar.set_subtitle(index, was)
        if tip:
            self._bar.set_tip(index, tip)
        if index == 0:
            self._retitle_header()
        self._fit_rail_to(name)
        return index

    def _fit_rail_to(self, name: str) -> None:
        """Widen the rail if this platform's font needs more than the budget
        for the name — measured in the selected weight, which is the wider."""
        needed = (QFontMetrics(theme.text(12, True)).horizontalAdvance(name)
                  + TEXT_X + PAD_X + self._rail_lay.contentsMargins().left()
                  + self._rail_lay.contentsMargins().right())
        if needed > self._rail_w:
            self._rail_w = needed
            if not self._collapsed:
                self._rail.setFixedWidth(self._rail_w)

    def rail_width(self) -> int:
        """The expanded rail's width: the budget, or what the font needed."""
        return self._rail_w

    def count(self) -> int:
        return self._stack.count()

    def widget(self, index: int):
        return self._stack.widget(index)

    def currentIndex(self) -> int:
        return self._stack.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._bar.set_current(index)
        self._retitle_header()

    def tabText(self, index: int) -> str:
        return self._bar.tabText(index)

    def tabBar(self) -> PlainTabBar:
        return self._bar

    def setTabToolTip(self, index: int, tip: str) -> None:
        self._tips[index] = tip
        self._bar.set_tip(index, tip)

    # -- state --------------------------------------------------------------- #
    def set_wording(self, plain: bool) -> None:
        """Plain shows both names stacked and the header sentence; expert shows
        only the name the docs use and drops the sentence — vocabulary and
        density, never layout, same as everywhere else."""
        self._plain = plain
        for index, (name, was) in self._names.items():
            self._bar.setTabText(index, name if plain or not was else was)
            self._bar.set_subtitle(index, was if plain else "")
        self._retitle_header()

    def set_collapsed(self, collapsed: bool) -> None:
        """Icons alone. Painting and width only — names, subtitles and the
        header keep their state, so expanding restores everything unchanged."""
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._rail.setFixedWidth(
            self.RAIL_COLLAPSED_W if collapsed else self._rail_w)
        for widget in self._rail_chrome:
            widget.setVisible(not collapsed)
        self._bar.set_collapsed(collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def text_room(self) -> int:
        """Pixels an expanded rail item has for its title, after the icon and
        the padding. Computed from the fixed widths rather than measured,
        because an unshown window has not run its layouts yet."""
        m = self._rail_lay.contentsMargins()
        return self._rail_w - m.left() - m.right() - TEXT_X - PAD_X

    def _retitle_header(self) -> None:
        index = self.currentIndex()
        if index < 0 or index not in self._names:
            return
        name, was = self._names[index]
        self._title.setText(name if self._plain or not was else was)
        self._was.setText(was.upper() if self._plain and was else "")
        self._was.setVisible(self._plain and bool(was))
        tip = " ".join((self._tips.get(index) or "").split())
        self._sub.setText(tip)
        self._sub.setVisible(self._plain and bool(tip))
