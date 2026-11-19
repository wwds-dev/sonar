"""The why-notable card in the Qt Screener (spec A2, A6, Design).

Real `MainWindow`, the recorded board; runs in both Qt modes.
"""
import copy
import json
import time
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from sonar.core import Live
from ui import app as ui_app
from ui import theme, words
from ui import why_card as W

BOARD = json.loads((Path(__file__).parent / "fixtures"
                    / "assets_board_2026-11-18.json").read_text())
HERE = Path(__file__).parent
ui_app_window: list = []


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    QApplication.instance() or QApplication([])
    win = ui_app.MainWindow(Live())
    win.poll.live.stop()
    win.poll.quit(); win.poll.wait(3000)
    win.timer.stop()           # the refresh tick would replace the recorded board
    for i in range(win.tabs.count()):
        if win.tabs.tabText(i) == "Screener":
            win.tabs.setCurrentIndex(i)
    win.resize(1280, 775)
    win.show()
    ui_app_window.append(win)
    yield win
    ui_app_window.clear()
    win.shutdown()


@pytest.fixture(autouse=True)
def _fresh(window, tmp_path, monkeypatch):
    monkeypatch.setattr(words, "_file", lambda: tmp_path / "wording.json")
    words.set_mode(words.PLAIN)
    window._drop_why_card()
    window._assets_sig = None
    window._refresh_cards(copy.deepcopy(BOARD))
    QApplication.processEvents()
    window._assets_area.verticalScrollBar().setValue(0)
    yield
    window._drop_why_card()


def board(**over):
    b = copy.deepcopy(BOARD)
    b.update(over)
    return b


_scan = __import__("itertools").count(1)     # every call is a new scan


def rebuild(window, b):
    """A new scan: a new `generated` stamp makes the board rebuild."""
    b["generated"] = b.get("generated", 0) + next(_scan)
    window._refresh_cards(b)
    for _ in range(3):          # layout, show and the scroll restore each take a turn
        QApplication.processEvents()


def click(widget):
    """A real click, so the widget is scrolled into view first (QTest injects
    the event at the window's coordinates, where something else may sit)."""
    area = ui_app_window[0]._assets_area
    if widget.window() is ui_app_window[0] and area.isAncestorOf(widget):
        area.ensureWidgetVisible(widget, 0, 0)
        QApplication.processEvents()
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, widget.rect().center())


def focused(window, widget) -> bool:
    """Where the window will put focus. Independent of whether the desktop has
    made this window the active one, which a test cannot rely on."""
    return window.focusWidget() is widget


def age_of(r) -> float:
    return max(0.0, time.time() - r._fetched_at)


def row(window, sym):
    return window._row_of(sym)


def test_clicking_the_score_opens_the_card_right_under_its_row(window):
    r = row(window, "NVDA")
    click(r.score_cell)
    lay = window._assets_lay
    assert window._why_open == "NVDA"
    assert lay.itemAt(lay.indexOf(r) + 1).widget() is window._why_card
    assert r.caret.text() == "▾"
    assert "shown" in r.score_cell.accessibleName()


def test_the_cell_is_a_control(window):
    r = row(window, "NVDA")
    c = r.score_cell
    assert c.focusPolicy() == Qt.StrongFocus
    assert c.cursor().shape() == Qt.PointingHandCursor
    assert c.toolTip() == f"Click to see why this row scores {r._score}"
    assert c.accessibleName() == (
        f"Why Nvidia is worth a look, {r._score} of 100; hidden")
    assert r.caret.text() == "▸"
    assert f"{theme.UP.name()}" in c.styleSheet() and "2px" in c.styleSheet()


def test_the_heading_tooltip_says_to_click_a_score():
    tip = {k: t for k, _n, _w, _a, t in ui_app.ASSET_COLS}["conf"]
    assert tip.endswith("Click a score to see why.")


def test_clicking_again_closes_it(window):
    r = row(window, "NVDA")
    click(r.score_cell)
    click(r.score_cell)
    assert window._why_open is None and window._why_card is None
    assert r.caret.text() == "▸"


