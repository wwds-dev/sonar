"""What a probability is allowed to do.

The bug this module was written against: a percentage a language model wrote in
prose was fed to Kelly and turned into a stake. These tests are the guard rail —
if a narrative estimate ever sizes a bet again, they fail.
"""

import pytest

from sonar import playmaker
from sonar.playmaker import devig as d
from sonar.playmaker import staking as s


# --------------------------------------------------------------------------- #
# The Estimate contract
# --------------------------------------------------------------------------- #
def test_an_estimate_carries_its_own_uncertainty():
    est = s.Estimate(0.55, 0.50, 0.60, "market")
    assert est.width == pytest.approx(0.10)


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_probabilities_outside_zero_to_one_are_refused(bad):
    with pytest.raises(ValueError, match="between 0 and 1"):
        s.Estimate(bad, 0.0, 1.0, "market")


def test_the_point_estimate_must_lie_inside_its_own_interval():
    with pytest.raises(ValueError, match="inside"):
        s.Estimate(0.70, 0.40, 0.60, "market")


# --------------------------------------------------------------------------- #
# The central rule
# --------------------------------------------------------------------------- #
def test_a_narrative_read_cannot_size_a_bet():
    """The whole reason this module exists."""
    est = s.from_narrative(0.62, "high")
    assert est is not None
    assert est.source == s.NARRATIVE
    assert not est.can_size
    assert s.kelly(est, -110) == 0.0


def test_a_confident_sounding_narrative_still_cannot_size_a_bet():
    for confidence in ("high", "medium", "low", "", "certain"):
        assert s.kelly(s.from_narrative(0.95, confidence), 100) == 0.0


def test_a_missing_narrative_probability_is_not_invented():
    assert s.from_narrative(None) is None


def test_market_and_consensus_estimates_may_size():
    assert s.from_market(-110, -110).can_size
    quotes = [d.Quote(f"b{i}", (-150, 130)) for i in range(4)]
    assert s.from_consensus(d.consensus(quotes), 0).can_size


def test_the_narrative_interval_is_deliberately_wide():
    """A stated confidence is not a measurement; the interval says so."""
    assert s.from_narrative(0.5, "high").width > 0.2


# --------------------------------------------------------------------------- #
# Where the numbers come from
# --------------------------------------------------------------------------- #
def test_a_market_estimate_is_the_devigged_price():
    est = s.from_market(-110, -110)
    assert est.probability == pytest.approx(0.5, abs=1e-9)
    assert est.source == "market"


def test_a_market_estimate_brackets_the_methods_that_disagree():
    est = s.from_market(-2000, 1100)
    assert est.low <= est.probability <= est.high
    assert est.width > 0.0


def test_one_price_alone_cannot_be_devigged():
    """-110 on its own is equally consistent with a juiced coin flip and with
    a genuine 52.4% favourite quoted at no margin. The signature says so."""
    with pytest.raises(TypeError):
        s.from_market(-110)


def test_the_same_price_means_different_things_in_different_markets():
    juiced = s.from_market(-110, -110).probability      # 4.8% margin
    flat = s.from_market(-110, 110).probability         # no margin at all
    assert juiced == pytest.approx(0.50, abs=1e-9)
    assert flat == pytest.approx(0.5238, abs=1e-4)


def test_a_consensus_estimate_narrows_as_books_are_added():
    tight = [d.Quote("a", (-150, 130)), d.Quote("b", (-152, 131)),
             d.Quote("c", (-148, 129))]
    loose = [d.Quote("a", (-150, 130)), d.Quote("b", (-200, 170)),
             d.Quote("c", (-110, -110))]
    assert (s.from_consensus(d.consensus(tight), 0).width
            < s.from_consensus(d.consensus(loose), 0).width)


def test_one_book_is_a_consensus_of_one_and_says_so():
    est = s.from_consensus(d.consensus([d.Quote("solo", (-110, -110))]), 0)
    assert est.width == 0.0
    assert "no spread" in est.basis


