"""The probability model — the number the Terminal tab is built around.

This module had **no tests at all** until now, which is how a ten-point
disagreement between two implementations of P(up) sat on the main tab
unnoticed: the signal read 50.0% and the caption under the lattice directly
below it read 60.5%, every hour, at the top of the hour.

`prob_up` is a closed form and `lattice_distribution` is a binomial
approximation of the same quantity. Testing each against fixed values is worth
something; testing them against *each other* is what found the bug, and is the
last test here.
"""

import math

import pytest

from sonar import model


# --------------------------------------------------------------------------- #
# The normal CDF, which is hand-rolled
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("x, expected", [
    (0.0, 0.5),
    (1.0, 0.8413447460685429),
    (-1.0, 0.15865525393145707),
    (1.96, 0.9750021048517795),
    (2.0, 0.9772498680518208),
    (-3.0, 0.0013498980316300933),
])
def test_phi_matches_known_normal_cdf_values(x, expected):
    """A wrong constant in here would bias every probability in the app by a
    consistent amount that still looked entirely plausible."""
    assert model._phi(x) == pytest.approx(expected, abs=1e-12)


def test_phi_is_symmetric():
    for x in (0.25, 1.0, 2.5, 4.0):
        assert model._phi(x) + model._phi(-x) == pytest.approx(1.0, abs=1e-12)


def test_phi_is_monotonic():
    values = [model._phi(x / 4) for x in range(-20, 21)]
    assert values == sorted(values)


# --------------------------------------------------------------------------- #
# Volatility
# --------------------------------------------------------------------------- #
def test_sigma_is_the_sample_standard_deviation():
    import statistics
    returns = [0.01, -0.01, 0.02, -0.02, 0.0]
    assert model.hourly_sigma(returns) == pytest.approx(statistics.stdev(returns))


def test_too_few_samples_fall_back_to_the_default():
    """Four hours of history is not a volatility estimate."""
    assert model.hourly_sigma([0.01, -0.01, 0.02, -0.02]) == 0.0045
    assert model.hourly_sigma([]) == 0.0045


def test_five_samples_is_enough_to_measure():
    assert model.hourly_sigma([0.01, -0.01, 0.02, -0.02, 0.0]) != 0.0045


def test_a_flat_series_cannot_return_zero_volatility():
    """Zero sigma divides by zero one call later."""
    assert model.hourly_sigma([0.0] * 10) > 0.0


def test_the_default_is_a_plausible_hourly_btc_number():
    assert 0.001 < model.hourly_sigma([]) < 0.02


# --------------------------------------------------------------------------- #
# P(up)
# --------------------------------------------------------------------------- #
def test_at_the_open_it_is_exactly_a_coin_flip():
    """The docstring's own claim: no information, no edge."""
    for sigma in (0.001, 0.0045, 0.05):
        for tau in (1.0, 0.5, 0.01):
            assert model.prob_up(100.0, 100.0, sigma, tau) == pytest.approx(0.5)


def test_above_the_open_is_favoured_and_below_is_not():
    assert model.prob_up(101.0, 100.0, 0.0045, 1.0) > 0.5
    assert model.prob_up(99.0, 100.0, 0.0045, 1.0) < 0.5


def test_it_is_symmetric_about_the_open():
    """A move up by a factor k and down by the same factor must mirror."""
    for k in (1.001, 1.01, 1.05):
        up = model.prob_up(100.0 * k, 100.0, 0.0045, 0.5)
        down = model.prob_up(100.0 / k, 100.0, 0.0045, 0.5)
        assert up + down == pytest.approx(1.0, abs=1e-12)


def test_it_rises_monotonically_with_price():
    values = [model.prob_up(99.0 + i * 0.1, 100.0, 0.0045, 1.0) for i in range(21)]
    assert values == sorted(values)


def test_running_out_of_time_collapses_it_toward_certainty():
    """As tau -> 0 only the current side of the open matters."""
    above = [model.prob_up(100.1, 100.0, 0.0045, tau) for tau in (1.0, 0.1, 0.01)]
    assert above == sorted(above)
    assert model.prob_up(100.1, 100.0, 0.0045, 1e-6) == pytest.approx(1.0, abs=1e-6)
    assert model.prob_up(99.9, 100.0, 0.0045, 1e-6) == pytest.approx(0.0, abs=1e-6)


def test_more_volatility_means_less_certainty():
    """The same displacement is weaker evidence in a noisier market."""
    calm = model.prob_up(101.0, 100.0, 0.002, 1.0)
    wild = model.prob_up(101.0, 100.0, 0.05, 1.0)
    assert 0.5 < wild < calm


@pytest.mark.parametrize("price, open_", [(0.0, 100.0), (100.0, 0.0), (-1.0, 100.0)])
def test_impossible_prices_return_no_opinion_rather_than_raising(price, open_):
    """A dead feed sends a zero. It must not take the tab down with it."""
    assert model.prob_up(price, open_, 0.0045, 1.0) == 0.5


def test_zero_volatility_does_not_divide_by_zero():
    assert 0.0 <= model.prob_up(101.0, 100.0, 0.0, 1.0) <= 1.0