def test_only_one_card_is_open(window):
    click(row(window, "NVDA").score_cell)
    click(row(window, "BABA").score_cell)
    assert window._why_open == "BABA"
    lay = window._assets_lay
    cards = [lay.itemAt(i).widget() for i in range(lay.count())
             if isinstance(lay.itemAt(i).widget(), ui_app.WhyCard)]
    assert cards == [window._why_card]
    assert row(window, "NVDA").caret.text() == "▸"
    assert row(window, "BABA").caret.text() == "▾"


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space])
def test_keyboard_opens_the_card(window, key):
    c = row(window, "NVDA").score_cell
    c.setFocus()
    QTest.keyClick(c, key)
    assert window._why_open == "NVDA"


def test_escape_closes_and_returns_focus_to_the_cell(window):
    r = row(window, "NVDA")
    click(r.score_cell)
    window._why_card.hide_btn.setFocus()
    QTest.keyClick(window._why_card.hide_btn, Qt.Key_Escape)
    assert window._why_open is None
    assert focused(window, r.score_cell)


def test_the_hide_button_closes_it(window):
    click(row(window, "NVDA").score_cell)
    window._why_card.hide_btn.click()
    assert window._why_open is None


def test_the_hide_button_is_next_in_tab_order(window):
    r = row(window, "NVDA")
    click(r.score_cell)
    nxt = r.score_cell.nextInFocusChain()
    while nxt.focusPolicy() == Qt.NoFocus:
        nxt = nxt.nextInFocusChain()
    assert nxt is window._why_card.hide_btn


def test_the_card_shows_the_cards_text(window):
    click(row(window, "BABA").score_cell)
    texts = " ".join(l.text() for l in window._why_card.findChildren(QLabel))
    c = W.build_card(row(window, "BABA").a, window._assets_board, plain=True,
                     age_s=age_of(row(window, "BABA")))
    assert c.title in texts and c.footer in texts and c.rounding_note in texts
    for ln in c.lines:
        assert ln.text in texts


# -- a new scan --------------------------------------------------------------- #
def test_a_rebuild_keeps_the_card_open_on_the_new_row(window):
    click(row(window, "NVDA").score_cell)
    old_card = window._why_card
    b = board()
    for a in b["assets"]:
        if a["symbol"] == "NVDA":
            a["comp"] = dict(a["comp"], news=0.5)
            a["confidence"] = round(100 * sum(
                W.A._W[k] * a["comp"].get(k, 0) for k in W.A._W), 1)
    rebuild(window, b)
    assert window._why_open == "NVDA"
    assert window._why_card is not old_card
    r = row(window, "NVDA")
    assert r.caret.text() == "▾"
    new = W.build_card(r.a, window._assets_board, plain=True, age_s=age_of(r))
    assert window._why_card.card == new
    old = W.build_card(BOARD["assets"][0], BOARD, plain=True, age_s=age_of(r))
    assert new.lines != old.lines          # the new numbers, not the old card


def test_a_rebuild_keeps_scroll_and_focus(window):
    window.resize(1280, 775)
    click(row(window, "NVDA").score_cell)
    bar = window._assets_area.verticalScrollBar()
    window._why_card.hide_btn.setFocus()
    QApplication.processEvents()
    assert bar.maximum() > 40
    bar.setValue(40)
    rebuild(window, board())
    assert bar.value() == 40
    assert focused(window, window._why_card.hide_btn)
    # focus on the cell comes back to the cell
    row(window, "NVDA").score_cell.setFocus()
    rebuild(window, board())
    assert focused(window, row(window, "NVDA").score_cell)


def test_a_scan_does_not_steal_focus_from_elsewhere(window):
    click(row(window, "NVDA").score_cell)
    window.wording_btn.setFocus()
    rebuild(window, board())
    assert focused(window, window.wording_btn)


def test_a_symbol_that_leaves_the_board_closes_the_card(window):
    click(row(window, "NVDA").score_cell)
    window._why_card.hide_btn.setFocus()
    b = board()
    b["assets"] = [a for a in b["assets"] if a["symbol"] != "NVDA"]
    rebuild(window, b)
    assert window._why_open is None and window._why_card is None
    assert focused(window, window.asset_header)
    lay = window._assets_lay
    assert not any(isinstance(lay.itemAt(i).widget(), ui_app.WhyCard)
                   for i in range(lay.count()))


def test_the_age_timer_never_touches_the_card(window):
    click(row(window, "NVDA").score_cell)
    card = window._why_card
    texts = [l.text() for l in card.findChildren(QLabel)]
    window._refresh_cards(window._assets_board)       # same signature: ticks only
    assert window._why_card is card
    assert [l.text() for l in card.findChildren(QLabel)] == texts


