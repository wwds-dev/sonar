"""The board has to be readable by someone who has never traded anything.

That is not a nicety here — it is the stated job of the documentation ("you do
not need a finance background to use this") and the app spent a year failing it
one abbreviation at a time. MOM, VOL, R:R, P(PROF), CONF is five pieces of
jargon in a row, and the explanations existed only as hover text, which cannot
be found by someone who does not already know there is something to hover.

So these are the rules that keep it readable, stated as tests rather than as an
intention: headings are words, every heading that names something non-obvious
links to the paragraph explaining it, that paragraph exists, and the one plain
sentence on each row never quietly acquires a direction.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from sonar.core import Live
from ui import app as ui_app
from ui import learn


@pytest.fixture(scope="module")
def window():
    QApplication.instance() or QApplication([])
    win = ui_app.MainWindow(Live())
    win.poll.live.stop()
    win.poll.quit(); win.poll.wait(3000)
    yield win
    win.shutdown()


# --------------------------------------------------------------------------- #
# headings
# --------------------------------------------------------------------------- #
def test_no_column_is_named_in_jargon():
    """The specific five, by name. Each one was a heading here."""
    headings = {h for _k, h, _w, _a, _t in ui_app.ASSET_COLS}
    for jargon in ("MOM", "VOL", "R:R", "P(PROF)", "CONF", "1D"):
        assert jargon not in headings


def test_headings_are_words_not_abbreviations():
    for _key, heading, _w, _a, _tip in ui_app.ASSET_COLS:
        if not heading:
            continue
        assert heading[0].isupper() and not heading.isupper(), \
            f"{heading!r} is shouting, which is what abbreviations did"


def test_every_help_link_lands_somewhere_real():
    """The guard that makes the links trustworthy. A heading that opens the
    manual at a section that no longer exists is worse than one that opens
    nothing: it looks like it worked."""
    _html, sections = learn.document()
    anchors = {a for a, _n, _t in sections}
    for _key, heading, _w, anchor, _tip in ui_app.ASSET_COLS:
        if anchor:
            assert anchor in anchors, f"{heading!r} links to a missing §{anchor}"


def test_the_hard_columns_all_carry_a_link():
    """Not every column needs one — "Price" explains itself. These do."""
    linked = {k for k, _h, _w, a, _t in ui_app.ASSET_COLS if a}
    assert {"momentum", "volatility", "lean", "plan", "conf"} <= linked


def test_clicking_a_heading_opens_the_manual_there(window):
    window.tabs.setCurrentIndex(0)
    window._show_learn("scores")
    assert window.tabs.tabText(window.tabs.currentIndex()) == "Learn"
    picked = window.learn_toc.currentItem()
    assert picked is not None and picked.data(Qt.UserRole) == "scores"


# --------------------------------------------------------------------------- #
# the sentence on every row
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("lean", ["Spike", "Elevated", "Normal", "Quiet"])
def test_the_plain_read_covers_every_news_level(lean):
    """A level with no wording falls back to bare momentum, which reads as a
    missing half-sentence."""
    read = ui_app._plain_read({"momentum": 0.12, "lean": lean})
    assert "," in read, f"{lean!r} produced {read!r}"


@pytest.mark.parametrize("momentum", [-0.4, -0.12, -0.05, 0.0, 0.05, 0.12, 0.4])
def test_the_plain_read_never_asserts_a_direction(momentum):
    """The single rule this app will not break, now that a *sentence* is on the
    row rather than only a number. Describing the past is fine; anything that
    reads as a forecast is the app breaking its own rule in a friendly voice."""
    read = ui_app._plain_read({"momentum": momentum, "lean": "Spike"})
    for forecast in ("will", "should", "buy", "sell", "expect", "likely",
                     "going to", "bullish", "bearish"):
        assert forecast not in read.lower(), f"{read!r} predicts something"


def test_swing_words_follow_the_number():
    assert ui_app._swing_words(0.045) == "big swings"
    assert ui_app._swing_words(0.020) == "medium"
    assert ui_app._swing_words(0.007) == "small swings"


# --------------------------------------------------------------------------- #
# the tab bar
# --------------------------------------------------------------------------- #
def test_every_tab_shows_both_names(window):
    """The plain name is for the reader; the original is for the forty
    sentences in the manual that refer to it, and for a month of habit."""
    bar = window.tabs.tabBar()
    pairs = {window.tabs.tabText(i): bar._subtitles.get(i, "")
             for i in range(window.tabs.count())}
    assert pairs["Screener"] == "ASSETS"
    assert pairs["Practice"] == "LAB"
    assert pairs["My trades"] == "BOOK"
    assert len(pairs) == window.tabs.count(), "two tabs share a name"


def test_a_tab_is_wide_enough_for_its_own_name(window):
    """Sized from the unselected font, every tab lost its last letter the
    moment it was clicked."""
    from PySide6.QtGui import QFontMetrics
    from ui import theme
    bar = window.tabs.tabBar()
    for i in range(window.tabs.count()):
        needed = QFontMetrics(theme.text(12, True)).horizontalAdvance(
            window.tabs.tabText(i))
        assert bar.tabRect(i).width() >= needed, window.tabs.tabText(i)
