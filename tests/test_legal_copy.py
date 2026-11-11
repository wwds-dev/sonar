"""Copy and packaging rules from the 2026-11-10 legal audit (findings 3, 4, 5, 7, 8, 9).

Source-level checks only (no window): they hold the wording and the build script in place.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ui import words

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / "ui" / "app.py").read_text()
DOCS = (ROOT / "static" / "docs.html").read_text()
BUILD = (ROOT / "build_app.sh").read_text()


def test_stake_tooltip_makes_no_safety_promise():
    for text in (words.STAKE_TIP, APP, DOCS):
        assert "without risking ruin" not in text
    assert "if the probability is right" in words.STAKE_TIP
    assert "over-bets" in words.STAKE_TIP


def test_stake_tooltip_is_the_one_the_window_uses():
    assert '("stake", words.STAKE_TIP)' in APP


@pytest.mark.parametrize("mode", [words.PLAIN, words.EXPERT])
def test_ai_label_in_both_wording_modes(mode, tmp_path, monkeypatch):
    monkeypatch.setattr(words, "_mode", mode)
    for pair in (words.LLM_READ_TITLE, words.MODEL_READ_TITLE):
        assert "AI-GENERATED" in words.pick(pair)
    assert "commentary, not advice" in words.AI_TAG
    assert "Claude" in words.AI_TAG


def test_llm_panel_and_model_read_use_the_label():
    assert "words.LLM_READ_TITLE" in APP and "words.MODEL_READ_TITLE" in APP
    assert "words.AI_TAG" in APP and "words.DIRECTION_NOTE" in APP
    assert '"LLM READ"' not in APP and "MODEL READ — commentary only" not in APP


def test_direction_note_denies_a_recommendation():
    assert "not a recommendation" in words.DIRECTION_NOTE
    assert "more often than chance" in words.DIRECTION_NOTE


def test_hourly_model_says_it_is_not_a_recommendation():
    """The one direction SONAR states itself carries the note on its own panel."""
    assert "not a recommendation" in words.HOURLY_MODEL_NOTE
    assert "not been shown to be an edge" in words.HOURLY_MODEL_NOTE
    panel = APP.split("def _terminal_tab", 1)[1].split("\n    def ", 1)[0]
    assert "words.HOURLY_MODEL_NOTE" in panel
    assert "wrap=True" in panel.split("words.HOURLY_MODEL_NOTE", 1)[1][:90], "a long label must wrap"
    # The note repeats the manual's claim; if Learn §4 ever says otherwise, this fails.
    assert re.search(r"has <b>not</b> been shown to be an edge", DOCS)


def test_playmaker_notice_is_shown_in_the_tab_manual_and_readme():
    assert "words.PLAYMAKER_NOTICE" in APP
    assert "not betting advice" in words.PLAYMAKER_NOTICE.lower()
    assert "addictive" in words.PLAYMAKER_NOTICE
    assert re.search(r"Not betting advice", DOCS)
    readme = ROOT / "sonar" / "playmaker" / "README.md"
    if readme.exists():                      # nested repo: absent in a bare clone
        assert "not betting advice" in readme.read_text().lower()


def test_no_copy_promises_safety_or_profit_in_the_new_notices():
    for text in (words.PLAYMAKER_NOTICE, words.AI_TAG, words.DIRECTION_NOTE, words.STAKE_TIP,
                 words.HOURLY_MODEL_NOTE):
        assert not re.search(r"\b(guarantee|risk[- ]free|safe|will profit)\b", text, re.I)


def test_build_removes_virtual_keyboard_and_ships_licences():
    assert "--exclude-module PySide6.QtVirtualKeyboard" in BUILD
    assert "virtualkeyboard" in BUILD.lower()
    assert 'cp packaging/licenses/* "$LIC/"' in BUILD
    # the strip and the copy must happen before the re-seal, or the signature breaks
    assert BUILD.index("Resources/licenses") < BUILD.index("codesign --force")
    assert BUILD.index("-iname 'QtVirtualKeyboard*'") < BUILD.index("codesign --force")


def test_licence_pack_exists_and_names_qt_lgpl():
    lic = ROOT / "packaging" / "licenses"
    for name in ("LGPL-3.0.txt", "GPL-3.0.txt", "THIRD_PARTY_NOTICES.md"):
        assert (lic / name).is_file(), name
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in (lic / "LGPL-3.0.txt").read_text()
    notes = (lic / "THIRD_PARTY_NOTICES.md").read_text()
    assert "LGPL-3.0" in notes and "code.qt.io" in notes and "Virtual Keyboard is not included" in notes


def test_selftest_checks_the_bundle():
    main = (ROOT / "main.py").read_text()
    assert "LGPL-3.0.txt" in main and "virtualkeyboard" in main


def test_support_and_security_files():
    support = (ROOT / "SUPPORT.md").read_text()
    security = (ROOT / "SECURITY.md").read_text()
    assert "SECURITY.md" in support and "7 days" in support
    assert "security/advisories/new" in security and "within 7 days" in security
