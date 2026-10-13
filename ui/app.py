"""The SONAR window.

Four tabs over one shared :class:`sonar.core.Live`:

    Terminal   the hourly BTC paper trade — signal, lattice, book, equity curve
    Assets     the real-asset screen, with buy/short and a plan per row
    Wire       the newswire, the scheduled calendar, and what it suggests
    Book       open paper positions, plus the calibration that grades the score
    Macro      the regime, which only matters at long horizons

The Polymarket board that used to sit here is gone. Mirroring a market's own
odds back at you is not analysis — there is no independent model for an
election or a Fed decision, so every row was just repeating the crowd. The one
part that *did* have a model, the hourly crypto up/down market, lives on the
Terminal where it always did.

The shell is the **Cockpit** (2026-09-29): a left rail carries the
destinations (both names each — see ``ui/tabs.py``), the wordmark, the wording
switch and the status line, and collapses to icons below
``RAIL_COLLAPSE_BELOW``; a page header names the current screen and keeps the
two knobs that shape everything visible everywhere: **risk** (how much you
stake, and what is worth showing) and **horizon** (when you want it to
resolve). Neither touches a confidence score — see ``sonar/risk.py`` for why
that boundary is load-bearing.
"""

from __future__ import annotations

import calendar
import html
import math
import os
import statistics
import sys
import time

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow,
                               QPlainTextEdit, QPushButton, QScrollArea,
                               QSizePolicy, QSpinBox, QTextBrowser,
                               QVBoxLayout, QWidget)
from shiboken6 import isValid

from sonar import calibration as calibration_mod
from sonar import horizon as hz_mod
from sonar import paths, playmaker, risk as risk_mod
from sonar import scoring as scoring_mod
from sonar import version as version_mod
from sonar.playmaker import devig as pm_devig, staking as pm_staking
from sonar.core import Live
from sonar.llm import _clean
from sonar import assets as asset_mod
from sonar import news as news_mod
from sonar import venues
from sonar.portfolio import PENDING
from sonar.assets import _W as ASSET_W

from . import learn as learn_mod
from . import theme
from . import words
from .charts import (AccountCurve, ComponentBar, DepthChart, EquityCurve,
                     HourBar, Lattice, PositionChart, PositionTiles, Sparkline)
from .tabs import PlainTabs
from .worker import (BacktestThread, ConfigThread, PollThread, PropThread,
                     ReadThread, SportsMeasureThread)

REFRESH_MS = 1000
#: The status line's hold clock (a seam for tests; monotonic, not wall time).
_now = time.monotonic
# Opening size, before the screen gets a say. See MainWindow._fit_to_screen.
# Wider than a 13" laptop on purpose: on a screen that has the room, the rail
# opens with its names showing; _fit_to_screen clamps it on one that does not,
# and the rail collapses to icons there (RAIL_COLLAPSE_BELOW).
PREFERRED_SIZE = (1440, 850)
SCREEN_MARGIN = 40           # leave the dock and the menu bar somewhere to live

# Below this window width the rail shows icons alone. The Screener's columns
# need ~1200pt before the rail takes a single point, so on the tested 1280×775
# minimum the full rail would crowd the board it navigates to. The expanded
# window's *minimum* must stay below this number — the fold triggers while the
# user drags the window narrower, and Qt stops a drag at the layout minimum,
# so a threshold under the minimum would be unreachable. test_layout holds it.
RAIL_COLLAPSE_BELOW = 1420

# Long enough for macOS to finish collapsing the full-screen Space before the
# window disappears into the menu bar. Shorter and the empty Space survives —
# and, reported twice now, the hide itself is dropped: AppKit ignores a hide
# aimed at a window that is still animating out of its Space, while Qt records
# it as hidden anyway. The window stays on screen, painting nothing, and every
# later close is a no-op because Qt believes there is nothing left to hide.
# 350ms was measured against the animation, not the drop; the exit animation
# alone runs ~0.55s on an idle machine and longer under load.
# It has to be a timer: Qt raises WindowStateChange when showNormal() is
# *called* — measured at 1ms after, with the animation still to come — and
# reports the restored geometry just as early, so nothing in Qt says when the
# transition has finished.
FULLSCREEN_EXIT_MS = 900

# A hide that did not reach the screen is retried this often, this far apart.
# `_confirm_hidden` asks the platform window whether it is still exposed, which
# is the one thing that disagrees with Qt when AppKit has dropped the hide.
HIDE_CONFIRM_MS = 250
HIDE_CONFIRM_TRIES = 6

# How long after hiding itself the window refuses to be reopened by an
# app-activation event. Leaving macOS full screen animates a Space transition
# and the app is re-activated when it finishes — *after* the deferred hide has
# run. The Dock-click handler in main.py then faithfully reopens the window the
# user just closed, which looks exactly like a close button that does nothing.
# A real Dock click a second later still works.
REOPEN_GRACE_MS = 1200

# The Assets board's columns: key, (plain heading, expert heading), width, docs
# anchor, tooltip. Widths and order are the same in both wordings — see
# `ui/words.py` for why the switch changes only the vocabulary. The
# header row and every row are built from this one list, so a column can never
# drift away from the heading that names it.
#
# The headings are English rather than abbreviations, which is the whole point
# of the Plain Language direction: MOM, VOL, R:R, P(PROF) and CONF are five
# pieces of jargon in a row, and a reader who does not already know them has no
# way in — the explanations existed only in hover text, which cannot be found by
# someone who does not know there is something to hover. Each heading whose
# meaning is not self-evident carries the anchor of the section that explains
# it, and clicking the heading opens the Learn tab there.
ASSET_COLS = [
    ("name", ("What it is", ""), 208, "", ""),
    ("trend", ("Trend", "TREND"), 58, "",
     "The price path over the window in the next column."),
    ("price", ("Price", "PRICE"), 76, "", "The latest price fetched for this market."),
    ("1d", ("Today", "1D"), 68, "", "How far it has moved since yesterday's close."),
    ("momentum", ("Recent move", "MOM"), 92, "scores",
     "How far it has moved over the window the horizon picks — five days on\n"
     "'This week'. A description of the past. Whether it says anything about\n"
     "the future is exactly what §11 tested, and the answer was no."),
    ("volatility", ("Swing size", "VOL"), 74, "learn",
     "How much this market typically moves in a day.\n"
     "Big swings mean bigger moves in BOTH directions — it says nothing\n"
     "about which way. It is why a target 5% away means something different\n"
     "on gold than on a meme coin."),
    ("lean", ("In the news", "NEWS"), 78, "learn",
     "How unusual today's coverage is: Quiet / Normal / Elevated / Spike.\n"
     "A flag for 'something is happening', not odds and not a direction.\n"
     "Over 25,504 historical setups neither a big move nor a news spike beat\n"
     "the 40% baseline (spike came in at +0.8 points, give or take 3.1)."),
    ("plan", ("If you traded it", "R:R · P(PROF)"), 106, "scores",
     "The plan behind the buy and short buttons: a target and a stop, both\n"
     "scaled to how much this market actually moves.\n"
     "The two numbers are the same number twice — the chance of hitting the\n"
     "target before the stop is 1/(1+reward:risk), so a fatter reward buys a\n"
     "lower hit rate and the two cancel exactly. Nothing here makes money;\n"
     "only a measured edge does, and none has been measured yet."),
    ("conf", ("Worth a look", "CONF"), 80, "scores",
     "0–100: how notable this looks right now.\n"
     "NOT the chance you will make money — that is the column to the left.\n"
     "The bar underneath splits the score into what produced it."),
    ("age", ("Updated", "AGE"), 72, "",
     "How long ago this row's price was actually fetched.\n"
     "The board recomputes about every 3 minutes, but only the 26 stalest of\n"
     "129 markets are refetched each time — so a few minutes old is normal,\n"
     "and a full rotation takes roughly 15. Gold past that means the rotation\n"
     "is falling behind, usually because the source is throttling us.\n"
     "Shown because a price that is quietly out of date is the one failure\n"
     "this app treats as unacceptable."),
    ("actions", ("", ""), 138, "", ""),
]

# Age thresholds, in seconds, derived from the rotation rather than picked:
# `assets.ROLL_BATCH` rows of `assets.WATCHLIST` are refetched per scan, so a
# full pass takes ceil(129/26) = 5 scans of ~3 minutes each. Anything inside
# that is the design working; past it the fetch is losing ground.
AGE_WARN_S = 20 * 60
AGE_BAD_S = 60 * 60


def _age_text(seconds: float, plain: bool | None = None) -> str:
    """A compact age. Never rounds down to "0m" — a row is never brand new
    enough for that to be true, and "0m" reads as "live" when it is not."""
    plain = words.plain() if plain is None else plain
    ago = " ago" if plain else ""
    if seconds < 60:
        return "under 1m" if plain else "<1m"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m{ago}"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{ago}" if hours < 10 else f"{hours}h{ago}"


def _age_color(seconds: float):
    if seconds >= AGE_BAD_S:
        return theme.DOWN
    if seconds >= AGE_WARN_S:
        return theme.GOLD
    return theme.MUTED


def _swing_words(daily_vol: float) -> str:
    """The same number in words. 4.3% a day means nothing to most people; "big
    swings" does, and the number is right there for anyone it does mean
    something to."""
    if daily_vol >= 0.030:
        return "big swings"
    if daily_vol >= 0.015:
        return "medium"
    return "small swings"


def _plain_read(a: dict) -> str:
    """One short phrase saying what this row is doing, in words.

    Everything in it is already on the row as a number. That is the point: the
    numbers are the evidence, this is the reading, and a reader who cannot yet
    do the second from the first is exactly who this app kept losing.

    Deliberately free of direction. "Down hard" is the past tense and says
    nothing about tomorrow — five studies over 116,563 asset-days found no way
    to tell — and a sentence that implied otherwise would be the app breaking
    its own rule in the friendliest possible voice.
    """
    move = a.get("momentum", 0.0)
    size = abs(move)
    if size >= 0.10:
        pace = "up hard" if move > 0 else "down hard"
    elif size >= 0.03:
        pace = "drifting up" if move > 0 else "slipping"
    else:
        pace = "barely moving"
    cover = {"Spike": "heavy news", "Elevated": "some news",
             "Normal": "quiet news", "Quiet": "no news"}.get(a.get("lean", ""), "")
    return f"{pace}, {cover}" if cover else pace


def _asset_widths() -> list[tuple[str, int]]:
    return [(key, width) for key, _names, width, _anchor, _tip in ASSET_COLS]


class HelpHeading(QLabel):
    """A column heading that opens the paragraph explaining its column.

    Hover text was the only explanation this board had, and hover text cannot
    be found by someone who does not already know there is something to find.
    A heading you can click can be — so the ones that carry an explanation are
    drawn in the link colour, take the pointing-hand cursor, and say so in the
    tooltip they already had.
    """

    def __init__(self, names: tuple[str, str], anchor: str, tip: str, on_help,
                 parent=None) -> None:
        super().__init__(words.pick(names), parent)
        self._names = names
        self._anchor = anchor
        self._on_help = on_help
        self.setFont(theme.text(9, bool(anchor)))
        self.setStyleSheet(
            f"color: {(theme.UP if anchor else theme.MUTED).name()};")
        if anchor:
            self.setCursor(Qt.PointingHandCursor)
            tip = f"Click to open the explanation.\n\n{tip}" if tip else \
                "Click to open the explanation."
        if tip:
            self.setToolTip(tip)

    def retitle(self) -> None:
        """Re-read the wording. Cheaper and less fragile than rebuilding the
        header, which would have to be re-inserted into a layout that also
        holds the scroll area."""
        self.setText(words.pick(self._names))

    def mousePressEvent(self, event) -> None:
        if self._anchor:
            self._on_help(self._anchor)
        super().mousePressEvent(event)


