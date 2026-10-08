"""Native chart widgets — QPainter replacements for the HTML canvases.

Everything the browser terminal drew on ``<canvas>`` is redrawn here with
``QPainter``: the equity curve, the price sparkline, the order-book depth, the
probability lattice, and the confidence component bars. No web view, so the
packaged bundle stays small and PyInstaller has nothing exotic to discover.

Each widget takes plain data (lists and dicts straight off the snapshot) and
owns nothing — set the data, call ``update()``, done.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import theme


class _Chart(QWidget):
    """Shared painter setup: dark panel, rounded frame, antialiasing."""

    def __init__(self, height: int = 160, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def _begin(self) -> QPainter:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(theme.BORDER, 1))
        p.setBrush(QBrush(theme.PANEL))
        p.drawRoundedRect(r, 8, 8)
        return p

    def _empty(self, p: QPainter, msg: str) -> None:
        p.setPen(QPen(theme.FAINT))
        p.setFont(theme.figure(10))
        p.drawText(self.rect(), Qt.AlignCenter, msg)


class EquityCurve(_Chart):
    """The paper bankroll over time.

    The seeded fair-odds backtest and the live paper trades are drawn in one
    line but separated by a gold divider, exactly as the browser terminal did —
    the backtest is expected-value-zero by construction and must never be
    mistaken for realised edge.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(190, parent)
        self.points: list[dict] = []
        self.start: float = 10_000.0

    def set_data(self, equity: list[dict], start: float) -> None:
        self.points, self.start = equity or [], start or 10_000.0
        self.update()

    def paintEvent(self, _e) -> None:
        p = self._begin()
        pts = self.points
        if len(pts) < 2:
            self._empty(p, "waiting for settled hours…")
            return

        pad_l, pad_r, pad_t, pad_b = 52, 12, 14, 20
        w, h = self.width(), self.height()
        gw, gh = w - pad_l - pad_r, h - pad_t - pad_b
        vals = [q["v"] for q in pts]
        lo, hi = min(vals + [self.start]), max(vals + [self.start])
        if hi - lo < 1e-9:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.10
        lo, hi = lo - pad, hi + pad

        def xy(i: int, v: float) -> QPointF:
            x = pad_l + gw * (i / max(1, len(pts) - 1))
            y = pad_t + gh * (1 - (v - lo) / (hi - lo))
            return QPointF(x, y)

        # horizontal grid + axis labels
        p.setFont(theme.figure(9))
        for k in range(5):
            v = lo + (hi - lo) * k / 4
            y = pad_t + gh * (1 - k / 4)
            p.setPen(QPen(theme.GRID, 1))
            p.drawLine(QPointF(pad_l, y), QPointF(w - pad_r, y))
            p.setPen(QPen(theme.FAINT))
            p.drawText(QRectF(2, y - 7, pad_l - 7, 14),
                       Qt.AlignRight | Qt.AlignVCenter, f"{v:,.0f}")

        # starting bankroll reference
        y0 = pad_t + gh * (1 - (self.start - lo) / (hi - lo))
        p.setPen(QPen(theme.FAINT, 1, Qt.DashLine))
        p.drawLine(QPointF(pad_l, y0), QPointF(w - pad_r, y0))

        # filled area under the curve, tinted by final P&L
        final_up = vals[-1] >= self.start
        tint = QColor(theme.UP if final_up else theme.DOWN)
        area = QPainterPath()
        area.moveTo(QPointF(pad_l, pad_t + gh))
        for i, q in enumerate(pts):
            area.lineTo(xy(i, q["v"]))
        area.lineTo(QPointF(pad_l + gw, pad_t + gh))
        area.closeSubpath()
        tint.setAlpha(28)
        p.fillPath(area, QBrush(tint))

        line = QPainterPath()
        line.moveTo(xy(0, pts[0]["v"]))
        for i, q in enumerate(pts[1:], 1):
            line.lineTo(xy(i, q["v"]))
        p.setPen(QPen(theme.UP if final_up else theme.DOWN, 1.6))
        p.drawPath(line)

        # the honest divider: everything left of it is a backtest, not profit
        first_live = next((i for i, q in enumerate(pts)
                           if q.get("kind") == "live"), None)
        if first_live:
            x = pad_l + gw * (first_live / max(1, len(pts) - 1))
            p.setPen(QPen(theme.GOLD, 1, Qt.DashLine))
            p.drawLine(QPointF(x, pad_t), QPointF(x, pad_t + gh))
            p.setPen(QPen(theme.GOLD))
            p.setFont(theme.figure(8, True))
            p.drawText(QPointF(x + 4, pad_t + 9), "LIVE")


