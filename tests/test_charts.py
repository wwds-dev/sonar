"""The QPainter charts: geometry and state, checked without a screen.

`ui/charts.py` sat at ~24% because painters look untestable. They are not: a
widget renders into an offscreen QPixmap exactly as it would into a window, so
"does a populated chart actually put ink on the canvas" and "does an empty one
say so instead of crashing" are both one render call. What a person would have
to eyeball is the aesthetics; what these pin down is the part that can silently
break — the data handling in front of the painting.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from sonar.assets import _W as ASSET_W
from ui import theme
from ui.charts import ComponentBar, DepthChart, EquityCurve, Lattice, Sparkline


@pytest.fixture(scope="module", autouse=True)
def app():
    yield QApplication.instance() or QApplication([])


def shot(widget, w=320, h=120) -> QImage:
    widget.resize(w, h)
    image = QImage(w, h, QImage.Format_ARGB32)
    image.fill(theme.BG)
    widget.render(image)               # a QImage is a QPaintDevice
    return image


def ink(widget, w=320, h=120) -> int:
    """Render offscreen and count pixels that differ from the background.

    The background is whatever colour dominates the render, not an assumption:
    `_Chart._begin` paints its own panel over the image fill, and outside the
    styled window even the widget's default background differs from the
    theme's — both earlier baselines saturated the count and made a populated
    chart and an empty one read identical."""
    from collections import Counter
    image = shot(widget, w, h)
    pixels = [image.pixel(x, y) for y in range(h) for x in range(w)]
    bg, _n = Counter(pixels).most_common(1)[0]
    return sum(1 for px in pixels if px != bg)


def coloured(image: QImage, colour, tol: int = 40) -> int:
    """Pixels within `tol` per channel of `colour` — how a specific mark
    (the gold LIVE divider, a segment) is found without counting the track."""
    want = (colour.red(), colour.green(), colour.blue())
    n = 0
    for y in range(image.height()):
        for x in range(image.width()):
            px = image.pixelColor(x, y)
            if (abs(px.red() - want[0]) <= tol
                    and abs(px.green() - want[1]) <= tol
                    and abs(px.blue() - want[2]) <= tol):
                n += 1
    return n


# --------------------------------------------------------------------------- #
# EquityCurve
# --------------------------------------------------------------------------- #
def equity_points(n=40, start=10_000.0):
    return [{"t": 1_700_000_000 + i * 3600, "v": start + i * 7,
             "kind": "backtest" if i < n // 2 else "live"} for i in range(n)]


def test_an_empty_equity_curve_renders_its_message_not_a_crash():
    assert ink(EquityCurve()) > 0, "the 'no data' message is itself ink"


def test_a_populated_equity_curve_draws_more_than_an_empty_one():
    empty, full = EquityCurve(), EquityCurve()
    full.set_data(equity_points(), 10_000.0)
    assert ink(full) > ink(empty)


def test_the_live_divider_appears_once_backtest_gives_way_to_live():
    """Everything left of the divider is a fair-odds warm-up, not profit, and
    the gold line is the only thing on this chart saying so."""
    plain, seeded = EquityCurve(), EquityCurve()
    plain.set_data([dict(p, kind="live") for p in equity_points()], 10_000.0)
    seeded.set_data(equity_points(), 10_000.0)
    assert coloured(shot(seeded), theme.GOLD) > 0, "the divider is drawn"
    assert coloured(shot(plain), theme.GOLD) == 0, \
        "an all-live curve has nothing to divide"


def test_a_flat_curve_does_not_divide_by_zero():
    flat = EquityCurve()
    flat.set_data([dict(p, v=10_000.0) for p in equity_points()], 10_000.0)
    assert ink(flat) > 0


# --------------------------------------------------------------------------- #
# Sparkline
# --------------------------------------------------------------------------- #
def test_a_sparkline_draws_its_series():
    s = Sparkline(30)
    s.set_values([1.0, 1.1, 1.05, 1.2, 1.15], up=True)
    assert ink(s, 92, 30) > 0


def test_one_point_is_not_a_line_and_not_a_crash():
    s = Sparkline(30)
    s.set_values([1.0], up=False)
    ink(s, 92, 30)                      # must simply not raise


# --------------------------------------------------------------------------- #
# DepthChart
# --------------------------------------------------------------------------- #
def test_the_book_is_drawn_and_an_empty_book_is_survivable():
    d = DepthChart()
    d.set_book([(0.48, 100.0), (0.47, 40.0)], [(0.52, 80.0), (0.53, 20.0)])
    with_book = ink(d)
    d.set_book([], [])
    assert with_book > 0
    ink(d)                              # empty side: message, not a crash


# --------------------------------------------------------------------------- #
# Lattice
# --------------------------------------------------------------------------- #
def lattice_payload():
    from sonar import model
    return model.lattice_distribution(100.5, 100.0, 0.0045, 0.5)


def test_the_lattice_draws_the_distribution():
    lt = Lattice()
    lt.set_data(lattice_payload())
    assert ink(lt) > 0


def test_a_lattice_with_no_data_renders_the_message():
    assert ink(Lattice()) > 0


# --------------------------------------------------------------------------- #
# ComponentBar — the one with real arithmetic in front of the painting
# --------------------------------------------------------------------------- #
def test_the_bar_keeps_only_weighted_nonzero_components():
    bar = ComponentBar()
    bar.set_parts({"momentum": 0.5, "news": 0.0, "volatility": 0.2}, ASSET_W)
    kept = dict(bar.parts)
    assert "news" not in kept, "a zero component is not a segment"
    assert kept["momentum"] == pytest.approx(ASSET_W["momentum"] * 0.5)


def test_the_fill_is_clamped_to_a_fraction():
    bar = ComponentBar()
    bar.set_parts({"momentum": 1.0}, ASSET_W, fill=1.7)
    assert bar.fill == 1.0
    bar.set_parts({"momentum": 1.0}, ASSET_W, fill=-0.3)
    assert bar.fill == 0.0


def test_an_empty_bar_says_so_in_its_tooltip():
    bar = ComponentBar()
    bar.set_parts({}, ASSET_W)
    assert bar.toolTip() == "no components"
    ink(bar, 80, 7)


def test_a_fuller_bar_is_longer():
    """`fill` is the meter half of the design: length reads as how notable,
    segments as why. If length stops tracking the score, the meter lies.
    Counted in the segment's own colour, because the track behind it fills
    the whole width in both."""
    short, long = ComponentBar(), ComponentBar()
    short.set_parts({"momentum": 1.0}, ASSET_W, fill=0.3)
    long.set_parts({"momentum": 1.0}, ASSET_W, fill=1.0)
    seg = theme.COMP["momentum"]
    assert coloured(shot(long, 80, 7), seg, tol=20) > \
        2 * coloured(shot(short, 80, 7), seg, tol=20)
