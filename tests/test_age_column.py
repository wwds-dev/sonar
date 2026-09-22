"""A price that is quietly out of date is this project's worst failure mode.

The Assets board refetches only ``assets.ROLL_BATCH`` of its 129 instruments per
scan, so a row's price is routinely several minutes old — by design, because
fetching all of them got this machine throttled, and a throttled scan returns
fewer rows rather than an error. That is defensible right up until the screen
shows the age as nothing at all, at which point a fifteen-minute-old number
reads exactly like a live one.

So the age is on the row. These tests hold it to the two things that make it
worth having: it must never round down to something that reads as "live", and it
must keep counting between scans rather than freezing at whatever the scan
measured.
"""

import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication

from ui import app as ui_app
from ui import theme


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def row(qapp, data_age_s: float, generated: float | None = None):
    a = {"name": "Meta", "symbol": "META", "cls": "Equity", "price": 749.54,
         "day_change": 0.0112, "momentum": 0.118, "momentum_days": 5,
         "volatility": 0.037, "lean": "Spike", "spark": [1.0, 2.0, 3.0],
         "comp": {"momentum": .5, "volatility": .3, "news": .8, "catalyst": .2},
         "confidence": 78.0, "data_age_s": data_age_s,
         "plan": {"rr": 1.5, "p_profit": 0.4, "calibrated": False}}
    return ui_app.AssetRow(a, lambda *x: None, lambda *x: None,
                           generated if generated is not None else time.time())


# --------------------------------------------------------------------------- #
# the text
# --------------------------------------------------------------------------- #
def test_a_fresh_row_never_reads_as_zero():
    """"0m" is indistinguishable from "live", and no row is ever live."""
    assert ui_app._age_text(0) == "<1m"
    assert ui_app._age_text(59) == "<1m"


def test_minutes_then_hours():
    assert ui_app._age_text(60) == "1m"
    assert ui_app._age_text(59 * 60) == "59m"
    assert ui_app._age_text(60 * 60) == "1h00m"
    assert ui_app._age_text(2 * 3600 + 180) == "2h03m"


def test_the_text_fits_its_column():
    """Qt elides a label squeezed below its text, which would turn the honest
    number into an unreadable glyph — the failure this column exists to avoid."""
    QApplication.instance() or QApplication([])
    width = dict(ui_app._asset_widths())["age"]
    fm = QFontMetrics(theme.mono(10))
    for seconds in (0, 90, 59 * 60, 3600, 11 * 3600, 99 * 3600):
        assert fm.horizontalAdvance(ui_app._age_text(seconds)) <= width


# --------------------------------------------------------------------------- #
# the colour
# --------------------------------------------------------------------------- #
def test_normal_staleness_is_not_dressed_up_as_a_fault():
    """A full rotation takes about fifteen minutes. Colouring that red would
    train the reader to ignore the colour."""
    assert ui_app._age_color(5 * 60) is theme.MUTED
    assert ui_app._age_color(15 * 60) is theme.MUTED


def test_past_a_rotation_it_warns_and_past_an_hour_it_alarms():
    assert ui_app._age_color(ui_app.AGE_WARN_S) is theme.GOLD
    assert ui_app._age_color(ui_app.AGE_BAD_S) is theme.DOWN


# --------------------------------------------------------------------------- #
# the row
# --------------------------------------------------------------------------- #
def test_the_row_shows_the_age_the_scan_measured(qapp):
    assert row(qapp, 312.0).age.text() == "5m"


def test_the_age_keeps_counting_between_scans(qapp):
    """The whole point. Rows are rebuilt only when a scan produces new data —
    about every three minutes — so an age frozen at build time would under-
    report by up to a full scan interval, every time."""
    r = row(qapp, 60.0)
    assert r.age.text() == "1m"
    r.update_age(time.time() + 9 * 60)
    assert r.age.text() == "10m"


def test_the_age_is_anchored_to_the_scan_not_to_the_render(qapp):
    """A row built from a five-minute-old snapshot must say eight minutes, not
    three: `data_age_s` is measured when the scan runs, not when it is drawn."""
    r = row(qapp, 180.0, generated=time.time() - 5 * 60)
    assert r.age.text() == "8m"


def test_the_board_still_fits_the_default_window(qapp):
    """Adding a column must not push the board past the width the window opens
    at — the columns are fixed-width, so the cost of one more is not absorbed."""
    assert row(qapp, 60.0).sizeHint().width() <= ui_app.PREFERRED_SIZE[0]
    assert ui_app.AssetHeader().sizeHint().width() <= ui_app.PREFERRED_SIZE[0]


def test_the_header_still_sits_over_the_columns(qapp):
    """Headings and cells are built from the same list, so the only difference
    between their widths may be the margins — the header's left margin covers
    the scroll area's own padding and the row panel's border. Anything else
    means a column was given a width of its own and the board is now misread
    by exactly one heading."""
    head, rw = ui_app.AssetHeader(), row(qapp, 60.0)
    hm, rm = head.layout().contentsMargins(), rw.layout().contentsMargins()
    offset = (hm.left() + hm.right()) - (rm.left() + rm.right())
    assert head.sizeHint().width() - rw.sizeHint().width() == offset