def test_zero_time_does_not_divide_by_zero():
    assert 0.0 <= model.prob_up(101.0, 100.0, 0.0045, 0.0) <= 1.0


# --------------------------------------------------------------------------- #
# The signal
# --------------------------------------------------------------------------- #
def test_the_signal_carries_the_model_probability_unchanged():
    sig = model.evaluate(101.0, 100.0, 0.0045, 0.5, market_up=0.7)
    assert sig.model_up == model.prob_up(101.0, 100.0, 0.0045, 0.5)


def test_edge_is_the_model_minus_the_market():
    sig = model.evaluate(101.0, 100.0, 0.0045, 0.5, market_up=0.7)
    assert sig.edge == pytest.approx(sig.model_up - 0.7)


def test_a_cheap_up_is_an_up_and_a_dear_one_is_a_down():
    """Priced against a model reading of ~0.59, not an extreme one — at a 1%
    move the model is already at 99.9% and nothing the market quotes is dear."""
    fair = model.prob_up(100.1, 100.0, 0.0045, 1.0)
    assert 0.5 < fair < 0.7, "the fixture drifted; pick a less extreme price"
    assert model.evaluate(100.1, 100.0, 0.0045, 1.0, market_up=0.30).side == "UP"
    assert model.evaluate(100.1, 100.0, 0.0045, 1.0, market_up=0.90).side == "DOWN"


def test_agreeing_exactly_with_the_market_reads_as_up():
    """A tie-break, and worth pinning so it cannot drift silently."""
    sig = model.evaluate(100.0, 100.0, 0.0045, 1.0, market_up=0.5)
    assert sig.edge == 0.0
    assert sig.side == "UP"


def test_abs_edge_ignores_direction():
    cheap = model.evaluate(100.1, 100.0, 0.0045, 1.0, market_up=0.30)
    dear = model.evaluate(100.1, 100.0, 0.0045, 1.0, market_up=0.90)
    assert cheap.edge > 0 > dear.edge
    assert cheap.abs_edge > 0 and dear.abs_edge > 0


# --------------------------------------------------------------------------- #
# The lattice
# --------------------------------------------------------------------------- #
def test_the_lattice_is_a_distribution():
    grid = model.lattice_distribution(100.0, 100.0, 0.0045, 1.0)
    assert sum(b["prob"] for b in grid["bins"]) == pytest.approx(1.0)
    assert len(grid["bins"]) == grid["rows"] + 1


def test_the_lattice_is_centred_on_the_current_price():
    grid = model.lattice_distribution(100.0, 100.0, 0.0045, 1.0)
    middle = grid["bins"][len(grid["bins"]) // 2]
    assert middle["price"] == pytest.approx(100.0)


def test_the_lattice_widens_with_volatility():
    calm = model.lattice_distribution(100.0, 100.0, 0.002, 1.0)["bins"]
    wild = model.lattice_distribution(100.0, 100.0, 0.05, 1.0)["bins"]
    assert wild[-1]["price"] - wild[0]["price"] > calm[-1]["price"] - calm[0]["price"]


def test_the_lattice_narrows_as_the_hour_runs_out():
    early = model.lattice_distribution(100.0, 100.0, 0.0045, 1.0)["bins"]
    late = model.lattice_distribution(100.0, 100.0, 0.0045, 0.05)["bins"]
    assert late[-1]["price"] - late[0]["price"] < early[-1]["price"] - early[0]["price"]


def test_a_bin_sitting_exactly_on_the_open_is_a_tie_not_a_win():
    """The bug this file was written for.

    `rows` is even, so there is always an exact-middle bin, and at the top of
    the hour — price == open, where every hour starts — it holds 21% of the
    distribution. Counting all of it as "up" put the caption under the Terminal
    tab's lattice at 60.5% while the signal above it read 50.0%.
    """
    grid = model.lattice_distribution(100.0, 100.0, 0.0045, 1.0)
    ties = [b for b in grid["bins"] if b["at_barrier"]]
    assert len(ties) == 1, "an even row count always puts one bin on the barrier"
    assert ties[0]["prob"] > 0.2, "and it is not a rounding-sized share"
    assert grid["p_up"] == pytest.approx(0.5), "at the money, it is a coin flip"


@pytest.mark.parametrize("price", [100.0, 100.5, 101.0, 99.5, 99.0, 105.0, 95.0])
@pytest.mark.parametrize("tau", [1.0, 0.5, 0.1])
def test_the_two_implementations_of_p_up_agree(price, tau):
    """The closed form and the binomial approximation must not disagree by more
    than the lattice's own resolution. This is the test that found the bug —
    each implementation looked fine on its own."""
    closed = model.prob_up(price, 100.0, 0.0045, tau)
    lattice = model.lattice_distribution(price, 100.0, 0.0045, tau)["p_up"]
    assert lattice == pytest.approx(closed, abs=0.05)


def test_the_lattice_reports_the_barrier_it_was_given():
    grid = model.lattice_distribution(100.0, 99.0, 0.0045, 1.0)
    assert grid["open"] == 99.0