# --------------------------------------------------------------------------- #
# Sizing on the pessimistic end
# --------------------------------------------------------------------------- #
def test_the_stake_is_sized_at_the_low_end_not_the_point_estimate():
    est = s.Estimate(0.60, 0.55, 0.65, "model")
    assert s.kelly(est, 100, cap=1.0) == pytest.approx(
        playmaker.kelly_fraction(0.55, 100))
    assert s.kelly(est, 100, cap=1.0) < playmaker.kelly_fraction(0.60, 100)


def test_a_wider_interval_stakes_less_on_the_same_point_estimate():
    tight = s.Estimate(0.60, 0.58, 0.62, "model")
    wide = s.Estimate(0.60, 0.52, 0.68, "model")
    assert s.kelly(wide, 100, cap=1.0) < s.kelly(tight, 100, cap=1.0)


def test_an_interval_spanning_break_even_stakes_nothing():
    """A tempting point estimate with honest uncertainty is not a bet."""
    est = s.Estimate(0.55, 0.45, 0.65, "model")
    assert s.kelly(est, 100) == 0.0


def test_the_cap_is_the_last_word():
    est = s.Estimate(0.99, 0.98, 1.0, "model")
    assert s.kelly(est, 100) == pytest.approx(s.MAX_FRACTION)


def test_no_edge_at_the_low_end_means_no_stake():
    est = s.Estimate(0.52, 0.50, 0.54, "model")
    assert s.kelly(est, -110) == 0.0


# --------------------------------------------------------------------------- #
# Edge means something different from expected value
# --------------------------------------------------------------------------- #
def test_the_old_edge_was_expected_value_wearing_a_hat():
    """`edge_versus_market` compares against the vig-inclusive price, which
    makes it exactly EV rescaled — two views of one number, not two numbers."""
    for odds in (-110, -300, 250, 1100):
        for p in (0.3, 0.55, 0.8):
            rescaled = playmaker.expected_value(p, odds) / playmaker.american_to_decimal(odds)
            assert playmaker.edge_versus_market(p, odds) == pytest.approx(rescaled, abs=1e-12)


def test_edge_against_the_fair_price_is_independent_of_expected_value():
    est = s.Estimate(0.55, 0.55, 0.55, "model")
    fair = s.from_market(-110, -110).probability   # 0.50
    assert s.edge_versus_fair(est, fair) == pytest.approx(0.05, abs=1e-9)
    assert s.edge_versus_fair(est, fair) != pytest.approx(
        playmaker.edge_versus_market(0.55, -110), abs=1e-3)


def test_agreeing_with_the_fair_price_is_no_edge_even_when_ev_is_negative():
    fair = s.from_market(-110, -110).probability
    est = s.Estimate(fair, fair, fair, "model")
    assert s.edge_versus_fair(est, fair) == pytest.approx(0.0, abs=1e-12)
    assert playmaker.expected_value(fair, -110) < 0     # the margin still costs


# --------------------------------------------------------------------------- #
# The assessment the UI reads
# --------------------------------------------------------------------------- #
def test_an_assessment_explains_why_it_declined_to_size():
    a = s.assess(s.from_narrative(0.62, "high"), -110, fair=0.5)
    assert a.fraction == 0.0
    assert "narrative" in a.note


def test_an_assessment_names_the_low_end_it_sized_on():
    a = s.assess(s.Estimate(0.70, 0.65, 0.75, "model"), 100, fair=0.5)
    assert a.fraction > 0.0
    assert "65.0%" in a.note


def test_an_assessment_says_when_uncertainty_is_what_blocked_the_bet():
    a = s.assess(s.Estimate(0.55, 0.45, 0.65, "model"), 100, fair=0.5)
    assert a.fraction == 0.0
    assert "no edge at this price" in a.note
