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

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QTabWidget,
                               QTextBrowser, QVBoxLayout, QWidget)

from sonar import horizon as hz_mod
from sonar import llm, paths, risk as risk_mod, sports
from sonar.core import Live
from sonar.assets import _W as ASSET_W

from . import theme
from .charts import ComponentBar, DepthChart, EquityCurve, Lattice, Sparkline
from .worker import BacktestThread, ConfigThread, PollThread, PropThread, ReadThread

REFRESH_MS = 1000
# Long enough for macOS to finish collapsing the full-screen Space before the
# window disappears into the menu bar. Shorter and the empty Space survives.
FULLSCREEN_EXIT_MS = 350

# The Assets table's columns: key, heading, width, tooltip. The header row and
# every asset row are both built from this one list, so a column can never drift
# away from the heading that names it.
ASSET_COLS = [
    ("name", "", 140, ""),
    ("trend", "TREND", 92, "Recent price path over the horizon's window."),
    ("price", "PRICE", 74, "Latest price."),
    ("1d", "1D", 58, "Change since yesterday's close."),
    ("momentum", "MOM", 86,
     "Change over the horizon's momentum window (1d / 5d / 20d)."),
    ("volatility", "VOL", 56, "Daily volatility of returns."),
    ("lean", "NEWS", 62,
     "How unusual today's coverage is: Quiet / Normal / Elevated / Spike.\n"
     "A notability flag, not odds. Over 25,504 independent historical\n"
     "setups neither momentum nor a news spike beat the 40% baseline\n"
     "(spike came in at +0.8 pts, ±3.1). It marks what is worth a look.\n"
     "Direction is yours — use buy or short."),
    ("rr", "R:R", 46,
     "Reward divided by risk, from a volatility-scaled target and stop.\n"
     "1.5 means the target is 1.5x as far away as the stop."),
    ("pprof", "P(PROF)", 60,
     "Probability of touching the target before the stop.\n"
     "With no proven edge this is exactly 1/(1+R:R) — so a fatter reward\n"
     "buys a lower hit rate and expected value stays zero. Only a measured\n"
     "edge (see the Book tab) moves it."),
    ("mix", "SCORE MIX", 76,
     "What drives the confidence score: momentum, volatility, news, catalyst."),
    ("conf", "CONF", 36,
     "Confidence 0–100: how notable this looks.\n"
     "NOT the probability you will make money — that is P(PROF)."),
    ("actions", "", 186, ""),
]


def _asset_widths() -> list[tuple[str, int]]:
    return [(key, width) for key, _heading, width, _tip in ASSET_COLS]


