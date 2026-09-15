"""The sport registry.

Adding a sport needed no new arithmetic — `devig` and `staking` are pure odds
maths and know nothing about what they are pricing. So these tests check the
registry is coherent and that the screen really does work unchanged on a
three-way market, which is the claim that would quietly stop being true.
"""

import pytest

from sonar import playmaker
from sonar.playmaker import devig as d
from sonar.playmaker import staking as s

SPORTS = playmaker.list_sports()


def test_every_sport_we_claim_is_registered():
    keys = {sp.key for sp in SPORTS}
    assert keys == {"nfl", "nba", "mlb", "nhl", "epl", "ucl", "ncaab", "ufc", "atp"}


def test_nfl_is_still_first():
    """It is the sport the module was built for; the picker should open on it."""
    assert SPORTS[0].key == "nfl"


def test_unknown_sport_is_refused():
    with pytest.raises(ValueError, match="unknown sport"):
        playmaker.get_sport("cricket")


@pytest.mark.parametrize("sport", SPORTS, ids=lambda sp: sp.key)
def test_a_sport_is_completely_described(sport):
    assert sport.name and sport.context_hint and sport.period_label
    assert sport.prop_types, f"{sport.key} has no props"
    assert sport.outcomes >= 2


@pytest.mark.parametrize("sport", SPORTS, ids=lambda sp: sp.key)
def test_prop_keys_are_unique_within_a_sport(sport):
    keys = [p.key for p in sport.prop_types]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("sport", SPORTS, ids=lambda sp: sp.key)
def test_every_prop_carries_a_label_and_a_unit(sport):
    for prop in sport.prop_types:
        assert prop.label and prop.unit, f"{sport.key}/{prop.key}"


@pytest.mark.parametrize("sport", SPORTS, ids=lambda sp: sp.key)
def test_every_sport_names_a_results_league(sport):
    """`<group>/<league>`, the shape the ESPN adapter will take."""
    assert sport.espn_path.count("/") == 1, sport.espn_path
    group, league = sport.espn_path.split("/")
    assert group and league


def test_results_leagues_are_distinct():
    paths = [sp.espn_path for sp in SPORTS]
    assert len(paths) == len(set(paths))


def test_the_sports_that_can_draw_price_three_outcomes():
    """Soccer prices the draw; nothing else here does."""
    three_way = {sp.key for sp in SPORTS if sp.outcomes == 3}
    assert three_way == {"epl", "ucl"}


def test_a_period_is_named_in_the_sport_s_own_language():
    by_key = {sp.key: sp.period_label for sp in SPORTS}
    assert by_key["ufc"] == "fight"
    assert by_key["epl"] == "match"
    assert by_key["nfl"] == "game"


# --------------------------------------------------------------------------- #
# The arithmetic is sport-agnostic — the reason adding eight was cheap
# --------------------------------------------------------------------------- #
def test_a_three_way_market_devigs_without_special_casing():
    probs = d.devig((150, 240, 180), "shin")
    assert len(probs) == 3
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)


def test_the_screen_works_on_a_three_way_market():
    """A soccer 1X2 outlier is found by the same code path as an NFL spread."""
    quotes = [
        d.Quote("DraftKings", (150, 240, 180)),
        d.Quote("Pinnacle", (155, 235, 175)),
        d.Quote("Bet365", (148, 245, 182)),
        d.Quote("generous", (150, 400, 180)),   # the draw, way out of line
    ]
    hits = d.screen(quotes, min_edge=0.01)
    assert hits[0].book == "generous"
    assert hits[0].outcome == 1                  # the draw
    assert hits[0].is_outlier


def test_a_three_way_estimate_sizes_like_any_other():
    quotes = [d.Quote(f"b{i}", (150, 240, 180)) for i in range(4)]
    est = s.from_consensus(d.consensus(quotes), 1)
    assert est.can_size


@pytest.mark.parametrize("sport", SPORTS, ids=lambda sp: sp.key)
def test_a_prompt_can_be_built_for_every_sport(sport):
    prompt = playmaker.build_prompt(
        sport, "Someone", sport.prop_types[0].label, "Over 1.5",
        "-110", "context", "data")
    assert sport.name in prompt
    assert sport.period_label.capitalize() in prompt


# --------------------------------------------------------------------------- #
# Checked live, but only when asked
# --------------------------------------------------------------------------- #
@pytest.mark.network
@pytest.mark.parametrize("sport", SPORTS, ids=lambda sp: sp.key)
def test_the_results_league_exists(sport):
    """Run with `-m network` to confirm ESPN still serves each league.

    Kept off the default run — a registry constant should not need the internet
    to be trusted, and the suite must never depend on someone else's uptime.
    """
    import json
    import urllib.request
    url = ("https://site.api.espn.com/apis/site/v2/sports/"
           f"{sport.espn_path}/scoreboard")
    with urllib.request.urlopen(url, timeout=20) as resp:
        assert resp.status == 200
        assert "events" in json.load(resp)
