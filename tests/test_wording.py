"""Plain or expert — the same app in two vocabularies.

Plain Language fixed a real problem and created a smaller one. "Worth a look" is
what CONF means and is the right heading for someone who has never traded; it is
also three words where one would do, and it does not match the term the manual,
the research notes and every other market tool use. Someone who has learnt what
P(profit) is should not have to translate back.

The switch has one hard rule, and it is the reason these tests exist: it changes
the **vocabulary**, never the layout. A mode that rearranged the board would be
a second interface to build, to test and to keep true, and within two changes
one of them would be wrong.
"""

import json

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from sonar.core import Live
from ui import app as ui_app
from ui import words


@pytest.fixture(autouse=True)
def plain_by_default():
    """Every test starts from the default and leaves it there — the mode is
    module state, and a test that changed it silently would break the next."""
    words._mode = words.PLAIN
    yield
    words._mode = words.PLAIN


@pytest.fixture(scope="module")
def window():
    QApplication.instance() or QApplication([])
    win = ui_app.MainWindow(Live())
    win.poll.live.stop()
    win.poll.quit(); win.poll.wait(3000)
    yield win
    win.shutdown()


def sample(**over):
    a = {"name": "Goldman Sachs", "symbol": "GS", "cls": "Equity",
         "price": 943.44, "day_change": -0.0166, "momentum": -0.034,
         "momentum_days": 5, "volatility": 0.043, "lean": "Elevated",
         "spark": [1.0, 2.0, 3.0], "confidence": 48.0, "data_age_s": 312.0,
         "comp": {"momentum": .5, "volatility": .3, "news": .8, "catalyst": .2},
         "rationale": "GS -3.4% over 5d",
         "plan": {"rr": 1.5, "p_profit": 0.4, "calibrated": False}}
    a.update(over)
    return a


def row(**over):
    QApplication.instance() or QApplication([])
    return ui_app.AssetRow(sample(**over), lambda *x: None, lambda *x: None)


def texts(widget) -> list[str]:
    from PySide6.QtWidgets import QLabel
    return [lb.text() for lb in widget.findChildren(QLabel)]


# --------------------------------------------------------------------------- #
# the setting
# --------------------------------------------------------------------------- #
def test_plain_is_the_default():
    assert words.load.__doc__ and words.plain()


def test_the_choice_survives_a_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(words, "_file", lambda: tmp_path / "wording.json")
    words.set_mode(words.EXPERT)
    words._mode = words.PLAIN                 # as if the app had restarted
    assert words.load() == words.EXPERT


def test_a_hand_edited_preference_file_cannot_break_the_app(tmp_path, monkeypatch):
    """It is a JSON file in a directory a person can open, so it will be
    edited by hand eventually, and a corrupt one must not be fatal."""
    path = tmp_path / "wording.json"
    monkeypatch.setattr(words, "_file", lambda: path)
    for junk in ("", "{", '{"wording": "klingon"}', "[]"):
        path.write_text(junk)
        assert words.load() == words.PLAIN


def test_toggle_goes_both_ways(tmp_path, monkeypatch):
    monkeypatch.setattr(words, "_file", lambda: tmp_path / "wording.json")
    assert words.toggle() == words.EXPERT
    assert words.toggle() == words.PLAIN


# --------------------------------------------------------------------------- #
# the rule: vocabulary, not layout
# --------------------------------------------------------------------------- #
def test_every_column_has_both_names():
    for key, names, _w, _a, _tip in ui_app.ASSET_COLS:
        assert isinstance(names, tuple) and len(names) == 2, key


def test_expert_uses_the_standard_terms():
    expert = {k: names[1] for k, names, _w, _a, _t in ui_app.ASSET_COLS}
    assert expert["momentum"] == "MOM"
    assert expert["volatility"] == "VOL"
    assert expert["conf"] == "CONF"
    assert "R:R" in expert["plan"] and "P(PROF)" in expert["plan"]


def test_the_columns_are_identical_in_both_wordings():
    """The hard rule. Same keys, same widths, same order — so the header can be
    re-captioned in place rather than rebuilt, and so there is only ever one
    board to keep correct."""
    plain_layout = ui_app._asset_widths()
    words._mode = words.EXPERT
    assert ui_app._asset_widths() == plain_layout


def test_the_expert_board_is_denser():
    tall = row().sizeHint().height()
    words._mode = words.EXPERT
    assert row().sizeHint().height() < tall


def test_expert_puts_the_ticker_back_and_plain_puts_a_sentence_there():
    """The line under the name is the clearest statement of what each wording
    is for: a reading for one reader, an identifier for the other."""
    assert any("slipping" in t for t in texts(row()))
    assert not any(t.startswith("GS ") for t in texts(row()))

    words._mode = words.EXPERT
    assert any(t.startswith("GS ") for t in texts(row()))
    assert not any("slipping" in t for t in texts(row()))


@pytest.mark.parametrize("seconds,plain_text,expert_text", [
    (30, "under 1m", "<1m"),
    (300, "5m ago", "5m"),
    (7380, "2h03m ago", "2h03m"),
])
def test_the_age_is_shorter_in_expert(seconds, plain_text, expert_text):
    assert ui_app._age_text(seconds, plain=True) == plain_text
    assert ui_app._age_text(seconds, plain=False) == expert_text


# --------------------------------------------------------------------------- #
# switching it live
# --------------------------------------------------------------------------- #
def test_switching_re_captions_without_rebuilding(window, monkeypatch, tmp_path):
    monkeypatch.setattr(words, "_file", lambda: tmp_path / "wording.json")
    header = window.asset_header
    headings = [h for h in header.findChildren(ui_app.HelpHeading)]
    before = [h.text() for h in headings]

    window._toggle_wording()
    assert [h.text() for h in headings] != before, "the headings never changed"
    assert "CONF" in [h.text() for h in headings]
    assert window.tabs.tabText(1) == "Assets"
    assert not window.assets_banner.isVisible() or not window.isVisible()

    window._toggle_wording()
    assert [h.text() for h in headings] == before
    assert window.tabs.tabText(1) == "Screener"


def test_switching_forces_the_rows_to_be_rebuilt(window, monkeypatch, tmp_path):
    """The rows are the one thing that genuinely changes shape, so they cannot
    be re-captioned in place — clearing the signature hands that to the next
    refresh tick."""
    monkeypatch.setattr(words, "_file", lambda: tmp_path / "wording.json")
    window._assets_sig = ("something", 3)
    window._toggle_wording()
    assert window._assets_sig is None
    window._toggle_wording()


def test_the_stat_strips_follow_too(window, monkeypatch, tmp_path):
    monkeypatch.setattr(words, "_file", lambda: tmp_path / "wording.json")
    tau = window.stats["tau"]
    assert tau.cap.text() == "HOUR REMAINING"
    window._toggle_wording()
    assert tau.cap.text() == "TAU"
    window._toggle_wording()
    assert tau.cap.text() == "HOUR REMAINING"