class AssetHeader(QFrame):
    """Column headings for the Assets board.

    Without these the screen was ten unlabelled numbers per row and you had to
    already know the layout to read it. With the Plain Language direction they
    are also the way in: each one that names something non-obvious is a link
    into the manual.
    """

    def __init__(self, on_help=None, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        # left margin = the scroll area's own 2px + the row panel's 12px + its
        # 1px border, so a heading sits directly over its column
        lay.setContentsMargins(15, 8, 12, 4)
        lay.setSpacing(12)
        for _key, names, width, anchor, tip in ASSET_COLS:
            lb = HelpHeading(names, anchor if on_help else "", tip,
                             on_help or (lambda _a: None))
            lb.setFixedWidth(width)
            lay.addWidget(lb)

    def retitle(self) -> None:
        for head in self.findChildren(HelpHeading):
            head.retitle()


def _scrolled(inner: QWidget) -> QScrollArea:
    """Put a tall tab inside a scroller so it stops being a floor.

    A QTabWidget's minimum height is its tallest page's, and the window's is the
    tab widget's — so the Lab's form-plus-output and Playmaker's four rows of
    controls between them decided how short SONAR could be made. That was
    survivable while everything was drawn in 9pt monospace; the interface font
    is taller, and `tests/test_layout.py` holds the window to a 13" laptop for a
    reason (it once opened 4,540pt wide on a 1,280pt screen).

    A scroller reports a small minimum and lets the content be whatever height
    it is, which is the right answer rather than a workaround: these two tabs
    are genuinely longer than a short screen.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(inner)
    return area


def panel() -> QFrame:
    f = QFrame()
    f.setObjectName("panel")
    return f


def _vline() -> QFrame:
    """A hairline between groups in a strip. Styled directly: a bare QFrame
    inherits the blanket QWidget background, which is invisible against a
    panel until the day it is not."""
    f = QFrame()
    f.setFixedWidth(1)
    f.setStyleSheet(f"background: {theme.BORDER.name()};")
    return f


def _hline() -> QFrame:
    """The horizontal twin of `_vline`: a hairline between two blocks of one
    panel, styled directly for the same reason."""
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {theme.BORDER.name()};")
    return f


def label(text: str = "", obj: str = "", font=None, align=None,
          wrap: bool = False) -> QLabel:
    """A themed QLabel.

    ``wrap`` matters more than it looks. A QLabel that does not wrap reports a
    sizeHint as wide as its text is long, and a layout cannot shrink below its
    children's minimums — so one unwrapped paragraph sets the minimum width of
    its tab, and the widest tab sets the minimum width of the whole window.
    Three of them once forced SONAR to open 4,540pt wide on a 1,280pt screen.

    Plain text by default: labels show feed, holder and exception text, and
    Qt's AutoText would draw any of it that looks like markup. A label meant
    for markup opts in with ``setTextFormat(Qt.RichText)``.
    """
    lb = QLabel(text)
    lb.setTextFormat(Qt.PlainText)
    lb.setWordWrap(wrap)
    if obj:
        lb.setObjectName(obj)
    if font:
        lb.setFont(font)
    if align:
        lb.setAlignment(align)
    return lb


class VersionBadge(QLabel):
    """``v2.100``, with the build stamp and staleness on hover.

    The text is fixed for the life of the window — a running app cannot change
    which build it is — but *staleness* is not: the checkout moves underneath it
    while the app stays open, which is exactly the situation that makes someone
    ask whether what they are looking at is current. So the tooltip is rebuilt
    on hover rather than frozen at construction.

    Hover is also the right place to pay for it. `version.tooltip()` shells out
    to git, which is ~30ms; that is nothing during a deliberate pause over a
    label and would be an odd thing to spend on every repaint.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(version_mod.version_string(), parent)
        self.setObjectName("muted")
        self.setFont(theme.figure(9))
        self.setToolTip(version_mod.tooltip())

    def enterEvent(self, e) -> None:       # noqa: D102
        self.setToolTip(version_mod.tooltip())
        super().enterEvent(e)


#: Stat strips are built from the key the value is stored under, which is how
#: five of them stayed in sync for free and also how "TAU" ended up on screen.
#: A key that is jargon gets an English caption here, once, for every strip.
STAT_WORDS = {
    "model": "our odds it rises",
    "market": "crowd's odds",
    "edge": "we disagree by",
    "tau": "hour remaining",
    "bankroll": "model's practice cash",
    "pnl": "model's profit / loss",
    "trades": "model's trades",
    "total p/l": "profit / loss",
    "equity": "account value",
    "unrealised": "open profit / loss",
    "p&l now": "profit / loss now",
    "at risk": "if every stop hits",
    "closed": "closed so far",
    "win rate": "how often it won",
    "profile": "risk setting",
    # Sports (Playmaker). "edge" is deliberately not used: a gap between two
    # bookmakers is a disagreement, not an advantage (UX U-13).
    "margin": "bookmaker's cut",
    "fair": "chance without the cut",
    "book spread": "how much books disagree",
    "best edge": "biggest price gap",
    "EV / unit": "expected per 1 staked",
    "stake": "bet size the formula allows",
    # Macro.
    "10y": "US 10-year borrowing rate",
    "curve": "long rate minus short rate",
    "fed funds": "US central-bank rate",
    "VIX": "expected market swings",
    "real 10y": "10-year rate after inflation",
    "CPI y/y": "prices vs a year ago",
    "unemployment": "people out of work",
}

#: Control labels with jargon in them, as (plain, expert). The expert wording
#: keeps the term; plain says what the control does (audit UX U-7).
CONTROL_WORDS = {
    "read_btn": ("AI commentary on this hour", "LLM read on this hour"),
    "protocol_box": ("test the score automatically", "protocol mode"),
    "lab_news": ("also count how much attention each name gets "
                 "(one extra request per symbol)",
                 "include attention (one extra request per symbol)"),
    "lab_catalyst": ("also count earnings dates (US shares, from SEC filings)",
                     "include earnings history (US equities, via EDGAR)"),
}

#: One line under each Practice control, plain wording only: the expert reader
#: has the control's own name, the plain reader needs to be told what it does.
PRACTICE_CAPTIONS = {
    "horizon": "How many days a trade is given to reach its target or stop.",
    "step": "Start a new test trade every this many daily bars. Bigger is "
            "faster, with fewer trades.",
}

#: The attribution table, as (plain, expert) for each heading and verdict.
ATTRIBUTION_HEADS = {
    "component": ("component", "component"),
    "weight": ("weight", "weight"),
    "ic": ("ranking skill (IC)", "IC"),
    "spread": ("best fifth − worst fifth", "top−bottom"),
    "blend": ("score without it", "blend without it"),
    "verdict": ("verdict", "verdict"),
}
ATTRIBUTION_VERDICTS = {
    "KEEP": "keep", "WEAK": "weak", "DROP": "drop", "INVERTED": "backwards",
    "UNCLEAR": "unclear", "not judged": "not judged",
}

#: The time-stop shadow of the score grade (docs/specs/shadow-time-stop.md,
#: Design D6), as (plain, expert). "Promised" and "advertised" stay with the
#: row P(profit). "edge" appears only in the reference phrase "what no edge
#: would give" (and its band form "no edge @σ̂"), in the reference's condition
#: "with no edge, exact fills and randomly wandering prices", and in negations
#: ("not a trading edge", "not a tradeable edge"). tests/test_shadow_ui.py
#: EDGE_ALLOWED lists exactly these. Both modes keep the same rows in order.
_SH_TIP = ("A second grade, beside the one above, which counts only closed positions. "
           "Here every protocol entry gets a result a fixed time after it opened (4 weeks "
           "on the week profile): at the target, at the stop, or at that day's close if it "
           "reached neither. Slow entries count too. It is tested only at three looks fixed "
           "in advance: the first 45, 101 and 201 entries.")
SHADOW_WORDS = {
    "SH_HEAD": ("EVERY ENTRY, GRADED AT A FIXED DATE", "TIME-STOP SHADOW"),
    "SH_TIP": (_SH_TIP, _SH_TIP),
    "SH_COUNT": ("{reached} of {entered} at {T}", "{reached}/{entered} past T"),
    "SH_ROW_WINDOW": ("the {n} with a result opened {first} to {last}",
                      "{n} graded: opened {first} to {last}"),
    "SH_ROW_WINDOW_NONE": ("entries opened {first} to {last} (none has a result yet)",
                           "opened {first} to {last} (none graded yet)"),
    "SH_ROW_WINDOW_UNDATED": ("({k} with no readable date)", "({k} undated)"),
    "SH_NOT_AVAILABLE": (
        "Not available from the running agent. It is an older version than this window.",
        "Not available from the running agent (older version)."),
    "SH_LOADING": ("Working it out: this needs a scan and a few daily closes.",
                   "Computing: waits for a scan and daily closes."),
    "SH_ERROR": ("Could not work it out this time ({reason}). Nothing is guessed; the next "
                 "scan tries again.",
                 "Error: {reason}. Nothing guessed; retried next scan."),
    "SH_EMPTY": ("Not a test yet: there are no protocol entries. Protocol mode on My trades "
                 "makes them.",
                 "Not a test yet: no protocol entries."),
    "SH_NONE_AT_T": ("Not a test yet. None of the {entered} entries has had {T} yet; the "
                     "first gets there on {next_t}.",
                     "Not a test yet. 0/{entered} past T; first on {next_t}."),
    "SH_BEFORE_LOOK": ("Not a test yet. {have} of the first {N} entries have a result; the "
                       "{ordinal} look is on or after {due}.",
                       "Not a test yet. {have}/{N} graded for look {k}; due on or after "
                       "{due}."),
    "SH_BEFORE_LOOK_UNDATED": ("Not a test yet. {have} of the first {N} entries have a "
                               "result; {missing} of them are not entered yet.",
                               "Not a test yet. {have}/{N} graded for look {k}; {missing} "
                               "not yet entered."),
    "SH_LOOK_WAITING_PRICE": ("Not a test yet. The {ordinal} look is due; {w} of its {N} "
                              "entries are still waiting for a closing price.",
                              "Not a test yet. Look {k} due; {w} of {N} awaiting a final "
                              "close."),
    # {date}: the latest t_T + 28 days among the waiting members. The look can
    # come later: the price attempts may not be used up, or the agent stopped.
    "SH_LOOK_WAITING_UNTIL": ("It waits for them until {date}; any still without a price "
                              "then are left out and the look goes ahead.",
                              "Until {date}, then excluded."),
    # A look is a result only once the ledger holds it (docs/specs/shadow-ledger.md):
    # every result line carries the date it was recorded, first.
    "SH_LOOK_NOT_CROSSED": ("Look {k} of 3, recorded {date}, first {N} entries ({used} with a "
                            "result): no link strong enough to cross the line yet. z = {z}; "
                            "the line is ±2.315.",
                            "Look {k}/3 (rec. {date}), n = {N} ({used} graded): HC3 slope z "
                            "{z}, |z| < 2.315, not crossed."),
    "SH_LOOK_NOT_ROBUST": ("Look {k} of 3, recorded {date}, first {N} entries ({used} with a "
                           "result): z = {z} is past the line, but not in every extreme case "
                           "for the {x} left out. This look does not count as crossed; the "
                           "test goes on.",
                           "Look {k}/3 (rec. {date}), n = {N} ({used} graded): HC3 slope z "
                           "{z}, |z| ≥ 2.315, extremes not; not crossed ({x} excl.)."),
    # Past the line, but the left-out members' barriers are unknown, so no
    # extreme could be worked out (domain r2 P3-3).
    "SH_LOOK_NOT_ROBUST_NA": ("Look {k} of 3, recorded {date}, first {N} entries ({used} "
                              "with a result): z = {z} is past the line, but the {x} left out "
                              "could not be filled in, so it does not count as crossed; the "
                              "test goes on.",
                              "Look {k}/3 (rec. {date}), n = {N} ({used} graded): HC3 slope z "
                              "{z}, |z| ≥ 2.315, extremes n/a; not crossed ({x} excl.)."),
    # After a look that did not count: says what a z past the line could say
    # at most, and that it does not hold here (domain r2 P3-2).
    "SH_CAVEAT_NOT_ROBUST": ("A z past the line would say at most that the score sorted these "
                             "past coin-flip paper entries after {T}; here it does not hold "
                             "once the left-out entries are counted. It does not show that "
                             "trading by score would make money: one test on {used} entries, "
                             "before costs, fees and slippage, with exact fills. It is not a "
                             "trading edge.",
                             "Not robust to the left-out entries; at most ranks past "
                             "random-direction paper outcomes at T; before costs, exact fills; "
                             "not a tradeable edge."),
    "SH_LOOK_UNRECORDED": ("Look {k} of 3: worked out but not recorded yet, so it is not "
                           "shown as a result.",
                           "Look {k}/3: not recorded; no result shown."),
    # The record cannot be used: the look may well be recorded (domain r2 P3-1).
    "SH_LOOK_BLOCKED": ("Look {k} of 3: not shown as a result while the record cannot be used.",
                        "Look {k}/3: record unavailable; no result shown."),
    # Not "z would be ... at the lowest": a point between the fills can lie
    # beyond them (domain r2 P2-1).
    "SH_EXTREMES": ("The {x} left out have no usable result. Filled in at the extremes for "
                    "the score (each at its target or its stop), the lowest z found was {lo} "
                    "and the highest {hi}. These are extreme cases, not estimates and not "
                    "limits.",
                    "{x} excl.: extreme z {lo} / {hi} (not a bound)"),
    "SH_NEXT_LOOK": ("Next look: the first {N2} entries, on or after {due}.",
                     "Next: n = {N2}, due on or after {due}."),
    "SH_NEXT_LOOK_UNDATED": ("Next look: the first {N2} entries, after {missing} more are "
                             "entered.",
                             "Next: n = {N2}, {missing} not yet entered."),
    "SH_LOOK_CROSSED_UP": ("Look {k} of 3, recorded {date}, first {N} entries ({used} with "
                           "a result): crossed the line. On these paper entries, higher "
                           "scores went with higher R on average. z = {z}; the line is "
                           "±2.315. The test ends here.",
                           "Look {k}/3 (rec. {date}), n = {N} ({used} graded): HC3 slope z "
                           "{z}, |z| ≥ 2.315, crossed. Design closed."),
    "SH_LOOK_CROSSED_DOWN": ("Look {k} of 3, recorded {date}, first {N} entries ({used} "
                             "with a result): crossed the line. On these paper entries, "
                             "higher scores went with lower R on average. z = {z}; the line "
                             "is ±2.315. The test ends here.",
                             "Look {k}/3 (rec. {date}), n = {N} ({used} graded): HC3 slope z "
                             "{z}, |z| ≥ 2.315, crossed. Design closed."),
    "SH_CAVEAT_CROSSED": ("This says only that the score sorted how these past coin-flip "
                          "paper entries ended after {T}. It does not show that trading "
                          "by score would make money: it is one test on {used} entries, "
                          "before costs, fees and slippage, with exact fills, and a test "
                          "like this can cross by chance even when there is no link. It is "
                          "not a trading edge.",
                          "Ranks past random-direction paper outcomes at T only; before "
                          "costs, exact fills, one test with a by-design false-alarm rate; "
                          "not a tradeable edge."),
    "SH_FINAL_NONE": ("Three looks, no crossing: no evidence that the score ranks {T_adj} "
                      "results, at the planned size. The test is finished.",
                      "Looks 1-3 not crossed: no evidence that the score ranks {T_adj} "
                      "results, at the planned size. Design closed."),
    "SH_ROW_SPLIT": ("{reached} with a result: {t} at the target ({tp}%) · {s} at the stop "
                     "({sp}%) · {x} at neither, valued at the close after {T} ({xp}%)",
                     "{reached} graded: target {t} ({tp}%) · stop {s} ({sp}%) · time {x} "
                     "({xp}%)"),
    "SH_ROW_WAITING": ("still waiting: {w} not yet at {T} (the next on {next_t}) · {wp} "
                       "waiting for a closing price",
                       "waiting: {w} before T (next {next_t}) · {wp} awaiting a final "
                       "close"),
    "SH_ROW_REF": ("what no edge would give after {T}, if the volatility estimate was right: "
                   "about {a}% at the target · {b}% at the stop · {c}% at neither. A "
                   "different split can mean the volatility estimate was off. With no "
                   "edge, exact fills and randomly wandering prices, the average result "
                   "would be about 0R.",
                   "what no edge would give at planned σ: {a}% / {b}% / {c}% (a σ̂ check); "
                   "mean ≈0R at any σ (exact fills)"),
    "SH_ROW_RUNNING": ("running, not a test: paper average {m}R (95% range for the average "
                       "{lo} to {hi}R) · link z = {z} · before costs; an average above 0 "
                       "here is not a trading edge",
                       "running, not a test: mean R {m} [{lo}, {hi}] · HC3 slope z {z} · "
                       "pre-cost; mean > 0 is not a tradeable edge"),
    "SH_ROW_RUNNING_WAIT": ("running figures start at 20 results; {k} to go",
                            "running stats from n = 20; {k} to go"),
    "SH_ROW_IC": ("for comparison only, not a test: rank correlation {ic} on these entries "
                  "at {T}, {icc} on the closed ones alone",
                  "descriptive only: rank IC {ic} (all at T) vs {icc} (closed only)"),
    "SH_ROW_PAST_LOOK": ("look {k}, first {N}: z = {z}, did not cross the line",
                         "look {k}, n = {N}: z {z}, not crossed"),
    "SH_ROW_PAST_LOOK_NOT_ROBUST": ("look {k}, first {N}: z = {z}, past the line but not in "
                                    "every extreme case; not crossed",
                                    "look {k}, n = {N}: z {z}, extremes not; not crossed"),
    "SH_ROW_PAST_LOOK_NA": ("look {k}, first {N}: z = {z}, past the line but the left-out "
                            "entries could not be filled in; not crossed",
                            "look {k}, n = {N}: z {z}, extremes n/a; not crossed"),
    "SH_ROW_LEFT_OUT": ("left out and counted: {m} chosen by hand · {l} closed by hand "
                        "before {T} · {p} with no closing price · {r} whose stop was at or "
                        "past the fill price (no R can be worked out)",
                        "excluded: {m} non-protocol · {l} hand-closed before T · {p} no "
                        "price · {r} risk ≤ 0"),
    "SH_ROW_GAP": ("{g} counted at the target or stop price because a daily close went past "
                   "it between checks (a real fill could have been different, often worse at a stop)",
                   "{g} gap exits, filled at the barrier, not the close beyond it"),
    "SH_ROW_BAND": ("scores {lo}-{hi}: {n} with a result · {t} target · {s} stop · {x} "
                    "neither · what no edge would give if the volatility estimate was right: "
                    "{a}% / {b}% / {c}%",
                    "score {lo}-{hi}  n={n}  T/S/N {t}/{s}/{x}  no edge @σ̂ {a}/{b}/{c}%"),
    "SH_WARN": ("Note: {x} of the first {N} entries were left out ({pct}%). This look rests "
                "on the other {used}.",
                "Note: {x}/{N} excluded ({pct}%) at look {k}."),
    "SH_NOTE": ("R is the result in units of the amount risked: -1R lost the amount risked, "
                "+{rr}R reached the target. This grade asks only whether the score sorts "
                "how coin-flip entries end after {T}. These are paper entries with a random "
                "direction, before costs, fees and slippage. Even a crossed line is not a "
                "trading edge and says nothing about how future entries end.",
                "R = result / initial risk. Ranks random-direction outcomes at T only; not "
                "a tradeable edge. Paper; before costs, fees and slippage; exact fills."),
    "SH_WORKED_OUT": ("Worked out {when}.", "As of {when}."),
    "SH_STALE": ("Not updated for {h} hours: the agent may be stopped.", "Stale: {h} h old."),
    # The ledger (docs/specs/shadow-ledger.md, Design): the record line, a
    # check that differs, a record that cannot be used, and errata. "Record",
    # not the spec's expert "ledger": the word holds "edge", which U-1 allows
    # only in its EDGE_ALLOWED phrases.
    "SH_RECORD": ("Record kept since {date}.", "Record since {date}."),
    # Retired records in the folder are always disclosed (domain r3 P1-1): a
    # new record after a retirement re-tests the same kind of entries.
    "SH_RECORD_RETIRED_ONE": ("Record kept since {date}. 1 earlier record was retired in this "
                              "folder, on {date0}. Its looks are not counted here, and this "
                              "record re-tests the same kind of entries.",
                              "Record since {date}; 1 retired ({date0})."),
    "SH_RECORD_RETIRED": ("Record kept since {date}. {n} earlier records were retired in this "
                          "folder, the first on {date0}. Their looks are not counted here, and "
                          "this record re-tests the same kind of entries.",
                          "Record since {date}; {n} retired (first {date0})."),
    "SH_MISMATCH": ("Worked out again today, look {k} comes out differently ({why}). As fixed "
                    "in advance, the result recorded on {date} is kept. Either one may rest on "
                    "a data error.",
                    "look {k}: check differs ({why}); recorded {date} kept by design"),
    "SH_WHY_MEMBERS": ("which entries it counts", "members"),
    "SH_WHY_Z": ("the z figure", "z"),
    "SH_MISMATCH_CONSTANTS": ("The test's fixed settings have changed since look {k} was "
                              "recorded on {date}. The recorded result belongs to the old "
                              "settings, and the new ones need their own record.",
                              "look {k}: constants changed since {date}; new settings need a "
                              "new record"),
    "SH_LEDGER_READ": ("The record of results could not be read ({reason}), so it is left "
                       "untouched for a person to check. Nothing new is recorded, and no look "
                       "is shown as a result.",
                       "record unreadable ({reason}); not recording"),
    # LedgerIdError: another book's record, or one with no anchor that this
    # book does not match (code review P1-1; G3: a reset is manual). The
    # steps are the README's; the file's name is not spelled out here, as it
    # holds "edge" (Build note 1).
    "SH_LEDGER_FOREIGN": ("It does not belong to this book, and it is never replaced "
                          "automatically. If the book was reset on purpose, retire the old "
                          "record as the README's reset steps say: rename its file, in the same "
                          "folder, to the retired name with its id. The old record and its "
                          "backups are kept, and a new record starts; it re-tests the same "
                          "kind of entries, and the record line says so.",
                          "not this book's; after a deliberate reset, retire the old record "
                          "(README, reset steps)"),
    # LedgerRetiredError: a copy of a retired record left in its place.
    "SH_LEDGER_RETIRED": ("It is the same record as a retired one in the folder, so it is not "
                          "used again. Retiring moves the file: take this copy away, or, if the "
                          "retirement was a mistake, the retired one.",
                          "a retired record; take this copy away, or undo the retirement"),
    # LedgerBehindError (security P3-3). The newest copy holds every recorded
    # look: one is made right after each look is recorded (code review r2 P2-N1).
    "SH_LEDGER_BEHIND": ("It is an older copy: it holds fewer recorded looks than this book's "
                         "record. Put the newest backup copy in its place: the last one by "
                         "name, here or off-site (on a look's day, the one with .look in its "
                         "name; after a reset, see the README).",
                         "older than this book's record; restore the newest backup copy, last "
                         "by name"),
    # "missing", by the anchor that says a record existed (code review r2
    # P2-N2): the book's marker, or only the folder's sidecar or backups.
    "SH_LEDGER_MISSING": ("The record of results is missing, though this book had one since "
                          "{date}.",
                          "record missing (this book's, since {date})"),
    "SH_LEDGER_MISSING_FOLDER": ("The record of results is missing, though this folder had one "
                                 "since {date}.",
                                 "record missing (this folder's, since {date})"),
    "SH_LEDGER_MISSING_UNDATED": ("The record of results is missing, though backups of it "
                                  "exist.",
                                  "record missing (backups exist)"),
    # Code review r3 P3-1, P3-2: on a look's day two copies carry the date,
    # and after a reset the folder holds two records' copies.
    "SH_LEDGER_RESTORE": ("It is not started again. Put the newest backup copy in its place: the "
                          "last one by name, here or off-site (on a look's day, the one with "
                          ".look in its name; after a reset, see the README).",
                          "restore the newest backup copy, last by name (README)"),
    # Not on the "this book had one" path: the book was not reset, and a
    # retirement is not honoured while its marker names the record (G3,
    # domain r3 P1-1).
    "SH_LEDGER_RESTORE_RETIRE": ("If the book was reset on purpose, retire the old record "
                                 "instead, as the README's reset steps say; it is kept, and a "
                                 "new record starts.",
                                 "after a deliberate reset, retire it (README)"),
    # Refused by the record's own checks (security P2-3): results and looks
    # are counted apart (code review r2 P3-N3).
    # "Written to the record", not "counted but not recorded" (domain r3 P3-1).
    "SH_LEDGER_REFUSED_ONE": ("1 result could not be written to the record: it did not pass the "
                              "record's own checks. It is not in the record, so a look that uses "
                              "it cannot be fully checked against the record.",
                              "1 result refused by the record's checks; not in record"),
    "SH_LEDGER_REFUSED": ("{n} results could not be written to the record: they did not pass the "
                          "record's own checks. They are not in the record, so a look that uses "
                          "them cannot be fully checked against the record.",
                          "{n} results refused by the record's checks; not in record"),
    "SH_LEDGER_REFUSED_LOOK_ONE": ("1 look could not be written to the record: it did not pass "
                                   "the record's own checks, so it is not shown as a result.",
                                   "1 look refused by the record's checks; no result shown"),
    "SH_LEDGER_REFUSED_LOOKS": ("{n} looks could not be written to the record: they did not pass "
                                "the record's own checks, so they are not shown as results.",
                                "{n} looks refused by the record's checks; no result shown"),
    "SH_LEDGER_WRITE": ("The latest results could not be recorded ({reason}); the next pass "
                        "tries again.",
                        "record write failed ({reason}); retrying"),
    # It names the look(s) and the corrected R (domain r2 P2-2).
    "SH_ERRATUM": ("Erratum {date}: a result counted in {where} was later found wrong "
                   "({reason}); {rpart}. As fixed in advance, the recorded look is "
                   "kept, and it may rest on this error.",
                   "erratum {date}, {where}: {reason}; {rpart}; recorded kept"),
    # An erratum may carry no corrected R (domain r3 P3-3).
    "SH_ERRATUM_R": ("corrected R {r}", "R → {r}"),
    "SH_ERRATUM_NO_R": ("it has no usable R", "R → none"),
    "SH_ERRATUM_LOOK": ("look {ks}", "look {ks}"),
    "SH_ERRATUM_LOOKS": ("looks {ks}", "looks {ks}"),
    "SH_ERRATUM_NO_LOOK": ("no recorded look", "no look"),
    # Errata touching a recorded look come first, then the newest (domain r3
    # P3-2); the hidden ones say how many touch a look.
    "SH_ERRATA_MORE": ("{n} more errata are in the record; {m} of them touch a recorded look.",
                       "+{n} errata ({m} on looks)"),
}
#: At most this many errata lines are shown; the rest are counted (security P3-1).
SHADOW_ERRATA_SHOWN = 5
SHADOW_ORDINALS = {1: "first", 2: "second", 3: "third"}
#: A daily-close readout, plus slack: older than this, the note says so.
SHADOW_STALE_H = 26
#: The running line waits for as many results as the existing grade does.
SHADOW_RUNNING_FROM = 20
#: More than this share of a cohort left out, and the look says so.
SHADOW_WARN_SHARE = 0.10


def _px(v: float | None) -> str:
    """A price, to the precision its size wants: two places from 10 up, four
    below it — a currency pair at 1.32 has nothing to say in two."""
    if v is None:
        return "—"
    return f"{v:,.2f}" if abs(v) >= 10 else f"{v:,.4f}"


def _day_text(ts: float | None) -> str:
    return time.strftime("%-d %b", time.localtime(ts)) if ts else "—"


def _band_top(bucket: dict) -> int:
    """A calibration band's printed upper bound. The top band is stored as
    80–101 so a score of exactly 100 falls inside a half-open range; a score
    never exceeds 100, so it reads "80–100" — "101" on screen looks like a bug."""
    return min(bucket["hi"], 100)


#: A score band with this share or more of its entered positions still open is
#: read with a caveat. The book has no time stop, so how long a position takes
#: to close depends on its score, and the closed ones are the quick ones —
#: see docs/audit/calibration-censoring-by-score.md.
CENSORED_SHARE = 0.40


def _open_span(seconds: float) -> str:
    """How long a position has been open, in the unit a book that keeps
    positions for days is read in. Never "0": under an hour says so."""
    if seconds < 3600:
        return "under an hour"
    if seconds < 86400:
        hours = round(seconds / 3600)
        return f"{hours} hour{'' if hours == 1 else 's'}"
    days = round(seconds / 86400, 1)
    return "1 day" if days == 1.0 else f"{days:.1f} days"


def _open_by_band(buckets: list, open_rows: list) -> list:
    """For each calibration band, in order: how many open positions were
    entered on a score inside it, and their median age in seconds (None when
    there are none). Banded as `calibration.buckets` bands the closed ones
    (lo <= score < hi), so a band's closed and open counts describe the same
    set of entries."""
    ages = [[] for _ in buckets]
    now = time.time()
    for row in open_rows:
        if row.get("status") == PENDING:        # accepted, not filled: nothing is entered yet
            continue
        score = row.get("confidence") or 0.0
        age = row.get("age_s")
        if age is None:
            age = now - (row.get("opened_at") or now)
        for i, b in enumerate(buckets):
            if b["lo"] <= score < b["hi"]:
                ages[i].append(float(age))
                break
    return [(len(a), statistics.median(a) if a else None) for a in ages]


def _money(v: float, signed: bool = False, places: int = 2) -> str:
    """``$1,234.56``, or ``+$1,234.56`` / ``-$1,234.56`` when the sign is the
    point — the sign goes before the currency, as a bank statement puts it."""
    body = f"{abs(v):,.{places}f}"
    if signed:
        return ("+$" if v >= 0 else "-$") + body
    return ("-$" if v < 0 else "$") + body


# -- the time-stop shadow of the score grade ------------------------------- #
# Formats for docs/specs/shadow-time-stop.md, Design D3–D4. The dict can come
# from another process (the holder, through /api/book), so every figure is
# formatted here from a number checked to be one, and every label shows plain
# text: nothing in the payload is ever rendered as markup.

def _sh_num(v) -> float | None:
    """A finite number from the shadow dict, or None. A bool is not one."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def _sh_int(v) -> int:
    n = _sh_num(v)
    return int(n) if n is not None else 0


def _sh_pct(v) -> int:
    """A share as a whole percent."""
    return round(100 * (_sh_num(v) or 0.0))


def _sh_t_words(t_days) -> tuple[str, str]:
    """``{T}`` and ``{T_adj}``: "4 weeks" / "4-week" for 28 days, "16 weeks"
    for 112, "5.6 days" otherwise; one readout mixing values of T says
    "4 holding periods" / "fixed-time"."""
    t = _sh_num(t_days)
    if t is None:
        return "4 holding periods", "fixed-time"
    if 7 <= t <= 112 and abs(t / 7 - round(t / 7)) < 1e-9:
        return f"{round(t / 7)} weeks", f"{round(t / 7)}-week"
    return f"{t:g} days", f"{t:g}-day"


#: Timestamps outside this range are not dates SONAR can have written (1970
#: to about 3237). `time.localtime` raises OSError past ~1e17 on macOS, and a
#: holder's payload must never be able to stop the window's refresh.
SHADOW_TS_MAX = 4e10


def _sh_ts(v) -> float | None:
    """A payload timestamp, or None when it is not a plausible date."""
    t = _sh_num(v)
    return t if t is not None and 0 <= t <= SHADOW_TS_MAX else None


def _sh_date(ts, now: float) -> str:
    """``6 Nov``, with the year when it is not this one ("7 Jan 2027")."""
    t = _sh_ts(ts)
    if t is None:
        return "n/a"
    day = time.localtime(t)
    text = time.strftime("%-d %b", day)
    if day.tm_year != time.localtime(now).tm_year:
        text += time.strftime(" %Y", day)
    return text


def _sh_z(z, crossed: bool | None = None) -> str:
    """z, signed, two places. Within 0.01 of the line it takes three, cut
    toward zero, so the figure shown can never contradict the verdict — which
    is reached on the unrounded value."""
    v = _sh_num(z)
    if v is None:
        return "n/a"
    line = calibration_mod.SHADOW_BOUNDARY
    crossed = abs(v) >= line if crossed is None else crossed
    if not 2.305 <= abs(v) < 2.325:
        return f"{v:+.2f}"
    shown = math.floor(abs(v) * 1000) / 1000
    if crossed and shown < line:
        shown = line
    elif not crossed and shown >= line:
        shown = line - 0.001
    return f"{'-' if v < 0 else '+'}{shown:.3f}"


def _sh_r(v) -> str:
    n = _sh_num(v)
    return "n/a" if n is None else f"{n:+.2f}"


def _sh_word(key: str, **kw) -> str:
    return words.pick(SHADOW_WORDS[key]).format(**kw)


def _sh_day(v, now: float) -> str:
    """An ISO day from the ledger (an erratum's date) as :func:`_sh_date`
    shows a timestamp; anything else reads n/a."""
    try:
        t = calendar.timegm(time.strptime(v, "%Y-%m-%d")) + 12 * 3600
    except (TypeError, ValueError, OverflowError):
        return "n/a"
    return _sh_date(t, now)


#: The ledger states in which no look is a result: the record cannot be used.
SHADOW_LEDGER_BLOCKED = ("read", "missing")


def _sh_ledger(d: dict) -> dict:
    led = d.get("ledger")
    return led if isinstance(led, dict) else {}


def _sh_shown(lk: dict, blocked: bool) -> bool:
    """Whether a look is shown as a result: evaluated, and in the ledger.
    A look worked out but not recorded, or any look while the record cannot
    be read or found, is not (S4) — however the payload is labelled."""
    return bool(lk.get("evaluated")) and lk.get("recorded") is True and not blocked


def _sh_parts(key: str, parts: list[tuple[int, dict]]) -> str:
    """A row of "·"-separated parts, each dropped when its count is zero. The
    row's lead-in ("left out and counted: ") stays whichever part is first."""
    pieces = words.pick(SHADOW_WORDS[key]).split(" · ")
    lead, sep, first = pieces[0].partition(": ")
    if sep:
        pieces[0] = first
    shown = [p.format(**kw) for p, (count, kw) in zip(pieces, parts, strict=True) if count]
    if not shown:
        return ""
    return (f"{lead}: " if sep else "") + " · ".join(shown)


def shadow_texts(shadow, detail: bool, now: float, t_default: float) -> dict[str, str]:
    """The text of every line of the shadow block, in the state D3 names.

    ``shadow`` is ``Live.shadow``: None while the holder works it out, the
    "unavailable" string when an older holder sends nothing, else the dict
    from :func:`sonar.calibration.shadow_time_stop`. ``t_default`` is T for
    the protocol's preset, used before any entry carries its own.
    """
    out = {"count": "", "status": "", "rows": "", "warn": "", "note": ""}
    rr = scoring_mod.K_TARGET / scoring_mod.K_STOP
    if not isinstance(shadow, dict):
        T, _adj = _sh_t_words(t_default)
        out["status"] = _sh_word("SH_LOADING" if shadow is None else "SH_NOT_AVAILABLE")
        out["note"] = _sh_word("SH_NOTE", rr=f"{rr:g}", T=T)
        return out

    d = shadow
    status: list[str] = []
    if d.get("error"):
        status.append(_sh_word("SH_ERROR", reason=_clean(d["error"], 80)))
    if "n_entered" not in d:                 # failed before a first readout
        out["status"] = " ".join(status) or _sh_word("SH_LOADING")
        out["note"] = _sh_word("SH_NOTE", rr=f"{rr:g}", T=_sh_t_words(t_default)[0])
        return out

    entered, reached = _sh_int(d.get("n_entered")), _sh_int(d.get("n_reached"))
    T, T_adj = _sh_t_words(d.get("t_days") if entered else t_default)
    rr = _sh_num(d.get("rr")) or rr
    looks = [lk for lk in (d.get("looks") if isinstance(d.get("looks"), list) else [])
             if isinstance(lk, dict)][:len(calibration_mod.SHADOW_LOOKS)]
    n_wait_price, n_no_price = _sh_int(d.get("n_wait_price")), _sh_int(d.get("n_no_price"))
    next_t = _sh_date(d.get("next_t"), now)

    waiting = _sh_parts("SH_ROW_WAITING", [
        (_sh_int(d.get("n_waiting")), {"w": _sh_int(d.get("n_waiting")), "T": T,
                                       "next_t": next_t}),
        (n_wait_price, {"wp": n_wait_price})])
    left_out = _sh_parts("SH_ROW_LEFT_OUT", [
        (_sh_int(d.get("n_nonprotocol")), {"m": _sh_int(d.get("n_nonprotocol"))}),
        (_sh_int(d.get("n_left")), {"l": _sh_int(d.get("n_left")), "T": T}),
        (n_no_price, {"p": n_no_price}),
        (_sh_int(d.get("n_no_risk")), {"r": _sh_int(d.get("n_no_risk"))})])
    gap = (_sh_word("SH_ROW_GAP", g=_sh_int(d.get("n_gap")))
           if _sh_int(d.get("n_gap")) else "")
    rows: list[str] = []
    named = None                    # the look the status sentence is about
    ledger = _sh_ledger(d)
    blocked = ledger.get("error") in SHADOW_LEDGER_BLOCKED

    if entered == 0:
        status.append(_sh_word("SH_EMPTY"))
        rows = [left_out]
    elif reached == 0 and d.get("next_t") is not None and not (n_wait_price or n_no_price):
        status.append(_sh_word("SH_NONE_AT_T", entered=entered, T=T, next_t=next_t))
        rows = [waiting, left_out]
    else:
        line, named = _sh_look_status(looks, now, T, T_adj, blocked)
        status.append(line)
        rows = _sh_rows(d, looks, named, detail, T, waiting, left_out, gap, blocked)

    window = _sh_window(d.get("entries"), now)
    rows = [window] + rows
    out["count"] = (_sh_word("SH_COUNT", reached=reached, entered=entered, T=T)
                    if entered else "")
    out["status"] = " ".join(status)
    out["rows"] = "\n".join(r for r in rows if r)
    out["warn"] = "\n".join(_sh_ledger_lines(d, looks, now, blocked)
                            + _sh_warnings(looks, now, blocked))
    note = _sh_word("SH_NOTE", rr=f"{rr:g}", T=T)
    at = _sh_ts(d.get("computed_at"))
    if at is not None:
        age_h = (now - at) / 3600
        note += " " + (_sh_word("SH_STALE", h=int(age_h)) if age_h > SHADOW_STALE_H else
                       _sh_word("SH_WORKED_OUT",
                                when=time.strftime("%-d %b %H:%M", time.localtime(at))))
    # A restarted record shows (domain P2-6): the date the ledger began.
    if not blocked and _sh_ts(ledger.get("created_at")) is not None:
        date = _sh_date(ledger.get("created_at"), now)
        # Retired records in this folder are always disclosed (domain r3 P1-1).
        n = _sh_int(ledger.get("retired"))
        if n > 0:
            note += " " + _sh_word("SH_RECORD_RETIRED_ONE" if n == 1 else "SH_RECORD_RETIRED",
                                   date=date, n=n,
                                   date0=_sh_date(ledger.get("retired_first"), now))
        else:
            note += " " + _sh_word("SH_RECORD", date=date)
    out["note"] = note
    return out


def _sh_ledger_lines(d: dict, looks: list[dict], now: float, blocked: bool) -> list[str]:
    """The ledger's own lines: why it cannot be used or written, a check that
    differs from the record, and errata. Text from the payload goes through
    `_clean`, as SH_ERROR's reason does."""
    out = []
    ledger = _sh_ledger(d)
    err = ledger.get("error")
    if err == "read":
        line = _sh_word("SH_LEDGER_READ", reason=_clean(ledger.get("reason"), 80))
        extra = {"LedgerIdError": "SH_LEDGER_FOREIGN",
                 "LedgerRetiredError": "SH_LEDGER_RETIRED",
                 "LedgerBehindError": "SH_LEDGER_BEHIND"}.get(ledger.get("reason"))
        out.append(f"{line} {_sh_word(extra)}" if extra else line)
    elif err == "missing":
        # "This book had one" only when the book's own marker says so; the
        # sidecar and the backups belong to the folder (code review r2 P2-N2).
        dated = _sh_ts(ledger.get("created_at")) is not None
        key = ("SH_LEDGER_MISSING_UNDATED" if not dated else
               "SH_LEDGER_MISSING" if ledger.get("reason") == "marker" else
               "SH_LEDGER_MISSING_FOLDER")
        head = _sh_word(key, date=_sh_date(ledger.get("created_at"), now) if dated else "")
        line = f"{head} {_sh_word('SH_LEDGER_RESTORE')}"
        # The book's own marker names the record, so the book was not reset:
        # retiring is not offered, and would not be honoured (G3, domain r3 P1-1).
        if ledger.get("reason") != "marker":
            line += " " + _sh_word("SH_LEDGER_RESTORE_RETIRE")
        out.append(line)
    elif err == "write":
        out.append(_sh_word("SH_LEDGER_WRITE", reason=_clean(ledger.get("reason"), 80)))
    for field, one, many in (("refused", "SH_LEDGER_REFUSED_ONE", "SH_LEDGER_REFUSED"),
                             ("refused_looks", "SH_LEDGER_REFUSED_LOOK_ONE",
                              "SH_LEDGER_REFUSED_LOOKS")):
        n = _sh_int(ledger.get(field))
        if n > 0:
            out.append(_sh_word(one if n == 1 else many, n=n))
    if blocked:
        return out
    # Bounded, whatever the payload holds (security P3-1).
    mismatches = d.get("mismatches") if isinstance(d.get("mismatches"), list) else []
    for mm in mismatches[:len(calibration_mod.SHADOW_LOOKS)]:
        if not isinstance(mm, dict):
            continue
        date = _sh_date(mm.get("recorded_at"), now)
        if mm.get("why") == "constants":
            out.append(_sh_word("SH_MISMATCH_CONSTANTS", k=_sh_int(mm.get("k")), date=date))
        elif mm.get("why") in ("members", "z"):
            why = _sh_word("SH_WHY_MEMBERS" if mm.get("why") == "members" else "SH_WHY_Z")
            out.append(_sh_word("SH_MISMATCH", k=_sh_int(mm.get("k")), why=why, date=date))
    errata = d.get("errata") if isinstance(d.get("errata"), list) else []
    rows = [er for er in errata[:calibration_mod.LEDGER_ERRATA_MAX] if isinstance(er, dict)]

    def looks_of(er) -> list[int]:
        ks = er.get("looks") if isinstance(er.get("looks"), list) else []
        return [_sh_int(k) for k in ks][:len(calibration_mod.SHADOW_LOOKS)]

    # Those touching a recorded look first, then the newest (domain r3 P3-2):
    # the five shown are the ones most likely to matter.
    rows.sort(key=lambda er: er.get("date") if isinstance(er.get("date"), str) else "",
              reverse=True)
    rows.sort(key=lambda er: not looks_of(er))
    for er in rows[:SHADOW_ERRATA_SHOWN]:
        ks = looks_of(er)
        # "1", "1 and 2", "1, 2 and 3" (code review r3 P3-5).
        ks_text = ", ".join(str(k) for k in ks[:-1]) + f" and {ks[-1]}" if len(ks) > 1 else (
            "".join(str(k) for k in ks))
        where = (_sh_word("SH_ERRATUM_NO_LOOK") if not ks else
                 _sh_word("SH_ERRATUM_LOOK" if len(ks) == 1 else "SH_ERRATUM_LOOKS",
                          ks=ks_text))
        r = _sh_num(er.get("r"))
        rpart = (_sh_word("SH_ERRATUM_R", r=_sh_r(r)) if r is not None
                 else _sh_word("SH_ERRATUM_NO_R"))
        out.append(_sh_word("SH_ERRATUM", date=_sh_day(er.get("date"), now),
                            reason=_clean(er.get("reason"), 80), rpart=rpart, where=where))
    hidden = rows[SHADOW_ERRATA_SHOWN:]
    if hidden:
        out.append(_sh_word("SH_ERRATA_MORE", n=len(hidden),
                            m=sum(1 for er in hidden if looks_of(er))))
    return out


def _sh_look_status(looks: list[dict], now: float, T: str, T_adj: str,
                    blocked: bool = False) -> tuple[str, int | None]:
    """The primary sentence once an entry has a result (D3 a3–d), and the look
    it names, if one. Only a recorded look is a result (:func:`_sh_shown`);
    one worked out and not recorded says so, with no z and no crossing."""
    shown = [lk for lk in looks if _sh_shown(lk, blocked)]
    unrecorded = [lk for lk in looks if lk.get("evaluated") and not _sh_shown(lk, blocked)]
    # `is True`: a payload's "no" or 1 is not a crossing (security P3-7).
    crossed = next((lk for lk in shown if lk.get("crossed") is True), None)
    pending = [lk for lk in looks if not lk.get("evaluated") and not lk.get("design_closed")]
    if crossed is not None:
        z = _sh_num(crossed.get("z")) or 0.0
        key = "SH_LOOK_CROSSED_UP" if z > 0 else "SH_LOOK_CROSSED_DOWN"
        used = _sh_int(crossed.get("used"))
        line = (_sh_word(key, k=_sh_int(crossed.get("k")), N=_sh_int(crossed.get("n")),
                         used=used, z=_sh_z(z, True),
                         date=_sh_date(crossed.get("recorded_at"), now))
                + " " + _sh_word("SH_CAVEAT_CROSSED", T=T, used=used))
        return line, _sh_int(crossed.get("k"))
    if looks and len(shown) == len(looks):
        return _sh_word("SH_FINAL_NONE", T_adj=T_adj), None
    due = next((lk for lk in pending if _sh_num(lk.get("due")) is not None
                and now >= _sh_num(lk.get("due"))), None)
    if due is not None:
        k = _sh_int(due.get("k"))
        line = _sh_word("SH_LOOK_WAITING_PRICE", ordinal=SHADOW_ORDINALS.get(k, str(k)),
                        k=k, w=_sh_int(due.get("n_wait_price")) + _sh_int(due.get("n_waiting")),
                        N=_sh_int(due.get("n")))
        if _sh_int(due.get("n_wait_price")) and _sh_ts(due.get("price_until")) is not None:
            line += " " + _sh_word("SH_LOOK_WAITING_UNTIL",
                                   date=_sh_date(due.get("price_until"), now))
        return line, None
    if unrecorded:
        return _sh_word("SH_LOOK_BLOCKED" if blocked else "SH_LOOK_UNRECORDED",
                        k=_sh_int(unrecorded[-1].get("k"))), None
    if shown:
        last = shown[-1]
        kw = {"k": _sh_int(last.get("k")), "N": _sh_int(last.get("n")),
              "used": _sh_int(last.get("used")), "date": _sh_date(last.get("recorded_at"), now)}
        if last.get("past_line"):
            # Past the line, but not robust to the members left out (G2 (a)):
            # the figure is shown on its own side of the line, with the caveat.
            na = _sh_num(last.get("z_lo")) is None or _sh_num(last.get("z_hi")) is None
            line = (_sh_word("SH_LOOK_NOT_ROBUST_NA" if na else "SH_LOOK_NOT_ROBUST",
                             z=_sh_z(last.get("z"), True), x=_sh_int(last.get("n_filled")),
                             **kw)
                    + " " + _sh_word("SH_CAVEAT_NOT_ROBUST", T=T, used=kw["used"]))
        else:
            line = _sh_word("SH_LOOK_NOT_CROSSED", z=_sh_z(last.get("z"), False), **kw)
        if pending:
            nxt = pending[0]
            if _sh_num(nxt.get("due")) is not None:
                line += " " + _sh_word("SH_NEXT_LOOK", N2=_sh_int(nxt.get("n")),
                                       due=_sh_date(nxt.get("due"), now))
            else:
                line += " " + _sh_word("SH_NEXT_LOOK_UNDATED", N2=_sh_int(nxt.get("n")),
                                       missing=_sh_int(nxt.get("n_missing")))
        return line, _sh_int(last.get("k"))
    if not pending:
        return _sh_word("SH_LOADING"), None
    first = pending[0]
    k = _sh_int(first.get("k"))
    kw = {"have": _sh_int(first.get("used")), "N": _sh_int(first.get("n")), "k": k,
          "ordinal": SHADOW_ORDINALS.get(k, str(k))}
    if _sh_num(first.get("due")) is not None:
        return _sh_word("SH_BEFORE_LOOK", due=_sh_date(first.get("due"), now), **kw), None
    return _sh_word("SH_BEFORE_LOOK_UNDATED", missing=_sh_int(first.get("n_missing")),
                    **kw), None


def _sh_window(entries, now: float) -> str:
    """The period the figures are about (domain r2 P2-2, owner decision
    2026-10-12): the first and last entry date of the graded protocol
    entries, or of every protocol entry when none is graded yet. Empty when
    there are no entries. Dates go through the payload clamp; a bad one reads
    n/a. Read from the readout itself, so a follower shows the holder's."""
    rows = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    if not rows:
        return ""
    graded = [e for e in rows if e.get("state") in calibration_mod.SHADOW_GRADED]
    stamps = [_sh_ts(e.get("opened_at")) for e in graded or rows]
    good = [t for t in stamps if t is not None]
    first, last = ((_sh_date(min(good), now), _sh_date(max(good), now)) if good
                   else ("n/a", "n/a"))
    # It names what it covers (domain r3 N-6): the graded entries, or, before
    # any is graded, every entry.
    if graded:
        line = _sh_word("SH_ROW_WINDOW", n=len(graded), first=first, last=last)
    else:
        line = _sh_word("SH_ROW_WINDOW_NONE", first=first, last=last)
    # A date that cannot be read is said, not silently counted inside the
    # period (code review r4 P3-B).
    undated = len(stamps) - len(good)
    return f"{line} {_sh_word('SH_ROW_WINDOW_UNDATED', k=undated)}" if undated else line


def _sh_rows(d: dict, looks: list[dict], named: int | None, detail: bool, T: str,
             waiting: str, left_out: str, gap: str, blocked: bool = False) -> list[str]:
    """Rows of D4, in order; each omitted when its inputs are absent."""
    reached = _sh_int(d.get("n_reached"))
    rows = []
    # The extreme fills of the look the sentence names, when it left any
    # members out for want of a result (Amendment 1 §3).
    for lk in looks:
        if (_sh_int(lk.get("k")) == named and _sh_shown(lk, blocked)
                and _sh_int(lk.get("n_filled")) and _sh_num(lk.get("z_lo")) is not None
                and _sh_num(lk.get("z_hi")) is not None):
            rows.append(_sh_word("SH_EXTREMES", x=_sh_int(lk.get("n_filled")),
                                 lo=_sh_z(lk.get("z_lo")), hi=_sh_z(lk.get("z_hi"))))
    if reached:
        t, s, x = (_sh_int(d.get("n_target")), _sh_int(d.get("n_stop")),
                   _sh_int(d.get("n_time")))
        rows.append(_sh_word("SH_ROW_SPLIT", reached=reached, T=T,
                             t=t, tp=round(100 * t / reached), s=s,
                             sp=round(100 * s / reached), x=x, xp=round(100 * x / reached)))
    rows.append(waiting)
    ref = d.get("ref")
    if reached and isinstance(ref, dict) and _sh_num(ref.get("target")) is not None:
        rows.append(_sh_word("SH_ROW_REF", T=T, a=_sh_pct(ref.get("target")),
                             b=_sh_pct(ref.get("stop")), c=_sh_pct(ref.get("neither"))))
    if reached >= SHADOW_RUNNING_FROM and _sh_num(d.get("mean_r")) is not None:
        rows.append(_sh_word("SH_ROW_RUNNING", m=_sh_r(d.get("mean_r")),
                             lo=_sh_r(d.get("mean_r_lo")), hi=_sh_r(d.get("mean_r_hi")),
                             z=_sh_z(d.get("z"))))
        if _sh_num(d.get("ic")) is not None:
            rows.append(_sh_word("SH_ROW_IC", ic=_sh_r(d.get("ic")),
                                 icc=_sh_r(d.get("ic_closed")), T=T))
    elif reached:
        rows.append(_sh_word("SH_ROW_RUNNING_WAIT", k=SHADOW_RUNNING_FROM - reached))
    for lk in looks:
        if (_sh_shown(lk, blocked) and lk.get("crossed") is not True
                and _sh_int(lk.get("k")) != named):
            past = bool(lk.get("past_line"))
            na = _sh_num(lk.get("z_lo")) is None or _sh_num(lk.get("z_hi")) is None
            key = (("SH_ROW_PAST_LOOK_NA" if na else "SH_ROW_PAST_LOOK_NOT_ROBUST") if past
                   else "SH_ROW_PAST_LOOK")
            rows.append(_sh_word(key, k=_sh_int(lk.get("k")), N=_sh_int(lk.get("n")),
                                 z=_sh_z(lk.get("z"), past)))
    rows += [left_out, gap]
    if detail:
        for b in d.get("bands") or []:
            if not isinstance(b, dict) or not _sh_int(b.get("n")):
                continue
            ref = b.get("ref") if isinstance(b.get("ref"), dict) else {}
            row = _sh_word("SH_ROW_BAND", lo=_sh_int(b.get("lo")), hi=_band_top(
                {"hi": _sh_int(b.get("hi"))}), n=_sh_int(b.get("n")),
                t=_sh_int(b.get("target")), s=_sh_int(b.get("stop")),
                x=_sh_int(b.get("time")), a=_sh_pct(ref.get("target")),
                b=_sh_pct(ref.get("stop")), c=_sh_pct(ref.get("neither")))
            if _sh_num(ref.get("target")) is None:
                # No reference: the part is left off, never dashed (D4 row 3).
                row = row.split(" · what no edge")[0].split("  no edge")[0]
            rows.append(row)
    return rows


def _sh_warnings(looks: list[dict], now: float, blocked: bool = False) -> list[str]:
    """D3 (h): a look shown as a result, or due and not yet evaluated, with
    more than 10% of its cohort left out says so for as long as it is shown.
    A look worked out but not recorded, or any while the record is blocked,
    is not a result and gets no such line (code review P3-5)."""
    out = []
    for lk in looks:
        due = _sh_num(lk.get("due"))
        shown = _sh_shown(lk, blocked) or (
            not lk.get("evaluated") and due is not None and now >= due
            and not lk.get("design_closed"))
        n, x = _sh_int(lk.get("n")), _sh_int(lk.get("n_excluded"))
        if shown and n and x / n > SHADOW_WARN_SHARE:
            out.append(_sh_word("SH_WARN", x=x, N=n, pct=round(100 * x / n), used=n - x,
                                k=_sh_int(lk.get("k"))))
    return out


class ShadowGrade(QFrame):
    """The second grade: every protocol entry, at a fixed date.

    The grade above it counts closed positions only, and the slow ones — mostly
    high scores — are still open, so it leans on quick resolvers. This block
    reads `Live.shadow` (docs/adr/0002) and says where that second grade
    stands. One class on both pages, so the two copies cannot drift apart;
    ``detail`` adds the per-band lines on My trades. It sits below the existing
    grade in the same panel and changes none of its labels. Until a
    pre-registered look has been evaluated it says it is not a test yet.
    """

    def __init__(self, detail: bool, on_help, parent=None) -> None:
        super().__init__(parent)
        self.detail = detail
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(_hline())
        head = QHBoxLayout()
        self.heading = HelpHeading(SHADOW_WORDS["SH_HEAD"], "grading", _SH_TIP, on_help)
        head.addWidget(self.heading)
        head.addStretch(1)
        self.shadow_count = label("", "faint", theme.figure(8))
        head.addWidget(self.shadow_count)
        lay.addLayout(head)
        self.shadow_status = label("", font=theme.text(11), wrap=True)
        self.shadow_rows = label("", "muted", theme.figure(10), wrap=True)
        self.shadow_warn = label("", font=theme.figure(10), wrap=True)
        self.shadow_warn.setStyleSheet(f"color: {theme.GOLD.name()};")
        self.shadow_warn.setVisible(False)
        self.shadow_note = label("", "faint", theme.figure(9), wrap=True)
        for lb in (self.shadow_count, self.shadow_status, self.shadow_rows,
                   self.shadow_warn, self.shadow_note):
            lb.setTextFormat(Qt.PlainText)      # payload text is never markup
        for lb in (self.shadow_status, self.shadow_rows, self.shadow_warn,
                   self.shadow_note):
            lay.addWidget(lb)
        self.setAccessibleName("Second grade, every entry at a fixed date")

    def render(self, shadow, t_default: float, now: float | None = None) -> None:
        now = time.time() if now is None else now
        try:
            texts = shadow_texts(shadow, self.detail, now, t_default)
        except (TypeError, ValueError, KeyError, AttributeError, IndexError,
                OverflowError, OSError):
            # A dict this build cannot read (another version's, or damaged):
            # say so rather than show half of it.
            texts = shadow_texts({"error": "unreadable"}, self.detail, now, t_default)
        self.heading.retitle()
        self.shadow_count.setText(texts["count"])
        self.shadow_status.setText(texts["status"])
        self.shadow_rows.setText(texts["rows"])
        self.shadow_rows.setVisible(bool(texts["rows"]))
        self.shadow_warn.setText(texts["warn"])
        self.shadow_warn.setVisible(bool(texts["warn"]))
        self.shadow_note.setText(texts["note"])


class Stat(QWidget):
    """A labelled figure — the basic readout unit, on five different strips."""

    def __init__(self, caption: str, tip: str = "", parent=None) -> None:
        super().__init__(parent)
        self._key = caption
        caption = self._caption()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        self.cap = label(caption.upper(), "faint", theme.figure(8))
        self.val = label("—", font=theme.figure(15, True))
        lay.addWidget(self.cap)
        lay.addWidget(self.val)
        if tip:
            self.setToolTip(tip)

    def _caption(self) -> str:
        return STAT_WORDS.get(self._key, self._key) if words.plain() \
            else self._key

    def retitle(self) -> None:
        self.cap.setText(self._caption().upper())

    def set(self, text: str, color=None) -> None:
        self.val.setText(text)
        self.val.setStyleSheet(f"color: {(color or theme.INK).name()};")



class AssetRow(QFrame):
    """One market on the board.

    Two lines per cell wherever the number alone is not the point: the figure on
    top for anyone who reads figures, and what it means underneath for everyone
    else. "4.3%" and "big swings" are the same fact, and printing only the first
    was the app choosing an audience.
    """

    def __init__(self, a: dict, on_read, on_trade, generated: float = 0.0,
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        # When this row's price was fetched, as an absolute time. `data_age_s`
        # is measured when the scan runs, so storing it as-is would freeze the
        # age at whatever it was then and count nothing afterwards — the exact
        # dishonesty the column exists to remove. Anchoring it to the scan's
        # own `generated` stamp lets `update_age` keep counting between scans.
        self._fetched_at = (generated or time.time()) - float(
            a.get("data_age_s") or 0.0)

        plain = words.plain()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 7 if plain else 4, 12, 7 if plain else 4)
        lay.setSpacing(12)
        widths = dict(_asset_widths())

        def cell(key, text, colour, sub="", font=None, sub_font=None):
            """A fixed-width column: the figure, and — in plain wording — what
            it means under it. Expert drops the second line, which is most of
            where the extra third of row height goes."""
            holder = QWidget()
            holder.setObjectName("cell")
            holder.setFixedWidth(widths[key])
            box = QVBoxLayout(holder)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(1)
            top = label(text, font=font or theme.figure(12))
            top.setStyleSheet(f"color: {colour.name()};")
            box.addWidget(top)
            if sub and plain:
                box.addWidget(label(sub, "faint", sub_font or theme.text(9)))
            return holder

        # -- what it is ----------------------------------------------------- #
        holder = QWidget()
        holder.setObjectName("cell")
        holder.setFixedWidth(widths["name"])
        name = QVBoxLayout(holder)
        name.setContentsMargins(0, 0, 0, 0)
        name.setSpacing(1)
        name.addWidget(label(a["name"], font=theme.text(12, True)))
        # Where this could actually be bought, and the marker for when it could
        # not. A board that ranks an index, a futures contract and a delisted
        # coin alongside buyable shares — without saying which is which — is
        # inviting an order that cannot be placed. 58 of 129 rows are only
        # reachable through a proxy, so the marker is not an edge case.
        v = venues.where(a["symbol"], a.get("cls", ""))
        mark = "" if (v.tradeable and not v.proxy) else ("  ⊘" if not v.tradeable
                                                         else "  ↗")
        sub = label(f'{a["cls"]} · {_plain_read(a)}{mark}' if plain
                    else f'{a["symbol"]}  ·  {a["cls"]}{mark}',
                    "faint", theme.text(9))
        if mark:
            sub.setStyleSheet(
                f"color: {(theme.DOWN if not v.tradeable else theme.GOLD).name()};")
        name.addWidget(sub)
        # A tooltip guesses markup as AutoText does; in follow mode these
        # fields are the holder's JSON.
        holder.setToolTip(f"{_clean(a['name'], 80)} ({_clean(a['symbol'], 16)}) · "
                          f"{_clean(a['cls'], 24)}\n\n"
                          f"{_clean(a.get('rationale', ''), 600)}\n\n{v.summary()}"
                          f"\n\nVenue list checked {venues.CHECKED}. "
                          "Reference only — not advice, and availability changes.")
        lay.addWidget(holder)

        # The sparkline sets the row's height floor once the second lines are
        # gone, so expert gets a shorter one — otherwise the denser wording
        # buys six pixels and looks like it did nothing.
        spark = Sparkline(34 if plain else 22)
        spark.frame = False
        spark.setFixedWidth(widths["trend"])
        # colour by the horizon's momentum so the line agrees with the number
        # printed next to it
        spark.set_values(a.get("spark", []), up=a["momentum"] >= 0)
        lay.addWidget(spark)

        lay.addWidget(cell("price", f'{a["price"]:,.2f}', theme.INK))
        lay.addWidget(cell("1d", f'{a["day_change"]*100:+.2f}%',
                           theme.pnl_color(a["day_change"])))
        lay.addWidget(cell(
            "momentum",
            f'{a["momentum"]*100:+.1f}%' if plain
            else f'{a["momentum"]*100:+.1f}% / {a["momentum_days"]}d',
            theme.pnl_color(a["momentum"]), f'over {a["momentum_days"]} days',
            font=None if plain else theme.figure(11)))
        lay.addWidget(cell("volatility", f'{a["volatility"]*100:.1f}%',
                           theme.MUTED, _swing_words(a["volatility"])))

        # -- in the news ---------------------------------------------------- #
        holder = QWidget()
        holder.setObjectName("cell")
        holder.setFixedWidth(widths["lean"])
        box = QHBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        colour = {"Spike": theme.GOLD, "Elevated": theme.UP}.get(a["lean"],
                                                                 theme.MUTED)
        lean = label(f'  {a["lean"]}  ' if plain else a["lean"],
                     font=theme.text(10, True))
        lean.setStyleSheet(
            f"color: {colour.name()}; border: 1px solid {colour.name()};"
            "border-radius: 7px; padding: 3px 2px;" if plain
            else f"color: {colour.name()};")
        lean.setToolTip(
            "How unusual today's coverage is — a flag for 'something is\n"
            "happening', not a direction. The old Bullish/Bearish lean was\n"
            "removed because the backtest found the move carried no edge.")
        box.addWidget(lean)
        box.addStretch(1)
        lay.addWidget(holder)

        # -- if you traded it ----------------------------------------------- #
        plan = a.get("plan") or {}
        rr = plan.get("rr", 0)
        pp = plan.get("p_profit", 0) * 100
        traded = cell("plan",
                      f"win {rr:.2g}× the risk" if plain
                      else f"{rr:.2f}  ·  {pp:.0f}%",
                      theme.MUTED, f"{pp:.0f}% of the time",
                      font=theme.text(10) if plain else theme.figure(11),
                      sub_font=theme.text(9))
        traded.setToolTip(
            f"Target {rr:.2g} times as far away as the stop, both scaled to how\n"
            f"much this market moves. The chance of reaching the target first\n"
            f"is {pp:.0f}%.\n\n"
            "That is 1/(1+reward:risk) exactly — the no-edge baseline, where\n"
            "expected value is zero. My trades grades whether closed positions\n"
            "kept to these odds; that grade never changes this number.")
        lay.addWidget(traded)

        # -- worth a look --------------------------------------------------- #
        holder = QWidget()
        holder.setObjectName("cell")
        holder.setFixedWidth(widths["conf"])
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(3)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(3)
        score = label(f'{a["confidence"]:.0f}', font=theme.figure(15, True))
        line.addWidget(score)
        if plain:
            line.addWidget(label("/ 100", "faint", theme.text(9)))
        line.addStretch(1)
        box.addLayout(line)
        bar = ComponentBar()
        # Length reads as "how notable", segments as "why". One 80px cell
        # cannot hold both any other way.
        bar.set_parts(a.get("comp", {}), ASSET_W, fill=a["confidence"] / 100.0)
        box.addWidget(bar)
        lay.addWidget(holder)

        # -- updated -------------------------------------------------------- #
        self.age = label("", font=theme.text(9))
        self.age.setFixedWidth(widths["age"])
        self.age.setToolTip(
            {k: t for k, _h, _w, _a, t in ASSET_COLS}["age"])
        self.update_age()
        lay.addWidget(self.age)

        # -- what you can do about it --------------------------------------- #
        acts = QWidget()
        acts.setObjectName("cell")
        acts.setFixedWidth(widths["actions"])
        al = QHBoxLayout(acts)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(5)
        for text_, tip, slot in [
            ("Buy" if plain else "buy",
             "Open a practice position betting this goes up, with the\n"
                    "target and stop from the column to the left.\n"
                    "Practice money — no order is placed anywhere.",
             lambda: on_trade(a["symbol"], "LONG")),
            ("Short" if plain else "short",
             "Open a practice position betting this goes down.\n"
             "Practice money — no order is placed anywhere.",
             lambda: on_trade(a["symbol"], "SHORT")),
            ("AI note" if plain else "read",
             "A written read from a language model (optional, off by\n"
             "default). Commentary — it cannot size a position.",
             lambda: on_read("asset", a["symbol"], a["name"])),
        ]:
            b = QPushButton(text_)
            b.setObjectName("row")
            b.setFont(theme.text(9))
            b.setToolTip(tip)
            # Explicit width: squeezed below their text Qt elides these into
            # unreadable glyphs rather than shrinking the font.
            b.setFixedWidth(44)
            b.clicked.connect(slot)
            al.addWidget(b)
        al.addStretch(1)
        lay.addWidget(acts)

    def update_age(self, now: float | None = None) -> None:
        """Re-render the age. Cheap enough for the 1s timer because the text
        only changes once a minute, and setText on an unchanged string still
        costs a relayout of the row."""
        seconds = max(0.0, (now or time.time()) - self._fetched_at)
        text = _age_text(seconds)
        if text == self.age.text():
            return
        self.age.setText(text)
        self.age.setStyleSheet(f"color: {_age_color(seconds).name()};")


class SuggestionCard(QFrame):
    """What the news points at, with an exit that is a price rather than a date."""

    def __init__(self, s: dict, on_trade, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(9)
        nm = label(f'{s["name"]}', font=theme.text(12, True))
        top.addWidget(nm)
        top.addWidget(label(s["symbol"], "faint", theme.figure(9)))
        lvl = label(s["news_level"], font=theme.figure(9, True))
        lvl.setStyleSheet(
            f"color: {(theme.GOLD if s['news_level']=='Spike' else theme.UP).name()};")
        top.addWidget(lvl)
        top.addStretch(1)
        conf = label(f'{s["confidence"]:.0f}', font=theme.figure(15, True))
        conf.setToolTip("Confidence: how notable this is — not the odds of profit.")
        top.addWidget(conf)
        lay.addLayout(top)

        if s.get("headlines"):
            h = s["headlines"][0]
            hl = label(f'{h["source"]} · {h["title"]}', "muted", theme.figure(9))
            hl.setTextFormat(Qt.PlainText)          # feed text is never markup
            hl.setWordWrap(True)
            lay.addWidget(hl)

        # The exit is exact because it is a price. The *date* is a distribution,
        # and is shown as one rather than invented as a single day.
        plan = QHBoxLayout()
        plan.setSpacing(14)
        for text, tip in [
            (f'in {s["price"]:,.2f}', "Entry at the current price — now, because "
                                      "that is when the coverage is."),
            (f'target {s["target"]:,.2f}', "Sell here. An exact price, not a guessed date."),
            (f'stop {s["stop"]:,.2f}', "Exit here if it goes wrong."),
            (f'{s["hold_p25"]}–{s["hold_p75"]}d (med {s["hold_median"]})',
             "How long this usually takes to reach one barrier or the other,\n"
             "measured over 6,771 historical setups. A distribution, not a date."),
        ]:
            lb = label(text, "muted", theme.figure(10))
            lb.setToolTip(tip)
            plan.addWidget(lb)
        plan.addStretch(1)
        for txt, direction in (("buy", "LONG"), ("short", "SHORT")):
            b = QPushButton(txt)
            b.setFont(theme.figure(9))
            b.setFixedWidth(56)
            b.setToolTip("Direction is yours: coverage says something is "
                         "happening, not which way it goes.")
            b.clicked.connect(lambda _=None, sym=s["symbol"], d=direction:
                              on_trade(sym, d))
            plan.addWidget(b)
        lay.addLayout(plan)

        if s.get("catalyst"):
            c = label(f'◆ scheduled: {s["catalyst"]} ({s["catalyst_date"]})',
                      font=theme.figure(9))
            c.setStyleSheet(f"color: {theme.GOLD.name()};")
            c.setToolTip("A date that is a fact, not a forecast — the one kind of "
                         "precise timing available.")
            lay.addWidget(c)


class TickerRow(QFrame):
    """One headline on the wire, newest first."""

    def __init__(self, h, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        age = label(f'{h.age_hours:.0f}h' if h.age_hours >= 1 else "now",
                    "faint", theme.figure(9))
        age.setFixedWidth(34)
        lay.addWidget(age)
        src = label(h.source, font=theme.figure(9))
        src.setStyleSheet(f"color: {theme.GOLD.name()};")
        src.setFixedWidth(104)
        lay.addWidget(src)
        title = label(h.title, font=theme.text(11))
        title.setTextFormat(Qt.PlainText)           # feed text is never markup
        title.setWordWrap(True)
        lay.addWidget(title, 1)


class EventRow(QFrame):
    """One scheduled catalyst: an earnings date or a listing."""

    def __init__(self, sym: str, what: str, when: str, colour, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        s = label(sym, font=theme.figure(10, True))
        s.setStyleSheet(f"color: {colour.name()};")
        s.setFixedWidth(66)
        lay.addWidget(s)
        w = label(what, "muted", theme.figure(9))
        w.setWordWrap(True)
        lay.addWidget(w, 1)
        lay.addWidget(label(when, "faint", theme.figure(9)))


class PositionRow(QFrame):
    """One open paper position, with where it sits between stop and target."""

    def __init__(self, p: dict, on_close, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(14)

        side = label(p["direction"], font=theme.figure(10, True))
        side.setStyleSheet(
            f"color: {(theme.UP if p['direction']=='LONG' else theme.DOWN).name()};")
        side.setFixedWidth(52)
        lay.addWidget(side)

        nm = QVBoxLayout()
        nm.setSpacing(0)
        nm.addWidget(label(p["name"], font=theme.text(12, True)))
        nm.addWidget(label(f'{p["symbol"]}  ·  {p["units"]:.4g} units',
                           "faint", theme.figure(9)))
        holder = QWidget()
        holder.setFixedWidth(170)
        holder.setLayout(nm)
        lay.addWidget(holder)

        for text, tip, width in [
            (f'entry {p["entry"]:,.2f}', "Price the position was opened at", 118),
            (f'now {p["price"]:,.2f}', "Latest marked price", 108),
            (f'stop {p["stop"]:,.2f}', "Closes here for a loss", 112),
            (f'target {p["target"]:,.2f}', "Closes here for a profit", 118),
        ]:
            lb = label(text, "muted", theme.figure(10))
            lb.setToolTip(tip)
            lb.setFixedWidth(width)
            lay.addWidget(lb)

        prog = ComponentBar()
        prog.setFixedWidth(90)
        prog.set_parts({"done": p["progress"], "left": 1 - p["progress"]},
                       {"done": 1.0, "left": 1.0})
        prog.setToolTip("How far price has travelled from the stop (left) "
                        "toward the target (right).")
        lay.addWidget(prog)

        unreal = label(f'{p["unrealised"]:+,.2f}', font=theme.figure(12, True))
        unreal.setStyleSheet(f"color: {theme.pnl_color(p['unrealised']).name()};")
        unreal.setFixedWidth(90)
        unreal.setToolTip("Mark-to-market profit or loss if closed now.")
        lay.addWidget(unreal)

        btn = QPushButton("close")
        btn.setFont(theme.figure(9))
        btn.setToolTip("Close this paper position at the current price.")
        btn.clicked.connect(lambda: on_close(p["id"]))
        lay.addWidget(btn)


class PositionCard(QFrame):
    """One open position as a picture: its recent prices with the entry, the
    target and the stop drawn in, the figures beside it, and where price sits
    between the stop and the target underneath.

    Updated in place rather than rebuilt: a card rebuilt every scan flickers,
    and thirty of them flicker together.
    """

    def __init__(self, p: dict, on_close, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.pos_id = p["id"]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        name = label(p.get("name") or p["symbol"], font=theme.text(12, True))
        head.addWidget(name)
        head.addWidget(label(p["symbol"], "faint", theme.figure(9)))
        side = label(p["direction"].lower(), font=theme.figure(8, True))
        side.setStyleSheet(
            f"color: {(theme.UP if p['direction'] == 'LONG' else theme.DOWN).name()};")
        head.addWidget(side)
        head.addStretch(1)
        self.pnl = label("", font=theme.figure(14, True))
        self.pnl.setToolTip("Mark-to-market profit or loss if closed now.")
        head.addWidget(self.pnl)
        lay.addLayout(head)

        mid = QHBoxLayout()
        mid.setSpacing(12)
        self.chart = PositionChart(64)
        self.chart.setToolTip("Recent daily closes. Gold is your entry, blue "
                              "the target, orange the stop; the dot is now.")
        mid.addWidget(self.chart, 1)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.stake = label("", "muted", theme.figure(9))
        self.now = label("", "muted", theme.figure(9))
        self.entry = label("", "muted", theme.figure(9))
        self.target = label("", "muted", theme.figure(9))
        self.stop = label("", "muted", theme.figure(9))
        for lb in (self.stake, self.now, self.entry, self.target, self.stop):
            col.addWidget(lb)
        holder = QWidget()
        holder.setObjectName("cell")
        holder.setLayout(col)
        holder.setFixedWidth(150)
        mid.addWidget(holder)
        lay.addLayout(mid)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        foot.addWidget(label("stop", "faint", theme.figure(8)))
        self.prog = ComponentBar()
        self.prog.setToolTip("How far price has travelled from the stop (left) "
                             "toward the target (right).")
        foot.addWidget(self.prog, 1)
        foot.addWidget(label("target", "faint", theme.figure(8)))
        btn = QPushButton("close")
        btn.setFont(theme.figure(9))
        btn.setToolTip("Close this paper position at the current price.")
        btn.clicked.connect(lambda: on_close(p["id"]))
        foot.addWidget(btn)
        lay.addLayout(foot)
        self.set_row(p)

    def set_row(self, p: dict) -> None:
        pnl = p.get("unrealised") or 0.0
        self.pnl.setText(f"{pnl:+,.2f}")
        self.pnl.setStyleSheet(f"color: {theme.pnl_color(pnl).name()};")
        self.stake.setText(f'invested  ${p.get("stake", 0):,.0f}')
        self.now.setText(f'now  {_px(p["price"])}  {p.get("pct", 0):+.2f}%')
        self.entry.setText(f'entry  {_px(p["entry"])}')
        self.target.setText(f'target  {_px(p["target"])}')
        self.stop.setText(f'stop  {_px(p["stop"])}')
        self.chart.set_position(p.get("spark") or [], p["entry"], p["target"],
                                p["stop"], p["price"], pnl >= 0)
        self.prog.set_parts({"done": p["progress"], "left": 1 - p["progress"]},
                            {"done": 1.0, "left": 1.0})


class ClosedRow(QWidget):
    """One resolved position on the landing page: what it was, how it ended,
    what it made. The grading of every closed trade stays on My trades."""

    HOW = {"TARGET": "hit target", "STOP": "hit stop", "MANUAL": "closed by you"}

    def __init__(self, p: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cell")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        lay.setSpacing(10)
        side = label(p["direction"].lower(), font=theme.figure(9, True))
        side.setStyleSheet(
            f"color: {(theme.UP if p['direction'] == 'LONG' else theme.DOWN).name()};")
        side.setFixedWidth(38)
        lay.addWidget(side)
        lay.addWidget(label(p.get("name") or p["symbol"], font=theme.text(11)), 1)
        outcome = p.get("outcome") or ""
        lay.addWidget(label(self.HOW.get(outcome, outcome.lower()), "faint",
                            theme.figure(9)))
        pnl = p.get("pnl") or 0.0
        amount = label(f"{pnl:+,.2f}", font=theme.figure(11, True),
                       align=Qt.AlignRight | Qt.AlignVCenter)
        amount.setStyleSheet(f"color: {theme.pnl_color(pnl).name()};")
        amount.setFixedWidth(66)
        lay.addWidget(amount)
        when = label(_day_text(p.get("closed_at")), "faint", theme.figure(9),
                     align=Qt.AlignRight | Qt.AlignVCenter)
        when.setFixedWidth(44)
        lay.addWidget(when)


class ReadPanel(QFrame):
    """The narrative track — visually separate from every measured number.

    Kept deliberately distinct from the confidence scores: this one is not
    calibrated, and the panel says so rather than letting a conviction number
    pass as a probability.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(5)
        head = QHBoxLayout()
        head.addWidget(label("LLM READ", "faint", theme.figure(8)))
        head.addStretch(1)
        self.badge = label("", font=theme.figure(9))
        head.addWidget(self.badge)
        lay.addLayout(head)
        self.subject = label("—", font=theme.text(12, True))
        self.subject.setWordWrap(True)
        lay.addWidget(self.subject)
        self.body = label("Select an opportunity and press “LLM read”.",
                          "muted", theme.text(11))
        self.body.setWordWrap(True)
        # The model's reply (steerable by a headline) and the subject are
        # never markup: an <a> or <img> must show as text (security S1).
        for lb in (self.badge, self.subject, self.body):
            lb.setTextFormat(Qt.PlainText)
        lay.addWidget(self.body)
        self.caveat = label("", "faint", theme.figure(9))
        self.caveat.setWordWrap(True)
        lay.addWidget(self.caveat)
        self.hide()

    def show_pending(self, subject: str) -> None:
        self.subject.setText(subject)
        self.badge.setText("reading…")
        self.badge.setStyleSheet(f"color: {theme.MUTED.name()};")
        self.body.setText("Waiting on the model — this takes a few seconds.")
        self.caveat.setText("")
        self.show()

    def show_read(self, r: dict, long_horizon: bool) -> None:
        if r.get("error"):
            self.badge.setText("unavailable")
            self.badge.setStyleSheet(f"color: {theme.DOWN.name()};")
            if r.get("subject"):
                self.subject.setText(r["subject"])
            self.body.setText(r["error"])
            self.caveat.setText(
                "The LLM read is optional and off by default. Everything else "
                "in SONAR — the model, the screener, the paper engine — is "
                "local arithmetic and keeps working without it.")
            return
        d = r.get("direction", "UNCLEAR")
        self.badge.setText(f'{d}  ·  conviction {r.get("conviction", 0)}/100')
        self.badge.setStyleSheet(f"color: {theme.side_color(d).name()};")
        self.subject.setText(r.get("subject", "—"))

        parts = [r.get("summary", "")]
        if r.get("catalysts"):
            parts.append("\nCatalysts\n" + "\n".join(f"  • {c}" for c in r["catalysts"]))
        if r.get("risks"):
            parts.append("\nRisks\n" + "\n".join(f"  • {c}" for c in r["risks"]))
        self.body.setText("\n".join(p for p in parts if p))

        note = ("Conviction is the model's subjective read, not a calibrated "
                "probability. It is logged and scored against the real outcome.")
        if long_horizon:
            note += (" At this horizon that scoring takes months — the "
                     "calibration table will stay empty for a long time.")
        self.caveat.setText(note)


class MainWindow(QMainWindow):
    def __init__(self, live: Live) -> None:
        super().__init__()
        self.live = live
        self._read_thread = None
        self._cfg_thread = None
        self._bt_thread = None
        self._lab_thread = None
        self._sports_thread = None
        self.tray = None            # set by main.py once the app exists
        self.allow_close = False    # released by a real quit — see eventFilter
        # Cmd-Q, the Dock's Quit and a logout all arrive at the *application* as
        # QEvent.Quit, never at this window, so the guard below has to watch for
        # them here.
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._hidden_at = 0.0       # when this window last hid itself
        # A close pressed in full screen hides on a timer — see closeEvent.
        self._hide_on_leaving_fullscreen = False
        # The version belongs in the title too: a screenshot of a window is
        # how bugs get reported here, and the title is in every screenshot.
        self.setWindowTitle(f"SONAR {version_mod.version_string()}")
        self._fit_to_screen()
        icon = paths.asset_path("icon.icns")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        words.load()          # before anything that reads the wording is built
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        # The rail runs the full height of the window, so the window itself
        # has no chrome margins — each region owns its own padding.
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Both names on every tab: the plain one leads, the one the docs and the
        # last month of muscle memory use sits under it. See `ui/tabs.py`.
        self.tabs = PlainTabs()
        self.tabs.set_rail_header(self._rail_header())
        # The landing page is the reader's own money. The hourly bitcoin
        # model, which opened the app for two months, lives at the foot of
        # Practice now — it is an experiment the engine runs, not a holding.
        self.tabs.add(_scrolled(self._portfolio_tab()), "My investments", "Portfolio",
                      "Everything you hold in practice money — what you put "
                      "in, and what it is worth right now.")
        self._asset_rows: list[AssetRow] = []   # ticked by the Updated column
        self.tabs.add(self._assets_tab(), "Screener", "Assets",
                      "129 markets ranked by how notable they look right now. "
                      "Notable, never 'going up'.")
        self.tabs.add(self._wire_tab(), "News", "Wire",
                      "The newswire, the calendar of what is already scheduled, "
                      "and alerts on what changed since the last scan.")
        self.tabs.add(self._book_tab(), "My trades", "Book",
                      "Your open practice positions, and the table that grades "
                      "the score against what actually happened.")
        self.tabs.add(self._macro_tab(), "Big picture", "Macro",
                      "The backdrop — rates, volatility, jobs — and what the "
                      "central banks have been saying.")
        # The manual stays on the main path; the two experiments come after it,
        # under their own heading (docs/specs/v1-product.md).
        self.tabs.add(self._learn_tab(), "Learn", "",
                      "The manual and the glossary. It assumes no finance "
                      "background — start at §1.")
        self._lab_scroll = _scrolled(self._lab_tab())
        self._lab_index = self.tabs.add(
            self._lab_scroll, "Practice", "Lab",
            "Test any claim this app makes against real history, make your "
            "own calls with the future hidden — and watch the hourly bitcoin "
            "model, the one place SONAR says which way something goes.")
        self.tabs.add(_scrolled(self._playmaker_tab()), "Sports", "Playmaker",
                      "Pricing a sports bet: what the bookmakers' margin is, "
                      "and where they disagree with each other.")
        self.tabs.set_group(self._lab_index, "Lab")
        # ⌘1…⌘8 reach every page in rail order: the rail was mouse-only.
        for i in range(min(self.tabs.count(), 9)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self,
                      activated=lambda i=i: self.tabs.setCurrentIndex(i))
        outer.addWidget(self.tabs, 1)

        self.tabs.set_header_widget(self._knobs())
        self.tabs.set_rail_footer(self._rail_footer())   # creates self.status
        self._apply_wording()
        self._sync_rail()

        self.poll = PollThread(live, self)
        self.poll.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)

    # -- chrome ------------------------------------------------------------ #
    #: What each risk profile means in words. The profiles themselves carry
    #: numbers — a stake fraction and a volatility ceiling — and "Aggressive"
    #: tells a newcomer nothing about either.
    RISK_WORDS = {
        "conservative": "calmest markets only",
        "moderate": "a middle ground",
        "aggressive": "shows the jumpiest markets",
    }

    def _rail_header(self) -> QWidget:
        """The rail's masthead: the wordmark, the build, and the promise.

        The version sits next to the name, not tucked in an About box. "I
        opened the app and nothing is new" was reported repeatedly against a
        bundle that was simply older than the work being described, and
        nothing on screen could have told anyone that.
        """
        holder = QWidget()
        col = QVBoxLayout(holder)
        col.setContentsMargins(6, 0, 4, 0)
        col.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(label("SONAR", "h1"))
        self.version_label = VersionBadge()
        top.addWidget(self.version_label)
        top.addStretch(1)
        col.addLayout(top)
        col.addWidget(label("practice money only — nothing here places a real "
                            "order", "faint", theme.text(9), wrap=True))
        return holder

    def _knobs(self) -> QWidget:
        """The two knobs everything else depends on, labelled as questions.

        They used to be a 22px combobox each, captioned `risk` and `horizon` in
        9pt grey. Both words are jargon for the setting they name, both boxes
        were smaller than the text beside them, and neither said what would
        happen if you changed it. Asking the question the setting answers costs
        one line and removes the guessing. They live in the page header — not
        on any one tab — because every screen depends on them.
        """
        holder = QWidget()
        holder.setObjectName("cell")
        bar = QHBoxLayout(holder)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(12)

        def field(caption: str, box: QComboBox, tip: str) -> QWidget:
            holder = QWidget()
            holder.setObjectName("cell")
            col = QVBoxLayout(holder)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(3)
            cap = label(caption, "muted", theme.text(9))
            cap.setToolTip(tip)
            col.addWidget(cap)
            box.setObjectName("toolbar")       # the big variant in the theme
            box.setFont(theme.text(11))
            box.setToolTip(tip)
            col.addWidget(box)
            return holder

        self.risk_box = QComboBox()
        for profile in risk_mod.PROFILES.values():
            words = self.RISK_WORDS.get(profile.name, "")
            self.risk_box.addItem(
                f"{profile.name.capitalize()}  ·  {words}" if words
                else profile.name.capitalize(), profile.name)
        self.risk_box.setCurrentIndex(
            list(risk_mod.PROFILES).index(self.live.risk.name))
        self.risk_box.currentIndexChanged.connect(self._apply_config)
        bar.addWidget(field(
            "How much risk are you willing to take?", self.risk_box,
            "How big a practice position is, and how wild a market has to be\n"
            "before it is hidden from the board.\n"
            "It never changes a score — a score measures the market, not you."))

        self.hz_box = QComboBox()
        for h in hz_mod.HORIZONS.values():
            self.hz_box.addItem(h.label, h.name)
        self.hz_box.setCurrentIndex(
            list(hz_mod.HORIZONS).index(self.live.horizon.name))
        self.hz_box.currentIndexChanged.connect(self._apply_config)
        bar.addWidget(field(
            "How long would you hold it?", self.hz_box,
            "Changes which window 'Recent move' measures and how far the\n"
            "target and stop sit from the price. Long horizons also bring in\n"
            "the big-picture backdrop."))
        # Always on screen, whatever the rail does: it used to live only in the
        # rail's header and went with it when the rail folded.
        chip = label("Practice money only", "muted", theme.text(10))
        chip.setToolTip("Every position here is simulated. Nothing in SONAR can "
                        "place a real order or touch a real account.")
        bar.addWidget(chip, 0, Qt.AlignBottom)
        return holder

    def _rail_footer(self) -> QWidget:
        """The rail's foot: the wording switch, the test plan, and the status
        line — the one line of running commentary the whole app gets.

        The old Learn button is gone because Learn is a destination on the
        rail now; two doors to the same tab is the pattern this workspace
        keeps removing.
        """
        holder = QWidget()
        col = QVBoxLayout(holder)
        col.setContentsMargins(4, 0, 4, 0)
        col.setSpacing(6)
        # Stacked, not side by side: half a rail is ~80px, and Qt elides a
        # button squeezed below its text into glyph soup rather than
        # shrinking the font — the same failure the row buttons pin at 44px.
        self.wording_btn = QPushButton("")
        self.wording_btn.setFont(theme.text(10))
        self.wording_btn.setToolTip(
            "Which words the app uses for the same numbers.\n\n"
            "Plain — 'Worth a look', 'Swing size', a sentence on every row.\n"
            "Expert — CONF, VOL, R:R, the ticker back on the row, and no\n"
            "second lines, which makes the board about a third shorter.\n\n"
            "Same columns, same order, same arithmetic either way.")
        self.wording_btn.clicked.connect(self._toggle_wording)
        col.addWidget(self.wording_btn)

        plan = QPushButton("Test plan")
        plan.setFont(theme.text(10))
        plan.setToolTip(
            "The acceptance checklist for signing off a build.\n"
            "Tick each case off as you go — the page remembers what you have\n"
            "already passed or failed. Seventeen are marked as regressions:\n"
            "each one has caught a real bug before.")
        plan.clicked.connect(self._open_testplan)
        col.addWidget(plan)

        # Wrapped, or one long trade confirmation sets the rail's minimum
        # width — the same QLabel trap tests/test_layout.py guards. The
        # width is pinned because heightForWidth through nested layouts
        # under-reports, and the label then paints past the window's bottom
        # edge rather than asking for the height it needs.
        self.status = label("starting…", "faint", theme.figure(9), wrap=True)
        self.status.setTextFormat(Qt.PlainText)     # shows error text
        self.status.setFixedWidth(self.tabs.rail_width() - 32)
        col.addWidget(self.status)
        return holder

    def _assets_tab(self) -> QWidget:
        """The board, under one sentence saying what it is.

        The sentence is there because the single most common way to misread
        this app is to take the ranking as a list of things that will go up. It
        is a list of things that look *notable*, the difference is the whole
        design, and a reader who has not been told cannot be expected to guess
        it from a column called CONF.
        """
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)

        banner = QFrame()
        banner.setObjectName("banner")
        bl = QHBoxLayout(banner)
        bl.setContentsMargins(14, 9, 12, 9)
        bl.setSpacing(12)
        line = label(
            "<b>What am I looking at?</b>  A list of markets ranked by how "
            "<b>interesting</b> they look right now — not by whether they will "
            "go up. Nothing here spends real money.",
            font=theme.text(11), wrap=True)
        line.setTextFormat(Qt.RichText)
        bl.addWidget(line, 1)
        for text_, anchor in [("What is \u201cworth a look\u201d?", "scores"),
                              ("Why is it always 40%?", "scores"),
                              ("Open the glossary", "learn")]:
            chip = QPushButton(text_)
            chip.setObjectName("chip")
            chip.setFont(theme.text(9))
            chip.setToolTip("Opens the manual at the section that answers this.")
            chip.clicked.connect(lambda _c=False, a=anchor: self._show_learn(a))
            bl.addWidget(chip)
        self.assets_banner = banner        # hidden in expert wording
        lay.addWidget(banner)
        self.asset_header = AssetHeader(self._show_learn)
        lay.addWidget(self._scroll_tab("assets", self.asset_header), 1)
        banner.setVisible(words.plain())
        return wrap

    def _learn_tab(self) -> QWidget:
        """The manual, in the window rather than in a browser.

        The prose already existed and was already good; what it was missing was
        being *here*. Someone looking at a number they do not understand is one
        click from the paragraph that explains it, instead of one context switch
        and a lost train of thought.

        Contents on the left, because a 60KB page with no way in is a wall.
        Search on the right, because the question is usually a single word —
        "vig", "Brier", "drawdown" — and hunting for it through fourteen
        sections is the thing that makes people give up on documentation.
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)

        html, sections = learn_mod.document()

        top = QHBoxLayout()
        top.setContentsMargins(2, 0, 8, 0)
        top.setSpacing(8)
        top.addWidget(label("FIND", "faint", theme.figure(8)))
        self.learn_find = QLineEdit()
        self.learn_find.setPlaceholderText(
            "a word you do not recognise — vig, Brier, drawdown, base rate…")
        self.learn_find.setFixedWidth(400)
        self.learn_find.returnPressed.connect(self._learn_search)
        top.addWidget(self.learn_find)
        self.learn_hint = label("", "faint", theme.figure(9))
        top.addWidget(self.learn_hint, 1)
        browser_btn = QPushButton("Open in browser")
        browser_btn.setFont(theme.figure(9))
        browser_btn.setToolTip(
            "The same page, rendered by a real browser. Qt draws a usable\n"
            "subset of it here; the browser draws all of it.")
        browser_btn.clicked.connect(self._open_docs)
        top.addWidget(browser_btn)
        lay.addLayout(top)

        body = QHBoxLayout()
        body.setContentsMargins(2, 0, 8, 0)
        body.setSpacing(8)

        self.learn_toc = QListWidget()
        self.learn_toc.setFixedWidth(268)
        self.learn_toc.setFont(theme.figure(10))
        # No horizontal scrolling: a contents list you have to scroll sideways
        # to read is not contents. The width above fits the longest heading.
        self.learn_toc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for anchor, number, title in sections:
            item = QListWidgetItem(f"{number} · {title}")
            item.setData(Qt.UserRole, anchor)
            item.setToolTip(f"{number} · {title}")   # the two long ones elide
            self.learn_toc.addItem(item)
        self.learn_toc.currentItemChanged.connect(self._learn_goto)
        body.addWidget(self.learn_toc)

        self.learn_view = QTextBrowser()
        self.learn_view.setOpenLinks(False)          # handled below
        self.learn_view.setOpenExternalLinks(False)
        self.learn_view.document().setDefaultStyleSheet(learn_mod.STYLESHEET)
        self.learn_view.setHtml(html)
        self.learn_view.anchorClicked.connect(self._learn_link)
        body.addWidget(self.learn_view, 1)
        lay.addLayout(body, 1)
        return w

    def _show_learn(self, anchor: str = "") -> None:
        """Bring the manual up, at a section when one is named.

        Named for what the reader wants rather than for the widget: the toolbar
        button, every clickable column heading and every chip in the Assets
        banner all land here. Selecting the contents row rather than scrolling
        directly is deliberate — the reader should be able to see *where* in
        the manual they just landed, and carry on from there.
        """
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Learn":
                self.tabs.setCurrentIndex(i)
                break
        if not anchor:
            return
        for row in range(self.learn_toc.count()):
            if self.learn_toc.item(row).data(Qt.UserRole) == anchor:
                self.learn_toc.setCurrentRow(row)
                return
        self.learn_view.scrollToAnchor(anchor)

    def _learn_goto(self, item, _previous=None) -> None:
        if item is not None:
            self.learn_view.scrollToAnchor(item.data(Qt.UserRole))

    def _learn_link(self, url: QUrl) -> None:
        """A cross-reference inside the page scrolls; anything else leaves."""
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            return
        fragment = url.fragment() or url.toString().lstrip("#")
        if fragment:
            self.learn_view.scrollToAnchor(fragment)

    def _learn_search(self) -> None:
        """Wrap around rather than stopping dead at the end of the document —
        a search that silently finds nothing because the cursor was already
        past the only match reads as a broken search box."""
        term = self.learn_find.text().strip()
        if not term:
            return
        if self.learn_view.find(term):
            self.learn_hint.setText("")
            return
        cursor = self.learn_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.learn_view.setTextCursor(cursor)
        found = self.learn_view.find(term)
        self.learn_hint.setText("" if found else f"nothing matches {term!r}")

    def _open_page(self, filename: str, what: str) -> None:
        """Open a bundled page in the default browser.

        ``static/`` ships inside the app bundle, so this resolves both frozen
        and from source. If it is somehow missing, say so in the status line
        rather than opening nothing and looking broken.
        """
        page = paths.resource_base() / "static" / filename
        if not page.exists():
            self._set_status(f"⚠  {what} not found at {page}", hold_s=True)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(page)))

    def _open_docs(self) -> None:
        self._open_page("docs.html", "documentation")

    def _open_testplan(self) -> None:
        self._open_page("testplan.html", "test plan")

    def _terminal_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        # -- this hour ------------------------------------------------------ #
        # Six figures used to sit in six equal cells, which told the reader
        # they mattered equally. They do not: the edge is the only number in
        # the app that is a disagreement with a market, so it is the biggest
        # thing on the screen and sits in the one highlighted cell; the price
        # anchors the left, and tau is drawn as the clock it is.
        strip = panel()
        g = QHBoxLayout(strip)
        g.setContentsMargins(16, 12, 16, 12)
        g.setSpacing(18)
        self.stats = {}

        def stat(key: str, tip: str, val_font=None) -> Stat:
            s = Stat(key, tip)
            if val_font is not None:
                s.val.setFont(val_font)
            self.stats[key] = s
            return s

        price_col = QVBoxLayout()
        price_col.setSpacing(4)
        price_col.addWidget(stat("price", "BTC/USD, live",
                                 theme.figure(21, True)))
        price_col.addWidget(stat("hour", "This hour's open → now"))
        g.addLayout(price_col)
        g.addWidget(_vline())
        g.addWidget(stat("model", "Our P(up) from the barrier model",
                         theme.figure(18, True)))
        g.addWidget(stat("market", "Polymarket's implied P(up)",
                         theme.figure(18, True)))

        edge_cell = QFrame()
        edge_cell.setObjectName("banner")
        el = QVBoxLayout(edge_cell)
        el.setContentsMargins(14, 8, 14, 8)
        el.addWidget(stat("edge", "Model minus market — our only disagreement",
                          theme.figure(20, True)))
        g.addWidget(edge_cell)
        g.addStretch(1)

        tau_col = QVBoxLayout()
        tau_col.setSpacing(5)
        tau_col.addWidget(stat("tau", "Fraction of the hour still to run"))
        self.hour_bar = HourBar()
        self.hour_bar.setFixedWidth(120)
        self.hour_bar.setToolTip("Fills as the hour runs; settles at :00.")
        tau_col.addWidget(self.hour_bar)
        tau_col.addStretch(1)
        g.addLayout(tau_col)
        lay.addWidget(strip)

        mid = QHBoxLayout()
        mid.setSpacing(10)
        self.lattice = Lattice()
        self.lattice.setToolTip("End-of-hour price distribution. Bars at or above "
                                "the open sum to P(up).")
        self.depth = DepthChart()
        mid.addWidget(self.lattice, 1)
        mid.addWidget(self.depth, 1)
        lay.addLayout(mid)

        self.equity = EquityCurve()
        self.equity.setToolTip("Paper bankroll. Everything left of the gold LIVE "
                               "divider is a fair-odds backtest with expected "
                               "value ≈ 0 — variance, not profit.")
        lay.addWidget(self.equity)

        # The ledger strip: what the paper book stands at, and how the model
        # is scoring against the market — one panel, because both are the
        # running account of the same bet.
        pstrip = panel()
        pg = QGridLayout(pstrip)
        pg.setContentsMargins(14, 10, 14, 10)
        pg.setVerticalSpacing(8)
        for i, (k, tip) in enumerate([
                ("bankroll", "Paper bankroll"), ("pnl", "Total paper P&L"),
                ("trades", "Settled live trades — the fair-odds warm-up rows "
                           "on the chart are not counted here"),
                ("win rate", "Share of live trades won"),
                ("profile", "Risk profile this bankroll was built under")]):
            s = Stat(k, tip)
            self.stats[k] = s
            pg.addWidget(s, 0, i)

        # Model vs market, scored on every hour watched — traded or not.
        # The direct test of the realised-vs-implied thesis, and it converges
        # at 24 observations a day instead of a few trades a week.
        # The line that says whether to trust the figures above, at their size
        # class rather than in small grey print below them.
        self.mvm = label("", "", theme.text(11), wrap=True)
        self.mvm.setToolTip(
            "Brier score (lower is better) of the model's P(up) against the\n"
            "market's, snapshotted mid-hour for every hour and settled on the\n"
            "real candle. Unlike the P&L this scores the hours the engine did\n"
            "NOT trade too, so it cannot be flattered by selection.")
        pg.addWidget(self.mvm, 1, 0, 1, 5)
        lay.addWidget(pstrip)

        self.read_panel = ReadPanel()
        lay.addWidget(self.read_panel)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.read_btn = QPushButton("LLM read on this hour")
        self.read_btn.clicked.connect(
            lambda: self._read("btc", "", "BTC/USD hourly up-or-down"))
        btn_row.addWidget(self.read_btn)
        lay.addLayout(btn_row)
        lay.addStretch(1)
        return w

    ASSETS_LOADING = ("Fetching prices for 129 markets — the first scan takes about "
                      "a minute.")
    # The other first-run lists. A bordered box with nothing in it looks broken,
    # so each says what it is waiting for (UX audit U-2).
    BOOK_EMPTY = "No trades yet — open one from the Screener."
    ALERTS_EMPTY = "Nothing yet — alerts need one scan to compare against."
    HEADLINES_LOADING = "Waiting for the first headlines…"
    SUGGESTIONS_LOADING = "Waiting for the first scan…"
    EVENTS_LOADING = "Waiting for the first calendar…"
    EVENTS_NONE = "No scheduled events found."

    def _scroll_tab(self, which: str, header: QWidget | None = None) -> QWidget:
        area = QScrollArea()
        area.setWidgetResizable(True)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(2, 8, 8, 8)
        lay.setSpacing(8)
        if which == "assets":
            # Before the first scan the board was an empty box under its column
            # headings — indistinguishable from a broken one.
            lay.addWidget(label(self.ASSETS_LOADING, "muted", theme.figure(10)))
        lay.addStretch(1)
        area.setWidget(host)
        setattr(self, f"_{which}_host", host)
        setattr(self, f"_{which}_lay", lay)
        setattr(self, f"_{which}_sig", None)
        if header is None:
            return area
        # Header sits outside the scroll area so it stays put while the rows
        # move under it.
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)
        wl.addWidget(header)
        wl.addWidget(area, 1)
        return wrap

    def _wire_tab(self) -> QWidget:
        """Breaking headlines, and the calendar of what is already scheduled."""
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(8)
        cols = QWidget()
        lay = QHBoxLayout(cols)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        alerts_panel = panel()
        al = QVBoxLayout(alerts_panel)
        al.setContentsMargins(14, 10, 14, 10)
        al.setSpacing(4)
        al.addWidget(label("WHAT CHANGED", "faint", theme.figure(8)))
        al.addWidget(label(
            "Fires on a transition, not on a level — news rising to Spike, "
            "volatility breaking from an instrument's own recent range, a "
            "scheduled catalyst arriving, heavy policy traffic. It tells you "
            "something moved and stops there: the score is a notability "
            "heuristic, five studies found no directional edge, and the "
            "blended score's measured IC is negative, so an alert shouting BUY "
            "would point at the wrong instruments with a straight face.",
            "faint", theme.figure(8), wrap=True))
        self.alert_list = label(self.ALERTS_EMPTY, "muted", theme.figure(9))
        self.alert_list.setWordWrap(True)
        al.addWidget(self.alert_list)
        outer.addWidget(alerts_panel)

        sugg = panel()
        sl = QVBoxLayout(sugg)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(6)
        sl.addWidget(label("WHAT THE NEWS IS POINTING AT", "faint", theme.figure(8)))
        sl.addWidget(label(
            "These are the names with something happening today — a place to "
            "look, not an edge. Over 25,504 historical setups a news spike beat "
            "the baseline by 0.8 points against a 3.1 error bar, and momentum "
            "by nothing at all. There is no best weekday either. What is exact "
            "is the exit: a target and a stop, typically resolving in 3-10 days. "
            "Direction is yours.", "faint", theme.figure(8), wrap=True))
        self._sugg_area = QScrollArea()
        self._sugg_area.setWidgetResizable(True)
        shost = QWidget()
        self._sugg_lay = QVBoxLayout(shost)
        self._sugg_lay.setContentsMargins(0, 4, 6, 4)
        self._sugg_lay.setSpacing(7)
        self._sugg_lay.addStretch(1)
        self._rebuild(self._sugg_lay, [], self.SUGGESTIONS_LOADING)
        self._sugg_area.setWidget(shost)
        sl.addWidget(self._sugg_area, 1)
        lay.addWidget(sugg, 3)

        left = panel()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 12, 14, 12)
        ll.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(label("NEWSWIRE", "faint", theme.figure(8)))
        head.addStretch(1)
        self.wire_meta = label("", "faint", theme.figure(8))
        head.addWidget(self.wire_meta)
        ll.addLayout(head)
        ll.addWidget(label(
            "Reuters, AP, Bloomberg and the FT are read through Google News — "
            "their own feeds are closed. dpa publishes no usable feed at all. "
            "Headlines are context and untrusted data: never an instruction, "
            "and no article body is fetched.", "faint", theme.figure(8), wrap=True))
        self._wire_area = QScrollArea()
        self._wire_area.setWidgetResizable(True)
        host = QWidget()
        self._wire_lay = QVBoxLayout(host)
        self._wire_lay.setContentsMargins(0, 4, 6, 4)
        self._wire_lay.setSpacing(5)
        self._wire_lay.addStretch(1)
        self._rebuild(self._wire_lay, [], self.HEADLINES_LOADING)
        self._wire_area.setWidget(host)
        ll.addWidget(self._wire_area, 1)
        lay.addWidget(left, 3)

        right = panel()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(6)
        rl.addWidget(label("SCHEDULED — EARNINGS & LISTINGS", "faint", theme.figure(8)))
        rl.addWidget(label(
            "A date is a fact; a direction is not. These sharpen *when* to look, "
            "never which way to lean.", "faint", theme.figure(8), wrap=True))
        self._events_area = QScrollArea()
        self._events_area.setWidgetResizable(True)
        ehost = QWidget()
        self._events_lay = QVBoxLayout(ehost)
        self._events_lay.setContentsMargins(0, 4, 6, 4)
        self._events_lay.setSpacing(5)
        self._events_lay.addStretch(1)
        self._rebuild(self._events_lay, [], self.EVENTS_LOADING)
        self._events_area.setWidget(ehost)
        rl.addWidget(self._events_area, 1)
        lay.addWidget(right, 2)
        outer.addWidget(cols, 1)

        self._wire_sig = None
        return w

    def _refresh_alerts(self) -> None:
        with self.live.lock:
            rows = list(self.live.alerts)
        if not rows:
            self.alert_list.setText(self.ALERTS_EMPTY)
            return
        out = []
        for a in rows[:6]:
            age = f"  ·  data {a['data_age_s'] // 60:.0f} min old" if a["stale"] else ""
            out.append(f"· {a['symbol']} — {a['message']}{age}")
        self.alert_list.setText("\n".join(out))

    def _refresh_wire(self) -> None:
        """Render the Wire from what the poll thread has already fetched.

        These two reads used to be `news.headlines()` and `events.payload()`,
        both of which fetch when their cache ages out — twenty-four feeds at a
        ten-second timeout, and a calendar walk, on the *UI thread*. Whichever
        of the two threads reached an expired cache first did the work, so every
        eight minutes there was a chance the window froze for up to half a
        minute: the event loop stopped, nothing repainted, and SONAR showed a
        blank white rectangle that ignored the close button.

        The cache-only accessors cannot fetch. If the poll thread has not
        filled them yet the panel is briefly empty, which is the right
        trade — an empty panel that repaints beats a full one behind a frozen
        window.
        """
        self._refresh_alerts()
        try:
            heads = self.live.news.cached()
            ev = self.live.events.cached_payload()
        except Exception:
            return
        # The asset scan has to be part of this key. Suggestions are built from
        # it, and it lands *after* the news does — gating the rebuild on
        # headlines alone left the panel permanently empty.
        with self.live.lock:
            asset_gen = self.live.assets.get("generated")
        sig = (len(heads), ev.get("generated"), asset_gen)
        if sig == self._wire_sig:
            return
        self._wire_sig = sig

        fresh = sorted((h for h in heads if h.dated),
                       key=lambda h: h.ts, reverse=True)[:60]
        # Spread, not just volume. Twenty-four feeds all repeating one bloc is
        # a different picture from the same count across nine, and the header is
        # the cheapest place to make that visible.
        spread = news_mod.bloc_spread(heads)
        state = spread["state_share"]
        self.wire_meta.setText(
            f'{len(heads)} headlines · {len({h.source for h in heads})} sources · '
            f'{spread["n_blocs"]} press blocs · {state * 100:.0f}% state-directed')
        rows = []
        for h in fresh:
            rows.append(TickerRow(h))
        # An empty cache is "not fetched yet" as far as the UI can tell: the
        # feeds keep retrying, so "waiting" stays true until one answers.
        self._rebuild(self._wire_lay, rows, self.HEADLINES_LOADING)

        try:
            sg = self.live.suggestions()
        except Exception:
            sg = []
        self._rebuild(self._sugg_lay,
                      [SuggestionCard(s, self._trade) for s in sg],
                      "Nothing with elevated coverage right now — which is a\n"
                      "normal state, not a failure to find something."
                      if asset_gen else self.SUGGESTIONS_LOADING)

        items = []
        for e in ev.get("earnings", [])[:25]:
            items.append(EventRow(f'{e["symbol"]}', f'earnings · {e["when"]}',
                                  f'{e["days_away"]}d', theme.GOLD))
        for l in ev.get("listings", [])[:15]:
            sym = l["symbol"] or "—"
            items.append(EventRow(sym, f'IPO {l["status"]} · {l["company"][:26]}',
                                  l["price"] or "", theme.UP))
        self._rebuild(self._events_lay, items,
                      self.EVENTS_NONE if ev.get("generated") else self.EVENTS_LOADING)

    def _book_tab(self) -> QWidget:
        """Open paper positions, and the only page that grades the app itself."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        head = panel()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 12, 14, 12)
        hl.setSpacing(26)
        self.book_stats = {}
        for k, tip in [("equity", "Cash plus the marked value of open positions."),
                       ("total p/l", "Against the starting paper cash."),
                       ("open", "Positions currently held."),
                       ("closed", "Positions that have resolved."),
                       ("win rate", "Share of closed positions that made money."),
                       ("unrealised", "Mark-to-market on what is still open.")]:
            s = Stat(k, tip)
            self.book_stats[k] = s
            hl.addWidget(s)
        hl.addStretch(1)
        # The calibration protocol: systematic, coin-flip-direction paper
        # entries so the table below fills with measurement instead of
        # discretion — or staying empty forever on an unclicked install.
        self.protocol_box = QCheckBox("protocol mode")
        self.protocol_box.setFont(theme.figure(9))
        self.protocol_box.setChecked(self.live.protocol_on)
        self.protocol_box.setToolTip(
            "Once a day, open small fixed-risk paper positions on the five\n"
            "highest- and five lowest-confidence rows, direction chosen by\n"
            "coin flip. Random on purpose: the score claims notability, not\n"
            "direction, and a coin flip isolates exactly the claim the\n"
            "calibration table tests. Measurement, not a strategy — and\n"
            "paper money only, as ever.")
        self.protocol_box.toggled.connect(self.live.set_protocol)
        hl.addWidget(self.protocol_box)
        lay.addWidget(head)

        cal = panel()
        cl = QVBoxLayout(cal)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(4)
        ch = QHBoxLayout()
        ch.addWidget(label("CALIBRATION — DOES A HIGH SCORE ACTUALLY WIN?",
                           "faint", theme.figure(8)))
        ch.addStretch(1)
        self.bt_btn = QPushButton("run backtest")
        self.bt_btn.setFont(theme.figure(9))
        self.bt_btn.setToolTip(
            "Replay the same plan over two years of real bars — five on the\n"
            "year profile, whose horizon two years are too short to test.\n"
            "Live positions take months to grade; this answers today —\n"
            "for the price half of the score, which is all history can test.")
        self.bt_btn.clicked.connect(self._run_backtest)
        ch.addWidget(self.bt_btn)
        cl.addLayout(ch)
        self.cal_verdict = label("—", font=theme.text(12))
        self.cal_verdict.setWordWrap(True)
        cl.addWidget(self.cal_verdict)
        self.cal_table = label("", "muted", theme.figure(10), wrap=True)
        cl.addWidget(self.cal_table)
        self.bt_result = label("", "muted", theme.figure(10))
        self.bt_result.setTextFormat(Qt.PlainText)     # shows error text
        self.bt_result.setWordWrap(True)
        cl.addWidget(self.bt_result)
        self.book_shadow = ShadowGrade(detail=True, on_help=self._show_learn)
        cl.addWidget(self.book_shadow)
        lay.addWidget(cal)

        area = QScrollArea()
        area.setWidgetResizable(True)
        host = QWidget()
        self._book_lay = QVBoxLayout(host)
        self._book_lay.setContentsMargins(2, 4, 8, 8)
        self._book_lay.setSpacing(8)
        self._book_lay.addStretch(1)
        self._rebuild(self._book_lay, [], self.BOOK_EMPTY)
        area.setWidget(host)
        lay.addWidget(area, 1)
        self._book_sig = None
        return w

    def _refresh_book(self) -> None:
        with self.live.lock:
            pos = dict(self.live.positions)
            cal = dict(self.live.calibration)
            shadow = self.live.shadow
        st = pos.get("stats", {})
        pnl = st.get("total_pnl", 0.0)
        for key, val, col in [
            ("equity", f'${st.get("equity", 0):,.0f}', theme.INK),
            ("total p/l", f'{pnl:+,.0f}', theme.pnl_color(pnl)),
            ("open", str(st.get("n_open", 0)), theme.INK),
            ("closed", str(st.get("n_closed", 0)), theme.INK),
            ("win rate", f'{st.get("win_rate", 0):.0f}%', theme.INK),
            ("unrealised", f'{st.get("unrealised", 0):+,.0f}',
             theme.pnl_color(st.get("unrealised", 0))),
        ]:
            self.book_stats[key].set(val, col)

        self.cal_verdict.setText(cal.get("verdict", "—"))
        rows = []
        mostly_open = []
        buckets = cal.get("buckets", [])
        for b, (n_open, age) in zip(buckets, _open_by_band(buckets, pos.get("open") or [])):
            if not b["n"] and not n_open:
                continue
            hr = "—" if not b["enough"] else f'{b["hit_rate"]*100:.0f}%'
            note = "" if b["enough"] else f'  (need {cal.get("min_sample", 20)})'
            still = (f"  still open {n_open} (median age {_open_span(age)})"
                     if n_open else "")
            rows.append(f'  score {b["lo"]:>3}–{_band_top(b):<3}  n={b["n"]:<4} '
                        f'hit {hr:<5} vs advertised {b["expected"]*100:.0f}%{note}{still}'
                        if b["n"] else
                        f'  score {b["lo"]:>3}–{_band_top(b):<3}  n=0{still}')
            if n_open / (b["n"] + n_open) >= CENSORED_SHARE:
                mostly_open.append(f'{b["lo"]}–{_band_top(b)}')
        if cal.get("n_manual"):
            rows.append(f"  {cal['n_manual']} closed by hand — not graded, and not in the "
                        "counts above")
        if mostly_open:
            rows.append(f"  provisional: slow positions are missing from this grade — "
                        f"{CENSORED_SHARE * 100:.0f}% or more of the positions entered "
                        f"at scores {', '.join(mostly_open)} are still open")
        self.cal_table.setText("\n".join(rows) or
                               "  no closed positions yet — nothing to grade")
        # After the existing grade, so nothing the shadow does can hold it up.
        self.book_shadow.render(shadow, self._shadow_t_default())

        sig = (st.get("n_open"), st.get("n_closed"), round(st.get("unrealised", 0), 1))
        if sig == self._book_sig:
            return
        self._book_sig = sig
        self._rebuild(self._book_lay,
                      [PositionRow(p, self._close_position)
                       for p in pos.get("open", [])],
                      self.BOOK_EMPTY)

    # -- portfolio: the landing page --------------------------------------- #
    CARD_COLUMNS = 3

    def _portfolio_tab(self) -> QWidget:
        """The landing page: the reader's own practice money, as a picture.

        Built from `self.live.positions` alone — the paper book — which is
        independent of the hourly engine, so it renders while the first poll
        is in flight and when another SONAR holds the engine lock. Four
        things, top to bottom: the figures as a hierarchy (the profit or loss
        is the biggest, because it is the question), the account's value over
        time, every position at a glance beside what already resolved, and a
        card per position. The page scrolls; the strip and the curve are what
        a short screen sees first.
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 8, 8)
        lay.setSpacing(10)

        strip = panel()
        g = QHBoxLayout(strip)
        g.setContentsMargins(16, 12, 16, 12)
        g.setSpacing(22)
        self.pstats: dict[str, Stat] = {}
        self.plines: dict[str, QLabel] = {}

        def stat(key: str, tip: str, size: int) -> Stat:
            s = Stat(key, tip)
            s.val.setFont(theme.figure(size, True))
            self.pstats[key] = s
            return s

        def cell(key: str, tip: str, size: int) -> QVBoxLayout:
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(stat(key, tip, size))
            line = label("", "faint", theme.figure(9), wrap=True)
            self.plines[key] = line
            col.addWidget(line)
            return col

        banner = QFrame()
        banner.setObjectName("banner")
        banner.setMinimumWidth(284)      # the line under the figure, unwrapped
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(14, 8, 14, 8)
        bl.addLayout(cell("p&l now", "Account value minus the cash you started "
                          "with: what is open plus what has closed.", 24))
        g.addWidget(banner)
        g.addWidget(_vline())
        g.addLayout(cell("equity", "Cash plus what the open positions are worth "
                         "right now.", 18))
        g.addLayout(cell("invested", "What the open positions committed at entry. "
                         "A long spends cash; a short borrows stock — both are "
                         "counted, and the line under says which is which.", 18))
        g.addLayout(cell("at risk", "What the open positions would lose if every "
                         "stop was hit — the figure the risk profile controls.", 18))
        g.addLayout(cell("closed", "Positions that have resolved, and how many "
                         "of them made money.", 18))
        g.addStretch(1)
        self.start_card = self._start_card()
        lay.addWidget(self.start_card)
        lay.addWidget(strip)

        # -- is the score right? ------------------------------------------- #
        # The question the app exists to answer, on the page it opens on.
        # Everything in it is measurement: the verdict `calibration.report`
        # reaches, the score bands it reaches it from, and what is still
        # missing before it may claim anything. The profit figures above
        # cannot answer it — a coin-flip position's profit is luck — and no
        # direction is ever in it.
        grade = panel()
        gl = QVBoxLayout(grade)
        gl.setContentsMargins(14, 10, 14, 10)
        gl.setSpacing(4)
        gh = QHBoxLayout()
        gh.addWidget(HelpHeading(
            ("IS THE SCORE RIGHT?", "CALIBRATION"), "grading",
            "Does a high confidence score hit its target more often than the "
            "plan promised? Graded on positions that resolved, never on opinion.",
            self._show_learn))
        gh.addStretch(1)
        self.grade_count = label("", "faint", theme.figure(8))
        gh.addWidget(self.grade_count)
        gl.addLayout(gh)
        self.grade_verdict = label("—", font=theme.text(12), wrap=True)
        gl.addWidget(self.grade_verdict)
        # Wraps: a band's line now carries its open count and age as well, and
        # an unwrapped label that long sets a floor under the window's width.
        self.grade_rows = label("", "muted", theme.figure(10), wrap=True)
        gl.addWidget(self.grade_rows)
        self.grade_next = label("", "faint", theme.figure(9), wrap=True)
        gl.addWidget(self.grade_next)
        self.shadow_grade = ShadowGrade(detail=False, on_help=self._show_learn)
        gl.addWidget(self.shadow_grade)
        lay.addWidget(grade)

        self.account_curve = AccountCurve()
        self.account_curve.setToolTip(
            "Cash plus what the open positions are worth, over time. The engine\n"
            "logs a point an hour and one at every entry or exit; the days\n"
            "before the log existed are rebuilt from the book's own records\n"
            "and real daily closes. The dashed line is the cash you started with.")
        lay.addWidget(self.account_curve)

        mid = QHBoxLayout()
        mid.setSpacing(10)
        tiles = panel()
        tl = QVBoxLayout(tiles)
        tl.setContentsMargins(14, 10, 14, 10)
        tl.setSpacing(4)
        th = QHBoxLayout()
        th.addWidget(label("ALL POSITIONS AT A GLANCE", "faint", theme.figure(8)))
        th.addStretch(1)
        self.tiles_line = label("", "faint", theme.figure(8))
        th.addWidget(self.tiles_line)
        tl.addLayout(th)
        self.tiles = PositionTiles()
        self.tiles.setMinimumHeight(186)
        tl.addWidget(self.tiles, 1)
        tl.addWidget(label("one tile per position · its size is what it can lose "
                           "· its colour is how it is doing · rest the pointer "
                           "on one", "faint", theme.figure(8), wrap=True))
        mid.addWidget(tiles, 3)

        closed = panel()
        cl = QVBoxLayout(closed)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(4)
        ch = QHBoxLayout()
        ch.addWidget(label("RECENTLY CLOSED", "faint", theme.figure(8)))
        ch.addStretch(1)
        self.closed_line = label("", "faint", theme.figure(8))
        ch.addWidget(self.closed_line)
        cl.addLayout(ch)
        self._closed_lay = QVBoxLayout()
        self._closed_lay.setSpacing(0)
        cl.addLayout(self._closed_lay, 1)
        cl.addWidget(label("the full list, and the grading of every closed "
                           "trade, is on My trades", "faint", theme.figure(8),
                           wrap=True))
        mid.addWidget(closed, 2)
        lay.addLayout(mid)

        eh = QHBoxLayout()
        eh.addWidget(label("EACH POSITION", "faint", theme.figure(8)))
        eh.addStretch(1)
        self.cards_line = label("", "faint", theme.figure(8))
        eh.addWidget(self.cards_line)
        lay.addLayout(eh)
        host = QWidget()
        host.setObjectName("cell")
        self._cards_grid = QGridLayout(host)
        self._cards_grid.setContentsMargins(0, 0, 0, 0)
        self._cards_grid.setSpacing(10)
        lay.addWidget(host)
        self._cards: dict[str, PositionCard] = {}
        self._cards_empty = label("No open positions. Use buy or short on the "
                                  "Screener.", "muted", theme.figure(10))
        lay.addWidget(self._cards_empty)
        lay.addStretch(1)
        self._portfolio_sig = None
        self._curve_sig = None
        return w

    def _shadow_t_default(self) -> float:
        """T for the preset protocol entries are made under, for the shadow
        block's words before any entry carries its own."""
        return calibration_mod.shadow_t_days(self.live.horizon.name)

    def _refresh_grade(self, cal: dict, closed: list, open_rows: list) -> None:
        """The calibration verdict in the words the manual uses (§10), plus
        what the verdict still lacks. Reads the same report My trades does.

        The report grades only positions that have closed, and the book has no
        time stop, so the grade is made of the quick ones. Each band's line
        therefore also says how many of its entries are still open and how old
        they are, and a band that is mostly open is named in the caveat.
        `closed` is only the latest forty rows; the closed count per band is
        the report's, which covers the whole book."""
        n = cal.get("n_settled", 0)
        need = cal.get("min_sample", 20)
        self.grade_verdict.setText(cal.get("verdict") or "—")
        rows = []
        mostly_open = []
        buckets = cal.get("buckets", [])
        for b, (n_open, age) in zip(buckets, _open_by_band(buckets, open_rows)):
            n_closed = b.get("n", 0)
            entered = n_closed + n_open
            if not entered:
                continue
            still = (f"{n_open} still open (median age {_open_span(age)})"
                     if n_open else "none still open")
            line = (f'scores {b["lo"]}–{_band_top(b)}:  {entered} entered, '
                    f'{still} · {n_closed} closed')
            if n_closed:
                wins = round(b["hit_rate"] * n_closed)
                note = "" if b.get("enough") else f"   (a band needs {need} to count)"
                line += (f' · {wins} won ({b["hit_rate"]*100:.0f}%) · the plan '
                         f'promised {b["expected"]*100:.0f}%{note}')
            rows.append(line)
            if n_open / entered >= CENSORED_SHARE:
                mostly_open.append(f'{b["lo"]}–{_band_top(b)}')
        if cal.get("enough") and cal.get("overall_hit_rate") is not None:
            line = (f'all {n}:  {cal["overall_hit_rate"]*100:.0f}% won against '
                    f'{(cal.get("advertised_rate") or 0)*100:.0f}% promised')
            if cal.get("score_ic") is not None:
                line += f' · rank correlation {cal["score_ic"]:+.2f}'
            rows.append(line)
        self.grade_rows.setText("\n".join(rows) or
                                "no closed positions yet — nothing to grade")
        self.grade_count.setText(f"{n} graded" if n else "")
        manual = cal.get("n_manual", 0)
        if manual:
            rows.append(f"{manual} closed by hand — not graded, and not in the counts "
                        "above: the odds are about reaching the target or the stop")
            self.grade_rows.setText("\n".join(rows))

        parts = []
        if mostly_open:
            where = (mostly_open[0] if len(mostly_open) == 1 else
                     ", ".join(mostly_open[:-1]) + " and " + mostly_open[-1])
            lead = ("the verdict is provisional" if cal.get("enough")
                    else "any verdict is provisional")
            parts.append(f"{lead}: slow positions are missing from the grade — "
                         f"{CENSORED_SHARE * 100:.0f}% or more of the positions "
                         f"entered at scores {where} are still open")
        if n < need:
            parts.append(f"{n} of the {need} closed positions a verdict needs — "
                         f"{need - n} to go")
        by_protocol = sum(1 for c in closed if c.get("protocol"))
        if by_protocol and n <= len(closed):
            parts.append(f"{by_protocol} of the {n} opened by protocol mode, direction "
                         f"by coin flip, so this grades the score and not a picker")
        if self.live.protocol_on:
            parts.append("protocol mode is on: up to 10 a day, resolving in a median "
                         "of 6 trading days")
        else:
            parts.append("protocol mode is off (My trades) — on, it fills this without "
                         "your own picks, which would grade you rather than the score")
        parts.append("the score claims that something is happening, never which way; "
                     "profit cannot grade it, because a coin-flip position's profit "
                     "is luck")
        self.grade_next.setText(" · ".join(parts))

    def _start_card(self) -> QWidget:
        """Start here — on an empty book, until the first trade or "Got it".
        A first launch used to open on a page of zeros with nothing saying
        what any of it was or what to do."""
        card = panel()
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(6)
        v.addWidget(label("START HERE", "muted", theme.figure(9, True)))
        body = label(
            "This is a paper book: practice money, never a real account.\n"
            "1.  Open the Screener and pick a row marked “worth a look” — the score "
            "says something is happening, never which way.\n"
            "2.  Press Buy or Short. The app sets the target and the stop; the "
            "position closes itself when it reaches one of them.\n"
            "3.  Come back here: this page shows how the book is doing and whether "
            "the score kept to its odds. The Learn tab explains every number.",
            "", theme.text(11), wrap=True)
        body.setTextFormat(Qt.PlainText)
        v.addWidget(body)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("Got it")
        ok.setFont(theme.text(10))
        ok.clicked.connect(self._dismiss_start_card)
        row.addWidget(ok)
        v.addLayout(row)
        card.setVisible(False)
        return card

    def _onboarding_file(self):
        return paths.user_data_base() / "onboarding.json"

    def _dismiss_start_card(self) -> None:
        self._start_dismissed = True       # sticks for this run even if the file can't be written
        try:
            paths.write_atomically(self._onboarding_file(), '{"start_card_dismissed": true}')
        except OSError:
            pass
        self.start_card.setVisible(False)

    def _sync_start_card(self, pos: dict) -> None:
        if getattr(self, "_start_dismissed", None) is None:     # read once
            self._start_dismissed = bool(paths.read_preferences(
                self._onboarding_file()).get("start_card_dismissed"))
        empty = not pos.get("open") and not pos.get("closed") \
            and not (pos.get("stats") or {}).get("n_closed")
        self.start_card.setVisible(empty and not self._start_dismissed)

    def _refresh_portfolio(self) -> None:
        with self.live.lock:
            pos = dict(self.live.positions)
            cal = dict(self.live.calibration)
            shadow = self.live.shadow
        self._sync_start_card(pos)
        st = pos.get("stats") or {}
        if st:
            self._refresh_grade(cal, pos.get("closed") or [], pos.get("open") or [])
        # After the existing grade, so nothing the shadow does can hold it up.
        self.shadow_grade.render(shadow, self._shadow_t_default())
        if not st:
            return
        pnl = st.get("total_pnl", 0.0)
        self.pstats["p&l now"].set(_money(pnl, signed=True), theme.pnl_color(pnl))
        self.plines["p&l now"].setText(
            f'{st.get("return_pct", 0):+.2f}%  ·  {st.get("unrealised", 0):+,.2f} open'
            f'  ·  {st.get("realised", 0):+,.2f} closed')
        self.pstats["equity"].set(f'${st.get("equity", 0):,.0f}')
        self.plines["equity"].setText(
            f'started with ${st.get("starting_cash", 0):,.0f} · '
            f'${st.get("cash", 0):,.0f} cash free')
        long_cash, short_notional = st.get("long_cash", 0), st.get("short_notional", 0)
        self.pstats["invested"].set(f"${long_cash + short_notional:,.0f}")
        self.plines["invested"].setText(
            f'${long_cash:,.0f} of your cash in {st.get("n_long", 0)} longs · '
            f'${short_notional:,.0f} borrowed for {st.get("n_short", 0)} shorts')
        risk = st.get("at_risk", 0)
        self.pstats["at risk"].set(_money(-risk, signed=True, places=0) if risk else "$0",
                                   theme.DOWN if risk else theme.INK)
        equity = st.get("equity") or 1.0
        self.plines["at risk"].setText(
            f'{risk / equity * 100:.1f}% of the account · {st.get("n_open", 0)} stops set')
        n_closed, wins = st.get("n_closed", 0), st.get("n_wins", 0)
        self.pstats["closed"].set(str(n_closed))
        self.plines["closed"].setText(
            f'{wins} won · {n_closed - wins} lost · {st.get("realised", 0):+,.2f}')

        points = pos.get("equity") or []
        curve_sig = (len(points), points[-1]["t"] if points else 0,
                     points[-1]["v"] if points else 0)
        if curve_sig != self._curve_sig:
            self._curve_sig = curve_sig
            self.account_curve.set_data(points, st.get("starting_cash"))

        rows = pos.get("open", [])
        sig = (tuple(p["id"] for p in rows),
               tuple(round(p.get("unrealised") or 0.0, 2) for p in rows),
               n_closed)
        if sig == self._portfolio_sig:
            return
        self._portfolio_sig = sig
        self.tiles.set_rows(rows)
        self.tiles_line.setText(
            f'{len(rows)} open · {st.get("n_long", 0)} long · {st.get("n_short", 0)} short')

        # Cards update in place; the grid is only re-laid when the set of
        # positions changes. Order is newest first and stays put — a page you
        # look at every day should not reshuffle under your eyes.
        ids = [p["id"] for p in rows]
        for pid in list(self._cards):
            if pid not in ids:
                self._cards.pop(pid).deleteLater()
        for p in rows:
            card = self._cards.get(p["id"])
            if card is None:
                self._cards[p["id"]] = PositionCard(p, self._close_position)
            else:
                card.set_row(p)
        if ids != getattr(self, "_card_order", None):
            self._card_order = ids
            while self._cards_grid.count():
                self._cards_grid.takeAt(0)
            order = sorted(rows, key=lambda p: -(p.get("opened_at") or 0))
            for i, p in enumerate(order):
                self._cards_grid.addWidget(self._cards[p["id"]],
                                           i // self.CARD_COLUMNS, i % self.CARD_COLUMNS)
        self._cards_empty.setVisible(not rows)
        self.cards_line.setText(
            f"{len(rows)} positions, newest first · gold ┄ entry · blue ┄ target "
            f"· orange ┄ stop" if rows else "")

        self._rebuild(self._closed_lay,
                      [ClosedRow(c) for c in (pos.get("closed") or [])[:6]],
                      "nothing has closed yet")
        self.closed_line.setText(f"last {min(6, n_closed)} of {n_closed}" if n_closed else "")

    # -- lab ---------------------------------------------------------------- #
    def _lab_tab(self) -> QWidget:
        """Run the algorithm against history, with the knobs exposed.

        The Book tab's backtest button answers one fixed question. This answers
        whichever one you ask, and the point is falsification rather than
        reassurance: on a market with nothing to find, the realised hit rate
        must meet `1/(1+R:R)` — 40% at the shipped 1.5:1 — because that
        identity is the claim the whole app rests on, and tests/test_backtest.py
        holds the backtest to it. There is no reward:risk control here: at 2:1
        and wider the backtest drops enough timed-out trials to bias its own
        baseline (QA plan, 2026-10-10), so adding one starts with fixing that.

        Everything runs on real bars through `sonar.backtest` — the same replay
        the research used, not a separate toy.
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)

        head = panel()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(14, 12, 14, 12)
        hl.setSpacing(6)
        hl.addWidget(label("SIMULATE AND TEST", "faint", theme.figure(8)))
        hl.addWidget(label(
            "Replays the plan over real historical bars: momentum and volatility "
            "from prior bars only, then walks forward through actual highs and "
            "lows. A bar that spans both barriers counts as a loss, because daily "
            "data cannot say which came first, and costs are excluded — so the "
            "truth is worse than whatever this prints.",
            "faint", theme.figure(8), wrap=True))

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(4)

        self.lab_universe = QComboBox()
        self.lab_universe.addItem("Whole watchlist", "all")
        for cls in ("Equity", "Index", "Forex", "Crypto", "Commodity"):
            self.lab_universe.addItem(cls, cls)
        self._lab_result = None          # the last run, re-rendered on a wording switch
        self.lab_range = QComboBox()
        for r in ("1y", "2y", "5y", "10y"):
            self.lab_range.addItem(r, r)
        self.lab_range.setCurrentText("2y")

        self.lab_horizon = QSpinBox()
        self.lab_horizon.setRange(1, 250)
        self.lab_horizon.setValue(5)
        self.lab_step = QSpinBox()
        self.lab_step.setRange(1, 30)
        self.lab_step.setValue(3)
        self.lab_news = QCheckBox("include attention (one extra request per symbol)")
        self.lab_catalyst = QCheckBox("include earnings history (US equities, via EDGAR)")
        self.lab_catalyst.setToolTip(
            "Attributes the catalyst weight against real Item-2.02 8-K filing\n"
            "dates — the component that was untested until Sep 2026, and the\n"
            "first to come back KEEP. ADRs carry no such filings and are\n"
            "skipped honestly.")

        for col, cap in enumerate(("UNIVERSE", "RANGE", "HORIZON (DAYS)", "STEP (BARS)")):
            form.addWidget(label(cap, "faint", theme.figure(8)), 0, col)
        form.addWidget(self.lab_universe, 1, 0)
        form.addWidget(self.lab_range, 1, 1)
        form.addWidget(self.lab_horizon, 1, 2)
        form.addWidget(self.lab_step, 1, 3)
        self.lab_captions = {}
        for key, col in (("horizon", 2), ("step", 3)):
            cap = label(PRACTICE_CAPTIONS[key], "faint", theme.figure(8), wrap=True)
            self.lab_captions[key] = cap
            form.addWidget(cap, 2, col)
        hl.addLayout(form)
        hl.addWidget(self.lab_news)
        hl.addWidget(self.lab_catalyst)

        row = QHBoxLayout()
        self.lab_btn = QPushButton("Run simulation")
        self.lab_btn.setFixedWidth(150)
        self.lab_btn.clicked.connect(self._lab_run)
        row.addWidget(self.lab_btn)
        self.lab_status = label("", "faint", theme.figure(9))
        self.lab_status.setTextFormat(Qt.PlainText)     # shows error text
        row.addWidget(self.lab_status, 1)
        hl.addLayout(row)
        lay.addWidget(head)

        self.lab_out = QTextBrowser()
        self.lab_out.setOpenExternalLinks(False)
        self.lab_out.setOpenLinks(False)
        self.lab_out.setHtml(
            "<p style='color:#7c8798'>No run yet. A whole-watchlist 2y replay takes "
            "a few seconds and hits the network once per instrument.</p>")
        lay.addWidget(self.lab_out, 1)

        # --- replay: the same history, but you make the calls ---------------- #
        rep = panel()
        rl = QVBoxLayout(rep)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(6)
        rl.addWidget(label("REPLAY — YOUR CALLS", "faint", theme.figure(8)))
        rl.addWidget(label(
            "The run above grades the model. This grades you. One setup at a "
            "time on real history, with everything after the cursor withheld — "
            "the chart stops where you are, so there is nothing to peek at. "
            "Call it or skip it; the model's call on the same setup is scored "
            "alongside yours either way, so skipping the hard ones cannot look "
            "like skill.",
            "faint", theme.figure(8), wrap=True))

        rrow = QHBoxLayout()
        self.rep_symbol = QComboBox()
        for sym, name, cls, _kw in asset_mod.WATCHLIST:
            self.rep_symbol.addItem(f"{name} ({sym})", sym)
        self.rep_stake = QSpinBox()
        self.rep_stake.setRange(10, 10_000)
        self.rep_stake.setValue(100)
        self.rep_stake.setPrefix("risk ")
        self.rep_stake.setSuffix(" per call")
        self.rep_start = QPushButton("Start replay")
        self.rep_start.setFixedWidth(130)
        self.rep_start.clicked.connect(self._replay_start)
        rrow.addWidget(self.rep_symbol, 1)
        rrow.addWidget(self.rep_stake)
        rrow.addWidget(self.rep_start)
        rl.addLayout(rrow)

        self.rep_setup = label("", "muted", theme.figure(10))
        self.rep_setup.setWordWrap(True)
        rl.addWidget(self.rep_setup)
        self.rep_spark = Sparkline(46)
        self.rep_spark.setFixedHeight(52)
        rl.addWidget(self.rep_spark)

        arow = QHBoxLayout()
        self.rep_long = QPushButton("Buy")
        self.rep_short = QPushButton("Short")
        self.rep_skip = QPushButton("Skip")
        for b, choice in ((self.rep_long, "LONG"), (self.rep_short, "SHORT"),
                          (self.rep_skip, "SKIP")):
            b.setFixedWidth(92)
            b.setEnabled(False)
            b.clicked.connect(lambda _=False, c=choice: self._replay_decide(c))
            arow.addWidget(b)
        self.rep_last = label("", "faint", theme.figure(9))
        arow.addWidget(self.rep_last, 1)
        rl.addLayout(arow)

        self.rep_card = QTextBrowser()
        self.rep_card.setOpenExternalLinks(False)
        self.rep_card.setFixedHeight(150)
        self.rep_card.setOpenLinks(False)
        self.rep_card.setHtml("<p style='color:#7c8798'>No replay running.</p>")
        rl.addWidget(self.rep_card)
        lay.addWidget(rep)

        # -- the sports models, measurable from where the other models are -- #
        sports = panel()
        sl = QVBoxLayout(sports)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(6)
        sl.addWidget(label("SPORTS MODELS — MEASURE", "faint", theme.figure(8)))
        sl.addWidget(label(
            "The same gate the markets side runs, for the ratings behind the "
            "Sports tab: fetch seasons of real results, predict every game "
            "from a table that has only seen the earlier ones, and score the "
            "predictions against the base rate. KEEP is what lets a model "
            "size a stake; anything else cannot. Until now this ran from a "
            "script, so a change to the rating could not be re-measured from "
            "inside the app.", "faint", theme.figure(8), wrap=True))
        srow = QHBoxLayout()
        srow.setSpacing(8)
        self.sm_sport = QComboBox()
        for sp in playmaker.list_sports():
            if sp.has_model and sp.has_results:
                self.sm_sport.addItem(sp.name, sp.key)
        srow.addWidget(self.sm_sport)
        srow.addWidget(label("seasons", "faint", theme.figure(8)))
        self.sm_seasons = QSpinBox()
        self.sm_seasons.setRange(2, 6)
        self.sm_seasons.setValue(3)
        self.sm_seasons.setToolTip(
            "Years of results to fetch. The verdict needs 200 scored games\n"
            "after the burn-in, so thin leagues want more seasons.")
        srow.addWidget(self.sm_seasons)
        self.sm_btn = QPushButton("measure")
        self.sm_btn.setFixedWidth(120)
        self.sm_btn.clicked.connect(self._sports_measure)
        srow.addWidget(self.sm_btn)
        self.sm_status = label("", "faint", theme.figure(9))
        srow.addWidget(self.sm_status, 1)
        sl.addLayout(srow)
        self.sm_result = label("", "muted", theme.figure(10), wrap=True)
        self.sm_result.setTextFormat(Qt.PlainText)     # shows error text
        sl.addWidget(self.sm_result)
        lay.addWidget(sports)

        # -- the hourly bitcoin model: the live experiment ------------------- #
        # It was the landing page until Oct 2026. It is an experiment the
        # engine runs around the clock, not something the reader holds, so it
        # sits with the other measurements — still the only place in the app
        # with an independent model, still scored against the market on every
        # hour. `_terminal_tab()` is unchanged; it is hosted here.
        model = panel()
        ml = QVBoxLayout(model)
        ml.setContentsMargins(14, 12, 14, 12)
        ml.setSpacing(6)
        ml.addWidget(label("THE HOURLY BITCOIN MODEL — THE LIVE EXPERIMENT",
                           "faint", theme.figure(8)))
        ml.addWidget(label(
            "The one place SONAR says which way it thinks something goes. A "
            "probability model prices each hour of bitcoin, compares itself "
            "to Polymarket, takes at most one simulated bet with its own "
            "practice cash — separate from yours — and grades itself against "
            "the market on every hour, traded or not.",
            "faint", theme.figure(8), wrap=True))
        ml.addWidget(self._terminal_tab())
        lay.addWidget(model)
        return w

    # -- sports measurement -------------------------------------------------#
    def _sports_measure(self) -> None:
        if self._sports_thread is not None and self._sports_thread.isRunning():
            return
        key = self.sm_sport.currentData()
        self.sm_btn.setEnabled(False)
        self.sm_status.setText(f"measuring {key}…")
        self.sm_result.setText("")
        self._sports_thread = SportsMeasureThread(key, self.sm_seasons.value(),
                                                  self)
        self._sports_thread.progress.connect(self.sm_status.setText)
        self._sports_thread.done.connect(self._sports_measured)
        self._sports_thread.start()

    def _sports_measured(self, r: dict) -> None:
        self.sm_btn.setEnabled(True)
        self.sm_status.setText(f'{r.get("n_games", 0)} games fetched')
        colour = {"KEEP": theme.UP, "ERROR": theme.DOWN,
                  "DROP": theme.DOWN}.get(r.get("verdict"), theme.GOLD)
        lines = [r.get("summary", "")]
        if r.get("untuned"):
            lines.append("This sport's Elo settings are a stand-in, not a "
                         "published figure — the measurement is exactly how "
                         "that stops being a guess.")
        buckets = r.get("buckets") or []
        if buckets:
            lines.append("calibration: " + "   ".join(
                f'{b["low"]:.0%}–{b["high"]:.0%}: said {b["predicted"]:.0%}, '
                f'got {b["realised"]:.0%} (n={b["n"]})'
                for b in buckets if b["n"] >= 30))
        self.sm_result.setText("\n".join(line for line in lines if line))
        self.sm_result.setStyleSheet(f"color: {colour.name()};")

    # -- replay ------------------------------------------------------------- #
    def _replay_start(self) -> None:
        from sonar import backtest, replay as replay_mod
        sym = self.rep_symbol.currentData()
        self.rep_last.setText(f"loading {sym}…")
        QApplication.processEvents()
        bars = backtest.fetch_bars(sym, "5y")
        if bars is None or len(bars.close) < 120:
            self.rep_last.setText(f"no usable history for {sym}")
            return
        self._replay = replay_mod.Session(
            bars, horizon_days=self.lab_horizon.value(),
            step=self.lab_step.value(), stake=float(self.rep_stake.value()))
        self.rep_last.setText(f"{len(bars.close)} bars loaded")
        self._replay_render()

    def _replay_decide(self, choice: str) -> None:
        sess = getattr(self, "_replay", None)
        if sess is None:
            return
        d = sess.decide(choice)
        if d is not None:
            if d.choice == "SKIP":
                self.rep_last.setText(
                    f"skipped · the model went {d.model_direction} "
                    f"and it {('won' if d.model_outcome == 'TARGET' else 'lost')}")
            else:
                won = d.outcome == "TARGET"
                self.rep_last.setText(
                    f"{d.choice} → {d.outcome} after {d.bars_held} bars · "
                    f"{'+' if won else ''}{d.pnl:,.2f}")
        self._replay_render()

    def _replay_render(self) -> None:
        sess = getattr(self, "_replay", None)
        if sess is None:
            return
        setup = sess.current()
        for b in (self.rep_long, self.rep_short, self.rep_skip):
            b.setEnabled(setup is not None)
        if setup is None:
            self.rep_setup.setText("History exhausted — the scorecard below is final.")
            self.rep_spark.set_values([])
        else:
            import datetime as _dt
            day = _dt.datetime.utcfromtimestamp(setup.t).strftime("%Y-%m-%d")
            # Deliberately no model_direction here: showing the algorithm's call
            # before yours would turn this into a test of whether you agree with
            # it, which is a different and much less interesting question.
            self.rep_setup.setText(
                f"{setup.symbol} · {day} · {setup.price:,.4f}   "
                f"momentum {setup.momentum * 100:+.2f}%   "
                f"vol {setup.volatility * 100:.2f}%/day   "
                f"score {setup.confidence:.0f}   "
                f"target {setup.target_long:,.4f} / stop {setup.stop_long:,.4f} "
                f"(long)   R:R {setup.rr:.2f}")
            self.rep_spark.set_values(setup.closes[-60:])
        self.rep_card.setHtml(self._scorecard_html(sess.scorecard()))

    @staticmethod
    def _scorecard_html(c: dict) -> str:
        you = c.get("your_hit_rate")
        model = c.get("model_hit_rate")
        pnl, mpnl = c.get("your_pnl", 0.0), c.get("model_pnl", 0.0)

        def money(x):
            colour = "#98c379" if x > 0 else ("#e06c75" if x < 0 else "#7c8798")
            return f"<b style='color:{colour}'>{x:+,.2f}</b>"

        rows = [
            ("Setups seen", f"{c['n_setups']}  ({c['n_taken']} called, "
                            f"{c['n_skipped']} skipped)"),
            ("Your hit rate", "—" if you is None else
             f"{you * 100:.1f}%" + (f" ±{2 * c['your_std_error'] * 100:.1f}"
                                    if c.get("your_std_error") else "")),
            ("Model, same setups", "—" if model is None else f"{model * 100:.1f}%"),
            ("Barrier baseline", f"{c['predicted'] * 100:.1f}%"),
            ("Your P&amp;L", money(pnl)),
            ("Model P&amp;L", money(mpnl)),
            ("Agreed with the model", f"{c['agreed_with_model']} of {c['n_taken']}"),
        ]
        body = "".join(
            f"<tr><td style='padding:1px 16px 1px 0;color:#7c8798'>{k}</td>"
            f"<td style='padding:1px 0'>{v}</td></tr>" for k, v in rows)
        return (f"<table>{body}</table>"
                f"<p style='color:#7c8798;margin:6px 0 0'>{c['verdict']}</p>"
                f"<p style='color:#5c6370;margin:2px 0'>Risk {c['stake']:,.0f} per "
                "call; a win pays the reward-to-risk multiple. Sized by risk so a "
                "coin and a currency pair cost the same to be wrong about.</p>")

    def _lab_symbols(self) -> list[str]:
        want = self.lab_universe.currentData()
        rows = [(sym, cls) for sym, _name, cls, _kw in asset_mod.WATCHLIST]
        if want == "all":
            return [s for s, _ in rows]
        return [s for s, cls in rows if cls == want]

    def _lab_run(self) -> None:
        if self._lab_thread is not None and self._lab_thread.isRunning():
            return
        symbols = self._lab_symbols()
        if not symbols:
            self.lab_status.setText("no instruments in that class")
            return
        self.lab_btn.setEnabled(False)
        self.lab_status.setText(f"replaying {len(symbols)} instruments…")
        # The universe is passed, not guessed from the symbols: only the
        # whole watchlist gets a verdict (owner decision P1-C).
        self._lab_thread = BacktestThread(
            symbols, self.lab_horizon.value(), self,
            rng=self.lab_range.currentData(), step=self.lab_step.value(),
            with_news=self.lab_news.isChecked(),
            with_catalyst=self.lab_catalyst.isChecked(),
            universe=self.lab_universe.currentData())
        self._lab_thread.progress.connect(
            lambda sym, n: self.lab_status.setText(f"{sym} — {n} setups so far"))
        self._lab_thread.done.connect(self._lab_done)
        self._lab_thread.start()

    def _lab_done(self, r: dict) -> None:
        self.lab_btn.setEnabled(True)
        n = r.get("n", 0)
        self.lab_status.setText(f"{n:,} resolved setups" if n else "no result")
        self._lab_result = r
        self.lab_out.setHtml(self._lab_html(r))

    @staticmethod
    def _short_window_reason(r: dict) -> str:
        """Why a run compared nothing, and what would leave room — the same
        sentence on the Lab and the Terminal."""
        text = ("A setup is compared only when at least two horizons of bars "
                "follow it. A longer range or a shorter horizon leaves room for "
                "that.")
        if r.get("longest_comparable_horizon"):
            text += (" On this range the longest series can compare a horizon "
                     f"of up to {r['longest_comparable_horizon']} days.")
        return text

    @staticmethod
    def _lab_html(r: dict) -> str:
        if not r.get("n"):
            out = (f"<p style='color:#e06c75'>"
                   f"{html.escape(str(r.get('verdict', 'nothing resolved')), quote=False)}"
                   "</p>")
            # Nothing to compare is still a count: how many ran out of time or
            # of data is the reason, and a run where every setup did must say
            # so rather than look empty.
            left = []
            if r.get("n_timeout"):
                left.append(f"{r['n_timeout']:,} ran out of time")
            if r.get("n_short_window"):
                left.append(f"{r['n_short_window']:,} too near the end of the data")
            if left:
                out += f"<p style='color:#7c8798'>{' · '.join(left)}.</p>"
            if r.get("n_short_window"):
                out += (f"<p style='color:#7c8798'>"
                        f"{MainWindow._short_window_reason(r)}</p>")
            return out
        hit, pred = r["hit_rate"], r["predicted"]
        se, delta = r["std_error"], r["delta"]
        # A run shown without a verdict (horizon too long, or too few setups)
        # is neither a finding nor "no edge": the reason is the verdict.
        withheld = r.get("withheld")
        # The colour follows the verdict summarise reached on unrounded
        # figures, not a re-derivation from the rounded ones (code review r5
        # P3-5); a hand-built summary without the flag falls back to them.
        within = (not r["significant"] if "significant" in r
                  else abs(delta) <= 2 * se) and not withheld
        colour = "#7c8798" if within or withheld else "#e5c07b"
        # Setups that touched neither barrier in time are out of the hit rate,
        # so the prediction is the one for setups that resolved in time — and
        # how many ran out is shown, not hidden (docs/adr/0001). Hand-built
        # and older summaries lack these fields and render without them.
        # The instruments are those that reached the comparison, which a long
        # horizon can make far fewer than those fetched.
        compared = r.get("symbols_compared", r.get("symbols", 0))
        resolved = f"{r['n']:,} across {compared} instruments"
        if "symbols_compared" in r and (r.get("symbols") or 0) > compared:
            resolved += f" (of {r['symbols']} fetched)"
        if r.get("n_timeout") is not None:
            resolved += (f" · {r['n_timeout']:,} ran out of time "
                         f"({r.get('timeout_share', 0.0):.1%})")
        # Setups with under two horizons of data left are counted, not compared.
        if r.get("n_short_window"):
            resolved += f" · {r['n_short_window']:,} too near the end of the data"
        predicted = f"{pred * 100:.2f}%"
        if r.get("baseline_untimed") is not None:
            predicted += f" ({r['baseline_untimed']:.0%} with unlimited time)"
        if r.get("expectancy_vs_null_r") is not None:
            expectancy = (words.pick(("Expectancy beyond a no-edge market",
                                      "Excess expectancy")),
                          f"{r['expectancy_vs_null_r']:+.3f} R per setup")
        else:
            expectancy = ("Expectancy", f"{r['expectancy_r']:+.3f} R per setup")
        rows = [("Resolved setups", resolved)]
        if r.get("compared_by_class"):
            rows.append(("Instruments compared", " · ".join(
                f"{k} {cls}" for cls, k in r["compared_by_class"].items())))
        if r.get("first_entry"):
            rows.append(("Entry dates", f"{r['first_entry']} to "
                                        f"{r['last_entry']} · "
                                        f"{r.get('n_entry_dates', 0):,} dates"))
        rows += [
            ("Realised hit rate", f"{hit * 100:.2f}%"),
            ("Predicted, for setups that resolved in time", predicted),
            ("Difference", f"{delta * 100:+.2f} pts  (error bar ±{2 * se * 100:.2f}; "
                           "setups entered on the same day counted together)"),
            expectancy,
            (words.pick(("Average drift, in normal-move units", "Implied drift")),
             f"{r['implied_edge_sigma']:+.4f} σ"),
            ("Average hold", f"{r['avg_bars_held']:.1f} bars"),
        ]
        body = "".join(
            f"<tr><td style='padding:2px 18px 2px 0;color:#7c8798'>{k}</td>"
            f"<td style='padding:2px 0'><b>{v}</b></td></tr>" for k, v in rows)
        out = [f"<table>{body}</table>",
               f"<p style='color:{colour}'><b>"
               f"{html.escape(str(r['verdict']), quote=False)}</b></p>"]

        if within:
            out.append("<p style='color:#7c8798'>The difference sits inside its own "
                       "error bar, which is what a model with no edge is supposed to "
                       "look like. That is the result, not a failure to find one.</p>")

        for title, key in (("Momentum buckets", "buckets"),
                           ("Attention buckets", "attention_buckets")):
            bk = r.get(key) or []
            if not bk:
                continue
            # An attention bucket is judged against the run (`vs_run`), so its
            # table shows that figure under that name; momentum buckets, and
            # older attention buckets without it, show the gap to the
            # prediction (code review r5 P3-1).
            gap, gap_head = "delta", "vs baseline"
            if key == "attention_buckets" and all("vs_run" in b for b in bk):
                gap, gap_head = "vs_run", "vs setups with attention"
            head = "".join(f"<th style='text-align:left;padding-right:16px'>{h}</th>"
                           for h in ("bucket", "n", "hit rate", gap_head))
            body = "".join(
                "<tr>" + "".join(
                    f"<td style='padding-right:16px'>{c}</td>" for c in (
                        b.get("label") or b.get("name") or "?",
                        f"{b.get('n', 0):,}",
                        f"{b.get('hit_rate', 0) * 100:.1f}%",
                        f"{b.get(gap, 0) * 100:+.1f}")) + "</tr>"
                for b in bk)
            out.append(f"<h4 style='margin:14px 0 4px'>{title}</h4>"
                       f"<table>{head}{body}</table>")

        if r.get("news_verdict"):
            out.append(f"<p style='color:#7c8798'>{r['news_verdict']}</p>")
        out.append(MainWindow._attribution_html(r.get("attribution") or {}))
        return "".join(out)

    # The colours carry the recommendation, so a glance is enough to see which
    # component is the problem one.
    _VERDICT_COLOUR = {"KEEP": "#98c379", "INVERTED": "#e06c75",
                       "DROP": "#e06c75", "WEAK": "#e5c07b",
                       "UNCLEAR": "#7c8798", "not measured": "#5c6370",
                       "not judged": "#7c8798"}

    @staticmethod
    def _verdict_word(verdict: str | None) -> str:
        """The component verdict as the reader's wording shows it. The colour
        lookup keeps the raw key; only the displayed word changes."""
        if verdict is None:
            return "—"
        return ATTRIBUTION_VERDICTS.get(verdict, verdict) if words.plain() \
            else verdict

    @staticmethod
    def _attribution_html(a: dict) -> str:
        """Which components earned their weight — the part you act on.

        A hit rate tells you whether the model as a whole worked. This tells you
        *which piece* of it did, which is the only version of that question you
        can do anything with.
        """
        rows = a.get("components") or []
        if not rows:
            return ("<h4 style='margin:16px 0 4px'>Component attribution</h4>"
                    f"<p style='color:#7c8798'>"
                    f"{html.escape(str(a.get('note', 'not enough setups')), quote=False)}"
                    "</p>")

        head = "".join(
            f"<th style='text-align:left;padding-right:14px'>{words.pick(h)}</th>"
            for h in ATTRIBUTION_HEADS.values())
        body = []
        for c in rows:
            sp = c.get("spread") or {}
            spread = sp.get("spread")
            se = sp.get("se")
            colour = MainWindow._VERDICT_COLOUR.get(c.get("verdict"), "#7c8798")
            cells = (
                c.get("component", "?"),
                f"{c.get('weight', 0):.2f}" if c.get("weight") is not None else "—",
                f"{c['ic']:+.3f}" if c.get("ic") is not None else "—",
                (f"{spread * 100:+.1f} ±{2 * se * 100:.1f}"
                 if spread is not None and se else "—"),
                (f"{c['blend_ic_without']:+.3f}"
                 if c.get("blend_ic_without") is not None else "—"),
                f"<b style='color:{colour}'>{MainWindow._verdict_word(c.get('verdict'))}</b>",
            )
            body.append("<tr>" + "".join(
                f"<td style='padding:2px 14px 2px 0'>{x}</td>" for x in cells) + "</tr>")

        out = ["<h4 style='margin:16px 0 4px'>Component attribution</h4>",
               f"<table>{head}{''.join(body)}</table>"]
        if words.plain():
            out.append(
                "<p style='color:#7c8798'>How to read it. <b>Ranking skill</b> "
                "(IC) is how closely a component's order of setups matches the "
                "order of what happened: 0 means its order says nothing, a "
                "negative number means it ranks backwards. <b>Best fifth − worst "
                "fifth</b> (the quintile spread) is the hit-rate gap between "
                "the setups it scored highest and lowest, in points. <b>Score "
                "without it</b> (leave-one-out) re-computes the blended score "
                "with that one component removed: if that number is higher, the "
                "component was dragging the score down. <b>Keep</b> means its "
                "ranking skill and its best-vs-worst gap are both bigger than "
                "chance would give; <b>weak</b> that both are small; <b>drop</b> "
                "that removing it does not lower the score's ranking skill; "
                "<b>backwards</b> that it is clearly negative; <b>unclear</b> "
                "that the readings disagree. Keep grades a piece of the score "
                "against past setups. It does not mean the piece makes money.</p>")

        blend = a.get("blend_ic")
        if blend is not None:
            # "Ranking the wrong way round" is a finding, so it needs one: a
            # run that gets a verdict, and a blend IC that clears the claim
            # bar (attribute's blend_ranks_backwards). Otherwise the number
            # stands alone (code-review r4 P2-1).
            backwards = a.get("blend_ranks_backwards") and not a.get("withheld")
            note = ("" if not backwards else
                    f" — a negative blend {words.pick(('ranking skill', 'IC'))} "
                    "means the score as a whole is ranking the wrong way round, "
                    "not merely failing to rank")
            out.append(f"<p style='color:#7c8798'>Blended score "
                       f"{words.pick(('ranking skill (IC)', 'IC'))} "
                       f"<b>{blend:+.3f}</b> over {a.get('n', 0):,} resolved "
                       f"setups{note}.</p>")

        # A run without a verdict grades no component: one line says so, in
        # place of a verdict line per component.
        if a.get("withheld") and a.get("note"):
            out.append(f"<p style='color:#7c8798'>{html.escape(str(a['note']), quote=False)}</p>")
        for c in rows:
            if c.get("why") and c.get("verdict") not in ("not measured",
                                                         "not judged"):
                colour = MainWindow._VERDICT_COLOUR.get(c["verdict"], "#7c8798")
                out.append(f"<p style='color:{colour};margin:2px 0'><b>"
                           f"{html.escape(str(c['component']), quote=False)}</b> — "
                           f"{html.escape(str(c['why']), quote=False)}</p>")

        if a.get("catalyst"):
            out.append(f"<p style='color:#5c6370'>catalyst — "
                       f"{html.escape(str(a['catalyst']), quote=False)}</p>")
        judged = ("the four components are judged together, with a stricter bar "
                  "for each than if it stood alone"
                  if words.plain() else
                  "p-values go through Benjamini-Hochberg together at "
                  f"q={a.get('fdr_q', 0.1)}")
        out.append(f"<p style='color:#5c6370'>{judged[0].upper() + judged[1:]}: "
                   "testing four components and reporting the best one is how "
                   "noise gets published.</p>")
        return "".join(out)

    # -- playmaker ------------------------------------------------------------ #
    def _playmaker_tab(self) -> QWidget:
        """Prop-bet analysis. NFL today; the sport picker is the extension point.

        The arithmetic is local and instant — devigging and the cross-book
        screen need no network and no model. The LLM read runs afterwards on a
        thread and is commentary only: `sonar.playmaker.staking` refuses to let
        a narrative estimate size a stake. Paper analysis; nothing places a wager.
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        form = panel()
        fl = QGridLayout(form)
        # Tight vertical rhythm: this form stacks four rows of controls and is
        # one of the two tabs that set the window's minimum height. The
        # interface font is taller than the monospace it replaced, and
        # `tests/test_layout.py` holds the whole window to a 13" laptop.
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setHorizontalSpacing(10)
        fl.setVerticalSpacing(5)

        self.sport_box = QComboBox()
        for sp in playmaker.list_sports():
            self.sport_box.addItem(sp.name, sp.key)
        self.sport_box.currentIndexChanged.connect(self._playmaker_sport_changed)

        self.prop_box = QComboBox()
        self.playmaker_subject = QLineEdit()
        self.playmaker_subject.setPlaceholderText("Player or team")
        self.playmaker_line = QLineEdit()
        self.playmaker_line.setPlaceholderText("Over 252.5")
        self.playmaker_context = QLineEdit()

        fl.addWidget(label("SPORT", "faint", theme.figure(8)), 0, 0)
        fl.addWidget(label("PROP", "faint", theme.figure(8)), 0, 1)
        fl.addWidget(label("SUBJECT", "faint", theme.figure(8)), 0, 2)
        fl.addWidget(self.sport_box, 1, 0)
        fl.addWidget(self.prop_box, 1, 1)
        fl.addWidget(self.playmaker_subject, 1, 2)
        fl.addWidget(label("LINE", "faint", theme.figure(8)), 2, 0)
        fl.addWidget(label("CONTEXT", "faint", theme.figure(8)), 2, 1)
        fl.addWidget(self.playmaker_line, 3, 0)
        fl.addWidget(self.playmaker_context, 3, 1, 1, 2)
        fl.setColumnStretch(2, 1)
        lay.addWidget(form)

        books_p = panel()
        bl = QVBoxLayout(books_p)
        bl.setContentsMargins(14, 12, 14, 12)
        bl.addWidget(label("PRICES BY BOOK", "faint", theme.figure(8)))
        bl.addWidget(label(
            "One book per line: its name, then its price for every side of the "
            "market. Both sides are required — a margin is how far a market's "
            "prices sum past certainty, so a single price cannot reveal one. "
            "Three books or more turns on the outlier screen.",
            "muted", theme.figure(9), wrap=True))
        self.playmaker_books = QPlainTextEdit()
        # Pasted tables line up with spaces; a proportional font ruins them.
        self.playmaker_books.setFont(theme.code(10))
        self.playmaker_books.setPlaceholderText(
            "DraftKings  -150  +130\nFanDuel     -155  +132\n"
            "Pinnacle    -148  +128\nBetMGM      -150  +210")
        self.playmaker_books.setFixedHeight(84)
        bl.addWidget(self.playmaker_books)
        self.playmaker_capability = label("", "faint", theme.figure(9), wrap=True)
        bl.addWidget(self.playmaker_capability)
        lay.addWidget(books_p)

        data_p = panel()
        dl = QVBoxLayout(data_p)
        dl.setContentsMargins(14, 12, 14, 12)
        dl.addWidget(label("SUPPORTING DATA", "faint", theme.figure(8)))
        self.playmaker_data = QPlainTextEdit()
        # Pasted tables line up with spaces; a proportional font ruins them.
        self.playmaker_data.setFont(theme.code(10))
        self.playmaker_data.setPlaceholderText(
            "Splits, recent games, defensive ranks. The model is told not to "
            "invent numbers, so what you paste here is what it reasons from.")
        self.playmaker_data.setFixedHeight(96)
        dl.addWidget(self.playmaker_data)

        row = QHBoxLayout()
        self.playmaker_btn = QPushButton("Price it")
        self.playmaker_btn.clicked.connect(self._playmaker_analyse)
        row.addWidget(self.playmaker_btn)
        self.playmaker_status = label("", "faint", theme.figure(9))
        # Shows exception text, which can quote a model or a file: never markup.
        self.playmaker_status.setTextFormat(Qt.PlainText)
        row.addWidget(self.playmaker_status, 1)
        dl.addLayout(row)
        lay.addWidget(data_p)

        # The arithmetic, shown whether or not a model read has run.
        nums = panel()
        nl = QGridLayout(nums)
        nl.setContentsMargins(14, 12, 14, 12)
        nl.setHorizontalSpacing(26)
        self.playmaker_stats = {}
        cells = [
            ("books",
             "How many bookmakers' prices were read.\n"
             "Three is the minimum for the screen below: with fewer there is no "
             "consensus for any one book to be out of line with."),
            ("margin",
             "The bookmaker's cut, built into the price.\n"
             "Add up what both sides imply and you get more than 100% — the "
             "excess is what the book keeps. 4.8% is standard. It is why "
             "betting at random loses money slowly even when you are right half "
             "the time."),
            ("fair",
             "The chance of the first outcome once the bookmaker's cut is "
             "removed.\n"
             "This is the market's real opinion. The price you are offered "
             "always implies something worse than this."),
            ("book spread",
             "How much the bookmakers disagree with each other.\n"
             "Tight means they are confident and you should be sceptical of any "
             "gap you find; wide means the true price is genuinely unclear."),
            ("best edge",
             "The biggest gap between one book's price and what all the others "
             "think, in percentage points.\n"
             "This is not a prediction about who wins — only that one bookmaker "
             "disagrees with the rest."),
            ("EV / unit",
             "What you would expect to win or lose per 1 staked, on average, if "
             "that gap is real.\n"
             "+0.05 means five pence expected profit per pound. Negative means "
             "the price is not worth taking."),
            ("stake",
             "What fraction of a bankroll the Kelly formula suggests — the size "
             "that grows money fastest over many bets without risking ruin.\n"
             "Sized at the pessimistic end of the estimate and capped, so it "
             "reads 0 whenever the edge might not be real. 0 is the normal "
             "answer."),
        ]
        for i, (k, tip) in enumerate(cells):
            st = Stat(k, tip)
            self.playmaker_stats[k] = st
            nl.addWidget(st, 0, i)
        lay.addWidget(nums)

        self.playmaker_out = QTextBrowser()
        self.playmaker_out.setOpenExternalLinks(False)
        self.playmaker_out.setOpenLinks(False)     # a pasted link loads nothing
        lay.addWidget(self.playmaker_out, 1)

        self._playmaker_sport_changed()
        return w

    def _playmaker_sport_changed(self) -> None:
        """Repoint the prop list, the context hint and the price example.

        A three-way sport wants three prices per book, so the placeholder shows
        three. Nothing else changes: the devigging and the screen take N
        outcomes and never learn which sport they are pricing.
        """
        sport = playmaker.get_sport(self.sport_box.currentData())
        self.prop_box.clear()
        for pt in sport.prop_types:
            self.prop_box.addItem(pt.label, pt.key)
        self.playmaker_context.setPlaceholderText(sport.context_hint)
        if sport.outcomes == 3:
            example = ("DraftKings  +150  +240  +180\n"
                       "Pinnacle    +155  +235  +175\n"
                       "Bet365      +148  +245  +182\n"
                       "BetMGM      +150  +400  +180")
        else:
            example = ("DraftKings  -150  +130\n"
                       "FanDuel     -155  +132\n"
                       "Pinnacle    -148  +128\n"
                       "BetMGM      -150  +210")
        self.playmaker_books.setPlaceholderText(example)
        self.playmaker_capability.setText(self._capability_note(sport))

    @staticmethod
    def _capability_note(sport) -> str:
        """Say plainly what this sport can and cannot do.

        The pricing half works everywhere — it is odds arithmetic and knows
        nothing about the sport. The rating half does not: a golf tournament is
        a finishing order across a hundred-odd players, not a contest between
        two sides, and cycling has no results feed at all. Leaving the reader
        to infer that from an empty panel would be the kind of silence that
        reads as a bug.
        """
        if sport.model == "dixon_coles":
            rated = ("Rated by Dixon-Coles over every international competition "
                     "these sides play — one pool of national-team ratings.")
        elif sport.model == "elo" and sport.shape == "winners":
            rated = ("Rated by Elo on wins and losses. No scoreline exists in "
                     "this sport, so there is no margin of victory to learn from.")
        elif sport.model == "elo":
            rated = "Rated by Elo, with margin of victory and home advantage."
        elif not sport.has_results:
            rated = ("No results feed exists for this sport, so nothing here "
                     "rates a competitor. Everything below still works — "
                     "removing the margin and screening the books is arithmetic "
                     "that needs no data.")
        else:
            rated = ("A finishing order across a large field, not a contest "
                     "between two sides, so no head-to-head model applies. "
                     "Everything below still works — pricing needs no model.")
        return rated

    # -- the arithmetic half: local, instant, no model involved --------------- #
    def _playmaker_price(self) -> tuple[list, str]:
        """Parse the book table and render everything the numbers alone support."""
        for key in self.playmaker_stats:
            self.playmaker_stats[key].set("—")
        text = self.playmaker_books.toPlainText().strip()
        if not text:
            return [], ("<b>No prices yet.</b><br>Enter at least one book's prices "
                        "for both sides of the market. Three books turns on the "
                        "cross-book screen, which is the part with a track record.")
        try:
            quotes = pm_devig.parse_quotes(text)
            # Books that disagree on the number of outcomes parse line by
            # line but cannot be compared: the same answer, not a crash.
            cons = pm_devig.consensus(quotes)
        except ValueError as exc:
            self.playmaker_status.setText(str(exc))
            return [], ("<b>Could not read the prices.</b><br>"
                        f"{html.escape(str(exc), quote=False)}")

        self.playmaker_stats["books"].set(str(len(quotes)))
        first = quotes[0]
        self.playmaker_stats["margin"].set(f"{pm_devig.overround(first.odds)*100:.2f}%")

        blocks = [self._devig_html(first)]

        self.playmaker_stats["fair"].set(f"{cons.probability[0]*100:.1f}%")
        se = cons.standard_error(0)
        self.playmaker_stats["book spread"].set(
            "—" if se != se else f"±{se*100:.2f} pts")

        opportunities = []
        if len(quotes) >= 3:
            opportunities = pm_devig.screen(quotes, min_edge=0.005)
            blocks.append(self._screen_html(quotes, cons, opportunities))
        else:
            blocks.append(
                "<b>CROSS-BOOK SCREEN</b><br>"
                f"Needs three books; {len(quotes)} entered. This is the one "
                "approach here with a published track record — Kaunitz, Zhong "
                "&amp; Kreiner (2017) found real profit betting nothing but "
                "outliers against a multi-book consensus. With one or two books "
                "there is no consensus to be an outlier against.")

        if opportunities:
            best = opportunities[0]
            est = pm_staking.from_consensus(
                pm_devig.consensus(quotes, exclude=best.book), best.outcome)
            assessment = pm_staking.assess(est, best.odds, fair=best.fair)
            self.playmaker_stats["best edge"].set(f"{best.edge*100:+.2f} pts")
            self.playmaker_stats["EV / unit"].set(f"{best.expected_value:+.3f}")
            self.playmaker_stats["stake"].set(f"{assessment.fraction*100:.2f}%")
            blocks.append(
                "<b>STAKE</b><br>"
                f"{assessment.note}.<br>"
                f"Estimate {est.probability*100:.1f}% "
                f"({est.low*100:.1f}–{est.high*100:.1f}%), from {est.basis}.")
        elif len(quotes) >= 3:
            self.playmaker_stats["best edge"].set("none")
            self.playmaker_stats["EV / unit"].set("—")
            self.playmaker_stats["stake"].set("0.00%")
        return opportunities, "<br><br>".join(blocks)

    def _devig_html(self, quote) -> str:
        """The three methods side by side — the argument for not using the usual one."""
        rows = []
        for name, probs in pm_devig.all_methods(quote.odds).items():
            cells = "".join(f"<td align=right>&nbsp;&nbsp;{p*100:.2f}%</td>" for p in probs)
            mark = " &larr; used" if name == pm_devig.DEFAULT_METHOD else ""
            rows.append(f"<tr><td>{name}{mark}</td>{cells}</tr>")
        sides = "".join(f"<td align=right>&nbsp;&nbsp;{o:+d}</td>" for o in quote.odds)
        return (f"<b>FAIR PRICE — {html.escape(quote.book, quote=False)}</b><br>"
                "<table cellspacing=0 cellpadding=2>"
                f"<tr><td><i>price</i></td>{sides}</tr>{''.join(rows)}</table>"
                "The three are all defensible ways to remove the same margin, and "
                "they disagree — most on longshots. The proportional method every "
                "calculator quotes is the one comparative studies rank last; it "
                "reads a favourite as cheaper and a longshot as dearer than it is.")

    def _screen_html(self, quotes, cons, opportunities) -> str:
        """Which book is out of line with the others, and by how much."""
        if not opportunities:
            return ("<b>CROSS-BOOK SCREEN</b><br>"
                    f"{len(quotes)} books, none materially out of line with the "
                    "others. That is the common and correct answer — the market "
                    "agreeing with itself is not a missed opportunity.")
        rows = []
        for o in opportunities:
            flag = " <b>outlier</b>" if o.is_outlier else ""
            z = "—" if o.z != o.z else f"{o.z:.1f}&sigma;"
            rows.append(
                f"<tr><td>{html.escape(o.book, quote=False)}{flag}</td>"
                f"<td align=right>&nbsp;&nbsp;side {o.outcome+1}</td>"
                f"<td align=right>&nbsp;&nbsp;{o.odds:+d}</td>"
                f"<td align=right>&nbsp;&nbsp;{o.fair*100:.1f}%</td>"
                f"<td align=right>&nbsp;&nbsp;{o.edge*100:+.2f}</td>"
                f"<td align=right>&nbsp;&nbsp;{o.expected_value:+.3f}</td>"
                f"<td align=right>&nbsp;&nbsp;{z}</td></tr>")
        return ("<b>CROSS-BOOK SCREEN</b><br>"
                "<table cellspacing=0 cellpadding=2>"
                "<tr><td><i>book</i></td><td align=right><i>&nbsp;&nbsp;side</i></td>"
                "<td align=right><i>&nbsp;&nbsp;price</i></td>"
                "<td align=right><i>&nbsp;&nbsp;peers say</i></td>"
                "<td align=right><i>&nbsp;&nbsp;edge</i></td>"
                "<td align=right><i>&nbsp;&nbsp;EV</i></td>"
                "<td align=right><i>&nbsp;&nbsp;z</i></td></tr>"
                f"{''.join(rows)}</table>"
                "Each row's peers exclude that row's own book, so a price cannot "
                "vote for itself. This says nothing about who wins — only that "
                "one book disagrees with the rest.")

    def _playmaker_analyse(self) -> None:
        self.playmaker_status.setText("")
        opportunities, html = self._playmaker_price()
        self.playmaker_out.setHtml(html)
        self._playmaker_html = html

        sport = playmaker.get_sport(self.sport_box.currentData())
        books = self.playmaker_books.toPlainText().strip()
        prompt = playmaker.build_prompt(
            sport,
            self.playmaker_subject.text().strip(),
            self.prop_box.currentText(),
            self.playmaker_line.text().strip(),
            books.splitlines()[0] if books else "",
            self.playmaker_context.text().strip(),
            self.playmaker_data.toPlainText(),
        )
        self.playmaker_btn.setEnabled(False)
        self.playmaker_status.setText("reading…")
        self.playmaker_thread = PropThread(playmaker.SYSTEM_PROMPT, prompt, self)
        self.playmaker_thread.done.connect(self._playmaker_done)
        self.playmaker_thread.start()

    def _playmaker_done(self, text: str, error: str) -> None:
        """Attach the model's read to the numbers — as commentary, not as input.

        Nothing here touches the stat cells. The percentage the model states is
        shown and explicitly marked unusable for sizing; `staking.Estimate`
        enforces that in the arithmetic, this only explains it.
        """
        self.playmaker_btn.setEnabled(True)
        if error:
            self.playmaker_status.setText(error)
            return
        self.playmaker_status.setText("")
        result = playmaker.parse_analysis(text)
        est = pm_staking.from_narrative(result.win_probability, result.confidence)

        head = ["<b>MODEL READ — commentary only</b>"]
        if est is not None:
            head.append(
                f"States {est.probability*100:.1f}% ({html.escape(result.lean or 'no lean')}, "
                f"confidence {html.escape(str(result.confidence or 'unstated'))}). "
                "Not used for the edge, the EV or the stake above: a language "
                "model's percentage is not a measurement, and feeding one to "
                "Kelly is the defect this tab was rebuilt to remove.")
        else:
            head.append(f"Lean {html.escape(result.lean or '—')}, "
                        f"confidence {html.escape(str(result.confidence or '—'))}; no figure stated.")

        # Model text is data, not markup: scraped pages steer it, and unescaped
        # it could draw its own bold, links or fake "commentary only" notices.
        blocks = ["<br>".join(head)]
        for name in playmaker.SECTIONS:
            body = result.sections.get(name)
            if body:
                blocks.append(f"<b>{name}</b><br>{html.escape(body).replace(chr(10), '<br>')}")
        narrative = ("<br><br>".join(blocks)
                     or html.escape(text).replace("\n", "<br>"))
        before = getattr(self, "_playmaker_html", "")
        self.playmaker_out.setHtml(f"{before}<br><br><hr>{narrative}" if before else narrative)


    def _macro_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        head = panel()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(14, 12, 14, 12)
        self.regime_lb = label("—", font=theme.figure(22, True))
        self.regime_sub = label("", "muted", theme.figure(10))
        self.regime_sub.setWordWrap(True)
        hl.addWidget(label("MACRO REGIME", "faint", theme.figure(8)))
        hl.addWidget(self.regime_lb)
        hl.addWidget(self.regime_sub)
        self.regime_bar = ComponentBar()
        self.regime_bar.setFixedHeight(9)
        hl.addWidget(self.regime_bar)
        lay.addWidget(head)

        inst = panel()
        il = QVBoxLayout(inst)
        il.setContentsMargins(14, 12, 14, 12)
        il.setSpacing(4)
        il.addWidget(label("CENTRAL BANK COMMUNICATION", "faint", theme.figure(8)))
        self.inst_level = label("—", font=theme.figure(15, True))
        il.addWidget(self.inst_level)
        il.addWidget(label(
            "Policy releases and speeches from the Fed and the Bank of England — "
            "the rare catalyst that is scheduled and public. Heavy traffic means "
            "the rate path is being repriced, which widens the distribution for "
            "everything priced off it. Which way it widens is not something this "
            "can know, and it does not claim to.",
            "faint", theme.figure(8), wrap=True))
        self.inst_list = label("", "muted", theme.figure(9))
        self.inst_list.setWordWrap(True)
        il.addWidget(self.inst_list)
        lay.addWidget(inst)

        grid = panel()
        gl = QGridLayout(grid)
        gl.setContentsMargins(14, 12, 14, 12)
        gl.setHorizontalSpacing(26)
        self.macro_stats = {}
        # Every tooltip here says what the number is in plain words first, then
        # how to read it. These are the figures a reader is least likely to
        # already know, and a tooltip that only restates the label ("effective
        # policy rate") helps nobody who needed the tooltip.
        cells = [
            ("10y",
             "What the US government pays to borrow for ten years.\n"
             "The benchmark almost everything else is priced against — "
             "mortgages, company debt, and what a share is worth today.\n"
             "Rising means borrowing is getting dearer everywhere."),
            ("curve",
             "The ten-year rate minus the two-year rate.\n"
             "Normally positive: lending for longer pays more. When it goes "
             "negative — 'inverted' — lenders expect rates to be cut, which "
             "usually means they expect a downturn.\n"
             "It has preceded most US recessions, with a lag of a year or more."),
            ("fed funds",
             "The interest rate the US central bank sets.\n"
             "The lever it pulls to cool inflation (raise) or support growth "
             "(cut). Every other rate takes its cue from this one."),
            ("VIX",
             "How much movement the options market is paying up for over the "
             "next month, in annualised percent.\n"
             "Below 15 is calm, above 25 is nervous, above 35 is a crisis.\n"
             "It says how big the swings may be, never which way."),
            ("real 10y",
             "The ten-year rate after subtracting inflation — what a lender "
             "actually earns in purchasing power.\n"
             "Negative means cash parked in government debt loses value over "
             "time, which pushes money toward shares and gold."),
            ("CPI y/y",
             "How much consumer prices have risen over twelve months.\n"
             "The number central banks are targeting, usually at 2%. Well "
             "above it and rates tend to rise; well below and they tend to fall."),
            ("unemployment",
             "The share of people looking for work who cannot find it, and how "
             "it has moved over a year.\n"
             "The level matters less than the direction: a rate that has turned "
             "up over twelve months is one of the more reliable recession "
             "signals there is."),
        ]
        for i, (k, tip) in enumerate(cells):
            s = Stat(k, tip)
            self.macro_stats[k] = s
            gl.addWidget(s, i // 4, i % 4)
        lay.addWidget(grid)

        self.macro_note = label("", "faint", theme.figure(9))
        self.macro_note.setWordWrap(True)
        lay.addWidget(self.macro_note)
        lay.addStretch(1)
        return w

    # -- actions ----------------------------------------------------------- #
    def _toggle_wording(self) -> None:
        words.toggle()
        self._apply_wording()

    def _apply_wording(self) -> None:
        """Push the current wording through everything that shows it.

        Re-captioning in place rather than rebuilding the window: the tab bar
        keeps both names already, the headings keep both already, and every
        stat strip is built from a key it can re-read. The rows are the one
        thing that genuinely has to be rebuilt — they change shape, not just
        text — and clearing the signature hands that to the next refresh tick
        rather than doing it on the click.
        """
        plain = words.plain()
        self.wording_btn.setText(f"Wording: {words.mode()}")
        self.tabs.set_wording(plain)
        self.asset_header.retitle()
        self.assets_banner.setVisible(plain)
        for cap in self.lab_captions.values():
            cap.setVisible(plain)
        if self._lab_result is not None:
            self.lab_out.setHtml(self._lab_html(self._lab_result))
        for stat in self.findChildren(Stat):
            stat.retitle()
        for attr, (easy, expert) in CONTROL_WORDS.items():
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setText(easy if plain else expert)
        self._assets_sig = None

    def _apply_config(self) -> None:
        if self._cfg_thread and self._cfg_thread.isRunning():
            return
        self.risk_box.setEnabled(False)
        self.hz_box.setEnabled(False)
        # Not an unbounded hold: refresh()'s own ⚠ (read-only, a failed poll,
        # health) must still get through during a long rescan. Its ordinary
        # line says "applying" instead while this is pending.
        self._config_pending = True
        self._set_status(self.APPLYING, hold_s=True)
        self._cfg_thread = ConfigThread(
            self.live, self.risk_box.currentData(), self.hz_box.currentData(), self)
        self._cfg_thread.done.connect(self._config_done)
        self._cfg_thread.start()

    def _sync_knobs(self) -> None:
        """Show the settings the engine is actually running.

        A window that may not write the book (another engine drives and
        cannot be followed) refuses a risk change or the protocol switch, and
        a takeover re-reads both from disk; either way the widget the user
        touched can disagree with the engine. Synced quietly, so setting the
        widget does not fire the action again."""
        if not (self._cfg_thread and self._cfg_thread.isRunning()):
            for box, name in ((self.risk_box, self.live.risk.name),
                              (self.hz_box, self.live.horizon.name)):
                i = box.findData(name)
                if i >= 0 and i != box.currentIndex():
                    box.blockSignals(True)
                    box.setCurrentIndex(i)
                    box.blockSignals(False)
        if self.protocol_box.isChecked() != self.live.protocol_on:
            self.protocol_box.blockSignals(True)
            self.protocol_box.setChecked(self.live.protocol_on)
            self.protocol_box.blockSignals(False)

    APPLYING = "applying — rescanning…"

    def _config_done(self, cfg: dict) -> None:
        self.risk_box.setEnabled(True)
        self.hz_box.setEnabled(True)
        self._config_pending = False
        why = cfg.get("refused") or cfg.get("error")
        if why:
            self._set_status(f"⚠  setting not applied: {why}", hold_s=True)
            if self._toast_target is None:
                # Not over a live Undo: the trade it offers is unrelated.
                self._warn(f"Setting not applied: {why}")
        for which in ("markets", "assets"):
            setattr(self, f"_{which}_sig", None)      # force a rebuild

    def _run_backtest(self) -> None:
        if self._bt_thread is not None and self._bt_thread.isRunning():
            return
        self.bt_btn.setEnabled(False)
        from sonar import backtest
        from sonar.assets import WATCHLIST
        # Two years, unless the profile's horizon needs more history than that
        # to compare anything (the 250-day profile does).
        days = self.live.horizon.momentum_days
        rng = backtest.range_for_horizon(days)
        span = {"2y": "two years", "5y": "five years"}.get(rng, rng)
        self.bt_result.setText(f"replaying {span} of bars…")
        self._bt_thread = BacktestThread(
            [s for s, _n, _c, _k in WATCHLIST], days, self, rng=rng,
            universe=backtest.WHOLE_WATCHLIST)
        self._bt_thread.done.connect(self._backtest_done)
        self._bt_thread.start()

    def _backtest_done(self, r: dict) -> None:
        self.bt_btn.setEnabled(True)
        left = (f' · {r["n_timeout"]:,} timed out'
                if r.get("n_timeout") is not None else '')
        if r.get("n_short_window"):
            left += f' · {r["n_short_window"]:,} too near the end of the data'
        if not r.get("n"):
            # Every setup ran out of time or of data: say how many, not just
            # "nothing" — and, if the data was too short, why, as the Lab does.
            self.bt_result.setText(
                f'backtest: {r.get("verdict", "no result")}'
                + (left if r.get("n_timeout") or r.get("n_short_window") else '')
                + ("\n  " + self._short_window_reason(r)
                   if r.get("n_short_window") else ''))
            return
        # The same figures the Lab shows (D7): beyond a market with nothing in
        # it, which the raw expectancy over resolved setups is not — that one
        # reads negative on no edge. Older summaries fall back to the raw one.
        if r.get("expectancy_vs_null_r") is not None:
            expectancy = (words.pick(("expectancy beyond a no-edge market",
                                      "excess expectancy"))
                          + f' {r["expectancy_vs_null_r"]:+.3f}R')
        else:
            expectancy = f'expectancy {r["expectancy_r"]:+.3f}R'
        lines = [
            f'BACKTEST · {r["n"]:,} resolved trials across '
            f'{r.get("symbols_compared", r.get("symbols", 0))} '
            f'instruments, {r["range"]} of daily bars, {r["horizon_days"]}d horizon'
            + left,
            f'  realised {r["hit_rate"]*100:.2f}%   '
            f'predicted {r["predicted"]*100:.2f}% for setups that resolved in time   '
            f'delta {r["delta"]*100:+.2f} pts (± {r["std_error"]*100*2:.1f})   '
            + expectancy,
        ]
        for b in r.get("buckets", []):
            lines.append(f'    |momentum| {b["lo"]*100:>3.0f}–{b["hi"]*100:<4.0f}%  '
                         f'n={b["n"]:<6} hit {b["hit_rate"]*100:5.1f}%')
        lines.append(f'  {r["verdict"]}')
        lines.append("  Price-based half only — historical news is not replayed, "
                     "and costs are excluded (both would push this down).")
        self.bt_result.setText("\n".join(lines))

    def _trade(self, symbol: str, direction: str) -> None:
        """Open a paper position. Deliberately synchronous — it is local
        bookkeeping against an already-fetched price. It can wait the few
        milliseconds of an engine-thread mark pass holding the book's lock;
        a broker that goes to the network would make that a real wait, and
        this would then belong on a thread."""
        result = self.live.trade(symbol, direction)
        self._set_status(("✓  " if result["ok"] else "⚠  ") + result["message"]
                         + "  ·  paper money only", hold_s=True)
        pos = result.get("position") or {}
        if result["ok"] and pos.get("id"):
            self._toast(f"{result['message']} — paper money only", pos["id"], "trade")
        elif not result["ok"]:
            self._warn(f"Not traded: {result['message']}")
        self._assets_sig = None          # force the board to redraw
        self._book_sig = None
        self._portfolio_sig = None

    def _close_position(self, pos_id: str) -> None:
        result = self.live.close_position(pos_id)
        self._set_status(("✓  " if result["ok"] else "⚠  ") + result["message"],
                         hold_s=True)
        if result["ok"]:
            self._toast(result["message"], pos_id, "close")
        else:
            self._warn(f"Not closed: {result['message']}")
        self._book_sig = None
        self._portfolio_sig = None

    def _read(self, kind: str, ident: str, subject: str) -> None:
        # The read panel lives with the hourly model at the foot of Practice,
        # so every path has to bring the user there — and scroll to it.
        # Reporting "unavailable" onto a page they are not looking at is
        # indistinguishable from the button being dead, which is exactly how
        # the Assets tab's read button used to behave.
        self.read_panel.show()
        self.tabs.setCurrentIndex(self._lab_index)
        self._lab_scroll.ensureWidgetVisible(self.read_panel)

        ok, why = self.live.llm_available()
        if not ok:
            self.read_panel.show_read({"subject": subject, "error": why}, False)
            return
        if self._read_thread and self._read_thread.isRunning():
            self.read_panel.show_read(
                {"subject": subject,
                 "error": "Another read is still running — one at a time."},
                False)
            return
        self.read_btn.setEnabled(False)
        self.read_panel.show_pending(subject)
        self._read_thread = ReadThread(self.live, kind, ident, self)
        self._read_thread.done.connect(self._read_done)
        self._read_thread.start()

    def _read_done(self, r: dict) -> None:
        self.read_btn.setEnabled(True)
        self.read_panel.show_read(r, self.live.horizon.long_horizon)

    # -- refresh ----------------------------------------------------------- #
    def refresh(self) -> None:
        with self.live.lock:
            snap = dict(self.live.snapshot)
            assets = dict(self.live.assets)

        # The paper book is independent of the hourly engine: it must render
        # even while the first BTC poll is still in flight, and even when
        # another SONAR holds the engine lock.
        self._refresh_book()
        self._refresh_portfolio()
        self._refresh_wire()
        self._sync_knobs()

        # The Screener and Big picture do not depend on the bitcoin feed: they
        # draw whatever the engine has, whatever state the hourly poll is in.
        # Gating them on it froze the core path on "Fetching prices…" for as
        # long as Binance and Coinbase were unreachable (closing UX C-1).
        status = snap.get("status")
        self._refresh_cards(assets, read_only=status == "read-only")
        self._refresh_macro(snap)

        if status == "read-only":
            # Another SONAR holds the engine lock and cannot be followed (a
            # second window), or the one being followed stopped answering.
            # Say so plainly rather than showing a window that looks broken;
            # the engine keeps trying for the lock behind this message.
            self._set_status("⚠  " + snap.get("detail", "another engine is running"))
            self.read_btn.setEnabled(False)
            return
        if status == "error":
            detail = " ".join(str(snap.get("detail") or "no reason given").split())
            following = snap.get("following")
            whose = (f'the engine at {following.split("//")[-1]}: ' if following else "")
            self._set_status(f"⚠  {whose}bitcoin price poll failed ({detail[:140]}) — retrying. "
                             "The Screener and Big picture do not depend on it.")
            return
        if status != "live":
            self._set_status(self.APPLYING if getattr(self, "_config_pending", False)
                             else f'{status or "…"} — first poll can take a moment')
            return
        self.read_btn.setEnabled(True)
        self._refresh_terminal(snap)
        if self.tray is not None:
            self.tray.update_state(snap)

        hz = self.live.horizon
        # Following: the launchd agent holds the lock and this window mirrors
        # it — every figure is the agent's, every action is handed to it.
        following = snap.get("following")
        who = (f'following the engine at {following.split("//")[-1]} · '
               if following else "")
        self._set_status(
            self.APPLYING if getattr(self, "_config_pending", False) else
            f'{who}risk {self.live.risk.name} · horizon {hz.name} · '
            f'{assets.get("n", 0)} assets · paper money only')
        # A dead loop leaves its last snapshot looking live; say so instead.
        problems = self.live.health()["problems"]
        if problems:
            self._set_status("⚠  " + "; ".join(p["text"] for p in problems))

    def _refresh_terminal(self, snap: dict) -> None:
        c, sig = snap.get("candle"), snap.get("signal")
        if c:
            self.stats["price"].set(f'{c["price"]:,.0f}',
                                    theme.UP if c["is_up"] else theme.DOWN)
            # feeds.Candle.change_pct is already in percent — do not scale again.
            self.stats["hour"].set(f'{c["change_pct"]:+.2f}%',
                                   theme.pnl_color(c["change_pct"]))
        if sig:
            self.stats["model"].set(f'{sig["model_up"]*100:.1f}%')
            self.stats["market"].set(f'{sig["market_up"]*100:.1f}%')
            # Coloured by side only once the model has beaten the market's
            # calibration; until then a bold, signed, coloured cents figure
            # read as "worth 3.2¢" when it is only a disagreement.
            proven = ((snap.get("portfolio") or {}).get("model_vs_market")
                      or {}).get("model_better")
            self.stats["edge"].set(f'{sig["edge"]*100:+.1f}¢',
                                   theme.side_color(sig["side"]) if proven
                                   else theme.MUTED)
            self.stats["tau"].set(f'{sig["tau"]*100:.0f}%')
            self.hour_bar.set_fraction(sig["tau"])
        self.lattice.set_data(snap.get("lattice", {}))
        m = snap.get("market") or {}
        self.depth.set_book(m.get("bids"), m.get("asks"))

        pf = snap.get("portfolio", {})
        st = pf.get("stats", {})
        if st:
            self.equity.set_data(pf.get("equity", []), st.get("starting_bankroll"))
            self.stats["bankroll"].set(f'${st["bankroll"]:,.0f}')
            self.stats["pnl"].set(f'{st["total_pnl"]:+,.0f}',
                                  theme.pnl_color(st["total_pnl"]))
            self.stats["trades"].set(str(st["n_trades"]))
            self.stats["win rate"].set(f'{st["win_rate"]:.0f}%')
            self.stats["profile"].set(st.get("risk_profile", "—"))
        mvm = pf.get("model_vs_market") or {}
        rh = pf.get("run_health") or {}
        buy = pf.get("buyability") or {}
        if buy.get("verdict"):
            # Calibrated is not the same as buyable; the second answer lives
            # on hover, where there is room for its error bar.
            self.mvm.setToolTip(self.mvm.toolTip().split("\n\nAt the touch:")[0]
                                + "\n\nAt the touch: " + buy["verdict"])
        plain = words.plain()
        health = ""
        if rh.get("started"):
            health = (f' · {rh.get("coverage_pct", 0):.0f}% of hours watched'
                      f' · {rh.get("voided", 0)} skipped' if plain else
                      f' · coverage {rh.get("coverage_pct", 0):.0f}%'
                      f' · {rh.get("voided", 0)} voided')
            age = rh.get("last_settled_age_s")
            if age is not None:
                health += (f' · last result {age // 60}m ago' if plain
                           else f' · last settle {age // 60}m ago')
            if rh.get("stale"):
                health += "  ⚠ no results lately" if plain else "  ⚠ STALLED"
        if mvm.get("n"):
            score = ("accuracy score (lower is better)" if plain else "Brier")
            self.mvm.setText(
                f'model vs market · {mvm["n"]} hrs scored · {score} '
                f'{mvm.get("model_brier", 0):.4f} vs {mvm.get("market_brier", 0):.4f}'
                f' — {mvm.get("verdict", "")}{health}')
        else:
            self.mvm.setText("model vs market: no settled hours scored yet — "
                             f"fills in as hours resolve, traded or not{health}")

    #: After this long with no board, "the first scan takes about a minute"
    #: is no longer true and the placeholder says so.
    ASSETS_LATE_S = 180

    def _assets_empty_text(self, assets: dict, now: float,
                           read_only: bool = False) -> str:
        """What the Screener says when it has no rows: never "fetching" once
        that has stopped being true (closing UX C-1)."""
        if assets.get("error"):
            # First: an old board's "filtered" or "fetching" is about a scan
            # that is no longer the latest. Neutral wording — the failure may be
            # after the prices arrived (marking the book, alerts).
            return (f"The last scan failed ({assets['error'][:140]}). "
                    "Trying again shortly.")
        if assets.get("generated"):
            if assets.get("priced") == 0:
                return ("No prices came back from the market data source on the last "
                        "scan. Trying again shortly.")
            return "No instruments pass this risk profile's volatility filter."
        if read_only:
            return ("No board in this window: it is read-only, and the status "
                    "line says why.")
        waited = now - self._assets_since
        if waited > self.ASSETS_LATE_S:
            return (f"Still no prices after {int(waited // 60)} minutes: the first "
                    "scan has not finished. It keeps trying.")
        return self.ASSETS_LOADING

    def _refresh_cards(self, assets: dict, read_only: bool = False) -> None:
        now = time.time()
        if read_only or getattr(self, "_assets_since", None) is None:
            # A read-only window does not scan: its "still no prices after N
            # minutes" clock starts when it may.
            self._assets_since = now
        empty = (self._assets_empty_text(assets, now, read_only)
                 if not assets.get("assets") else None)
        asig = (assets.get("generated"), assets.get("n"), empty)
        if asig != self._assets_sig:
            self._assets_sig = asig
            generated = float(assets.get("generated") or 0.0)
            # Kept so the AGE column can keep counting between scans. The list
            # is replaced in the same breath as the widgets it names, so it can
            # never outlive them — a stale entry here would be a deleted C++
            # object and a RuntimeError on the next tick.
            self._asset_rows = [AssetRow(a, self._read, self._trade, generated)
                                for a in assets.get("assets", [])]
            self._rebuild(self._assets_lay, list(self._asset_rows), empty or "")
        else:
            for row in self._asset_rows:
                row.update_age(now)

    @staticmethod
    def _rebuild(lay: QVBoxLayout, widgets: list[QWidget], empty_msg: str) -> None:
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not widgets:
            # Wrapped: an error can make this long, and an unwrapped label
            # sets the window's minimum width (see label()).
            lay.addWidget(label(empty_msg, "muted", theme.figure(10), wrap=True))
        for wdg in widgets:
            lay.addWidget(wdg)
        lay.addStretch(1)

    def _refresh_institutions(self) -> None:
        with self.live.lock:
            inst = dict(self.live.inst)
        pr = inst.get("pressure") or {}
        level = pr.get("level", "—")
        self.inst_level.setText(level)
        self.inst_level.setStyleSheet(
            f"color: {(theme.GOLD if level == 'Heavy' else theme.MUTED).name()};")
        rows = [f"· [{e['institution']}] {e['title'][:88]}"
                for e in (inst.get("policy") or inst.get("recent") or [])[:5]]
        self.inst_list.setTextFormat(Qt.PlainText)  # feed text is never markup
        self.inst_list.setText("\n".join(rows) or "nothing on the wire yet")

    def _refresh_macro(self, snap: dict) -> None:
        self._refresh_institutions()
        mc = snap.get("macro")
        if not mc:
            self.regime_lb.setText("—")
            self.regime_lb.setStyleSheet(f"color: {theme.MUTED.name()};")
            self.regime_sub.setText("")
            # No figures without a regime: a dash beside the last known 10y and
            # VIX read as current numbers once the feed behind them stopped.
            self.regime_bar.set_parts({}, {})
            for stat in self.macro_stats.values():
                stat.set("—")
            if snap.get("status") == "read-only":
                # Nothing loads here and the horizon cannot be changed: say so,
                # rather than "Loading…" or advice that would be refused.
                self.macro_note.setText("The macro regime is not available in this "
                                        "window: it is read-only, and the status "
                                        "line says why.")
                return
            on_long = (snap.get("horizon") or {}).get("macro",
                                                      self.live.horizon.macro)
            self.macro_note.setText(
                "Loading the macro regime…" if on_long else
                "The macro regime is only material at long horizons. "
                "Switch to “This quarter” or “This year” to load it.")
            return
        r = mc.get("regime", "unknown")
        self.regime_lb.setText(r.upper())
        self.regime_lb.setStyleSheet(
            f"color: {theme.REGIME.get(r, theme.MUTED).name()};")
        self.regime_sub.setText(mc.get("rationale", ""))
        comp = {k: v for k, v in (mc.get("comp") or {}).items() if k != "score"}
        self.regime_bar.set_parts(comp, {k: 1.0 for k in comp})

        def setv(key, val, fmt="{:.2f}", color=None):
            self.macro_stats[key].set("—" if val is None else fmt.format(val),
                                      color)
        setv("10y", mc.get("ten_year"), "{:.2f}%")
        cs = mc.get("curve_spread")
        setv("curve", cs, "{:+.2f}pp",
             theme.DOWN if cs is not None and cs < 0 else theme.UP)
        setv("fed funds", mc.get("fed_funds"), "{:.2f}%")
        setv("VIX", mc.get("vix"), "{:.1f}")
        setv("real 10y", mc.get("real_10y"), "{:+.2f}%")
        cpi = mc.get("cpi_yoy")
        setv("CPI y/y", None if cpi is None else cpi * 100, "{:.2f}%")
        u, uc = mc.get("unemployment"), mc.get("unemployment_chg_12m")
        self.macro_stats["unemployment"].set(
            "—" if u is None else f'{u:.1f}%' + (f' ({uc:+.1f})' if uc is not None else ''))
        self.macro_note.setText(
            "Components are a published, transparent blend — curve 0.30, "
            "volatility 0.30, policy 0.20, labour 0.20 — describing conditions, "
            "not forecasting them. Source: FRED. "
            f'As of {", ".join(f"{k} {v}" for k, v in (mc.get("as_of") or {}).items() if v)}.')

    # Total grace for the background threads to notice they should finish --
    # a budget shared across all of them, not each. Per-thread it was 4s each,
    # and shutdown() runs on the UI thread, so six threads could hold the event
    # loop for 24 seconds with the window on screen painting nothing. That is
    # the same white rectangle the deadlock below produced, just self-healing.
    #
    # The poll loop returns almost at once once stopped. Anything slower is a
    # socket already in flight, and those run to timeouts of 8-30s, which no
    # wait worth making can outlast -- so the budget is for the common case and
    # _exit_now handles the rest.
    SHUTDOWN_GRACE_MS = 1500

    def shutdown(self) -> None:
        """Stop the background threads before the process exits.

        Qt calls ``qFatal()`` when a QThread is destroyed while still running,
        and qFatal aborts: the process dies with SIGABRT and macOS reports
        "Python quit unexpectedly" rather than exiting cleanly. Interpreter
        shutdown destroys this window, which *owns* those threads, so stopping
        them here is not optional — lab_hub's MainWindow.shutdown guards the
        same way for the same reason.

        Wired to ``QApplication.aboutToQuit`` so it runs however the quit
        arrived: the tray's Quit item, Cmd-Q, or a logout.
        """
        timer = getattr(self, "timer", None)
        if timer is not None:
            timer.stop()
        self.live.stop()                    # ends the poll loop's wait()
        deadline = time.monotonic() + self.SHUTDOWN_GRACE_MS / 1000.0
        stragglers = []
        for name, thread in self._owned_threads():
            if thread is None or not thread.isRunning():
                continue
            thread.quit()                   # no-op for run()-override threads
            left = max(0, int((deadline - time.monotonic()) * 1000))
            if not thread.wait(left):
                stragglers.append(name)
        if stragglers:
            self._exit_now(stragglers)

    def _owned_threads(self):
        """Every QThread this window owns, not just the long-lived ones.

        A thread parented here is destroyed when the window is, and Qt aborts
        the process if it is still running at that moment — so a thread left off
        this list is a crash on quit that only shows up when that feature
        happens to be mid-flight. The Playmaker read and the backtest were both
        missing, which is how the SIGABRT came back.
        """
        return (("poll", getattr(self, "poll", None)),
                ("read", self._read_thread),
                ("config", self._cfg_thread),
                ("backtest", self._bt_thread),
                ("lab", self._lab_thread),
                ("sports_measure", self._sports_thread),
                ("playmaker", getattr(self, "playmaker_thread", None)))

    def _exit_now(self, stragglers) -> None:
        """Leave without running interpreter teardown.

        This is the fix for the blank white window, reported four times and
        misdiagnosed three: **the close button was never the bug.** The window
        went white because the process deadlocked, and it deadlocked here.

        The old last resort was ``QThread.terminate()``. On a thread running
        Python that is not a last resort, it is a hang: terminate kills the
        thread wherever it happens to be, and if it holds the **GIL** — which a
        thread running Python always does — the GIL is never released. Every
        Python thread then blocks in ``take_gil`` forever, including the one
        running the Qt event loop. Nothing repaints, so macOS shows the window's
        empty backing store: a white rectangle, in an app themed near-black,
        that ignores every click. ``AGENTS.md`` already records this trap
        costing hours in the *test suite*; the same call was live in shutdown.

        It fired reliably rather than rarely. ``live.stop()`` is cooperative and
        only lands between fetches, so a quit during any in-flight request had
        to outlast a socket timeout of 8-30s within the grace above — and then
        terminated a thread that was, by construction, mid-``read()`` in Python.

        So: do not stop the thread at all. End the process instead. ``os._exit``
        skips interpreter teardown entirely, so the QThread destructors that
        would call ``qFatal()`` never run — which was the only reason terminate
        was ever wanted. Nothing is lost by leaving this way: the engine writes
        through on every change rather than saving at exit, and the lock below
        is a PID file that the next launch reclaims when its holder is gone.
        """
        live = getattr(self, "live", None)
        lock = getattr(live, "engine_lock", None)
        if lock is not None:
            try:
                lock.release()  # else the next launch starts read-only
            except OSError:
                pass
        sys.stderr.write(
            "SONAR: exiting with %s still in flight; "
            "not waiting for the network\n" % ", ".join(stragglers))
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except (OSError, ValueError):
                pass
        os._exit(0)

    def eventFilter(self, obj, e) -> bool:
        """Let a genuine quit through the hide-on-close guard.

        Reported as "used Cmd-Q and the app didn't close". macOS asks the app to
        terminate, and **Qt implements that by sending a close event to every
        window** — so a window that ignores one cancels the quit. `closeEvent`
        ignored every close except the tray's, because the tray's Quit was the
        only thing that ever set `allow_close`.

        From full screen it was worse than a no-op. `closeEvent` had already run
        `showNormal()` and scheduled the deferred hide, so the window dropped out
        of full screen and sat there blank while the process stayed alive —
        which is what the screenshot showed.

        Watching for `QEvent.Quit` here rather than in `main.py` keeps the
        release next to the guard it releases, and makes it testable without
        building the real application subclass.
        """
        if e.type() == QEvent.Type.Quit:
            self.allow_close = True
        return super().eventFilter(obj, e)

    def closeEvent(self, e) -> None:
        """Hide, don't quit — see ui/tray.py for why.

        Closing the window while the engine is mid-hour would abandon a priced
        position before it settles, which is exactly the data the app exists to
        collect. Quitting is available, but it is a deliberate act from the
        menu bar rather than the side effect of a close button.

        This has been reported as broken three times, and **every time the
        design was fine and the hide was not**. Once because leaving a
        full-screen Space re-activated the app after the deferred hide had run,
        so the Dock handler reopened the window it had just closed
        (`reopen_allowed`). Once because the UI thread was blocked in a network
        fetch, so the event loop never ran and the window sat on screen painting
        nothing (`tests/test_ui_thread.py`). Once because the deferred hide ran
        while the Space was still animating: AppKit drops a hide aimed at a
        window in that state and Qt records it anyway, so the window stayed on
        screen and the next close had nothing left to hide
        (`_hide_after_fullscreen`, `_confirm_hidden`).

        So the thing to check when someone says the close button does nothing is
        whether the window actually became invisible — not whether it should
        have quit. `tests/test_window_close.py` asserts it does, which nothing
        did before.
        """
        if getattr(self, "allow_close", False) or self.tray is None:
            self.timer.stop()
            e.accept()
            return
        e.ignore()
        if not self.isVisible():
            # Qt already considers this window hidden, yet the user just pressed
            # its close button — so the last hide never reached the screen and
            # `hide()` would be a no-op. Reported as "I click the red X again
            # and nothing happens". Put Qt back in sync with what is actually
            # on screen, then hide for real.
            self.setVisible(True)
            self._hide_now()
            QTimer.singleShot(HIDE_CONFIRM_MS,
                              lambda: self._confirm_hidden(HIDE_CONFIRM_TRIES))
            self.tray.note_hidden()
            return
        if self.isFullScreen():
            # Hiding a full-screen window leaves its macOS Space behind with
            # nothing in it — the user closes SONAR and is left staring at a
            # black screen. Drop back to a normal window first, and let the
            # Space transition finish before actually hiding.
            self._hide_on_leaving_fullscreen = True
            self.showNormal()
            QTimer.singleShot(FULLSCREEN_EXIT_MS, self._hide_after_fullscreen)
        else:
            self._hide_now()
        self.tray.note_hidden()

    def _hide_after_fullscreen(self, tries: int = HIDE_CONFIRM_TRIES) -> None:
        """The deferred half of a close pressed in full screen.

        It can arrive after the user has already reopened the window — from the
        menu bar, or by clicking the close button again while the Space was
        still animating — and hiding then would be the app swallowing a window
        the user just asked for. `reveal()` clears the flag; this is a no-op
        once it has.
        """
        if not isValid(self) or not self._hide_on_leaving_fullscreen:
            return
        if self.isFullScreen():
            # showNormal() has not taken yet. Hiding now would leave an empty
            # Space behind, so wait for the transition rather than force it.
            # Bounded, because a window the user has put back into full screen
            # would otherwise keep a hide armed for the rest of the session.
            if tries > 0:
                QTimer.singleShot(
                    FULLSCREEN_EXIT_MS,
                    lambda: self._hide_after_fullscreen(tries - 1))
            else:
                self._hide_on_leaving_fullscreen = False
            return
        self._hide_on_leaving_fullscreen = False
        self._hide_now()
        QTimer.singleShot(HIDE_CONFIRM_MS,
                          lambda: self._confirm_hidden(HIDE_CONFIRM_TRIES))

    def _confirm_hidden(self, tries: int) -> None:
        """Ask again if the hide did not reach the screen.

        AppKit drops a hide aimed at a window that is still animating out of its
        full-screen Space. Qt marks the window hidden regardless, so `isVisible`
        agrees with the hide and only the platform window knows better: it stays
        *exposed*. That mismatch is the bug behind both halves of the report —
        a window left on screen painting nothing, and a second press of the
        close button doing nothing because Qt had nothing left to hide.

        Showing before hiding again is deliberate: a `hide()` Qt considers
        redundant never reaches the platform window at all.

        This runs from a timer, so it can outlive the window: a quit, or a test
        run tearing windows down, deletes the C++ object while the callback is
        still queued. `isValid` is the answer to that — without it the call
        raised "Internal C++ object already deleted" after the last test of
        every suite run, exit code 0, easy to learn to ignore.
        """
        if not isValid(self) or tries <= 0 or self.isVisible():
            return
        handle = self.windowHandle()
        if handle is None or not handle.isExposed():
            return
        self.setVisible(True)
        self._hide_now()
        QTimer.singleShot(HIDE_CONFIRM_MS,
                          lambda: self._confirm_hidden(tries - 1))

    def _fit_to_screen(self) -> None:
        """Open at the preferred size, or the screen's, whichever is smaller.

        A window taller than the display opens with its title bar tucked under
        the menu bar and its status line off the bottom; wider than the display
        and half the toolbar is gone. 820pt of height did exactly that on a
        1280x800 laptop, which is not an unusual screen.
        """
        want_w, want_h = PREFERRED_SIZE
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            want_w = min(want_w, avail.width() - SCREEN_MARGIN)
            want_h = min(want_h, avail.height() - SCREEN_MARGIN)
        self.resize(want_w, want_h)

    # -- the status line, the window status bar, the undo toast ------------- #
    TOAST_MS = 8000

    def _status_bar_parts(self):
        """Built on first use: the window's status bar carries the status line
        while the rail is folded to icons (it used to vanish with the rail's
        foot below 1420px — trade results, errors, read-only notices and all),
        and the undo toast at any width."""
        if getattr(self, "_bar_status", None) is None:
            bar = self.statusBar()
            bar.setSizeGripEnabled(False)
            self._bar_status = label("", "faint", theme.figure(9))
            self._toast_label = label("", "", theme.text(10))
            for lb in (self._bar_status, self._toast_label):
                lb.setTextFormat(Qt.PlainText)  # status and errors, never markup
            self._toast_undo = QPushButton("Undo")
            self._toast_undo.setFont(theme.text(10))
            self._toast_undo.clicked.connect(self._undo_clicked)
            bar.addWidget(self._bar_status, 1)
            bar.addPermanentWidget(self._toast_label)
            bar.addPermanentWidget(self._toast_undo)
            self._toast_label.hide()
            self._toast_undo.hide()
            self._toast_timer = QTimer(self)
            self._toast_timer.setSingleShot(True)
            self._toast_timer.timeout.connect(self._toast_done)
            self._toast_target: tuple[str, str] | None = None
            bar.setVisible(self.tabs.is_collapsed())
            self._bar_status.setVisible(self.tabs.is_collapsed())
        return self._bar_status

    def _set_status(self, text: str, hold_s: float | bool = False) -> None:
        """Write the status line. ``hold_s`` keeps it for that many seconds
        (True: as long as a toast) against refresh()'s once-a-second rewrite,
        which used to erase a refused trade's warning within a second (closing
        UX C-2). A later held message replaces an earlier one at once."""
        now = _now()
        if hold_s is False:
            if now < getattr(self, "_status_hold_until", 0.0):
                return
        else:
            span = self.TOAST_MS / 1000 if hold_s is True else float(hold_s)
            self._status_hold_until = now + span
        self.status.setText(text)
        self._status_bar_parts().setText(text)

    def _sync_status_bar(self) -> None:
        self._status_bar_parts()
        toast = not self._toast_label.isHidden()
        self._bar_status.setVisible(self.tabs.is_collapsed())
        self.statusBar().setVisible(self.tabs.is_collapsed() or toast)

    def _toast(self, text: str, pos_id: str, kind: str) -> None:
        """Did it — and here is the way back, for a few seconds. A one-click
        trade with its result in a line the user may not be looking at was
        the misclick trap; Undo takes it back before it can count."""
        self._status_bar_parts()
        self._toast_target = (pos_id, kind)
        self._toast_label.setText(f"✓  {text}")
        self._toast_label.show()
        self._toast_undo.show()
        self._toast_undo.setEnabled(True)
        self._toast_timer.start(self.TOAST_MS)
        self._sync_status_bar()

    def _warn(self, text: str) -> None:
        """A refusal, held as long as a success's toast but with nothing to
        undo: the user who clicked and looked away still sees it."""
        self._status_bar_parts()
        self._toast_target = None
        self._toast_label.setText(f"⚠  {text}")
        self._toast_label.show()
        self._toast_undo.hide()
        self._toast_timer.start(self.TOAST_MS)
        self._sync_status_bar()

    def _toast_done(self) -> None:
        self._toast_target = None
        self._toast_label.hide()
        self._toast_undo.hide()
        self._sync_status_bar()

    def _undo_clicked(self) -> None:
        if self._toast_target is None:
            return
        pos_id, kind = self._toast_target
        result = self.live.undo(pos_id, kind)
        self._toast_timer.stop()
        self._toast_done()
        self._set_status(("↶  " if result["ok"] else "⚠  ") + result["message"],
                         hold_s=True)
        if not result["ok"]:
            self._warn(f"Not undone: {result['message']}")
        self._assets_sig = self._book_sig = self._portfolio_sig = None

    def _sync_rail(self) -> None:
        """Fold or unfold the rail to match the window's width.

        Split out of resizeEvent because Qt only delivers resize events to a
        window that is (about to be) shown — a hidden window resized
        programmatically, which is what every test does, changes geometry
        without the event, so the tests call this directly.
        """
        self.tabs.set_collapsed(self.width() < RAIL_COLLAPSE_BELOW)
        self._sync_status_bar()

    def resizeEvent(self, e) -> None:
        """Give the board its width back on a small screen.

        Below RAIL_COLLAPSE_BELOW the rail drops to icons — state untouched,
        painting only, see ``PlainTabs.set_collapsed``. Guarded because Qt
        delivers the first resize while ``_fit_to_screen`` runs, before the
        rail exists.
        """
        super().resizeEvent(e)
        if getattr(self, "tabs", None) is not None:
            self._sync_rail()

    def reveal(self) -> None:
        """Bring the window back — the tray item and a Dock click both land here.

        Everything that reopens the window goes through this, because a reveal
        has to call off a hide that is still pending: closing from full screen
        schedules one for once the Space has collapsed, and that timer would
        otherwise hide the window the user has just asked for.
        """
        self._hide_on_leaving_fullscreen = False
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _hide_now(self) -> None:
        """Hide, and remember when — see :meth:`reopen_allowed`."""
        self._hidden_at = time.monotonic()
        self.hide()

    def reopen_allowed(self) -> bool:
        """Is an app activation a real Dock click, or our own hide echoing back?

        Qt cannot tell the two apart: both arrive as ApplicationActivate. The
        only thing that distinguishes them is timing — the echo lands within a
        few hundred milliseconds of a hide this window performed itself.
        """
        return (time.monotonic() - self._hidden_at) * 1000 > REOPEN_GRACE_MS
