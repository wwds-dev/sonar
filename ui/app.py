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

The toolbar carries the two knobs that shape everything: **risk** (how much you
stake, and what is worth showing) and **horizon** (when you want it to resolve).
Neither touches a confidence score — see ``sonar/risk.py`` for why that boundary
is load-bearing.
"""

from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow,
                               QPlainTextEdit, QPushButton, QScrollArea,
                               QSizePolicy, QSpinBox, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from sonar import horizon as hz_mod
from sonar import llm, paths, playmaker, risk as risk_mod
from sonar import version as version_mod
from sonar.playmaker import devig as pm_devig, staking as pm_staking
from sonar.core import Live
from sonar import assets as asset_mod
from sonar import news as news_mod
from sonar import venues
from sonar.assets import _W as ASSET_W

from . import learn as learn_mod
from . import theme
from . import words
from .charts import ComponentBar, DepthChart, EquityCurve, Lattice, Sparkline
from .tabs import PlainTabs
from .worker import BacktestThread, ConfigThread, PollThread, PropThread, ReadThread

REFRESH_MS = 1000
# Opening size, before the screen gets a say. See MainWindow._fit_to_screen.
PREFERRED_SIZE = (1240, 820)
SCREEN_MARGIN = 40           # leave the dock and the menu bar somewhere to live

# Long enough for macOS to finish collapsing the full-screen Space before the
# window disappears into the menu bar. Shorter and the empty Space survives.
# It has to be a timer: Qt raises WindowStateChange when showNormal() is
# *called* — measured at 1ms after, with the animation still to come — and
# reports the restored geometry just as early, so nothing in Qt says when the
# transition has finished.
FULLSCREEN_EXIT_MS = 350

# How long after hiding itself the window refuses to be reopened by an
# app-activation event. Leaving macOS full screen animates a Space transition
# and the app is re-activated when it finishes — *after* the deferred hide has
# run. The Dock-click handler in main.py then faithfully reopens the window the
# user just closed, which looks exactly like a close button that does nothing.
# A real Dock click a second later still works.
REOPEN_GRACE_MS = 1000

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
    ("age", ("Updated", "AGE"), 66, "",
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


def label(text: str = "", obj: str = "", font=None, align=None,
          wrap: bool = False) -> QLabel:
    """A themed QLabel.

    ``wrap`` matters more than it looks. A QLabel that does not wrap reports a
    sizeHint as wide as its text is long, and a layout cannot shrink below its
    children's minimums — so one unwrapped paragraph sets the minimum width of
    its tab, and the widest tab sets the minimum width of the whole window.
    Three of them once forced SONAR to open 4,540pt wide on a 1,280pt screen.
    """
    lb = QLabel(text)
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
    "bankroll": "practice cash",
    "pnl": "profit / loss",
    "total p/l": "profit / loss",
    "equity": "account value",
    "unrealised": "open profit / loss",
}


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
        holder.setToolTip(f"{a['name']} ({a['symbol']}) · {a['cls']}\n\n"
                          f"{a.get('rationale', '')}\n\n{v.summary()}"
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
        proven = plan.get("calibrated")
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
            + ("Shifted by an edge measured from positions that actually closed."
               if proven else
               "That is 1/(1+reward:risk) exactly — the no-edge baseline, where\n"
               "expected value is zero. It moves only when the Book tab has\n"
               "measured a real edge, and it has not yet."))
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
            ("Read" if plain else "read",
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
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
        outer.addLayout(self._toolbar())

        # Both names on every tab: the plain one leads, the one the docs and the
        # last month of muscle memory use sits under it. See `ui/tabs.py`.
        self.tabs = PlainTabs()
        self.tabs.add(self._terminal_tab(), "Live model", "Terminal",
                      "The hourly bitcoin up/down model — the one place SONAR "
                      "says which way it thinks something goes.")
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
        self.tabs.add(_scrolled(self._lab_tab()), "Practice", "Lab",
                      "Test any claim this app makes against real history, and "
                      "make your own calls on setups with the future hidden.")
        self.tabs.add(_scrolled(self._playmaker_tab()), "Sports", "Playmaker",
                      "Pricing a sports bet: what the bookmakers' margin is, "
                      "and where they disagree with each other.")
        self.tabs.add(self._learn_tab(), "Learn", "",
                      "The manual and the glossary. It assumes no finance "
                      "background — start at §1.")
        outer.addWidget(self.tabs, 1)

        self._apply_wording()

        self.status = label("starting…", "faint", theme.figure(9))
        outer.addWidget(self.status)

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

    def _toolbar(self) -> QHBoxLayout:
        """The two knobs everything else depends on, labelled as questions.

        They used to be a 22px combobox each, captioned `risk` and `horizon` in
        9pt grey. Both words are jargon for the setting they name, both boxes
        were smaller than the text beside them, and neither said what would
        happen if you changed it. Asking the question the setting answers costs
        one line and removes the guessing.
        """
        bar = QHBoxLayout()
        bar.setSpacing(12)

        title = QVBoxLayout()
        title.setContentsMargins(0, 0, 0, 0)
        title.setSpacing(1)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(label("SONAR", "h1"))
        # Next to the name, not tucked in an About box. "I opened the app and
        # nothing is new" was reported repeatedly against a bundle that was
        # simply older than the work being described, and nothing on screen
        # could have told anyone that.
        self.version_label = VersionBadge()
        top.addWidget(self.version_label)
        top.addStretch(1)
        title.addLayout(top)
        title.addWidget(label("practice money only — nothing here places a real "
                              "order", "faint", theme.text(9)))
        holder = QWidget()
        holder.setLayout(title)
        bar.addWidget(holder)
        bar.addStretch(1)

        def field(caption: str, box: QComboBox, tip: str) -> QWidget:
            holder = QWidget()
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

        buttons = QVBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(3)
        buttons.addWidget(label("", "faint", theme.text(9)))   # align with the boxes
        row = QHBoxLayout()
        row.setSpacing(8)
        self.wording_btn = QPushButton("")
        self.wording_btn.setFont(theme.text(11))
        self.wording_btn.setToolTip(
            "Which words the app uses for the same numbers.\n\n"
            "Plain — 'Worth a look', 'Swing size', a sentence on every row.\n"
            "Expert — CONF, VOL, R:R, the ticker back on the row, and no\n"
            "second lines, which makes the board about a third shorter.\n\n"
            "Same columns, same order, same arithmetic either way.")
        self.wording_btn.clicked.connect(self._toggle_wording)
        row.addWidget(self.wording_btn)

        learn = QPushButton("Learn")
        learn.setObjectName("primary")
        learn.setFont(theme.text(11))
        learn.setToolTip(
            "The manual and the glossary, inside the app: what every number\n"
            "means, how the model works, and what SONAR will not do.\n"
            "Start at §1 if markets are new to you — it assumes nothing.")
        learn.clicked.connect(lambda: self._show_learn())
        row.addWidget(learn)

        plan = QPushButton("Test plan")
        plan.setFont(theme.text(11))
        plan.setToolTip(
            "The acceptance checklist for signing off a build.\n"
            "Tick each case off as you go — the page remembers what you have\n"
            "already passed or failed. Twenty are marked as regressions: each\n"
            "one has caught a real bug before.")
        plan.clicked.connect(self._open_testplan)
        row.addWidget(plan)
        buttons.addLayout(row)
        holder = QWidget()
        holder.setLayout(buttons)
        bar.addWidget(holder)
        return bar

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
            self.status.setText(f"⚠  {what} not found at {page}")
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

        strip = panel()
        g = QGridLayout(strip)
        g.setContentsMargins(14, 10, 14, 10)
        self.stats = {}
        cells = [("price", "BTC/USD, live"), ("hour", "This hour's open → now"),
                 ("model", "Our P(up) from the barrier model"),
                 ("market", "Polymarket's implied P(up)"),
                 ("edge", "Model minus market — our only disagreement"),
                 ("tau", "Fraction of the hour still to run")]
        for i, (k, tip) in enumerate(cells):
            s = Stat(k, tip)
            self.stats[k] = s
            g.addWidget(s, 0, i)
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

        pstrip = panel()
        pg = QGridLayout(pstrip)
        pg.setContentsMargins(14, 10, 14, 10)
        for i, (k, tip) in enumerate([
                ("bankroll", "Paper bankroll"), ("pnl", "Total paper P&L"),
                ("trades", "Settled live trades — the fair-odds warm-up rows "
                           "on the chart are not counted here"),
                ("win rate", "Share of live trades won"),
                ("profile", "Risk profile this bankroll was built under")]):
            s = Stat(k, tip)
            self.stats[k] = s
            pg.addWidget(s, 0, i)
        lay.addWidget(pstrip)

        # Model vs market, scored on every hour watched — traded or not.
        # The direct test of the realised-vs-implied thesis, and it converges
        # at 24 observations a day instead of a few trades a week.
        self.mvm = label("", "muted", theme.figure(10), wrap=True)
        self.mvm.setToolTip(
            "Brier score (lower is better) of the model's P(up) against the\n"
            "market's, snapshotted mid-hour for every hour and settled on the\n"
            "real candle. Unlike the P&L this scores the hours the engine did\n"
            "NOT trade too, so it cannot be flattered by selection.")
        lay.addWidget(self.mvm)

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

    def _scroll_tab(self, which: str, header: QWidget | None = None) -> QWidget:
        area = QScrollArea()
        area.setWidgetResizable(True)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(2, 8, 8, 8)
        lay.setSpacing(8)
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
        self.alert_list = label("nothing yet", "muted", theme.figure(9))
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
            self.alert_list.setText("nothing yet — alerts need one scan to "
                                    "compare against")
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
        self._rebuild(self._wire_lay, rows, "no headlines yet")

        try:
            sg = self.live.suggestions()
        except Exception:
            sg = []
        self._rebuild(self._sugg_lay,
                      [SuggestionCard(s, self._trade) for s in sg],
                      "Nothing with elevated coverage right now — which is a\n"
                      "normal state, not a failure to find something.")

        items = []
        for e in ev.get("earnings", [])[:25]:
            items.append(EventRow(f'{e["symbol"]}', f'earnings · {e["when"]}',
                                  f'{e["days_away"]}d', theme.GOLD))
        for l in ev.get("listings", [])[:15]:
            sym = l["symbol"] or "—"
            items.append(EventRow(sym, f'IPO {l["status"]} · {l["company"][:26]}',
                                  l["price"] or "", theme.UP))
        self._rebuild(self._events_lay, items, "no scheduled events found")

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
            "Replay the same plan over two years of real bars.\n"
            "Live positions take months to grade; this answers today —\n"
            "for the price half of the score, which is all history can test.")
        self.bt_btn.clicked.connect(self._run_backtest)
        ch.addWidget(self.bt_btn)
        cl.addLayout(ch)
        self.cal_verdict = label("—", font=theme.text(12))
        self.cal_verdict.setWordWrap(True)
        cl.addWidget(self.cal_verdict)
        self.cal_table = label("", "muted", theme.figure(10))
        cl.addWidget(self.cal_table)
        self.bt_result = label("", "muted", theme.figure(10))
        self.bt_result.setWordWrap(True)
        cl.addWidget(self.bt_result)
        lay.addWidget(cal)

        area = QScrollArea()
        area.setWidgetResizable(True)
        host = QWidget()
        self._book_lay = QVBoxLayout(host)
        self._book_lay.setContentsMargins(2, 4, 8, 8)
        self._book_lay.setSpacing(8)
        self._book_lay.addStretch(1)
        area.setWidget(host)
        lay.addWidget(area, 1)
        self._book_sig = None
        return w

    def _refresh_book(self) -> None:
        with self.live.lock:
            pos = dict(self.live.positions)
            cal = dict(self.live.calibration)
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
        for b in cal.get("buckets", []):
            if not b["n"]:
                continue
            hr = "—" if not b["enough"] else f'{b["hit_rate"]*100:.0f}%'
            note = "" if b["enough"] else f'  (need {cal.get("min_sample", 20)})'
            rows.append(f'  score {b["lo"]:>3}–{b["hi"]:<3}  n={b["n"]:<4} '
                        f'hit {hr:<5} vs advertised {b["expected"]*100:.0f}%{note}')
        self.cal_table.setText("\n".join(rows) or
                               "  no closed positions yet — nothing to grade")

        sig = (st.get("n_open"), st.get("n_closed"), round(st.get("unrealised", 0), 1))
        if sig == self._book_sig:
            return
        self._book_sig = sig
        self._rebuild(self._book_lay,
                      [PositionRow(p, self._close_position)
                       for p in pos.get("open", [])],
                      "No open paper positions. Use buy or short on the Assets tab.")

    # -- lab ---------------------------------------------------------------- #
    def _lab_tab(self) -> QWidget:
        """Run the algorithm against history, with the knobs exposed.

        The Book tab's backtest button answers one fixed question. This answers
        whichever one you ask, and the point is falsification rather than
        reassurance: change the reward:risk and watch the realised hit rate move
        to meet `1/(1+R:R)`, because that identity is the claim the whole app
        rests on. If it ever stops holding, something here is wrong.

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

        for col, cap in enumerate(("UNIVERSE", "RANGE", "HORIZON (DAYS)", "STEP (BARS)")):
            form.addWidget(label(cap, "faint", theme.figure(8)), 0, col)
        form.addWidget(self.lab_universe, 1, 0)
        form.addWidget(self.lab_range, 1, 1)
        form.addWidget(self.lab_horizon, 1, 2)
        form.addWidget(self.lab_step, 1, 3)
        hl.addLayout(form)
        hl.addWidget(self.lab_news)

        row = QHBoxLayout()
        self.lab_btn = QPushButton("Run simulation")
        self.lab_btn.setFixedWidth(150)
        self.lab_btn.clicked.connect(self._lab_run)
        row.addWidget(self.lab_btn)
        self.lab_status = label("", "faint", theme.figure(9))
        row.addWidget(self.lab_status, 1)
        hl.addLayout(row)
        lay.addWidget(head)

        self.lab_out = QTextBrowser()
        self.lab_out.setOpenExternalLinks(False)
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
        self.rep_card.setHtml("<p style='color:#7c8798'>No replay running.</p>")
        rl.addWidget(self.rep_card)
        lay.addWidget(rep)
        return w

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
        self._lab_thread = BacktestThread(
            symbols, self.lab_horizon.value(), self,
            rng=self.lab_range.currentData(), step=self.lab_step.value(),
            with_news=self.lab_news.isChecked())
        self._lab_thread.progress.connect(
            lambda sym, n: self.lab_status.setText(f"{sym} — {n} setups so far"))
        self._lab_thread.done.connect(self._lab_done)
        self._lab_thread.start()

    def _lab_done(self, r: dict) -> None:
        self.lab_btn.setEnabled(True)
        n = r.get("n", 0)
        self.lab_status.setText(f"{n:,} resolved setups" if n else "no result")
        self.lab_out.setHtml(self._lab_html(r))

    @staticmethod
    def _lab_html(r: dict) -> str:
        if not r.get("n"):
            return (f"<p style='color:#e06c75'>{r.get('verdict', 'nothing resolved')}"
                    "</p>")
        hit, pred = r["hit_rate"], r["predicted"]
        se, delta = r["std_error"], r["delta"]
        within = abs(delta) <= 2 * se
        colour = "#7c8798" if within else "#e5c07b"
        rows = [
            ("Resolved setups", f"{r['n']:,} across {r.get('symbols', 0)} instruments"),
            ("Realised hit rate", f"{hit * 100:.2f}%"),
            ("Predicted by the barrier maths", f"{pred * 100:.2f}%"),
            ("Difference", f"{delta * 100:+.2f} pts  (±{2 * se * 100:.2f} at 2 s.e.)"),
            ("Expectancy", f"{r['expectancy_r']:+.3f} R per setup"),
            ("Implied drift", f"{r['implied_edge_sigma']:+.4f} σ"),
            ("Average hold", f"{r['avg_bars_held']:.1f} bars"),
        ]
        body = "".join(
            f"<tr><td style='padding:2px 18px 2px 0;color:#7c8798'>{k}</td>"
            f"<td style='padding:2px 0'><b>{v}</b></td></tr>" for k, v in rows)
        out = [f"<table>{body}</table>",
               f"<p style='color:{colour}'><b>{r['verdict']}</b></p>"]

        if within:
            out.append("<p style='color:#7c8798'>The difference sits inside its own "
                       "error bar, which is what a model with no edge is supposed to "
                       "look like. That is the result, not a failure to find one.</p>")

        for title, key in (("Momentum buckets", "buckets"),
                           ("Attention buckets", "attention_buckets")):
            bk = r.get(key) or []
            if not bk:
                continue
            head = "".join(f"<th style='text-align:left;padding-right:16px'>{h}</th>"
                           for h in ("bucket", "n", "hit rate", "vs baseline"))
            body = "".join(
                "<tr>" + "".join(
                    f"<td style='padding-right:16px'>{c}</td>" for c in (
                        b.get("label", "?"), f"{b.get('n', 0):,}",
                        f"{b.get('hit_rate', 0) * 100:.1f}%",
                        f"{b.get('delta', 0) * 100:+.1f}")) + "</tr>"
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
                       "UNCLEAR": "#7c8798", "not measured": "#5c6370"}

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
                    f"<p style='color:#7c8798'>{a.get('note', 'not enough setups')}"
                    "</p>")

        head = "".join(f"<th style='text-align:left;padding-right:14px'>{h}</th>"
                       for h in ("component", "weight", "IC", "top−bottom",
                                 "blend without it", "verdict"))
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
                f"<b style='color:{colour}'>{c.get('verdict', '—')}</b>",
            )
            body.append("<tr>" + "".join(
                f"<td style='padding:2px 14px 2px 0'>{x}</td>" for x in cells) + "</tr>")

        out = ["<h4 style='margin:16px 0 4px'>Component attribution</h4>",
               f"<table>{head}{''.join(body)}</table>"]

        blend = a.get("blend_ic")
        if blend is not None:
            note = ("" if blend > 0 else
                    " — a negative blend IC means the score as a whole is ranking "
                    "the wrong way round, not merely failing to rank")
            out.append(f"<p style='color:#7c8798'>Blended score IC "
                       f"<b>{blend:+.3f}</b> over {a.get('n', 0):,} resolved "
                       f"setups{note}.</p>")

        for c in rows:
            if c.get("why") and c.get("verdict") not in ("not measured",):
                colour = MainWindow._VERDICT_COLOUR.get(c["verdict"], "#7c8798")
                out.append(f"<p style='color:{colour};margin:2px 0'><b>"
                           f"{c['component']}</b> — {c['why']}</p>")

        if a.get("catalyst"):
            out.append(f"<p style='color:#5c6370'>catalyst — {a['catalyst']}</p>")
        out.append("<p style='color:#5c6370'>p-values go through Benjamini-Hochberg "
                   f"together at q={a.get('fdr_q', 0.1)}: testing four components and "
                   "reporting the best one is how noise gets published.</p>")
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
        except ValueError as exc:
            self.playmaker_status.setText(str(exc))
            return [], f"<b>Could not read the prices.</b><br>{exc}"

        self.playmaker_stats["books"].set(str(len(quotes)))
        first = quotes[0]
        self.playmaker_stats["margin"].set(f"{pm_devig.overround(first.odds)*100:.2f}%")

        blocks = [self._devig_html(first)]

        cons = pm_devig.consensus(quotes)
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
        return (f"<b>FAIR PRICE — {quote.book}</b><br>"
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
                f"<tr><td>{o.book}{flag}</td><td align=right>&nbsp;&nbsp;side {o.outcome+1}</td>"
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
                f"States {est.probability*100:.1f}% ({result.lean or 'no lean'}, "
                f"confidence {result.confidence or 'unstated'}). "
                "Not used for the edge, the EV or the stake above: a language "
                "model's percentage is not a measurement, and feeding one to "
                "Kelly is the defect this tab was rebuilt to remove.")
        else:
            head.append(f"Lean {result.lean or '—'}, "
                        f"confidence {result.confidence or '—'}; no figure stated.")

        blocks = ["<br>".join(head)]
        for name in playmaker.SECTIONS:
            body = result.sections.get(name)
            if body:
                blocks.append(f"<b>{name}</b><br>{body.replace(chr(10), '<br>')}")
        narrative = "<br><br>".join(blocks) or text.replace("\n", "<br>")
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
        for stat in self.findChildren(Stat):
            stat.retitle()
        self._assets_sig = None

    def _apply_config(self) -> None:
        if self._cfg_thread and self._cfg_thread.isRunning():
            return
        self.risk_box.setEnabled(False)
        self.hz_box.setEnabled(False)
        self.status.setText("applying — rescanning…")
        self._cfg_thread = ConfigThread(
            self.live, self.risk_box.currentData(), self.hz_box.currentData(), self)
        self._cfg_thread.done.connect(self._config_done)
        self._cfg_thread.start()

    def _config_done(self, _cfg: dict) -> None:
        self.risk_box.setEnabled(True)
        self.hz_box.setEnabled(True)
        for which in ("markets", "assets"):
            setattr(self, f"_{which}_sig", None)      # force a rebuild

    def _run_backtest(self) -> None:
        if self._bt_thread is not None and self._bt_thread.isRunning():
            return
        self.bt_btn.setEnabled(False)
        self.bt_result.setText("replaying two years of bars…")
        from sonar.assets import WATCHLIST
        self._bt_thread = BacktestThread(
            [s for s, _n, _c, _k in WATCHLIST],
            self.live.horizon.momentum_days, self)
        self._bt_thread.done.connect(self._backtest_done)
        self._bt_thread.start()

    def _backtest_done(self, r: dict) -> None:
        self.bt_btn.setEnabled(True)
        if not r.get("n"):
            self.bt_result.setText(f'backtest: {r.get("verdict", "no result")}')
            return
        lines = [
            f'BACKTEST · {r["n"]:,} resolved trials across {r["symbols"]} '
            f'instruments, {r["range"]} of daily bars, {r["horizon_days"]}d horizon',
            f'  realised {r["hit_rate"]*100:.2f}%   '
            f'predicted {r["predicted"]*100:.2f}%   '
            f'delta {r["delta"]*100:+.2f} pts (± {r["std_error"]*100*2:.1f})   '
            f'expectancy {r["expectancy_r"]:+.3f}R',
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
        bookkeeping against an already-fetched price, so there is nothing to
        wait on and a spinner would be theatre."""
        result = self.live.trade(symbol, direction)
        self.status.setText(("✓  " if result["ok"] else "⚠  ") + result["message"]
                            + "  ·  paper money only")
        self._assets_sig = None          # force the board to redraw
        self._book_sig = None

    def _close_position(self, pos_id: str) -> None:
        result = self.live.close_position(pos_id)
        self.status.setText(("✓  " if result["ok"] else "⚠  ") + result["message"])
        self._book_sig = None

    def _read(self, kind: str, ident: str, subject: str) -> None:
        # The read panel lives on the Terminal tab, so every path has to bring
        # the user there. Reporting "unavailable" onto a tab they are not
        # looking at is indistinguishable from the button being dead — which is
        # exactly how the Assets tab's read button used to behave.
        self.read_panel.show()
        self.tabs.setCurrentIndex(0)

        ok, why = llm.available()
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
        self._refresh_wire()

        if snap.get("status") == "read-only":
            # Another SONAR (usually the launchd agent) holds the engine lock.
            # Say so plainly rather than showing a window that looks broken.
            self.status.setText("⚠  " + snap.get("detail", "another engine is running"))
            self.read_btn.setEnabled(False)
            return
        if snap.get("status") != "live":
            self.status.setText(f'{snap.get("status", "…")} — first poll can take a moment')
            return
        self._refresh_terminal(snap)
        self._refresh_cards(assets)
        self._refresh_macro(snap)
        if self.tray is not None:
            self.tray.update_state(snap)

        hz = self.live.horizon
        self.status.setText(
            f'risk {self.live.risk.name} · horizon {hz.name} · '
            f'{assets.get("n", 0)} assets · paper money only')

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
            self.stats["edge"].set(f'{sig["edge"]*100:+.1f}¢',
                                   theme.side_color(sig["side"]))
            self.stats["tau"].set(f'{sig["tau"]*100:.0f}%')
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
        health = ""
        if rh.get("started"):
            health = (f' · coverage {rh.get("coverage_pct", 0):.0f}%'
                      f' · {rh.get("voided", 0)} voided')
            age = rh.get("last_settled_age_s")
            if age is not None:
                health += f' · last settle {age // 60}m ago'
            if rh.get("stale"):
                health += "  ⚠ STALLED"
        if mvm.get("n"):
            self.mvm.setText(
                f'model vs market · {mvm["n"]} hrs scored · Brier '
                f'{mvm.get("model_brier", 0):.4f} vs {mvm.get("market_brier", 0):.4f}'
                f' — {mvm.get("verdict", "")}{health}')
        else:
            self.mvm.setText("model vs market: no settled hours scored yet — "
                             f"fills in as hours resolve, traded or not{health}")

    def _refresh_cards(self, assets: dict) -> None:
        asig = (assets.get("generated"), assets.get("n"))
        if asig != self._assets_sig:
            self._assets_sig = asig
            generated = float(assets.get("generated") or 0.0)
            # Kept so the AGE column can keep counting between scans. The list
            # is replaced in the same breath as the widgets it names, so it can
            # never outlive them — a stale entry here would be a deleted C++
            # object and a RuntimeError on the next tick.
            self._asset_rows = [AssetRow(a, self._read, self._trade, generated)
                                for a in assets.get("assets", [])]
            self._rebuild(self._assets_lay, list(self._asset_rows),
                          "No instruments pass this risk profile's volatility filter.")
        else:
            now = time.time()
            for row in self._asset_rows:
                row.update_age(now)

    @staticmethod
    def _rebuild(lay: QVBoxLayout, widgets: list[QWidget], empty_msg: str) -> None:
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not widgets:
            lay.addWidget(label(empty_msg, "muted", theme.figure(10)))
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
        self.inst_list.setText("\n".join(rows) or "nothing on the wire yet")

    def _refresh_macro(self, snap: dict) -> None:
        self._refresh_institutions()
        mc = snap.get("macro")
        if not mc:
            self.regime_lb.setText("—")
            self.regime_lb.setStyleSheet(f"color: {theme.MUTED.name()};")
            self.regime_sub.setText("")
            self.macro_note.setText(
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

        This has been reported as broken twice, and **both times the design was
        fine and the hide was not**. Once because leaving a full-screen Space
        re-activated the app after the deferred hide had run, so the Dock
        handler reopened the window it had just closed (`reopen_allowed`). Once
        because the UI thread was blocked in a network fetch, so the event loop
        never ran and the window sat on screen painting nothing
        (`tests/test_ui_thread.py`).

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

    def _hide_after_fullscreen(self) -> None:
        """The deferred half of a close pressed in full screen.

        It can arrive after the user has already reopened the window — from the
        menu bar, or by clicking the close button again while the Space was
        still animating — and hiding then would be the app swallowing a window
        the user just asked for. `reveal()` clears the flag; this is a no-op
        once it has.
        """
        if not self._hide_on_leaving_fullscreen:
            return
        self._hide_on_leaving_fullscreen = False
        self._hide_now()

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

    def reveal(self) -> None:
        """Bring the window back — the tray item and a Dock click both land here.

        Everything that reopens the window goes through this, because a reveal
        has to call off a hide that is still pending: closing from full screen
        schedules one for a third of a second later, and that timer would
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
