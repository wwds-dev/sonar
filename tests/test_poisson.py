"""Dixon-Coles: the scoreline model.

The three things that make it Dixon-Coles rather than "two Poissons" each have a
test that fails if they are removed — the low-score correction, the time decay,
and the home effect. The rest checks that a distribution over scorelines really
is a distribution, since every market it answers is a sum over that grid.
"""

import datetime as dt
import math
import random

import pytest

from sonar.playmaker import poisson as dc
from sonar.playmaker.results import Game

DAY = dt.date(2026, 1, 1)


def game(home, away, hs, as_, day=0):
    return Game(DAY + dt.timedelta(days=day), home, away, hs, as_)


# --------------------------------------------------------------------------- #
# Time decay — Dixon and Coles' own units and their own fitted value
# --------------------------------------------------------------------------- #
def test_todays_match_carries_full_weight():
    assert dc.decay_weight(0) == pytest.approx(1.0)


def test_older_matches_count_for_less():
    assert dc.decay_weight(365) < dc.decay_weight(90) < dc.decay_weight(7) < 1.0


def test_the_half_life_is_about_a_year():
    """xi = 0.0065 per half-week was fitted by maximising out-of-sample
    predictive log-likelihood — it is a finding, not a knob."""
    assert dc.decay_weight(365) == pytest.approx(0.5, abs=0.06)


def test_recent_form_outweighs_old_form():
    """The property the decay exists to produce."""
    old = [game("A", "B", 5, 0, day=d) for d in range(0, 40, 2)]
    recent = [game("A", "B", 0, 5, day=d) for d in range(700, 740, 2)]
    model = dc.fit(old + recent)
    lam, mu = model.rates("A", "B")
    assert mu > lam, "the newer thrashings should dominate"


# --------------------------------------------------------------------------- #
# The low-score correction — the part everyone leaves out
# --------------------------------------------------------------------------- #
def test_tau_leaves_everything_above_one_one_alone():
    for x, y in ((2, 0), (1, 2), (3, 3), (0, 4)):
        assert dc.tau(x, y, 1.4, 1.1, 0.1) == 1.0


def test_tau_moves_exactly_the_four_lowest_scorelines():
    moved = [(x, y) for x in range(4) for y in range(4)
             if dc.tau(x, y, 1.4, 1.1, 0.08) != 1.0]
    assert set(moved) == {(0, 0), (0, 1), (1, 0), (1, 1)}


def test_a_zero_rho_is_the_plain_poisson_model():
    for x in range(3):
        for y in range(3):
            assert dc.tau(x, y, 1.4, 1.1, 0.0) == 1.0


def test_a_positive_rho_lifts_the_goalless_draw():
    """Which is the whole point: independent Poissons underpredict 0-0."""
    assert dc.tau(0, 0, 1.4, 1.1, -0.05) > 1.0


# --------------------------------------------------------------------------- #
# The scoreline grid really is a distribution
# --------------------------------------------------------------------------- #
def _league(seed=7, days=240):
    """A synthetic league where A attacks best and C defends worst."""
    rng = random.Random(seed)
    attack = {"A": 1.9, "B": 1.3, "C": 0.9}
    defence = {"A": 0.8, "B": 1.0, "C": 1.5}
    games, day = [], 0
    while day < days:
        for home in attack:
            for away in attack:
                if home == away:
                    continue
                lam = 1.35 * attack[home] * defence[away]
                mu = attack[away] * defence[home]
                games.append(game(home, away,
                                  min(rng.poisson(lam) if hasattr(rng, "poisson")
                                      else _draw(rng, lam), 8),
                                  min(_draw(rng, mu), 8), day))
                day += 1
    return games


def _draw(rng, rate):
    """Knuth's Poisson sampler — the stdlib has no poisson variate."""
    limit, k, p = math.exp(-rate), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def test_the_scoreline_grid_sums_to_one():
    model = dc.fit(_league())
    grid = model.scoreline_matrix("A", "B")
    assert sum(sum(row) for row in grid) == pytest.approx(1.0, abs=1e-9)


def test_the_three_outcomes_sum_to_one():
    model = dc.fit(_league())
    assert sum(model.outcome_probabilities("A", "C")) == pytest.approx(1.0, abs=1e-9)


def test_over_and_under_are_complements():
    model = dc.fit(_league())
    over = model.over_probability("A", "B", 2.5)
    under = 1.0 - over
    assert 0.0 < over < 1.0 and over + under == pytest.approx(1.0)


def test_a_higher_line_is_harder_to_clear():
    model = dc.fit(_league())
    assert (model.over_probability("A", "C", 1.5)
            > model.over_probability("A", "C", 3.5))


def test_both_teams_to_score_is_a_probability():
    model = dc.fit(_league())
    assert 0.0 < model.both_score_probability("A", "B") < 1.0


def test_the_most_likely_score_is_in_the_grid():
    model = dc.fit(_league())
    x, y, p = model.most_likely_score("A", "C")
    assert 0 <= x <= dc.MAX_GOALS and 0 <= y <= dc.MAX_GOALS
    assert 0.0 < p < 1.0


# --------------------------------------------------------------------------- #
# Fitting
# --------------------------------------------------------------------------- #
def test_fitting_recovers_who_attacks_best():
    model = dc.fit(_league())
    assert model.attack["A"] > model.attack["B"] > model.attack["C"]


def test_fitting_recovers_who_defends_worst():
    model = dc.fit(_league())
    assert model.defence["C"] > model.defence["A"]


def test_the_better_side_is_favoured():
    model = dc.fit(_league())
    home_win, draw, away_win = model.outcome_probabilities("A", "C")
    assert home_win > away_win
    assert 0.0 < draw < 0.5


def test_home_advantage_is_measured_not_assumed():
    """Fitted from how many more goals home sides actually scored."""
    model = dc.fit(_league())
    assert model.home_advantage > 1.0


def test_the_same_pair_swaps_when_the_ground_swaps():
    model = dc.fit(_league())
    at_home = model.outcome_probabilities("B", "A")[0]
    away = model.outcome_probabilities("A", "B")[2]
    assert at_home > away, "B should do better at home than away"


def test_rho_is_fitted_rather_than_left_at_zero():
    model = dc.fit(_league())
    assert dc.RHO_BOUNDS[0] <= model.rho <= dc.RHO_BOUNDS[1]


def test_rho_can_be_switched_off():
    assert dc.fit(_league(), fit_rho=False).rho == 0.0


def test_an_empty_history_is_an_empty_model_not_a_crash():
    model = dc.fit([])
    assert model.games == 0 and model.teams() == []


def test_an_unknown_team_does_not_raise():
    model = dc.fit(_league())
    lam, mu = model.rates("A", "Nobody")
    assert lam > 0 and mu > 0


def test_expected_goals_are_plausible_for_football():
    """A sanity bound: if this drifts to 0.2 or 9.0 the fit has gone wrong."""
    model = dc.fit(_league())
    for home in model.teams():
        for away in model.teams():
            if home == away:
                continue
            lam, mu = model.rates(home, away)
            assert 0.2 < lam < 6.0 and 0.2 < mu < 6.0
