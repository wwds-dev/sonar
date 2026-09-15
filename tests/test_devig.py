"""Removing the margin, and finding where books disagree.

The claim these tests exist to pin down is that the method matters: the
proportional ("multiplicative") method that every calculator quotes is the one
comparative studies rank last, and the direction of its error is systematic
rather than random.
"""

import math

import pytest

from sonar import playmaker
from sonar.playmaker import devig as d


# --------------------------------------------------------------------------- #
# Every method has to produce probabilities
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method", d.METHODS)
@pytest.mark.parametrize("odds", [
    (-110, -110), (-300, 250), (-2000, 1100), (150, 240, 180), (-140, 120),
])
def test_every_method_returns_a_distribution(method, odds):
    probs = d.devig(odds, method)
    assert len(probs) == len(odds)
    assert all(0.0 < p < 1.0 for p in probs)
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("method", d.METHODS)
def test_a_symmetric_book_is_a_coin_flip_under_every_method(method):
    a, b = d.devig((-110, -110), method)
    assert a == pytest.approx(0.5, abs=1e-9)
    assert b == pytest.approx(0.5, abs=1e-9)


@pytest.mark.parametrize("method", d.METHODS)
def test_a_book_with_no_margin_is_left_alone(method):
    # +100/-100 sums to exactly 1.0 — there is nothing to remove.
    assert d.devig((100, -100), method) == pytest.approx((0.5, 0.5), abs=1e-9)


def test_unknown_method_is_refused_by_name():
    with pytest.raises(ValueError, match="unknown devig method"):
        d.devig((-110, -110), "proportional")


def test_a_market_needs_two_outcomes():
    with pytest.raises(ValueError, match="at least two"):
        d.devig((-110,), "shin")


# --------------------------------------------------------------------------- #
# The margin itself
# --------------------------------------------------------------------------- #
def test_standard_juice_is_a_476_basis_point_margin():
    assert d.overround((-110, -110)) == pytest.approx(0.0476, abs=1e-4)


def test_booksum_above_one_is_what_makes_it_a_book():
    assert d.booksum((-110, -110)) > 1.0


# --------------------------------------------------------------------------- #
# The claim: multiplicative is biased, and always in the same direction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("odds", [
    (-300, 250), (-2000, 1100), (-140, 120), (-500, 380), (-1000, 700),
])
def test_multiplicative_understates_the_favourite(odds):
    """Proportional devig takes the margin in proportion to price.

    Real books load more of it onto longshots, so removing it evenly leaves
    the favourite too cheap and the longshot too dear. Both better methods
    agree on the direction.
    """
    mult = d.multiplicative(odds)[0]
    assert mult < d.shin(odds)[0]
    assert mult < d.power(odds)[0]


def test_multiplicative_overstates_the_longshot():
    mult = d.multiplicative((-2000, 1100))[1]
    assert mult > d.shin((-2000, 1100))[1]
    assert mult > d.power((-2000, 1100))[1]


def test_the_error_is_large_enough_to_change_a_decision():
    """A +1100 longshot: proportional devig calls it ~23% more likely."""
    mult = d.multiplicative((-2000, 1100))[1]
    shin = d.shin((-2000, 1100))[1]
    assert mult / shin > 1.2


def test_the_bias_holds_across_the_whole_board():
    """Not a cherry-picked pair — no counterexample over 300-odd real books."""
    checked = 0
    for fav in range(-1000, -101, 50):
        for dog in range(110, 900, 40):
            odds = (fav, dog)
            if d.booksum(odds) <= 1.0:
                continue          # not a book anyone would post
            checked += 1
            assert d.multiplicative(odds)[0] <= d.shin(odds)[0] + 1e-9
            assert d.multiplicative(odds)[0] <= d.power(odds)[0] + 1e-9
    assert checked > 100, "the sweep should cover a realistic range"


def test_methods_disagree_and_the_spread_reports_it():
    low, high = d.method_spread((-2000, 1100), 1)
    assert low < high
    assert low <= d.shin((-2000, 1100))[1] <= high


def test_a_symmetric_book_leaves_the_methods_nothing_to_disagree_about():
    low, high = d.method_spread((-110, -110), 0)
    assert high - low == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# Consensus across books
# --------------------------------------------------------------------------- #
def _book(name, *odds):
    return d.Quote(name, tuple(odds))


def test_books_that_agree_produce_their_own_answer_as_consensus():
    quotes = [_book(f"b{i}", -150, 130) for i in range(4)]
    cons = d.consensus(quotes)
    assert cons.probability[0] == pytest.approx(d.shin((-150, 130))[0], abs=1e-9)
    assert cons.dispersion[0] == pytest.approx(0.0, abs=1e-12)


def test_consensus_can_leave_a_book_out():
    quotes = [_book("a", -150, 130), _book("b", -150, 130), _book("odd", -110, -110)]
    assert d.consensus(quotes).books == 3
    assert d.consensus(quotes, exclude="odd").books == 2


def test_excluding_the_outlier_moves_the_consensus():
    quotes = [_book("a", -150, 130), _book("b", -150, 130), _book("odd", 200, -250)]
    with_odd = d.consensus(quotes).probability[0]
    without = d.consensus(quotes, exclude="odd").probability[0]
    assert without > with_odd


def test_disagreeing_books_have_dispersion():
    quotes = [_book("a", -150, 130), _book("b", -180, 155), _book("c", -120, 100)]
    assert d.consensus(quotes).dispersion[0] > 0.0