def test_the_wording_switch_rerenders_the_open_card(window):
    click(row(window, "NVDA").score_cell)
    words.set_mode(words.EXPERT)
    window._apply_wording()
    window._refresh_cards(window._assets_board)
    QApplication.processEvents()
    assert window._why_open == "NVDA"
    assert window._why_card.card.title.startswith("NVDA — NOTABILITY")
    assert row(window, "NVDA").caret.text() == "▾"
    words.set_mode(words.PLAIN)


def test_no_rows_means_no_card(window):
    click(row(window, "NVDA").score_cell)
    rebuild(window, {"status": "starting", "assets": []})
    assert window._why_card is None and window._why_open is None


# -- layout ------------------------------------------------------------------- #
def test_the_tallest_card_fits_the_viewport_at_the_minimum_window(window):
    window.resize(1280, 775)
    QApplication.processEvents()
    area = window._assets_area
    r = row(window, "BABA")             # earnings label + W8 note
    click(r.score_cell)
    QApplication.processEvents()
    card = window._why_card
    vp = area.viewport()
    top = card.mapTo(vp, card.rect().topLeft()).y()
    bottom = card.mapTo(vp, card.rect().bottomLeft()).y()
    assert top >= 0 and bottom <= vp.height(), (top, bottom, vp.height())
    assert card.height() <= 330, card.height()
    assert card.width() <= r.width()        # it adds no width of its own


def test_the_card_adds_no_width(window):
    before = window.minimumSizeHint().width()
    click(row(window, "BABA").score_cell)
    assert window.minimumSizeHint().width() <= before


def test_the_stale_line_shows_in_the_open_card(window):
    b = board()
    for a in b["assets"]:
        if a["symbol"] == "NVDA":
            a["data_age_s"] = 3 * 3600.0
    rebuild(window, b)
    click(row(window, "NVDA").score_cell)
    assert window._why_card.card.stale


# -- text colours and contrast ------------------------------------------------ #
def lum(c: QColor) -> float:
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c.red()) + 0.7152 * f(c.green()) + 0.0722 * f(c.blue())


def ratio(a: QColor, b: QColor) -> float:
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_every_text_colour_on_the_card_is_a_theme_text_colour_and_readable(window):
    b = board()
    for a in b["assets"]:
        if a["symbol"] == "NVDA":
            a["data_age_s"] = 3 * 3600.0
    rebuild(window, b)
    click(row(window, "NVDA").score_cell)
    allowed = {theme.INK.name(), theme.MUTED.name(), theme.FAINT.name(),
               theme.GOLD.name(), theme.DOWN.name()}
    seen = set()
    for lb in window._why_card.findChildren(QLabel):
        css = lb.styleSheet()
        assert css.startswith("color: "), (lb.text(), css)
        colour = css.split(":")[1].strip(" ;")
        assert colour in allowed
        seen.add(colour)
        assert ratio(QColor(colour), theme.PANEL) >= 4.5, (colour, lb.text())
    assert {theme.INK.name(), theme.MUTED.name(), theme.FAINT.name()} <= seen


# -- the learn paragraph and the strings ------------------------------------- #
def learn_paragraph() -> str:
    import re
    html = (HERE.parent / "static" / "docs.html").read_text()
    m = re.search(r'<h3 id="why-card">.*?(?=<div class="callout|<h3|<h2)', html, re.S)
    assert m, "the Learn paragraph is missing from static/docs.html"
    return re.sub(r"<[^>]+>", " ", m.group(0))


def test_the_learn_paragraph_names_the_four_maxima_from_the_weights():
    import re
    text = " ".join(learn_paragraph().split())
    for k, word in (("news", "news"), ("momentum", "recent move"),
                    ("catalyst", "earnings date"), ("volatility", "swing size")):
        assert re.search(rf"{word}, up to {W.max_points(k)}\b", text), (k, text)


def test_no_banned_term_in_the_learn_paragraph_or_the_cell_strings(window):
    from tests.test_why_card import banned_in
    r = row(window, "NVDA")
    strings = [learn_paragraph(), r.score_cell.toolTip(), r.score_cell.accessibleName(),
               {k: t for k, _n, _w, _a, t in ui_app.ASSET_COLS}["conf"].split("\n")[-1]]
    click(r.score_cell)
    strings += [r.score_cell.accessibleName(), window._why_card.hide_btn.toolTip(),
                window._why_card.hide_btn.accessibleName(),
                window._why_card.accessibleName()]
    for s in strings:
        assert not banned_in(s), (s, banned_in(s))