class Sparkline(_Chart):
    """A compact price line — used for BTC and for each asset row."""

    def __init__(self, height: int = 46, parent=None) -> None:
        super().__init__(height, parent)
        self.values: list[float] = []
        self.frame = True
        self.up: bool | None = None

    def set_values(self, values: list[float], up: bool | None = None) -> None:
        """``up`` overrides the line colour.

        Without it the line colours by first-vs-last over the whole fetched
        series, which can contradict the momentum figure printed beside it —
        the series is 20+ points long while the horizon window may be 5 days.
        Passing the momentum sign keeps a row internally consistent.
        """
        self.values = [v for v in (values or []) if v is not None]
        self.up = up
        self.update()

    def paintEvent(self, _e) -> None:
        if self.frame:
            p = self._begin()
        else:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)
        v = self.values
        if len(v) < 2:
            if self.frame:
                self._empty(p, "…")
            return
        pad = 6
        w, h = self.width() - pad * 2, self.height() - pad * 2
        lo, hi = min(v), max(v)
        rng = (hi - lo) or 1.0
        up = self.up if self.up is not None else v[-1] >= v[0]
        path = QPainterPath()
        for i, val in enumerate(v):
            pt = QPointF(pad + w * i / (len(v) - 1),
                         pad + h * (1 - (val - lo) / rng))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.setPen(QPen(theme.UP if up else theme.DOWN, 1.4))
        p.drawPath(path)


class DepthChart(_Chart):
    """Polymarket order book — bids left, asks right, depth as width."""

    def __init__(self, parent=None) -> None:
        super().__init__(150, parent)
        self.bids: list[list[float]] = []
        self.asks: list[list[float]] = []

    def set_book(self, bids, asks) -> None:
        self.bids, self.asks = bids or [], asks or []
        self.update()

    def paintEvent(self, _e) -> None:
        p = self._begin()
        if not self.bids and not self.asks:
            self._empty(p, "no order book")
            return
        rows = 6
        bids = sorted(self.bids, key=lambda r: -r[0])[:rows]
        asks = sorted(self.asks, key=lambda r: r[0])[:rows]
        biggest = max([r[1] for r in bids + asks] or [1.0])
        pad, rowh = 10, (self.height() - 26) / rows
        mid = self.width() / 2

        p.setFont(theme.figure(9))
        p.setPen(QPen(theme.FAINT))
        p.drawText(QRectF(pad, 4, mid - pad, 14), Qt.AlignLeft, "BIDS")
        p.drawText(QRectF(mid, 4, mid - pad, 14), Qt.AlignRight, "ASKS")

        for i in range(rows):
            y = 22 + i * rowh
            if i < len(bids):
                price, size = bids[i][0], bids[i][1]
                wpx = (mid - pad - 46) * (size / biggest)
                c = QColor(theme.UP); c.setAlpha(60)
                p.fillRect(QRectF(mid - 46 - wpx, y, wpx, rowh - 3), QBrush(c))
                p.setPen(QPen(theme.INK))
                p.drawText(QRectF(mid - 44, y, 40, rowh - 3),
                           Qt.AlignRight | Qt.AlignVCenter, f"{price*100:.1f}¢")
            if i < len(asks):
                price, size = asks[i][0], asks[i][1]
                wpx = (mid - pad - 46) * (size / biggest)
                c = QColor(theme.DOWN); c.setAlpha(60)
                p.fillRect(QRectF(mid + 46, y, wpx, rowh - 3), QBrush(c))
                p.setPen(QPen(theme.INK))
                p.drawText(QRectF(mid + 4, y, 40, rowh - 3),
                           Qt.AlignLeft | Qt.AlignVCenter, f"{price*100:.1f}¢")


