"""Component attribution: which parts of the score earn their weight.

A hit rate says whether the model as a whole worked. It cannot say *which piece*
of it did, which is the only version of the question you can act on. These tests
pin down the verdicts, and especially the one that is easy to get backwards.
"""

import pytest

from sonar import backtest


def _trials(n, mom_wins=False, vol_wins=False, seed=1):
    """Synthetic setups where a chosen component genuinely predicts, or doesn't."""
    import random
    rng = random.Random(seed)
    out = []
    for i in range(n):
        m, v = rng.random(), rng.random()
        p = 0.4
        if mom_wins:
            p = 0.15 + 0.5 * m
        if vol_wins:
            p = 0.85 - 0.5 * v          # high vol loses — the inverted case
        out.append({"outcome": "TARGET" if rng.random() < p else "STOP",
                    "predicted": 0.4, "bars_held": 5, "momentum": m, "vol": v,
                    "c_momentum": m, "c_volatility": v, "c_news": None})
    return out


def test_too_few_setups_refuses_to_attribute():
    out = backtest.attribute(_trials(20))
    assert out["components"] == []
    assert "too few" in out["note"]


def test_a_component_that_predicts_is_kept():
    out = backtest.attribute(_trials(1500, mom_wins=True))
    mom = next(c for c in out["components"] if c["component"] == "momentum")
    assert mom["verdict"] == "KEEP", mom
    assert mom["ic"] > 0


def test_a_component_scored_backwards_is_called_inverted_not_kept():
    """The verdict that matters. A significant *negative* IC on a component
    carried with a positive weight is worse than dead weight — it pushes the
    wrong instruments up the board. Calling that KEEP because the p-value
    passed would be exactly the wrong conclusion."""
    out = backtest.attribute(_trials(1500, vol_wins=True))
    vol = next(c for c in out["components"] if c["component"] == "volatility")
    assert vol["verdict"] == "INVERTED", vol
    assert vol["ic"] < 0
    assert "wrong instruments" in vol["why"]


def test_pure_noise_is_not_called_a_keeper():
    out = backtest.attribute(_trials(1500, seed=7))
    for c in out["components"]:
        if c.get("ic") is not None:
            assert c["verdict"] != "KEEP", c


def test_an_unmeasured_component_is_not_a_passing_one():
    """news has no historical series here; silence must not read as approval."""
    out = backtest.attribute(_trials(1500))
    news = next(c for c in out["components"] if c["component"] == "news")
    assert news["verdict"] == "not measured"


def test_catalyst_is_reported_as_untested(): 
    out = backtest.attribute(_trials(1500))
    assert "not measured" in out["catalyst"]


def test_leave_one_out_is_reported(): 
    out = backtest.attribute(_trials(1500, mom_wins=True))
    mom = next(c for c in out["components"] if c["component"] == "momentum")
    assert mom["blend_ic_without"] is not None
    assert mom["loo_cost"] is not None


def test_quintile_spread_needs_a_sample():
    assert backtest._quintile_spread(_trials(20), "c_momentum")["spread"] is None


def test_quintile_spread_finds_a_real_one():
    sp = backtest._quintile_spread(_trials(1500, mom_wins=True), "c_momentum")
    assert sp["spread"] > 0.2, sp
    assert sp["top"] > sp["bottom"]


def test_fdr_is_applied_across_components_not_per_component():
    """Testing four things and reporting the best is how noise gets published."""
    import inspect
    assert "benjamini_hochberg" in inspect.getsource(backtest.attribute)
