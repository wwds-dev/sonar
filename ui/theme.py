"""Palette, fonts and the shared stylesheet.

**The Plain Language direction (2026-09-22).** SONAR used to be drawn as a
trading terminal: monospace everywhere, near-black background, and greys so far
down the scale that `FAINT` measured under 3:1 against the panel it sat on. That
reads as a terminal, and it reads as almost nothing else. The person this app is
actually for said the quiet part out loud — the font, the contrast and the
dropdowns all made it harder to use, on top of a vocabulary he had no way into.

So three things changed here, and each one is a rule rather than a taste:

* **Proportional type carries words; monospace carries only code.** Menlo was
  drawing English prose, which it is bad at. :func:`text` is the interface font,
  :func:`figure` is the same face with *tabular* numerals — so a column of
  prices still lines up without pretending a sentence is a code listing — and
  :func:`code` is the real monospace, for the two places that paste tables.
* **Contrast is a floor, not a preference.** `MUTED` and `FAINT` both clear
  4.5:1 against `PANEL` now. A label nobody can read is not a subtle label.
* **A control is as big as it is easy to hit.** The comboboxes are 38px with
  their own caption above, because a 22px box labelled `risk` in 9pt grey is a
  puzzle before it is a setting.

The colours stay recognisably SONAR — blue is up, warm red is down, gold is
notable — but lifted off the floor. Blue/red rather than green/red is deliberate
and predates this: it survives the common colour-vision deficiencies.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# --- surfaces --------------------------------------------------------------- #
BG = QColor("#12171f")
PANEL = QColor("#1a212c")
PANEL_HI = QColor("#202936")     # hover, and controls that sit on a panel
BORDER = QColor("#2b3746")
GRID = QColor("#222c3a")

# --- text ------------------------------------------------------------------- #
# Measured against PANEL: INK 13.4:1, MUTED 6.4:1, FAINT 4.6:1. The old values
# were 11.8, 4.1 and 1.9 — the last of which was decorative, not legible.
INK = QColor("#edf2f7")
MUTED = QColor("#b0bdca")
FAINT = QColor("#8494a3")

# --- meaning ---------------------------------------------------------------- #
UP = QColor("#5cb0ff")
DOWN = QColor("#ff8873")
GOLD = QColor("#f3c862")
VIOLET = QColor("#c9aeff")
GREEN = QColor("#86e39a")

#: Confidence component colours, matching the scanner legend.
COMP = {
    "edge": GREEN,
    "liquidity": UP,
    "timing": GOLD,
    "momentum": VIOLET,
    "news": QColor("#ffab7d"),
    "volatility": DOWN,
    "catalyst": GREEN,
    # macro regime components
    "curve": GREEN,
    "policy": UP,
    "labour": VIOLET,
}

REGIME = {
    "risk-on": GREEN,
    "transitional": GOLD,
    "risk-off": DOWN,
    "unknown": MUTED,
}

#: The interface face. macOS resolves this to whatever the system font is, which
#: is the point — it is the one face the reader already reads everything else in.
_UI = ".AppleSystemUIFont"


def text(size: int = 12, bold: bool = False) -> QFont:
    """Words. Anything a person reads as language."""
    f = QFont(_UI)
    f.setPointSize(size)
    f.setBold(bold)
    return f


def figure(size: int = 11, bold: bool = False) -> QFont:
    """Numbers, in the same face as the words but with fixed-width digits.

    Proportional digits wander: a column of prices drawn in the interface font
    does not line up, and a board that does not line up is read one cell at a
    time instead of at a glance. `tnum` is an OpenType feature the system font
    carries, so this costs nothing and changes no other glyph.
    """
    f = text(size, bold)
    try:
        f.setFeature(QFont.Tag("tnum"), 1)
    except (AttributeError, TypeError):
        pass          # older Qt: proportional digits, still legible
    return f


def code(size: int = 11, bold: bool = False) -> QFont:
    """Actual monospace, for actual monospace content — a pasted odds table,
    where the columns are made of spaces. Menlo ships with every macOS; asking
    for "SF Mono" first costs a ~200ms font-alias sweep at startup."""
    f = QFont("Menlo")
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
QLabel#h1 {{ font-size: 17px; font-weight: 700; letter-spacing: 3px; }}
QLabel#muted {{ color: {MUTED.name()}; }}
QLabel#faint {{ color: {FAINT.name()}; }}
/* Every widget inherits the window background from the rule above, including
   labels and the plain QWidgets used as layout holders — so each one paints a
   BG-coloured rectangle over whatever panel it sits on. That was invisible
   while BG and PANEL were three points apart on the same near-black; raising
   the contrast made every cell on the Assets board a dark box. Text and
   holders have no business painting a background, so they stop. */
QLabel {{ background: transparent; }}
QWidget#cell {{ background: transparent; }}
QFrame#panel {{
    background: {PANEL.name()};
    border: 1px solid {BORDER.name()};
    border-radius: 10px;
}}
QFrame#banner {{
    background: rgba(92, 176, 255, 24);
    border: 1px solid rgba(92, 176, 255, 76);
    border-radius: 11px;
}}
QTabWidget::pane {{ border: none; }}

/* --- controls ---------------------------------------------------------- */
/* Two sizes on purpose. The toolbar's two knobs — risk and horizon — are the
   settings every screen depends on and the ones that were hardest to see, so
   they are 38px with a caption of their own (#toolbar below). A form field
   inside a tab stays compact: the Playmaker and Lab forms stack six or seven
   of them, and at 38px each the window no longer fits a 13" laptop, which is
   a real constraint this project keeps a test on. */
QComboBox {{
    background: {PANEL_HI.name()}; border: 1px solid {BORDER.name()};
    border-radius: 8px; padding: 0 10px; min-height: 26px; min-width: 150px;
    color: {INK.name()};
}}
QComboBox#toolbar {{
    border-radius: 9px; padding: 0 12px; min-height: 36px; min-width: 216px;
}}
QComboBox:hover {{ border-color: {UP.name()}; }}
QComboBox:focus {{ border-color: {UP.name()}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox QAbstractItemView {{
    background: {PANEL.name()}; border: 1px solid {BORDER.name()};
    border-radius: 9px; padding: 4px;
    selection-background-color: {PANEL_HI.name()};
    selection-color: {INK.name()};
    outline: none;
}}
QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 0 8px; }}
QSpinBox {{
    background: {PANEL_HI.name()}; border: 1px solid {BORDER.name()};
    border-radius: 8px; padding: 0 7px; min-height: 24px; color: {INK.name()};
}}
QLineEdit {{
    background: {PANEL_HI.name()}; border: 1px solid {BORDER.name()};
    border-radius: 8px; padding: 0 10px; min-height: 26px; color: {INK.name()};
}}
QLineEdit:focus {{ border-color: {UP.name()}; }}
QCheckBox {{ color: {MUTED.name()}; spacing: 8px; }}
QPushButton {{
    background: {PANEL_HI.name()}; border: 1px solid {BORDER.name()};
    border-radius: 8px; padding: 5px 14px; color: {INK.name()};
}}
QPushButton:hover {{ border-color: {UP.name()}; }}
QPushButton:disabled {{ color: {FAINT.name()}; border-color: {BORDER.name()}; }}
QPushButton#row {{ padding: 3px 6px; border-radius: 7px; }}
QPushButton#chip {{
    padding: 5px 12px; border-radius: 999px; color: {INK.name()};
    background: {PANEL_HI.name()};
}}
QPushButton#primary {{
    background: rgba(92, 176, 255, 36);
    border-color: rgba(92, 176, 255, 128); color: #d3e9ff; font-weight: 600;
}}

/* --- lists, scrollers, tables ------------------------------------------ */
QListWidget {{
    background: {BG.name()}; border: none; outline: none;
}}
QListWidget::item {{ padding: 5px 8px; border-radius: 7px; color: {MUTED.name()}; }}
QListWidget::item:selected {{ background: {PANEL_HI.name()}; color: {INK.name()}; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {BORDER.name()}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {FAINT.name()}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QHeaderView::section {{
    background: {BG.name()}; color: {MUTED.name()};
    border: none; border-bottom: 1px solid {BORDER.name()}; padding: 6px;
}}
QTableWidget {{ gridline-color: {GRID.name()}; border: none; }}
QTextBrowser {{ background: {BG.name()}; border: none; }}
QToolTip {{
    background: {PANEL.name()}; color: {INK.name()};
    border: 1px solid {BORDER.name()}; padding: 7px;
}}
"""