class AssetHeader(QFrame):
    """Column headings for the Assets table.

    Without these the screen was ten unlabelled numbers per row and you had to
    already know the layout to read it.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        # left margin = the scroll area's own 2px + the row panel's 12px, so a
        # heading sits directly over its column
        lay.setContentsMargins(15, 8, 12, 4)
        lay.setSpacing(14)
        for _key, heading, width, tip in ASSET_COLS:
            lb = label(heading, "faint", theme.mono(8))
            lb.setFixedWidth(width)
            if tip:
                lb.setToolTip(tip)
            lay.addWidget(lb)


def panel() -> QFrame:
    f = QFrame()
    f.setObjectName("panel")
    return f


def label(text: str = "", obj: str = "", font=None, align=None) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    if font:
        lb.setFont(font)
    if align:
        lb.setAlignment(align)
    return lb


class Stat(QWidget):
    """A labelled figure — the terminal's basic readout unit."""

    def __init__(self, caption: str, tip: str = "", parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        self.cap = label(caption.upper(), "faint", theme.mono(8))
        self.val = label("—", font=theme.mono(15, True))
        lay.addWidget(self.cap)
        lay.addWidget(self.val)
        if tip:
            self.setToolTip(tip)

    def set(self, text: str, color=None) -> None:
        self.val.setText(text)
        self.val.setStyleSheet(f"color: {(color or theme.INK).name()};")



class AssetRow(QFrame):
    """One instrument on the screener."""

    def __init__(self, a: dict, on_read, on_trade, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(14)

        widths = dict(_asset_widths())

        holder = QWidget()
        holder.setFixedWidth(widths["name"])
        name = QVBoxLayout(holder)
        name.setContentsMargins(0, 0, 0, 0)
        name.setSpacing(0)
        name.addWidget(label(a["name"], font=theme.ui_font(12, True)))
        name.addWidget(label(f'{a["symbol"]}  ·  {a["cls"]}', "faint", theme.mono(9)))
        lay.addWidget(holder)

        spark = Sparkline(38)
        spark.frame = False
        spark.setFixedWidth(widths["trend"])
        # colour by the horizon's momentum so the line agrees with the number
        # printed next to it and with the lean
        spark.set_values(a.get("spark", []), up=a["momentum"] >= 0)
        lay.addWidget(spark)

        for key, text, tip, col in [
            ("price", f'{a["price"]:,.2f}', "Latest price", theme.INK),
            ("1d", f'{a["day_change"]*100:+.2f}%', "1-day change",
             theme.pnl_color(a["day_change"])),
            ("momentum", f'{a["momentum"]*100:+.1f}% / {a["momentum_days"]}d',
             "Change over the horizon's momentum window",
             theme.pnl_color(a["momentum"])),
            ("volatility", f'{a["volatility"]*100:.1f}%',
             "Daily volatility of returns", theme.MUTED),
        ]:
            lb = label(text, font=theme.mono(11))
            lb.setStyleSheet(f"color: {col.name()};")
            lb.setToolTip(tip)
            lb.setFixedWidth(widths[key])
            lay.addWidget(lb)

        lean = label(a["lean"], font=theme.mono(10, True))
        _news_col = {"Spike": theme.GOLD, "Elevated": theme.UP}
        lean.setStyleSheet(
            f"color: {_news_col.get(a['lean'], theme.MUTED).name()};")
        lean.setToolTip(
            "How unusual today's coverage is — a notability signal, not a\n"
            "direction. The old Bullish/Bearish lean was removed because the\n"
            "backtest found momentum carried no edge at all.")
        lean.setFixedWidth(widths["lean"])
        lay.addWidget(lean)

        plan = a.get("plan") or {}
        rr = label(f'{plan.get("rr", 0):.2f}', font=theme.mono(11))
        rr.setFixedWidth(widths["rr"])
        rr.setToolTip("Reward : risk from a volatility-scaled target and stop.")
        lay.addWidget(rr)

        pp = label(f'{plan.get("p_profit", 0)*100:.0f}%', font=theme.mono(11, True))
        pp.setFixedWidth(widths["pprof"])
        pp.setStyleSheet(
            f"color: {(theme.INK if plan.get('calibrated') else theme.MUTED).name()};")
        pp.setToolTip(
            "Probability of hitting the target before the stop.\n"
            + ("Shifted by a measured edge from closed positions."
               if plan.get("calibrated") else
               "Grey because no edge has been proven yet — this is the\n"
               "driftless baseline 1/(1+R:R), where expected value is zero."))
        lay.addWidget(pp)

        bar = ComponentBar()
        bar.setFixedWidth(widths["mix"])
        bar.set_parts(a.get("comp", {}), ASSET_W)
        lay.addWidget(bar)

        conf = label(f'{a["confidence"]:.0f}', font=theme.mono(14, True))
        conf.setFixedWidth(widths["conf"])
        lay.addWidget(conf)

        acts = QWidget()
        acts.setFixedWidth(widths["actions"])
        al = QHBoxLayout(acts)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(4)
        for text, tip, slot in [
            ("buy", "Open a paper LONG with this plan's target and stop.\n"
                    "Paper money — no order is placed anywhere.",
             lambda: on_trade(a["symbol"], "LONG")),
            ("short", "Open a paper SHORT — the way to act on a bearish read.\n"
                      "Paper money — no order is placed anywhere.",
             lambda: on_trade(a["symbol"], "SHORT")),
            ("read", "Narrative LLM read (optional feature).",
             lambda: on_read("asset", a["symbol"], a["name"])),
        ]:
            b = QPushButton(text)
            b.setFont(theme.mono(9))
            b.setToolTip(tip)
            # Explicit width: squeezed below their text Qt elides these into
            # unreadable glyphs rather than shrinking the font.
            b.setFixedWidth(58)
            b.clicked.connect(slot)
            al.addWidget(b)
        lay.addWidget(acts)


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
        nm = label(f'{s["name"]}', font=theme.ui_font(12, True))
        top.addWidget(nm)
        top.addWidget(label(s["symbol"], "faint", theme.mono(9)))
        lvl = label(s["news_level"], font=theme.mono(9, True))
        lvl.setStyleSheet(
            f"color: {(theme.GOLD if s['news_level']=='Spike' else theme.UP).name()};")
        top.addWidget(lvl)
        top.addStretch(1)
        conf = label(f'{s["confidence"]:.0f}', font=theme.mono(15, True))
        conf.setToolTip("Confidence: how notable this is — not the odds of profit.")
        top.addWidget(conf)
        lay.addLayout(top)

        if s.get("headlines"):
            h = s["headlines"][0]
            hl = label(f'{h["source"]} · {h["title"]}', "muted", theme.mono(9))
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
            lb = label(text, "muted", theme.mono(10))
            lb.setToolTip(tip)
            plan.addWidget(lb)
        plan.addStretch(1)
        for txt, direction in (("buy", "LONG"), ("short", "SHORT")):
            b = QPushButton(txt)
            b.setFont(theme.mono(9))
            b.setFixedWidth(56)
            b.setToolTip("Direction is yours: coverage says something is "
                         "happening, not which way it goes.")
            b.clicked.connect(lambda _=None, sym=s["symbol"], d=direction:
                              on_trade(sym, d))
            plan.addWidget(b)
        lay.addLayout(plan)

        if s.get("catalyst"):
            c = label(f'◆ scheduled: {s["catalyst"]} ({s["catalyst_date"]})',
                      font=theme.mono(9))
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
                    "faint", theme.mono(9))
        age.setFixedWidth(34)
        lay.addWidget(age)
        src = label(h.source, font=theme.mono(9))
        src.setStyleSheet(f"color: {theme.GOLD.name()};")
        src.setFixedWidth(104)
        lay.addWidget(src)
        title = label(h.title, font=theme.ui_font(11))
        title.setWordWrap(True)
        lay.addWidget(title, 1)


class EventRow(QFrame):
    """One scheduled catalyst: an earnings date or a listing."""

    def __init__(self, sym: str, what: str, when: str, colour, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        s = label(sym, font=theme.mono(10, True))
        s.setStyleSheet(f"color: {colour.name()};")
        s.setFixedWidth(66)
        lay.addWidget(s)
        w = label(what, "muted", theme.mono(9))
        w.setWordWrap(True)
        lay.addWidget(w, 1)
        lay.addWidget(label(when, "faint", theme.mono(9)))


class PositionRow(QFrame):
    """One open paper position, with where it sits between stop and target."""

    def __init__(self, p: dict, on_close, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(14)

        side = label(p["direction"], font=theme.mono(10, True))
        side.setStyleSheet(
            f"color: {(theme.UP if p['direction']=='LONG' else theme.DOWN).name()};")
        side.setFixedWidth(52)
        lay.addWidget(side)

        nm = QVBoxLayout()
        nm.setSpacing(0)
        nm.addWidget(label(p["name"], font=theme.ui_font(12, True)))
        nm.addWidget(label(f'{p["symbol"]}  ·  {p["units"]:.4g} units',
                           "faint", theme.mono(9)))
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
            lb = label(text, "muted", theme.mono(10))
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

        unreal = label(f'{p["unrealised"]:+,.2f}', font=theme.mono(12, True))
        unreal.setStyleSheet(f"color: {theme.pnl_color(p['unrealised']).name()};")
        unreal.setFixedWidth(90)
        unreal.setToolTip("Mark-to-market profit or loss if closed now.")
        lay.addWidget(unreal)

        btn = QPushButton("close")
        btn.setFont(theme.mono(9))
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
        head.addWidget(label("LLM READ", "faint", theme.mono(8)))
        head.addStretch(1)
        self.badge = label("", font=theme.mono(9))
        head.addWidget(self.badge)
        lay.addLayout(head)
        self.subject = label("—", font=theme.ui_font(12, True))
        self.subject.setWordWrap(True)
        lay.addWidget(self.subject)
        self.body = label("Select an opportunity and press “LLM read”.",
                          "muted", theme.ui_font(11))
        self.body.setWordWrap(True)
        lay.addWidget(self.body)
        self.caveat = label("", "faint", theme.mono(9))
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
        self.tray = None            # set by main.py once the app exists
        self.allow_close = False    # flipped only by the tray's Quit action
        self.setWindowTitle("SONAR")
        self.resize(1180, 820)
        icon = paths.asset_path("icon.icns")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
        outer.addLayout(self._toolbar())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._terminal_tab(), "Terminal")
        self.tabs.addTab(self._scroll_tab("assets", AssetHeader()), "Assets")
        self.tabs.addTab(self._wire_tab(), "Wire")
        self.tabs.addTab(self._book_tab(), "Book")
        self.tabs.addTab(self._macro_tab(), "Macro")
        self.tabs.addTab(self._sports_tab(), "Sports")
        outer.addWidget(self.tabs, 1)

        self.status = label("starting…", "faint", theme.mono(9))
        outer.addWidget(self.status)

        self.poll = PollThread(live, self)
        self.poll.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)

    # -- chrome ------------------------------------------------------------ #
    def _toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(label("SONAR", "h1"))
        bar.addWidget(label("paper money only", "faint", theme.mono(9)))
        bar.addStretch(1)

        bar.addWidget(label("risk", "muted", theme.mono(9)))
        self.risk_box = QComboBox()
        for p in risk_mod.PROFILES.values():
            self.risk_box.addItem(p.name.capitalize(), p.name)
        self.risk_box.setCurrentIndex(
            list(risk_mod.PROFILES).index(self.live.risk.name))
        self.risk_box.setToolTip(
            "How much you stake and what is worth showing.\n"
            "Never changes a confidence score — that measures the market, not you.")
        self.risk_box.currentIndexChanged.connect(self._apply_config)
        bar.addWidget(self.risk_box)

        bar.addWidget(label("horizon", "muted", theme.mono(9)))
        self.hz_box = QComboBox()
        for h in hz_mod.HORIZONS.values():
            self.hz_box.addItem(h.label, h.name)
        self.hz_box.setCurrentIndex(
            list(hz_mod.HORIZONS).index(self.live.horizon.name))
        self.hz_box.setToolTip(
            "When you want it to resolve. Shifts the timing curve and the\n"
            "asset momentum window; long horizons add the macro regime.")
        self.hz_box.currentIndexChanged.connect(self._apply_config)
        bar.addWidget(self.hz_box)

        docs = QPushButton("Docs")
        docs.setFont(theme.mono(9))
        docs.setToolTip("What every number means, how the model works, and "
                        "what SONAR deliberately will not do.")
        docs.clicked.connect(self._open_docs)
        bar.addWidget(docs)
        return bar

    def _open_docs(self) -> None:
        """Open the bundled documentation in the default browser.

        ``static/`` ships inside the app bundle, so this resolves both frozen
        and from source. If it is somehow missing, say so in the status line
        rather than opening nothing and looking broken.
        """
        page = paths.resource_base() / "static" / "docs.html"
        if not page.exists():
            self.status.setText(f"⚠  documentation not found at {page}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(page)))

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
                ("trades", "Settled trades"), ("win rate", "Share of trades won"),
                ("profile", "Risk profile this bankroll was built under")]):
            s = Stat(k, tip)
            self.stats[k] = s
            pg.addWidget(s, 0, i)
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
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        sugg = panel()
        sl = QVBoxLayout(sugg)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(6)
        sl.addWidget(label("WHAT THE NEWS IS POINTING AT", "faint", theme.mono(8)))
        sl.addWidget(label(
            "These are the names with something happening today — a place to "
            "look, not an edge. Over 25,504 historical setups a news spike beat "
            "the baseline by 0.8 points against a 3.1 error bar, and momentum "
            "by nothing at all. There is no best weekday either. What is exact "
            "is the exit: a target and a stop, typically resolving in 3-10 days. "
            "Direction is yours.", "faint", theme.mono(8)))
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
        head.addWidget(label("NEWSWIRE", "faint", theme.mono(8)))
        head.addStretch(1)
        self.wire_meta = label("", "faint", theme.mono(8))
        head.addWidget(self.wire_meta)
        ll.addLayout(head)
        ll.addWidget(label(
            "Reuters, AP, Bloomberg and the FT are read through Google News — "
            "their own feeds are closed. dpa publishes no usable feed at all. "
            "Headlines are context and untrusted data: never an instruction, "
            "and no article body is fetched.", "faint", theme.mono(8)))
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
        rl.addWidget(label("SCHEDULED — EARNINGS & LISTINGS", "faint", theme.mono(8)))
        rl.addWidget(label(
            "A date is a fact; a direction is not. These sharpen *when* to look, "
            "never which way to lean.", "faint", theme.mono(8)))
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

        self._wire_sig = None
        return w

    def _refresh_wire(self) -> None:
        try:
            heads = self.live.news.headlines()
            ev = self.live.events.payload()
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
        self.wire_meta.setText(f'{len(heads)} headlines · '
                               f'{len({h.source for h in heads})} sources')
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
        lay.addWidget(head)

        cal = panel()
        cl = QVBoxLayout(cal)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(4)
        ch = QHBoxLayout()
        ch.addWidget(label("CALIBRATION — DOES A HIGH SCORE ACTUALLY WIN?",
                           "faint", theme.mono(8)))
        ch.addStretch(1)
        self.bt_btn = QPushButton("run backtest")
        self.bt_btn.setFont(theme.mono(9))
        self.bt_btn.setToolTip(
            "Replay the same plan over two years of real bars.\n"
            "Live positions take months to grade; this answers today —\n"
            "for the price half of the score, which is all history can test.")
        self.bt_btn.clicked.connect(self._run_backtest)
        ch.addWidget(self.bt_btn)
        cl.addLayout(ch)
        self.cal_verdict = label("—", font=theme.ui_font(12))
        self.cal_verdict.setWordWrap(True)
        cl.addWidget(self.cal_verdict)
        self.cal_table = label("", "muted", theme.mono(10))
        cl.addWidget(self.cal_table)
        self.bt_result = label("", "muted", theme.mono(10))
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

    # -- sports ------------------------------------------------------------ #
    def _sports_tab(self) -> QWidget:
        """Prop-bet analysis. NFL today; the sport picker is the extension point.

        Same division as the rest of SONAR: `sonar.sports` does the arithmetic
        (implied probability, EV, Kelly) and the model is asked only for the
        narrative on top of it. Paper analysis — nothing here places a wager.
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        form = panel()
        fl = QGridLayout(form)
        fl.setContentsMargins(14, 12, 14, 12)
        fl.setHorizontalSpacing(10)
        fl.setVerticalSpacing(8)

        self.sport_box = QComboBox()
        for sp in sports.list_sports():
            self.sport_box.addItem(sp.name, sp.key)
        self.sport_box.currentIndexChanged.connect(self._sports_sport_changed)

        self.prop_box = QComboBox()
        self.sports_subject = QLineEdit()
        self.sports_subject.setPlaceholderText("Player or team")
        self.sports_line = QLineEdit()
        self.sports_line.setPlaceholderText("Over 252.5")
        self.sports_odds = QLineEdit()
        self.sports_odds.setPlaceholderText("-110")
        self.sports_context = QLineEdit()

        fl.addWidget(label("SPORT", "faint", theme.mono(8)), 0, 0)
        fl.addWidget(label("PROP", "faint", theme.mono(8)), 0, 1)
        fl.addWidget(label("SUBJECT", "faint", theme.mono(8)), 0, 2)
        fl.addWidget(self.sport_box, 1, 0)
        fl.addWidget(self.prop_box, 1, 1)
        fl.addWidget(self.sports_subject, 1, 2)
        fl.addWidget(label("LINE", "faint", theme.mono(8)), 2, 0)
        fl.addWidget(label("PRICE", "faint", theme.mono(8)), 2, 1)
        fl.addWidget(label("CONTEXT", "faint", theme.mono(8)), 2, 2)
        fl.addWidget(self.sports_line, 3, 0)
        fl.addWidget(self.sports_odds, 3, 1)
        fl.addWidget(self.sports_context, 3, 2)
        fl.setColumnStretch(2, 1)
        lay.addWidget(form)

        data_p = panel()
        dl = QVBoxLayout(data_p)
        dl.setContentsMargins(14, 12, 14, 12)
        dl.addWidget(label("SUPPORTING DATA", "faint", theme.mono(8)))
        self.sports_data = QPlainTextEdit()
        self.sports_data.setPlaceholderText(
            "Splits, recent games, defensive ranks. The model is told not to "
            "invent numbers, so what you paste here is what it reasons from.")
        self.sports_data.setFixedHeight(96)
        dl.addWidget(self.sports_data)

        row = QHBoxLayout()
        self.sports_btn = QPushButton("Analyse prop")
        self.sports_btn.clicked.connect(self._sports_analyse)
        row.addWidget(self.sports_btn)
        self.sports_status = label("", "faint", theme.mono(9))
        row.addWidget(self.sports_status, 1)
        dl.addLayout(row)
        lay.addWidget(data_p)

        # The arithmetic, shown whether or not a model read has run.
        nums = panel()
        nl = QGridLayout(nums)
        nl.setContentsMargins(14, 12, 14, 12)
        nl.setHorizontalSpacing(26)
        self.sports_stats = {}
        cells = [("lean", "The model's direction, or NO EDGE"),
                 ("confidence", "The model's own stated confidence — not a probability"),
                 ("model win %", "The model's estimated win probability"),
                 ("price implies", "Break-even win rate the odds demand, vig included"),
                 ("edge", "Model probability minus what the price implies"),
                 ("EV / unit", "Expected value per unit staked at this price"),
                 ("¼ kelly", "A quarter of the full-Kelly stake, as % of bankroll")]
        for i, (k, tip) in enumerate(cells):
            st = Stat(k, tip)
            self.sports_stats[k] = st
            nl.addWidget(st, 0, i)
        lay.addWidget(nums)

        self.sports_out = QTextBrowser()
        self.sports_out.setOpenExternalLinks(False)
        lay.addWidget(self.sports_out, 1)

        self._sports_sport_changed()
        return w

    def _sports_sport_changed(self) -> None:
        sport = sports.get_sport(self.sport_box.currentData())
        self.prop_box.clear()
        for pt in sport.prop_types:
            self.prop_box.addItem(pt.label, pt.key)
        self.sports_context.setPlaceholderText(sport.context_hint)

    def _sports_analyse(self) -> None:
        odds_text = self.sports_odds.text().strip()
        odds = None
        if odds_text:
            try:
                odds = int(odds_text.replace("+", ""))
                if odds_text.startswith("+"):
                    odds = abs(odds)
            except ValueError:
                self.sports_status.setText("price must be american odds, e.g. -110")
                return

        sport = sports.get_sport(self.sport_box.currentData())
        prompt = sports.build_prompt(
            sport,
            self.sports_subject.text().strip(),
            self.prop_box.currentText(),
            self.sports_line.text().strip(),
            odds_text,
            self.sports_context.text().strip(),
            self.sports_data.toPlainText(),
        )
        self._sports_odds = odds
        self.sports_btn.setEnabled(False)
        self.sports_status.setText("reading…")
        self.sports_thread = PropThread(sports.SYSTEM_PROMPT, prompt, self)
        self.sports_thread.done.connect(self._sports_done)
        self.sports_thread.start()

    def _sports_done(self, text: str, error: str) -> None:
        self.sports_btn.setEnabled(True)
        if error:
            self.sports_status.setText(error)
            return
        self.sports_status.setText("")
        result = sports.parse_analysis(text)
        odds = getattr(self, "_sports_odds", None)

        self.sports_stats["lean"].set(result.lean or "—")
        self.sports_stats["confidence"].set(result.confidence or "—")
        prob = result.win_probability
        self.sports_stats["model win %"].set(f"{prob*100:.1f}%" if prob is not None else "—")

        if odds is not None:
            implied = sports.implied_probability(odds)
            self.sports_stats["price implies"].set(f"{implied*100:.1f}%")
            if prob is not None:
                edge = sports.edge_versus_market(prob, odds)
                ev = sports.expected_value(prob, odds)
                self.sports_stats["edge"].set(f"{edge*100:+.1f} pts")
                self.sports_stats["EV / unit"].set(f"{ev:+.3f}")
                self.sports_stats["¼ kelly"].set(f"{sports.kelly_fraction(prob, odds)/4*100:.2f}%")
            else:
                for k in ("edge", "EV / unit", "¼ kelly"):
                    self.sports_stats[k].set("—")
        else:
            for k in ("price implies", "edge", "EV / unit", "¼ kelly"):
                self.sports_stats[k].set("—")

        blocks = []
        for name in sports.SECTIONS:
            body = result.sections.get(name)
            if body:
                blocks.append(f"<b>{name}</b><br>{body.replace(chr(10), '<br>')}")
        self.sports_out.setHtml("<br><br>".join(blocks) or text.replace("\n", "<br>"))


    def _macro_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        head = panel()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(14, 12, 14, 12)
        self.regime_lb = label("—", font=theme.mono(22, True))
        self.regime_sub = label("", "muted", theme.mono(10))
        self.regime_sub.setWordWrap(True)
        hl.addWidget(label("MACRO REGIME", "faint", theme.mono(8)))
        hl.addWidget(self.regime_lb)
        hl.addWidget(self.regime_sub)
        self.regime_bar = ComponentBar()
        self.regime_bar.setFixedHeight(9)
        hl.addWidget(self.regime_bar)
        lay.addWidget(head)

        grid = panel()
        gl = QGridLayout(grid)
        gl.setContentsMargins(14, 12, 14, 12)
        gl.setHorizontalSpacing(26)
        self.macro_stats = {}
        cells = [("10y", "10-year Treasury yield"),
                 ("curve", "10y minus 2y. Negative = inverted, the classic "
                           "recession signal."),
                 ("fed funds", "Effective policy rate"),
                 ("VIX", "The market's own forward volatility estimate"),
                 ("real 10y", "10-year yield minus CPI year-over-year"),
                 ("CPI y/y", "Headline inflation, year-over-year"),
                 ("unemployment", "Rate, with 12-month change")]
        for i, (k, tip) in enumerate(cells):
            s = Stat(k, tip)
            self.macro_stats[k] = s
            gl.addWidget(s, i // 4, i % 4)
        lay.addWidget(grid)

        self.macro_note = label("", "faint", theme.mono(9))
        self.macro_note.setWordWrap(True)
        lay.addWidget(self.macro_note)
        lay.addStretch(1)
        return w

    # -- actions ----------------------------------------------------------- #
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
            scan = dict(self.live.scan)
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
        self._refresh_cards(scan, assets)
        self._refresh_macro(snap)
        if self.tray is not None:
            self.tray.update_state(snap)

        hz = self.live.horizon
        self.status.setText(
            f'risk {self.live.risk.name} · horizon {hz.name} · '
            f'{scan.get("n_shown", 0)}/{scan.get("n_scanned", 0)} markets · '
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

    def _refresh_cards(self, scan: dict, assets: dict) -> None:
        asig = (assets.get("generated"), assets.get("n"))
        if asig != self._assets_sig:
            self._assets_sig = asig
            self._rebuild(self._assets_lay,
                          [AssetRow(a, self._read, self._trade)
                           for a in assets.get("assets", [])],
                          "No instruments pass this risk profile's volatility filter.")

    @staticmethod
    def _rebuild(lay: QVBoxLayout, widgets: list[QWidget], empty_msg: str) -> None:
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not widgets:
            lay.addWidget(label(empty_msg, "muted", theme.mono(10)))
        for wdg in widgets:
            lay.addWidget(wdg)
        lay.addStretch(1)

    def _refresh_macro(self, snap: dict) -> None:
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

    # Grace for a background thread to notice it should finish. The poll loop
    # returns almost at once once stopped; the ceiling is a network call already
    # in flight, and those sockets time out around 8-10s.
    SHUTDOWN_WAIT_MS = 4000

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
        # Every QThread this window owns, not just the long-lived ones. A
        # thread parented here is destroyed when the window is, and Qt aborts
        # the process if it is still running at that moment — so a thread left
        # off this list is a crash on quit that only shows up when that feature
        # happens to be mid-flight. The sports read and the backtest were both
        # missing, which is how the SIGABRT came back.
        for thread in (getattr(self, "poll", None),
                       self._read_thread, self._cfg_thread,
                       self._bt_thread, getattr(self, "sports_thread", None)):
            if thread is None or not thread.isRunning():
                continue
            thread.quit()                   # no-op for run()-override threads
            if thread.wait(self.SHUTDOWN_WAIT_MS):
                continue
            # Last resort: a thread wedged in a slow network read. Terminating
            # at exit is ugly, but it beats aborting the process, and there is
            # nothing to corrupt — the engine persists on every write.
            thread.terminate()
            thread.wait(500)

    def closeEvent(self, e) -> None:
        """Hide, don't quit — see ui/tray.py for why.

        Closing the window while the engine is mid-hour would abandon a priced
        position before it settles, which is exactly the data the app exists to
        collect. Quitting is available, but it is a deliberate act from the
        menu bar rather than the side effect of a close button.
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
            self.showNormal()
            QTimer.singleShot(FULLSCREEN_EXIT_MS, self.hide)
        else:
            self.hide()
        self.tray.note_hidden()
