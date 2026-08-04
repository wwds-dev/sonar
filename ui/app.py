"""The SONAR window.

Four tabs over one shared :class:`sonar.core.Live`:

    Terminal   the hourly BTC paper trade — signal, lattice, book, equity curve
    Markets    ranked prediction markets for the current horizon
    Assets     the real-asset screen
    Macro      the regime, which only matters at long horizons

The toolbar carries the two knobs that shape everything: **risk** (how much you
stake, and what is worth showing) and **horizon** (when you want it to resolve).
Neither touches a confidence score — see ``sonar/risk.py`` for why that boundary
is load-bearing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QMainWindow, QPushButton, QScrollArea,
                               QSizePolicy, QTabWidget, QVBoxLayout, QWidget)

from sonar import horizon as hz_mod
from sonar import llm, paths, risk as risk_mod
from sonar.core import Live
from sonar.scanner import _W_CRYPTO, _W_OTHER
from sonar.assets import _W as ASSET_W

from . import theme
from .charts import ComponentBar, DepthChart, EquityCurve, Lattice, Sparkline
from .worker import ConfigThread, PollThread, ReadThread

REFRESH_MS = 1000


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


class MarketCard(QFrame):
    """One ranked prediction market."""

    def __init__(self, s: dict, on_read, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.s = s
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        top = QHBoxLayout()
        q = label(s["question"], font=theme.ui_font(12, True))
        q.setWordWrap(True)
        top.addWidget(q, 1)
        conf = label(f'{s["confidence"]:.0f}', font=theme.mono(16, True))
        conf.setToolTip("Confidence 0–100: how notable and tradeable this looks.\n"
                        "NOT the probability you will make money.")
        top.addWidget(conf, 0, Qt.AlignTop)
        lay.addLayout(top)

        bar = ComponentBar()
        bar.set_parts(s.get("comp", {}),
                      _W_CRYPTO if s.get("side") else _W_OTHER)
        lay.addWidget(bar)

        meta = QHBoxLayout()
        meta.setSpacing(14)
        for text, tip in [
            (f'{s["category"]}', "Market category"),
            (f'{s["hours_left"]:.1f}h left', "Time until resolution"),
            (f'${s["volume24h"]:,.0f} 24h', "24-hour volume"),
            (f'{s["yes_price"]*100:.1f}¢', "Market's own price for YES"),
        ]:
            lb = label(text, "muted", theme.mono(10))
            lb.setToolTip(tip)
            meta.addWidget(lb)
        if s.get("side"):
            lb = label(f'model {s["side"]} {s["edge"]*100:+.1f}¢',
                       font=theme.mono(10, True))
            lb.setStyleSheet(f"color: {theme.side_color(s['side']).name()};")
            lb.setToolTip("Model probability minus market price — the only true "
                          "edge signal, and only crypto up/down markets have one.")
            meta.addWidget(lb)
        elif s.get("market_lean"):
            meta.addWidget(label(f'market {s["market_lean"]}', "muted",
                                 theme.mono(10)))
        meta.addStretch(1)
        btn = QPushButton("LLM read")
        btn.setFont(theme.mono(9))
        btn.clicked.connect(lambda: on_read("market", s["id"], s["question"]))
        meta.addWidget(btn)
        lay.addLayout(meta)

        if s.get("rationale"):
            r = label(s["rationale"], "muted", theme.mono(10))
            r.setWordWrap(True)
            lay.addWidget(r)


class AssetRow(QFrame):
    """One instrument on the screener."""

    def __init__(self, a: dict, on_read, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(14)

        name = QVBoxLayout()
        name.setSpacing(0)
        name.addWidget(label(a["name"], font=theme.ui_font(12, True)))
        name.addWidget(label(f'{a["symbol"]}  ·  {a["cls"]}', "faint", theme.mono(9)))
        lay.addLayout(name)

        spark = Sparkline(38)
        spark.frame = False
        spark.setFixedWidth(110)
        # colour by the horizon's momentum so the line agrees with the number
        # printed next to it and with the lean
        spark.set_values(a.get("spark", []), up=a["momentum"] >= 0)
        lay.addWidget(spark)

        for text, tip, col in [
            (f'{a["price"]:,.2f}', "Latest price", theme.INK),
            (f'{a["day_change"]*100:+.2f}%', "1-day change",
             theme.pnl_color(a["day_change"])),
            (f'{a["momentum"]*100:+.1f}% / {a["momentum_days"]}d',
             "Change over the horizon's momentum window",
             theme.pnl_color(a["momentum"])),
            (f'vol {a["volatility"]*100:.1f}%', "Daily volatility of returns",
             theme.MUTED),
        ]:
            lb = label(text, font=theme.mono(11))
            lb.setStyleSheet(f"color: {col.name()};")
            lb.setToolTip(tip)
            lay.addWidget(lb)

        lean = label(a["lean"], font=theme.mono(10, True))
        lean.setStyleSheet(
            f"color: {(theme.UP if a['lean']=='Bullish' else theme.DOWN if a['lean']=='Bearish' else theme.MUTED).name()};")
        lean.setToolTip("Sign of (horizon momentum + crude news sentiment).\n"
                        "A computed indicator, not advice.")
        lay.addWidget(lean)

        bar = ComponentBar()
        bar.setFixedWidth(90)
        bar.set_parts(a.get("comp", {}), ASSET_W)
        lay.addWidget(bar)

        conf = label(f'{a["confidence"]:.0f}', font=theme.mono(14, True))
        lay.addWidget(conf)

        btn = QPushButton("read")
        btn.setFont(theme.mono(9))
        btn.clicked.connect(lambda: on_read("asset", a["symbol"], a["name"]))
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
            self.body.setText(r["error"])
            self.caveat.setText("")
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
        self.tabs.addTab(self._scroll_tab("markets"), "Markets")
        self.tabs.addTab(self._scroll_tab("assets"), "Assets")
        self.tabs.addTab(self._macro_tab(), "Macro")
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
        return bar

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

    def _scroll_tab(self, which: str) -> QWidget:
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
        return area

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

    def _read(self, kind: str, ident: str, subject: str) -> None:
        ok, why = llm.available()
        if not ok:
            self.read_panel.show_read({"error": why}, False)
            self.read_panel.show()
            return
        if self._read_thread and self._read_thread.isRunning():
            return
        self.read_btn.setEnabled(False)
        self.read_panel.show_pending(subject)
        self.tabs.setCurrentIndex(0)
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

        if snap.get("status") != "live":
            self.status.setText(f'{snap.get("status", "…")} — first poll can take a moment')
            return
        self._refresh_terminal(snap)
        self._refresh_cards(scan, assets)
        self._refresh_macro(snap)

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
        sig = (scan.get("generated"), scan.get("n_shown"))
        if sig != self._markets_sig:
            self._markets_sig = sig
            self._rebuild(self._markets_lay,
                          [MarketCard(s, self._read)
                           for s in scan.get("suggestions", [])],
                          "No markets match this horizon and risk profile.")
        asig = (assets.get("generated"), assets.get("n"))
        if asig != self._assets_sig:
            self._assets_sig = asig
            self._rebuild(self._assets_lay,
                          [AssetRow(a, self._read) for a in assets.get("assets", [])],
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

    def closeEvent(self, e) -> None:
        self.timer.stop()
        e.accept()
