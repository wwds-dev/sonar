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
    assert keys == {"nfl", "ncaaf", "nba", "mma", "intl_football", "golf", "cycling"}


def test_no_club_football_is_registered():
    """International team games only. A club competition creeping back in would
    quietly double the fixture list and pollute the national-team ratings."""
    names = " ".join(sp.name for sp in SPORTS).lower()
    paths = " ".join(path for sp in SPORTS for path in sp.espn_paths)
    for club in ("premier league", "champions league", "la liga", "bundesliga"):
        assert club not in names
    for code in ("eng.1", "uefa.champions", "esp.1", "ger.1", "ita.1"):
        assert code not in paths


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
def test_every_results_league_is_well_formed(sport):
    """`<group>/<league>`, the shape the ESPN adapter takes."""
    for path in sport.espn_paths:
        assert path.count("/") == 1, path
        group, league = path.split("/")
        assert group and league


def test_results_leagues_are_distinct():
    paths = [path for sp in SPORTS for path in sp.espn_paths]
    assert len(paths) == len(set(paths))


def test_international_football_pools_every_competition_it_plays():
    """National sides play a handful of times a year across many competitions.
    Splitting them would leave no single one with enough matches to fit on."""
    intl = playmaker.get_sport("intl_football")
    assert len(intl.espn_paths) > 10
    assert all(p.startswith("soccer/") for p in intl.espn_paths)
    assert "soccer/fifa.world" in intl.espn_paths


def test_cycling_admits_it_has_no_results_feed():
    """ESPN serves no cycling endpoint. An empty tuple is the honest answer;
    the alternative is a rating nobody could check."""
    assert playmaker.get_sport("cycling").espn_paths == ()
    assert not playmaker.get_sport("cycling").has_results


def test_the_sport_that_can_draw_prices_three_outcomes():
    three_way = {sp.key for sp in SPORTS if sp.outcomes == 3}
    assert three_way == {"intl_football"}


def test_a_period_is_named_in_the_sport_s_own_language():
    by_key = {sp.key: sp.period_label for sp in SPORTS}
    assert by_key["mma"] == "fight"
    assert by_key["intl_football"] == "match"
    assert by_key["golf"] == "tournament"
    assert by_key["cycling"] == "race"
    assert by_key["nfl"] == "game"


# --------------------------------------------------------------------------- #
# Result shapes, and being honest about what can be modelled
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sport", SPORTS, ids=lambda sp: sp.key)
def test_every_sport_declares_a_known_shape(sport):
    assert sport.shape in ("scores", "winners", "field")


def test_field_events_have_no_head_to_head_model():
    """Golf and cycling are a finishing order across a hundred competitors.
    Pretending Elo applies would be inventing an answer."""
    for key in ("golf", "cycling"):
        sport = playmaker.get_sport(key)
        assert sport.shape == "field"
        assert sport.model == ""
        assert not sport.has_model


def test_mma_is_head_to_head_but_has_no_scoreline():
    mma = playmaker.get_sport("mma")
    assert mma.shape == "winners"
    assert mma.model == "elo"


def test_football_gets_the_scoreline_model():
    assert playmaker.get_sport("intl_football").model == "dixon_coles"


def test_the_sports_that_can_be_rated_all_have_a_feed():
    for sport in SPORTS:
        if sport.has_model:
            assert sport.has_results, f"{sport.key} claims a model with no data"


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
