"""The in-app documentation has to stay true to the app.

Docs rot silently. A tab gets renamed, a section gets renumbered, a cross-
reference points at the wrong thing, and nothing fails — the page still renders,
it just lies. Renumbering eleven sections to make room for a twelfth is exactly
the operation that breaks a `§6` buried three paragraphs down, so it is worth a
test rather than a careful read.

The learning-centre checks exist because the documentation has a specific job:
someone with no finance background should be able to read it. A glossary that
quietly loses half its entries still looks like a glossary.
"""

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "static" / "docs.html"
HTML = DOCS.read_text()

SECTIONS = re.findall(r'<h2 id="([a-z-]+)"><span class="n">(\d+)</span>([^<]*)', HTML)
TOC = re.findall(r'<a href="#([a-z-]+)">(\d+) · ([^<]*)</a>', HTML)


def test_the_page_exists_and_is_not_a_stub():
    assert len(HTML) > 10_000


def test_every_section_is_in_the_table_of_contents():
    assert [(anchor, number) for anchor, number, _ in SECTIONS] == \
           [(anchor, number) for anchor, number, _ in TOC]


def test_sections_are_numbered_from_one_without_gaps():
    numbers = [int(n) for _, n, _ in SECTIONS]
    assert numbers == list(range(1, len(numbers) + 1))


def test_no_link_points_at_a_section_that_does_not_exist():
    anchors = {anchor for anchor, _, _ in SECTIONS}
    broken = [a for a in re.findall(r'href="#([a-z-]+)"', HTML) if a not in anchors]
    assert not broken, f"dead links: {broken}"


def test_every_numbered_cross_reference_resolves():
    """The check that renumbering breaks. A stale section reference reads as
    authoritative and sends the reader somewhere unrelated."""
    numbers = {n for _, n, _ in SECTIONS}
    dangling = [m for m in re.findall(r'§(\d+)', HTML) if m not in numbers]
    assert not dangling, f"references to missing sections: {dangling}"


def test_no_section_anchor_is_used_twice():
    anchors = [anchor for anchor, _, _ in SECTIONS]
    assert len(anchors) == len(set(anchors))


# --------------------------------------------------------------------------- #
# The docs have to describe the app that actually exists
# --------------------------------------------------------------------------- #
def test_every_tab_the_app_builds_is_documented():
    app = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text()
    tabs = re.findall(r'addTab\([^,]+,\s*"([^"]+)"\)', app)
    assert tabs, "no tabs found — the pattern in app.py changed"
    for tab in tabs:
        assert f"<td>{tab}</td>" in HTML, f"{tab} has no row in the tabs table"


def test_every_registered_sport_is_named():
    from sonar import playmaker
    for sport in playmaker.list_sports():
        assert sport.name in HTML, f"{sport.name} is not mentioned in the docs"


# --------------------------------------------------------------------------- #
# The learning centre
# --------------------------------------------------------------------------- #
def test_the_learning_centre_comes_first():
    """Someone who needs the primer should not have to find it."""
    assert SECTIONS[0][0] == "learn"


@pytest.mark.parametrize("term", [
    # markets
    "Position", "Long / short", "Volatility", "Momentum", "Stop / target",
    "Drawdown", "Paper trading", "Basis point",
    # probability
    "Base rate", "Expected value", "Calibration", "Out-of-sample", "Brier score",
    # betting
    "Odds", "Implied probability", "The vig", "Devigging", "Kelly",
    "Closing line",
    # macro — the tab the app is least approachable in
    "Yield curve", "Fed funds", "VIX", "CPI", "Real yield",
])
def test_the_glossary_defines(term):
    assert f"<td>{term}</td>" in HTML, f"{term!r} lost its glossary entry"


def test_the_primer_says_what_the_confidence_score_is_not():
    """The single most misreadable number in the app."""
    learn = HTML[HTML.index('id="learn"'):HTML.index('id="tabs"')]
    assert "confidence" in learn.lower()
    assert "not" in learn.lower() and "go up" in learn.lower()


def test_the_primer_says_there_is_no_real_money():
    learn = HTML[HTML.index('id="learn"'):HTML.index('id="tabs"')]
    assert "pretend money" in learn or "no real account" in learn


def test_the_playmaker_section_carries_the_capacity_caveat():
    """Quoting Kaunitz's profit without Kaunitz's account limits would be
    selling the reader something."""
    section = HTML[HTML.index('id="playmaker"'):]
    assert "limited the accounts" in section