# --------------------------------------------------------------------------- #
# Review fixes
# --------------------------------------------------------------------------- #
def _count(image, rect, colour: QColor) -> int:
    rgb = colour.rgb()
    return sum(1 for x in range(rect.left(), rect.right() + 1)
               for y in range(rect.top(), rect.bottom() + 1)
               if image.pixel(x, y) == rgb)


def test_the_score_cell_paints_no_dark_box(window):
    """CR P1-1: QFrame#scorecell inherited the window's BG, so all 129 rows drew a
    BG-coloured rectangle on their PANEL. The old holder was transparent.
    (The app sets theme.STYLESHEET on the QApplication; setting it on the one
    widget cascades the same rules without restyling the whole window.)"""
    r = row(window, "NVDA")
    r.setStyleSheet(theme.STYLESHEET)
    for _ in range(3):                  # let the new rows be laid out and shown
        QApplication.processEvents()
    img = r.grab().toImage()
    rect = r.score_cell.geometry()
    assert not img.isNull() and rect.height() > 20, rect
    assert _count(img, rect, theme.BG) == 0
    assert _count(img, rect, theme.PANEL) > 200     # it is the panel showing through


def test_the_cards_points_holders_paint_no_dark_box(window):
    click(row(window, "NVDA").score_cell)
    card = window._why_card
    card.setStyleSheet(theme.STYLESHEET)
    for _ in range(3):
        QApplication.processEvents()
    img = card.grab().toImage()
    assert not img.isNull()
    holders = [w for w in card.findChildren(QWidget)
               if w.objectName() == "cell" and w.width() == window._why_card.POINTS_W]
    assert len(holders) == 4
    for h in holders:
        rect = h.geometry()
        rect.moveTopLeft(h.mapTo(card, rect.topLeft()) - rect.topLeft())
        assert _count(img, rect, theme.BG) == 0


def test_the_score_cell_is_announced_as_a_button(window):
    from PySide6.QtGui import QAccessible
    QAccessible.setActive(True)
    cell = row(window, "NVDA").score_cell
    iface = QAccessible.queryAccessibleInterface(cell)
    assert iface.role() == QAccessible.Role.Button
    assert iface.text(QAccessible.Text.Name) == cell.accessibleName()
    assert iface.state().focusable


def test_a_held_key_does_not_flicker_the_card(window):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    c = row(window, "NVDA").score_cell
    c.setFocus()
    first = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ", False, 1)
    repeat = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ", True, 1)
    c.keyPressEvent(first)
    assert window._why_open == "NVDA"
    for _ in range(5):
        c.keyPressEvent(repeat)
    assert window._why_open == "NVDA"


def test_a_scan_keeps_focus_on_any_score_cell(window):
    """CR P3-4: only the open row's cell kept focus across a scan."""
    window._drop_why_card()
    row(window, "BABA").score_cell.setFocus()
    rebuild(window, board())
    assert focused(window, row(window, "BABA").score_cell)


def test_learn_says_what_the_card_says():
    text = " ".join(learn_paragraph().split())
    assert "something is happening" not in text            # DF P1-2
    assert "usually moves" not in text                     # DF P2-1
    assert "SONAR's estimate of its daily swing" in text
    assert "partly compared with other markets of the same kind" in text.replace("\n", " ")
    assert "does not say which way the price goes next" in text


def test_the_dispute_pointer_names_a_section_that_exists():
    import re
    html = (HERE.parent / "static" / "docs.html").read_text()
    n = re.search(r"section (\d+)\)", W.UNDER_DISPUTE["volatility"]).group(1)
    assert re.search(rf'<h2 id="[a-z]+"><span class="n">{n}</span>What the research found',
                     html)


def test_a_score_cell_whose_row_leaves_the_board_sends_focus_to_the_header(window):
    """QA P2-1: with the card closed or open, focus on a row's own score cell,
    and that row leaving the board, used to land on another row's cell."""
    for opened in (False, True):
        window._drop_why_card()
        if opened:
            click(row(window, "NVDA").score_cell)
        row(window, "NVDA").score_cell.setFocus()
        b = board()
        b["assets"] = [a for a in b["assets"] if a["symbol"] != "NVDA"]
        rebuild(window, b)
        assert focused(window, window.asset_header), opened
        rebuild(window, board())            # put it back for the next pass

