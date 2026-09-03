"""The window has to fit on the screen it opens on.

SONAR once opened **4,540pt wide** on a 1,280pt display. Nothing was broken in
any way a test or a self-test could see: it built, it ran, it passed 301 tests,
and three quarters of the interface was simply off the right-hand edge.

The cause is a Qt rule that is easy to forget. A QLabel that does not wrap
reports a sizeHint as wide as its text is long; a layout cannot shrink below its
children's minimums; a QTabWidget's minimum is the widest tab's. So a single
unwrapped paragraph in one tab sets the minimum width of the entire window, and
``resize()`` is silently ignored because it is below that minimum.

These tests measure minimum size hints, which are independent of whatever screen
the test runner happens to have.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel

from sonar.core import Live
from ui.app import PREFERRED_SIZE, MainWindow

# A 13" MacBook at its default scaling, minus the menu bar. Not a large screen,
# and not a rare one — if the window does not fit here it does not fit.
SCREEN_W, SCREEN_H = 1280, 775


@pytest.fixture(scope="module")
def window():
    app = QApplication.instance() or QApplication([])
    win = MainWindow(Live())
    win.poll.live.stop()
    win.poll.quit(); win.poll.wait(3000)
    yield win
    win.shutdown()


def test_the_window_fits_a_small_laptop(window):
    m = window.minimumSizeHint()
    assert m.width() <= SCREEN_W, (
        f"the window cannot be made narrower than {m.width()}pt, so on a "
        f"{SCREEN_W}pt screen it opens with {m.width() - SCREEN_W}pt off the edge")
    assert m.height() <= SCREEN_H


def test_no_single_tab_forces_the_window_wide(window):
    """Pinpoints the culprit when the test above fails."""
    over = {window.tabs.tabText(i): window.tabs.widget(i).minimumSizeHint().width()
            for i in range(window.tabs.count())
            if window.tabs.widget(i).minimumSizeHint().width() > SCREEN_W}
    assert not over, f"tabs too wide to fit the screen: {over}"


def test_long_prose_labels_wrap(window):
    """The specific defect, stated as a rule.

    Anything wide enough to matter must wrap, or it becomes a floor on the
    window's width that no resize() can get under.
    """
    guilty = [(lb.text()[:60], lb.sizeHint().width())
              for lb in window.findChildren(QLabel)
              if lb.sizeHint().width() > SCREEN_W and not lb.wordWrap()]
    assert not guilty, f"unwrapped labels wider than the screen: {guilty}"


def test_the_preferred_size_is_itself_reasonable():
    """A preferred size larger than a common screen is a bug in waiting."""
    assert PREFERRED_SIZE[0] <= SCREEN_W
    # Height is allowed to exceed the small-laptop case because _fit_to_screen
    # clamps it, but it should not be absurd.
    assert PREFERRED_SIZE[1] <= 1000


def test_fit_to_screen_never_grows_the_window(window):
    """Clamping only ever shrinks — a big monitor must not get a huge window."""
    window._fit_to_screen()
    assert window.width() <= PREFERRED_SIZE[0]
    assert window.height() <= PREFERRED_SIZE[1]