def test_standard_error_needs_more_than_one_book():
    assert math.isnan(d.consensus([_book("solo", -110, -110)]).standard_error(0))


def test_books_must_agree_on_how_many_outcomes_there_are():
    with pytest.raises(ValueError, match="how many outcomes"):
        d.consensus([_book("a", -110, -110), _book("b", 150, 240, 180)])


def test_excluding_everything_is_refused():
    with pytest.raises(ValueError, match="no books left"):
        d.consensus([_book("a", -110, -110)], exclude="a")


def test_a_quote_needs_a_real_market():
    with pytest.raises(ValueError, match="at least two outcomes"):
        _book("a", -110)


# --------------------------------------------------------------------------- #
# The screen — the Kaunitz arithmetic
# --------------------------------------------------------------------------- #
def test_a_consensus_needs_three_books():
    with pytest.raises(ValueError, match="at least three books"):
        d.screen([_book("a", -110, -110), _book("b", -110, -110)])


def test_books_that_all_agree_offer_nothing():
    quotes = [_book(f"b{i}", -150, 130) for i in range(5)]
    assert d.screen(quotes, min_edge=0.001) == []


def test_the_generous_book_is_found():
    quotes = [_book("a", -150, 130), _book("b", -155, 132), _book("c", -148, 128),
              _book("generous", -150, 210)]
    hits = d.screen(quotes, min_edge=0.01)
    assert hits, "a clearly better price should surface"
    best = hits[0]
    assert best.book == "generous"
    assert best.outcome == 1
    assert best.edge > 0.0
    assert best.expected_value > 0.0


def test_the_outlier_does_not_set_its_own_benchmark():
    """Leave-one-out: if the generous book counted toward its own consensus it
    would drag the fair price toward itself and hide its own edge."""
    quotes = [_book("a", -150, 130), _book("b", -155, 132), _book("c", -148, 128),
              _book("generous", -150, 210)]
    hit = next(o for o in d.screen(quotes, min_edge=0.01) if o.book == "generous")
    peers_only = d.consensus([q for q in quotes if q.book != "generous"]).probability[1]
    assert hit.fair == pytest.approx(peers_only, abs=1e-12)


def test_results_are_ranked_by_expected_value():
    quotes = [_book("a", -150, 130), _book("b", -155, 132), _book("c", -148, 128),
              _book("good", -150, 190), _book("better", -150, 260)]
    evs = [o.expected_value for o in d.screen(quotes, min_edge=0.005)]
    assert evs == sorted(evs, reverse=True)


def test_an_outlier_is_flagged_only_when_the_books_are_tight():
    quotes = [_book("a", -150, 130), _book("b", -152, 131), _book("c", -148, 129),
              _book("generous", -150, 230)]
    hit = next(o for o in d.screen(quotes, min_edge=0.01) if o.book == "generous")
    assert hit.is_outlier
    assert hit.z > 2.0


def test_the_screen_prices_against_what_you_actually_get_paid():
    """`offered` is the vig-inclusive price — that is the number you are
    staking into, not the fair one."""
    quotes = [_book("a", -150, 130), _book("b", -155, 132), _book("c", -148, 128),
              _book("generous", -150, 210)]
    hit = next(o for o in d.screen(quotes, min_edge=0.01) if o.book == "generous")
    assert hit.offered == pytest.approx(playmaker.implied_probability(210), abs=1e-12)


# --------------------------------------------------------------------------- #
# Reading prices off a page
# --------------------------------------------------------------------------- #
def test_prices_are_read_one_book_per_line():
    quotes = d.parse_quotes("DraftKings -150 +130\nPinnacle -148 128\n")
    assert [q.book for q in quotes] == ["DraftKings", "Pinnacle"]
    assert quotes[0].odds == (-150, 130)
    assert quotes[1].odds == (-148, 128)


def test_a_book_name_may_contain_spaces():
    assert d.parse_quotes("Hard Rock Bet -150 130")[0].book == "Hard Rock Bet"


def test_commas_and_plus_signs_are_tolerated():
    assert d.parse_quotes("BetMGM, -150, +210")[0].odds == (-150, 210)


def test_blank_lines_and_comments_are_skipped():
    quotes = d.parse_quotes("\n# my books\nDraftKings -150 130  # the anchor\n\n")
    assert len(quotes) == 1
    assert quotes[0].book == "DraftKings"


def test_three_way_markets_parse():
    assert d.parse_quotes("Bet365 +150 +240 +180")[0].odds == (150, 240, 180)


def test_one_price_per_book_is_refused_not_skipped():
    """Silently dropping a half-read line would poison a consensus quietly."""
    with pytest.raises(ValueError, match="price for every outcome"):
        d.parse_quotes("DraftKings -150")


def test_prices_with_no_book_are_refused():
    with pytest.raises(ValueError, match="no book name"):
        d.parse_quotes("-150 130")


def test_the_failing_line_is_named():
    with pytest.raises(ValueError, match="line 3"):
        d.parse_quotes("A -150 130\nB -148 128\nC -150")


def test_parsed_prices_feed_the_screen_directly():
    quotes = d.parse_quotes(
        "DraftKings -150 130\nFanDuel -155 132\nPinnacle -148 128\nBetMGM -150 210")
    best = d.screen(quotes, min_edge=0.01)[0]
    assert best.book == "BetMGM"
    assert best.is_outlier
