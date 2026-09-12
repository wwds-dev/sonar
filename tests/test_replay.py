"""Replay: grading the user instead of the model.

The load-bearing tests are the lookahead ones. A discretionary replay that leaks
the future does not crash — it flatters, and it feels like evidence while being
worth nothing. Everything else here is arithmetic; that part is the design.
"""

import pytest

from sonar import replay
from sonar.backtest import Bars
from sonar.replay import LONG, SHORT, SKIP, Session


def _bars(n=400, start=100.0, drift=0.0, seed=3):
    import random
    rng = random.Random(seed)
    close, high, low, t = [], [], [], []
    p = start
    for i in range(n):
        p *= 1 + drift + rng.gauss(0, 0.01)
        close.append(p)
        high.append(p * 1.01)
        low.append(p * 0.99)
        t.append(1_600_000_000 + i * 86400)
    return Bars(symbol="TEST", time=t, close=close, high=high, low=low)


# --- the lookahead guarantee ---------------------------------------------- #
def test_the_setup_does_not_contain_the_future():
    """Not 'does not use' — does not *contain*. A UI cannot render what it was
    never handed, and that is the only version of this guarantee that holds."""
    b = _bars()
    s = Session(b, horizon_days=5, step=3, start=100)
    setup = s.current()
    assert len(setup.closes) == setup.index + 1
    assert setup.closes[-1] == b.close[setup.index]
    assert all(c in b.close[:setup.index + 1] for c in setup.closes)


def test_the_spark_stops_at_the_cursor():
    s = Session(_bars(), horizon_days=5, start=120)
    setup = s.current()
    assert setup.as_dict()["spark"][-1] == pytest.approx(round(setup.price, 4))


def test_the_closes_are_a_copy_not_a_live_slice():
    """Handing out the underlying list would let a caller mutate the series."""
    s = Session(_bars(), horizon_days=5, start=100)
    setup = s.current()
    setup.closes.append(9999.0)
    assert s.bars.close[-1] != 9999.0


def test_the_cursor_only_moves_forward():
    s = Session(_bars(), horizon_days=5, step=3, start=100)
    first = s.current().index
    s.decide(SKIP)
    assert s.current().index > first


def test_a_decision_cannot_be_retaken():
    """Going back is lookahead wearing a different hat: the outcome is known."""
    s = Session(_bars(), horizon_days=5, step=3, start=100)
    i = s.current().index
    s.decide(LONG)
    assert s.current().index != i
    assert not hasattr(s, "rewind") and not hasattr(s, "back")


# --- decisions and money --------------------------------------------------- #
def test_a_skip_costs_and_earns_nothing():
    s = Session(_bars(), horizon_days=5, start=100, stake=100.0)
    d = s.decide(SKIP)
    assert d.choice == SKIP and d.pnl == 0.0 and d.outcome is None


def test_the_model_is_graded_on_skipped_setups_too():
    """Otherwise skipping every hard one would read as skill."""
    s = Session(_bars(), horizon_days=5, start=100)
    d = s.decide(SKIP)
    assert d.model_outcome is not None


def test_a_loss_costs_exactly_the_stake():
    s = Session(_bars(), horizon_days=5, start=100, stake=250.0)
    assert s._pnl("STOP", 1.5) == -250.0


def test_a_win_pays_the_reward_to_risk_multiple():
    s = Session(_bars(), horizon_days=5, start=100, stake=250.0)
    assert s._pnl("TARGET", 1.5) == 375.0


def test_an_unresolved_setup_pays_nothing():
    s = Session(_bars(), horizon_days=5, start=100, stake=250.0)
    assert s._pnl("TIMEOUT", 1.5) == 0.0
    assert s._pnl(None, 1.5) == 0.0


def test_risk_sizing_makes_instruments_comparable():
    """A volatile coin and a quiet pair must cost the same to be wrong about,
    or P&L measures volatility rather than judgement."""
    quiet = Session(_bars(seed=1), horizon_days=5, start=100, stake=100.0)
    wild = Session(_bars(seed=2), horizon_days=5, start=100, stake=100.0)
    assert quiet._pnl("STOP", 1.5) == wild._pnl("STOP", 1.5)


def test_an_invalid_choice_is_refused():
    s = Session(_bars(), horizon_days=5, start=100)
    with pytest.raises(ValueError, match="LONG, SHORT or SKIP"):
        s.decide("MAYBE")


# --- the scorecard --------------------------------------------------------- #
def test_a_short_session_refuses_to_draw_a_conclusion():
    s = Session(_bars(), horizon_days=5, step=5, start=100)
    for _ in range(5):
        s.decide(LONG)
    card = s.scorecard()
    assert "too few" in card["verdict"]


def test_the_scorecard_carries_an_error_bar():
    s = Session(_bars(), horizon_days=5, step=2, start=60)
    for _ in range(40):
        if s.current() is None:
            break
        s.decide(LONG)
    card = s.scorecard()
    if card["n_resolved"] >= 20:
        assert card["your_std_error"] is not None
        # Whichever way the result went, the bar is stated. A verdict without
        # its uncertainty is the mistake this app exists not to make.
        assert "±" in card["verdict"], card["verdict"]


def test_skips_are_counted_separately_from_calls():
    s = Session(_bars(), horizon_days=5, step=3, start=100)
    s.decide(LONG); s.decide(SKIP); s.decide(SHORT)
    card = s.scorecard()
    assert card["n_setups"] == 3 and card["n_taken"] == 2 and card["n_skipped"] == 1


def test_the_baseline_follows_the_reward_to_risk_setting():
    """P(profit) = 1/(1+R:R). If the scorecard compared against a fixed 40%
    while the barriers moved, the verdict would be measured off the wrong line."""
    s = Session(_bars(), horizon_days=5, start=100, k_target=3.0, k_stop=1.0)
    assert s.scorecard()["predicted"] == pytest.approx(0.25)


def test_agreement_with_the_model_is_tracked():
    s = Session(_bars(), horizon_days=5, step=3, start=100)
    d = s.decide(s.current().model_direction)
    assert s.scorecard()["agreed_with_model"] == 1
    assert d.choice == d.model_direction


def test_a_session_that_runs_out_returns_nothing_rather_than_raising():
    b = _bars(n=60)
    s = Session(b, horizon_days=5, step=3, start=59)
    assert s.current() is None
    assert s.decide(LONG) is None
