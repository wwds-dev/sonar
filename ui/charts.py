"""Native chart widgets — QPainter replacements for the HTML canvases.

Everything the browser terminal drew on ``<canvas>`` is redrawn here with
``QPainter``: the equity curve, the price sparkline, the order-book depth, the
probability lattice, and the confidence component bars. No web view, so the
packaged bundle stays small and PyInstaller has nothing exotic to discover.

Each widget takes plain data (lists and dicts straight off the snapshot) and
owns nothing — set the data, call ``update()``, done.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

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
        p.setFont(theme.mono(10))
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
        p.setFont(theme.mono(9))
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
            p.setFont(theme.mono(8, True))
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

        p.setFont(theme.mono(9))
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
        p.setFont(theme.mono(9))
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

    def set_parts(self, comp: dict, weights: dict) -> None:
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
        if total <= 0:
            p.fillRect(self.rect(), QBrush(theme.GRID))
            return
        x = 0.0
        for name, v in self.parts:
            seg = self.width() * (v / total)
            p.fillRect(QRectF(x, 0, seg, self.height()),
                       QBrush(theme.COMP.get(name, theme.MUTED)))
            x += seg