class Lattice(_Chart):
    """The Galton-board view of the end-of-hour price distribution.

    Bars at or above the hour's open are 'up' coloured; summing them reproduces
    the model's P(up) to binomial resolution, which is the point — it makes the
    probability visible as a shape rather than a number.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(150, parent)
        self.data: dict = {}

    def set_data(self, data: dict) -> None:
        self.data = data or {}
        self.update()

    def paintEvent(self, _e) -> None:
        p = self._begin()
        bins = self.data.get("bins") or []
        if not bins:
            self._empty(p, "no live hour")
            return
        pad_l, pad_r, pad_t, pad_b = 10, 10, 18, 22
        w = self.width() - pad_l - pad_r
        h = self.height() - pad_t - pad_b
        peak = max(b["prob"] for b in bins) or 1.0
        bw = w / len(bins)

        for i, b in enumerate(bins):
            bh = h * (b["prob"] / peak)
            x = pad_l + i * bw
            y = pad_t + (h - bh)
            c = QColor(theme.UP if b["up"] else theme.DOWN)
            c.setAlpha(200)
            p.fillRect(QRectF(x + 1, y, bw - 2, bh), QBrush(c))

        p.setPen(QPen(theme.FAINT))
        p.setFont(theme.figure(9))
        p_up = self.data.get("p_up")
        if p_up is not None:
            p.drawText(QRectF(pad_l, self.height() - pad_b + 2, w, 16),
                       Qt.AlignCenter,
                       f"P(up) = {p_up*100:.1f}%   ·   open {self.data.get('open', 0):,.0f}")


class ComponentBar(QWidget):
    """The stacked confidence breakdown — the reason a score is never a black box.

    Each segment is one weighted component, so the number on a card can always
    be read back to what produced it.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(7)
        self.parts: list[tuple[str, float]] = []
        self.fill = 1.0

    def set_parts(self, comp: dict, weights: dict, fill: float = 1.0) -> None:
        """``fill`` is how much of the width the bar occupies, 0–1.

        At 1.0 the bar is a pure breakdown: the segments say what the score is
        made of and the length says nothing. Passing the score itself makes it
        a meter as well — length reads as "how notable", segments still read as
        "why" — which is the only way to show both in one 80px cell.
        """
        self.fill = max(0.0, min(1.0, fill))
        self.parts = [(k, weights[k] * comp.get(k, 0.0))
                      for k in weights if comp.get(k)]
        self.setToolTip("  ".join(
            f"{k} {comp.get(k, 0):.2f}×{weights[k]:.2f}" for k in weights
            if comp.get(k)) or "no components")
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        total = sum(v for _, v in self.parts)
        p.fillRect(self.rect(), QBrush(theme.GRID))       # the track
        if total <= 0:
            return
        span = self.width() * self.fill
        x = 0.0
        for name, v in self.parts:
            seg = span * (v / total)
            p.fillRect(QRectF(x, 0, seg, self.height()),
                       QBrush(theme.COMP.get(name, theme.MUTED)))
            x += seg


