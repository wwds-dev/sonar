"""The manual has to be reachable without leaving the app.

It was always good and always one context switch away: a button that opened a
web browser. Someone staring at a number they do not understand is exactly the
person who will not go and find a second window, and the documentation's stated
job — that a reader with no finance background can use this — fails at that
step rather than in the prose.

These tests hold the in-app copy to the two things that make it worth having:
it is the *same* file as the browser version, so the prose can never drift; and
it is navigable, because a 60KB page with no way in is a wall.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from sonar.core import Live
from ui import learn
from ui.app import MainWindow


@pytest.fixture(scope="module")
def window():
    QApplication.instance() or QApplication([])
    win = MainWindow(Live())
    win.poll.live.stop()
    win.poll.quit(); win.poll.wait(3000)
    yield win
    win.shutdown()


# --------------------------------------------------------------------------- #
# the translation
# --------------------------------------------------------------------------- #
def test_the_web_page_chrome_is_gone():
    """A "back to the app" link, inside the app."""
    html, _ = learn.document()
    assert "<header" not in html
    assert 'class="toc"' not in html


def test_the_css_qt_cannot_read_is_gone():
    """Qt silently drops the rules it cannot parse and keeps the rest, so a
    half-understood stylesheet renders worse than no stylesheet at all."""
    html, _ = learn.document()
    assert "<style" not in html
    assert "var(--" not in html


def test_every_section_gets_an_anchor_qt_can_follow():
    """The page marks sections with `id`, which a browser follows and Qt does
    not. Without this the contents list scrolls nowhere."""
    html, sections = learn.document()
    assert sections
    for anchor, _number, _title in sections:
        assert f'<a name="{anchor}"></a>' in html


def test_the_contents_come_from_the_page():
    """Not from a list kept here — that is the copy that goes stale."""
    _html, sections = learn.document()
    assert sections[0][0] == "learn"
    assert [int(n) for _a, n, _t in sections] == list(range(1, len(sections) + 1))


# --------------------------------------------------------------------------- #
# the tab
# --------------------------------------------------------------------------- #
def test_the_app_has_a_learn_tab(window):
    assert "Learn" in [window.tabs.tabText(i) for i in range(window.tabs.count())]


def test_the_toolbar_button_lands_on_it(window):
    window.tabs.setCurrentIndex(0)
    window._show_learn()
    assert window.tabs.tabText(window.tabs.currentIndex()) == "Learn"


def test_the_primer_and_the_glossary_are_actually_rendered(window):
    text = window.learn_view.toPlainText()
    assert len(text) > 10_000
    for term in ("Expected value", "Base rate", "Yield curve", "The vig"):
        assert term in text, f"{term!r} did not survive the translation"


def test_the_contents_list_matches_the_document(window):
    _html, sections = learn.document()
    assert window.learn_toc.count() == len(sections)
    anchors = [window.learn_toc.item(i).data(Qt.UserRole)
               for i in range(window.learn_toc.count())]
    assert anchors == [a for a, _n, _t in sections]


def test_picking_a_section_scrolls_there(window):
    """Shown first on purpose: a QTextBrowser that has never been laid out has
    no scroll range at all, so the assertion would pass or fail for a reason
    that has nothing to do with the anchors."""
    window._show_learn()
    window.resize(1180, 820)
    window.show()
    QApplication.processEvents()
    view = window.learn_view
    assert view.verticalScrollBar().maximum() > 0, "the document never laid out"

    window.learn_toc.setCurrentRow(window.learn_toc.count() - 1)
    bottom = view.verticalScrollBar().value()
    assert bottom > 0, "the last section is not reachable from the contents"

    window.learn_toc.setCurrentRow(0)
    assert view.verticalScrollBar().value() < bottom
    window.hide()


def test_search_finds_a_word_and_says_so_when_it_cannot(window):
    window.learn_find.setText("devigging")
    window._learn_search()
    assert window.learn_hint.text() == ""
    window.learn_find.setText("nonesuchwordatall")
    window._learn_search()
    assert "nothing matches" in window.learn_hint.text()


def test_search_wraps_rather_than_dying_at_the_end(window):
    """The cursor is left wherever the last search finished. Without a wrap the
    second search for the same word finds nothing, which reads as a bug."""
    for _ in range(3):
        window.learn_find.setText("volatility")
        window._learn_search()
        assert window.learn_hint.text() == ""
