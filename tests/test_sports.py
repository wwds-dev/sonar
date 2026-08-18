"""Sports prop analysis — odds arithmetic and response parsing.

The arithmetic is the part that decides whether a wager looks good, so it is
asserted against hand-checkable values rather than against itself.
"""

import pytest

from sonar import sports


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_nfl_is_registered():
    assert sports.get_sport("nfl").name == "NFL"
    assert sports.list_sports()


def test_unknown_sport_is_refused():
    with pytest.raises(ValueError):
        sports.get_sport("quidditch")


# --------------------------------------------------------------------------- #
# Odds conversion
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("odds,decimal", [
    (-110, 1.9091), (-200, 1.5), (+100, 2.0), (+150, 2.5), (+250, 3.5),
])
def test_american_to_decimal(odds, decimal):
    assert sports.american_to_decimal(odds) == pytest.approx(decimal, abs=1e-4)


def test_even_money_is_a_coin_flip():
    assert sports.implied_probability(100) == pytest.approx(0.5)


def test_standard_juice_implies_more_than_half():
    """-110 needs 52.38% to break even — the 2.38% over a coin flip is the vig."""
    assert sports.implied_probability(-110) == pytest.approx(0.5238, abs=1e-4)


def test_zero_odds_is_rejected():
    with pytest.raises(ValueError):
        sports.american_to_decimal(0)


# --------------------------------------------------------------------------- #
# Vig
# --------------------------------------------------------------------------- #
def test_removing_vig_makes_two_sides_sum_to_one():
    a, b = sports.remove_vig(-110, -110)
    assert a + b == pytest.approx(1.0)
    assert a == pytest.approx(0.5)


def test_vig_removal_keeps_the_favourite_favoured():
    fav, dog = sports.remove_vig(-200, +170)
    assert fav > dog
    assert fav + dog == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Expected value — the number that decides whether to bet
# --------------------------------------------------------------------------- #
def test_break_even_probability_has_no_expected_value():
    assert sports.expected_value(sports.implied_probability(-110), -110) == pytest.approx(0.0, abs=1e-9)


def test_edge_over_the_price_is_positive_ev():
    assert sports.expected_value(0.60, -110) > 0


def test_worse_than_the_price_is_negative_ev():
    assert sports.expected_value(0.45, -110) < 0


def test_expected_value_scales_with_stake():
    single = sports.expected_value(0.60, +100, stake=1.0)
    double = sports.expected_value(0.60, +100, stake=2.0)
    assert double == pytest.approx(single * 2)


def test_certain_win_returns_the_full_profit():
    assert sports.expected_value(1.0, +150, stake=10.0) == pytest.approx(15.0)


def test_certain_loss_returns_the_stake():
    assert sports.expected_value(0.0, +150, stake=10.0) == pytest.approx(-10.0)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_probability_outside_zero_to_one_is_rejected(bad):
    with pytest.raises(ValueError):
        sports.expected_value(bad, -110)


# --------------------------------------------------------------------------- #
# Kelly
# --------------------------------------------------------------------------- #
def test_no_edge_means_no_stake():
    assert sports.kelly_fraction(sports.implied_probability(-110), -110) == pytest.approx(0.0, abs=1e-9)


def test_negative_edge_never_suggests_a_stake():
    """A losing bet must return 0, not a negative fraction to 'lay' the other side."""
    assert sports.kelly_fraction(0.30, -110) == 0.0


def test_kelly_grows_with_the_edge():
    assert sports.kelly_fraction(0.70, +100) > sports.kelly_fraction(0.55, +100)


def test_kelly_at_even_money_is_twice_the_edge():
    """The textbook case: at +100, f = 2p - 1."""
    assert sports.kelly_fraction(0.60, +100) == pytest.approx(0.20)


# --------------------------------------------------------------------------- #
# Edge vs the market
# --------------------------------------------------------------------------- #
def test_edge_is_measured_against_the_price_not_against_half():
    assert sports.edge_versus_market(0.5238, -110) == pytest.approx(0.0, abs=1e-4)
    assert sports.edge_versus_market(0.60, -110) > 0


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
def test_prompt_carries_every_supplied_value():
    prompt = sports.build_prompt(
        sports.NFL, "J. Allen", "Passing yards", "Over 252.5", "-110",
        "vs MIA, week 3, home", "last 5 games: 280, 240, 301, 255, 268",
    )
    for needle in ("NFL", "J. Allen", "Passing yards", "252.5", "-110",
                   "week 3", "301"):
        assert needle in prompt


def test_prompt_marks_missing_inputs_rather_than_inventing_them():
    prompt = sports.build_prompt(sports.NFL, "", "Spread", "", "", "", "")
    assert "(not given)" in prompt
    assert "(no supporting data supplied)" in prompt


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
SAMPLE = """PROP OVERVIEW
J. Allen, passing yards over 252.5 at -110.

OVER CASE
Averaged 288 over the last five.

UNDER CASE
Opponent allows the fewest pass yards in the league.

EDGE ASSESSMENT
Lean: OVER
Confidence: medium
Estimated win probability: 57%

MISSING DATA
none
"""


def test_sections_are_separated():
    result = sports.parse_analysis(SAMPLE)
    assert "Averaged 288" in result.sections["OVER CASE"]
    assert "fewest pass yards" in result.sections["UNDER CASE"]
    assert "OVER CASE" not in result.sections["PROP OVERVIEW"]


def test_verdict_fields_are_extracted():
    result = sports.parse_analysis(SAMPLE)
    assert result.lean == "OVER"
    assert result.confidence == "medium"
    assert result.win_probability == pytest.approx(0.57)


def test_extracted_probability_feeds_expected_value():
    """The parse is only useful if its number can drive the arithmetic."""
    result = sports.parse_analysis(SAMPLE)
    assert sports.expected_value(result.win_probability, -110) > 0


def test_markdown_headings_are_tolerated():
    result = sports.parse_analysis(SAMPLE.replace("OVER CASE", "**OVER CASE**"))
    assert "Averaged 288" in result.sections["OVER CASE"]


def test_no_edge_is_read_as_a_verdict():
    result = sports.parse_analysis("EDGE ASSESSMENT\nLean: NO EDGE\nConfidence: low\n")
    assert result.lean == "NO EDGE"


def test_unparseable_text_does_not_raise():
    result = sports.parse_analysis("the model rambled without headings")
    assert result.lean == ""
    assert result.win_probability is None
    assert result.raw