class HourBar(QWidget):
    """How far through the hour the model's trade is — tau, drawn as time.

    The signal's tau is the *fraction of the hour still to run*, and as a bare
    percentage it reads like yet another probability sitting between four real
    ones. A filling bar cannot be misread that way: it is visibly a clock.
    The number stays printed above it; this adds the shape, not a new claim.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(5)
        self.remaining: float | None = None

    def set_fraction(self, remaining: float | None) -> None:
        self.remaining = None if remaining is None else \
            max(0.0, min(1.0, float(remaining)))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        radius = self.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(theme.GRID))
        p.drawRoundedRect(QRectF(self.rect()), radius, radius)
        if self.remaining is None:
            return
        elapsed = (1.0 - self.remaining) * self.width()
        if elapsed >= 1:
            p.setBrush(QBrush(theme.UP))
            p.drawRoundedRect(QRectF(0, 0, elapsed, self.height()),
                              radius, radius)


class AccountCurve(_Chart):
    """The paper book's account value over time — cash plus what the open
    positions are worth, as the book logged it (``Portfolio.log_equity``).

    Time runs along the x-axis for real: a gap in the log (the engine was not
    running) is a gap on the chart, not a seam. ``EquityCurve`` above is
    index-based because each of its points is one settled hour; this one mixes
    the daily points the seed reconstructs with the hourly ones the live engine
    writes, so only the clock keeps them honest.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(170, parent)
        self.points: list[dict] = []
        self.start: float = 10_000.0

    def set_data(self, points: list[dict], start: float) -> None:
        self.points = [q for q in (points or [])
                       if q.get("t") is not None and q.get("v") is not None]
        self.start = start or 10_000.0
        self.update()

    def paintEvent(self, _e) -> None:
        p = self._begin()
        pts = self.points
        if len(pts) < 2:
            self._empty(p, "no account history yet — the first scan writes the first point")
            return

        pad_l, pad_r, pad_t, pad_b = 56, 14, 14, 22
        w, h = self.width(), self.height()
        gw, gh = w - pad_l - pad_r, h - pad_t - pad_b
        t0, t1 = pts[0]["t"], pts[-1]["t"]
        if t1 - t0 < 60:
            t1 = t0 + 60
        vals = [q["v"] for q in pts]
        lo, hi = min(vals + [self.start]), max(vals + [self.start])
        if hi - lo < 1e-9:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.10
        lo, hi = lo - pad, hi + pad

        def xy(t: float, v: float) -> QPointF:
            return QPointF(pad_l + gw * (t - t0) / (t1 - t0),
                           pad_t + gh * (1 - (v - lo) / (hi - lo)))

        p.setFont(theme.figure(9))
        for k in range(5):
            v = lo + (hi - lo) * k / 4
            y = pad_t + gh * (1 - k / 4)
            p.setPen(QPen(theme.GRID, 1))
            p.drawLine(QPointF(pad_l, y), QPointF(w - pad_r, y))
            p.setPen(QPen(theme.FAINT))
            p.drawText(QRectF(2, y - 7, pad_l - 7, 14),
                       Qt.AlignRight | Qt.AlignVCenter, f"{v:,.0f}")

        # dates along the bottom — the one thing an index-based curve cannot say
        p.setFont(theme.figure(8))
        p.setPen(QPen(theme.FAINT))
        for k in range(4):
            t = t0 + (t1 - t0) * k / 3
            x = pad_l + gw * k / 3
            # The end labels hug their ends, inside the plot: a centred box
            # at the first tick would sit on the y-axis figures, and one at
            # the last would hang past the widget's edge and be clipped.
            if k == 0:
                box, align = QRectF(x, h - pad_b + 5, 96, 14), Qt.AlignLeft
            elif k == 3:
                box, align = QRectF(x - 96, h - pad_b + 5, 96, 14), Qt.AlignRight
            else:
                box, align = QRectF(x - 48, h - pad_b + 5, 96, 14), Qt.AlignHCenter
            p.drawText(box, align | Qt.AlignVCenter,
                       time.strftime("%-d %b", time.localtime(t)))

        # the starting cash: above it is profit, below it a loss
        y0 = pad_t + gh * (1 - (self.start - lo) / (hi - lo))
        p.setPen(QPen(theme.FAINT, 1, Qt.DashLine))
        p.drawLine(QPointF(pad_l, y0), QPointF(w - pad_r, y0))

        final_up = vals[-1] >= self.start
        tint = QColor(theme.UP if final_up else theme.DOWN)
        area = QPainterPath()
        area.moveTo(QPointF(pad_l, y0))
        for q in pts:
            area.lineTo(xy(q["t"], q["v"]))
        area.lineTo(QPointF(xy(t1, 0).x(), y0))
        area.closeSubpath()
        tint.setAlpha(28)
        p.fillPath(area, QBrush(tint))

        line = QPainterPath()
        line.moveTo(xy(pts[0]["t"], pts[0]["v"]))
        for q in pts[1:]:
            line.lineTo(xy(q["t"], q["v"]))
        p.setPen(QPen(theme.UP if final_up else theme.DOWN, 1.6))
        p.drawPath(line)
        end = xy(pts[-1]["t"], pts[-1]["v"])
        p.setBrush(QBrush(theme.UP if final_up else theme.DOWN))
        p.setPen(Qt.NoPen)
        p.drawEllipse(end, 2.5, 2.5)


