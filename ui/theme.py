"""Palette and shared painting helpers.

The colours are lifted verbatim from the HTML terminal's CSS variables so the
native app reads as the same product rather than a port of it.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

BG = QColor("#080b11")
PANEL = QColor("#0d131d")
BORDER = QColor("#1a2431")
INK = QColor("#e6edf3")
MUTED = QColor("#7f8ea0")
FAINT = QColor("#4a5867")
UP = QColor("#3ea6ff")
DOWN = QColor("#ff6a54")
GOLD = QColor("#e8b84b")
GRID = QColor("#141d29")

# Confidence component colours, matching the scanner legend.
COMP = {
    "edge": QColor("#7ee787"),
    "liquidity": QColor("#3ea6ff"),
    "timing": QColor("#e8b84b"),
    "momentum": QColor("#d2a8ff"),
    "news": QColor("#ff9f6a"),
    "volatility": QColor("#ff6a54"),
    # macro regime components
    "curve": QColor("#7ee787"),
    "policy": QColor("#3ea6ff"),
    "labour": QColor("#d2a8ff"),
}

REGIME = {
    "risk-on": QColor("#7ee787"),
    "transitional": QColor("#e8b84b"),
    "risk-off": QColor("#ff6a54"),
    "unknown": MUTED,
}


def mono(size: int = 11, bold: bool = False) -> QFont:
    # Menlo ships with every macOS and matches exactly; asking for "SF Mono"
    # first costs a ~200ms font-alias sweep on startup for no visual gain.
    f = QFont("Menlo")
    f.setPointSize(size)
    f.setBold(bold)
    return f


def ui_font(size: int = 12, bold: bool = False) -> QFont:
    f = QFont(".AppleSystemUIFont")
    f.setPointSize(size)
    f.setBold(bold)
    return f


def side_color(side: str | None) -> QColor:
    return UP if side == "UP" else DOWN if side == "DOWN" else MUTED


def pnl_color(v: float | None) -> QColor:
    if v is None:
        return MUTED
    return UP if v > 0 else DOWN if v < 0 else MUTED


STYLESHEET = f"""
QWidget {{ background: {BG.name()}; color: {INK.name()}; }}
QLabel#h1 {{ font-size: 15px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED.name()}; }}
QLabel#faint {{ color: {FAINT.name()}; }}
QFrame#panel {{
    background: {PANEL.name()};
    border: 1px solid {BORDER.name()};
    border-radius: 8px;
}}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {MUTED.name()};
    padding: 7px 16px; margin-right: 2px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {INK.name()}; border-bottom: 2px solid {UP.name()}; }}
QComboBox {{
    background: {PANEL.name()}; border: 1px solid {BORDER.name()};
    border-radius: 6px; padding: 4px 10px; min-width: 140px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL.name()}; border: 1px solid {BORDER.name()};
    selection-background-color: {BORDER.name()};
}}
QPushButton {{
    background: {PANEL.name()}; border: 1px solid {BORDER.name()};
    border-radius: 6px; padding: 5px 14px;
}}
QPushButton:hover {{ border-color: {UP.name()}; }}
QPushButton:disabled {{ color: {FAINT.name()}; border-color: {BORDER.name()}; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {BORDER.name()}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QHeaderView::section {{
    background: {BG.name()}; color: {MUTED.name()};
    border: none; border-bottom: 1px solid {BORDER.name()}; padding: 5px;
}}
QTableWidget {{ gridline-color: {GRID.name()}; border: none; }}
QToolTip {{
    background: {PANEL.name()}; color: {INK.name()};
    border: 1px solid {BORDER.name()}; padding: 5px;
}}
"""