def squarify(weights: list[float], x: float, y: float, w: float, h: float,
             ) -> list[tuple[float, float, float, float]]:
    """Bruls, Huizing & van Wijk's treemap layout, as pure geometry.

    Lays one rectangle per weight into the box, in the order given (largest
    first keeps the result readable), each as close to square as the row it
    lands in allows. Returns ``(x, y, w, h)`` per weight. Zero weights get a
    zero-area rectangle rather than breaking the arithmetic.
    """
    out: list[tuple[float, float, float, float]] = []
    total = sum(weights)
    if not weights or total <= 0 or w <= 0 or h <= 0:
        return [(x, y, 0.0, 0.0) for _ in weights]
    areas = [max(0.0, wt) * (w * h) / total for wt in weights]

    def worst(row: list[float], side: float) -> float:
        s = sum(row)
        if s <= 0 or side <= 0:
            return float("inf")
        mx, mn = max(row), min(row)
        if mn <= 0:
            return float("inf")
        return max(side * side * mx / (s * s), s * s / (side * side * mn))

    i, n = 0, len(areas)
    while i < n:
        along_height = w >= h          # a wide box takes vertical strips
        side = h if along_height else w
        row: list[float] = []
        best = None
        j = i
        while j < n:
            cand = row + [areas[j]]
            score = worst(cand, side)
            if best is not None and score > best and len(row) >= 1:
                break
            row, best = cand, score
            j += 1
        s = sum(row)
        thick = s / side if side > 0 else 0.0
        off = 0.0
        for a in row:
            length = a / thick if thick > 0 else 0.0
            if along_height:
                out.append((x, y + off, thick, length))
            else:
                out.append((x + off, y, length, thick))
            off += length
        if along_height:
            x += thick
            w -= thick
        else:
            y += thick
            h -= thick
        i = j
    return out


class PositionTiles(_Chart):
    """Every open position as one tile: its size is what the position can lose
    (the stop's cost — the figure the risk profile controls), its colour is how
    it is doing. Mostly blue or mostly orange is readable before a single
    number is, which is the point of a picture.

    Sized by risk rather than by stake deliberately: a currency short carries
    a notional thirty times an equity long's for the same risk budget, and
    sizing by notional would make the picture about leverage conventions
    instead of about the bets.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(150, parent)
        self.rows: list[dict] = []
        self._tiles: list[tuple[QRectF, dict]] = []
        self.setMouseTracking(True)

    def set_rows(self, rows: list[dict]) -> None:
        self.rows = sorted((r for r in (rows or []) if r.get("symbol")),
                           key=lambda r: -(r.get("cash_at_risk") or r.get("stake") or 0))
        self.update()

    @staticmethod
    def tip(r: dict) -> str:
        pnl = r.get("unrealised", 0.0) or 0.0
        return (f'{r.get("name", r["symbol"])} · {r.get("direction", "").lower()}\n'
                f'invested ${r.get("stake", 0):,.0f} · now {pnl:+,.2f} '
                f'({r.get("pct", 0):+.2f}%)\n'
                f'can lose ${r.get("cash_at_risk", 0):,.0f} if the stop is hit')

    def paintEvent(self, _e) -> None:
        p = self._begin()
        self._tiles = []
        rows = self.rows
        if not rows:
            self._empty(p, "nothing open — buy or short on the Screener")
            return
        inset = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        weights = [max(float(r.get("cash_at_risk") or r.get("stake") or 0), 1e-6)
                   for r in rows]
        boxes = squarify(weights, inset.x(), inset.y(), inset.width(), inset.height())
        top = max((abs(r.get("unrealised") or 0.0) for r in rows), default=0.0) or 1.0
        for r, (x, y, w, h) in zip(rows, boxes):
            if w < 2 or h < 2:
                continue
            rect = QRectF(x + 1, y + 1, w - 2, h - 2)
            self._tiles.append((rect, r))
            pnl = r.get("unrealised") or 0.0
            if abs(pnl) < 0.005:
                fill, edge, ink = QColor(theme.GRID), QColor(theme.BORDER), theme.MUTED
            else:
                base = theme.UP if pnl > 0 else theme.DOWN
                fill, edge, ink = QColor(base), QColor(base), theme.INK
                fill.setAlphaF(0.18 + 0.62 * abs(pnl) / top)
                edge.setAlphaF(min(1.0, 0.33 + 0.62 * abs(pnl) / top))
            p.setPen(QPen(edge, 1))
            p.setBrush(QBrush(fill))
            p.drawRoundedRect(rect, 3, 3)
            if w >= 30 and h >= 15:
                p.setPen(QPen(ink))
                p.setFont(theme.figure(9, True))
                text = QRectF(rect).adjusted(5, 3, -4, -2)
                p.drawText(text, Qt.AlignLeft | Qt.AlignTop | Qt.TextSingleLine,
                           self.caption(r, p.fontMetrics(), text.width()))
                if w >= 46 and h >= 28:
                    p.setFont(theme.figure(8))
                    p.drawText(text, Qt.AlignLeft | Qt.AlignBottom | Qt.TextSingleLine,
                               f"{pnl:+,.2f}")

    @staticmethod
    def caption(r: dict, fm, room: float) -> str:
        """What to write on a tile: the name if it fits ("USD/SEK", "Gold"),
        else the symbol without its venue dressing ("USDSEK=X" → "USDSEK",
        "^GSPC" → "GSPC"), else whatever of that fits with an ellipsis."""
        name = r.get("name") or ""
        if name and fm.horizontalAdvance(name) <= room:
            return name
        symbol = r["symbol"].lstrip("^").split("=")[0]
        if fm.horizontalAdvance(symbol) <= room:
            return symbol
        return fm.elidedText(symbol, Qt.ElideRight, int(room))

    def tile_at(self, pos) -> dict | None:
        for rect, r in self._tiles:
            if rect.contains(QPointF(pos)):
                return r
        return None

    def mouseMoveEvent(self, e) -> None:            # noqa: D102
        r = self.tile_at(e.position())
        if r is None:
            QToolTip.hideText()
        else:
            QToolTip.showText(e.globalPosition().toPoint(), self.tip(r), self)
        super().mouseMoveEvent(e)


class PositionChart(_Chart):
    """One position's recent prices with its three prices drawn in: the entry
    (gold), the target (blue) and the stop (orange), and a dot where price is
    now. The card beside it says which is which; here they are just lines, so
    the eye reads "near the target" or "near the stop" without a legend.
    """

    def __init__(self, height: int = 64, parent=None) -> None:
        super().__init__(height, parent)
        self.frame = False
        self.closes: list[float] = []
        self.entry = self.target = self.stop = self.price = None
        self.up = True

    def set_position(self, closes: list[float], entry: float, target: float,
                     stop: float, price: float, up: bool) -> None:
        self.closes = [c for c in (closes or []) if c is not None]
        self.entry, self.target, self.stop, self.price = entry, target, stop, price
        self.up = up
        self.update()

    def paintEvent(self, _e) -> None:
        if self.frame:
            p = self._begin()
        else:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)
        series = list(self.closes)
        if self.price is not None:
            series.append(self.price)
        if len(series) < 2 or self.entry is None:
            if self.frame:
                self._empty(p, "no price history yet")
            return
        pad_x, pad_y = 4, 5
        w, h = self.width() - pad_x * 2, self.height() - pad_y * 2
        levels = [v for v in (self.entry, self.target, self.stop) if v is not None]
        lo, hi = min(series + levels), max(series + levels)
        rng = (hi - lo) or 1.0

        def y(v: float) -> float:
            # Snapped to pixel centres: a one-pixel line on a row boundary is
            # drawn as two half-tone rows, and a dashed one all but vanishes.
            return int(pad_y + h * (1 - (v - lo) / rng)) + 0.5

        for v, colour, dash in ((self.target, theme.UP, [3, 3]),
                                (self.stop, theme.DOWN, [3, 3]),
                                (self.entry, theme.GOLD, [2, 3])):
            if v is None:
                continue
            pen = QPen(colour, 1)
            pen.setDashPattern(dash)
            p.setPen(pen)
            p.drawLine(QPointF(pad_x, y(v)), QPointF(pad_x + w, y(v)))

        colour = theme.UP if self.up else theme.DOWN
        path = QPainterPath()
        for i, v in enumerate(series):
            pt = QPointF(pad_x + w * i / (len(series) - 1), y(v))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.setPen(QPen(colour, 1.5))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(colour))
        p.drawEllipse(QPointF(pad_x + w, y(series[-1])), 2.5, 2.5)
