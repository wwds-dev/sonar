"""The prediction models, and the gate that decides whether they may speak.

Two claims are pinned down here. First, that the Elo implementation is the
published one and not a plausible-looking approximation of it — the
margin-of-victory scaling and the autocorrelation correction each have a test
that fails if they are dropped. Second, and more important: that a model which
has not been measured out of sample cannot size a bet, however good its
probability looks.
"""

import datetime as dt

import pytest

from sonar import playmaker
from sonar.playmaker import ratings as r
from sonar.playmaker import results as res
from sonar.playmaker import scoring as sc

DAY = dt.date(2026, 1, 1)


def game(home, away, hs, as_, day=0):
    return res.Game(DAY + dt.timedelta(days=day), home, away, hs, as_)


# --------------------------------------------------------------------------- #
# Reading results
# --------------------------------------------------------------------------- #
def _event(home, away, hs, as_, completed=True, date="2026-01-01T00:00Z"):
    return {"date": date, "competitions": [{
        "date": date,
        "status": {"type": {"completed": completed}},
        "competitors": [
            {"homeAway": "home", "score": hs, "team": {"abbreviation": home}},
            {"homeAway": "away", "score": as_, "team": {"abbreviation": away}},
        ]}]}


def test_a_finished_game_is_read():
    games = res.parse_scoreboard({"events": [_event("SEA", "NE", 13, 10)]})
    assert len(games) == 1
    assert (games[0].home, games[0].away) == ("SEA", "NE")
    assert games[0].home_score == 13 and games[0].away_score == 10


def test_an_unfinished_game_is_skipped_not_counted_as_a_draw():
    """Counting a scheduled fixture 0-0 would bias every rating to the mean."""
    assert res.parse_scoreboard(
        {"events": [_event("SEA", "NE", 0, 0, completed=False)]}) == []


def test_a_malformed_entry_costs_only_itself():
    payload = {"events": [_event("SEA", "NE", 13, 10),
                          {"competitions": [{"status": {"type": {"completed": True}}}]},
                          _event("GB", "CHI", 20, 17)]}
    assert len(res.parse_scoreboard(payload)) == 2


def test_an_empty_payload_is_not_an_error():
    assert res.parse_scoreboard({}) == []


def test_margin_total_and_result():
    g = game("A", "B", 3, 1)
    assert g.margin == 2 and g.total == 4 and g.result == 1.0
    assert game("A", "B", 1, 3).result == 0.0
    assert game("A", "B", 2, 2).result == 0.5



def test_a_sport_with_no_feed_says_so_rather_than_failing_obscurely():
    with pytest.raises(ValueError, match="no results feed"):
        res.fetch_range("cycling", DAY, DAY)


def test_a_field_event_cannot_be_forced_into_a_result_table():
    """Golf has a feed, but a finishing order across 132 players is not a
    `Game` and no amount of parsing makes it one."""
    with pytest.raises(ValueError, match="field event"):
        res.fetch_range("golf", DAY, DAY)


def _bout(a, b, a_won, completed=True):
    return {"events": [{"date": "2026-01-01T00:00Z", "competitions": [
        {"date": "2026-01-01T00:00Z",
         "status": {"type": {"completed": completed}},
         "competitors": [
             {"order": 1, "winner": a_won, "athlete": {"displayName": a}},
             {"order": 2, "winner": not a_won if a_won is not None else False,
              "athlete": {"displayName": b}}]}]}]}


def test_a_fight_card_is_read_as_one_bout_per_competition():
    payload = _bout("A", "B", True)
    payload["events"][0]["competitions"].append(
        _bout("C", "D", False)["events"][0]["competitions"][0])
    bouts = res.parse_bouts(payload)
    assert len(bouts) == 2
    assert bouts[0].home == "A" and bouts[0].result == 1.0
    assert bouts[1].home == "C" and bouts[1].result == 0.0


def test_a_draw_or_no_contest_is_skipped_rather_than_scored_as_half():
    """Usually a foul or an injury — it says nothing about who is better."""
    payload = _bout("A", "B", False)
    payload["events"][0]["competitions"][0]["competitors"][1]["winner"] = False
    assert res.parse_bouts(payload) == []


def test_an_unfinished_fight_is_skipped():
    assert res.parse_bouts(_bout("A", "B", True, completed=False)) == []


# --------------------------------------------------------------------------- #
# Elo
# --------------------------------------------------------------------------- #
def test_equal_teams_on_neutral_ground_is_a_coin_flip():
    cfg = r.EloConfig(home_advantage=0.0)
    assert r.expected(1500, 1500, cfg) == pytest.approx(0.5)


def test_home_advantage_favours_the_home_side():
    assert r.expected(1500, 1500, r.EloConfig(home_advantage=65.0)) > 0.5


def test_a_stronger_team_is_favoured():
    cfg = r.EloConfig(home_advantage=0.0)
    assert r.expected(1700, 1500, cfg) > r.expected(1600, 1500, cfg) > 0.5


def test_four_hundred_points_is_ten_to_one():
    """The scale constant, which is what makes a rating point mean something."""
    cfg = r.EloConfig(home_advantage=0.0)
    assert r.expected(1900, 1500, cfg) == pytest.approx(10 / 11, abs=1e-9)


def test_the_winner_gains_exactly_what_the_loser_drops():
    table = r.Table(r.EloConfig())
    r.update(table, game("A", "B", 30, 10))
    assert table.value("A") - 1500 == pytest.approx(1500 - table.value("B"))


def test_winning_raises_a_rating_and_losing_lowers_it():
    table = r.Table(r.EloConfig())
    r.update(table, game("A", "B", 30, 10))
    assert table.value("A") > 1500 > table.value("B")


def test_a_bigger_win_moves_the_rating_further():
    """Margin of victory: a blowout is more evidence than a squeaker."""
    narrow, wide = r.Table(r.EloConfig()), r.Table(r.EloConfig())
    r.update(narrow, game("A", "B", 21, 20))
    r.update(wide, game("A", "B", 45, 3))
    assert wide.value("A") > narrow.value("A")


def test_the_autocorrelation_correction_damps_a_favourite_s_blowout():
    """Without it, good teams' ratings run away — they are the ones who get to
    run up scores. The same scoreline must move a favourite less than an
    underdog."""
    favourite = r.Table(r.EloConfig())
    favourite.ratings["A"] = r.Rating(1800.0)
    favourite.ratings["B"] = r.Rating(1400.0)
    before = favourite.value("A")
    r.update(favourite, game("A", "B", 40, 10))
    favourite_gain = favourite.value("A") - before

    underdog = r.Table(r.EloConfig())
    underdog.ratings["A"] = r.Rating(1400.0)
    underdog.ratings["B"] = r.Rating(1800.0)
    before = underdog.value("A")
    r.update(underdog, game("A", "B", 40, 10))
    assert underdog.value("A") - before > favourite_gain


def test_a_draw_still_moves_the_ratings():
    """log(max(0,1) + 1) keeps a level game from being silently discarded."""
    table = r.Table(r.EloConfig(draws=True))
    table.ratings["A"] = r.Rating(1700.0)
    table.ratings["B"] = r.Rating(1500.0)
    r.update(table, game("A", "B", 1, 1))
    assert table.value("A") < 1700, "the favourite should pay for dropping points"
    assert table.value("B") > 1500


def test_ratings_regress_between_seasons():
    table = r.Table(r.EloConfig(season_regression=1 / 3))
    table.ratings["A"] = r.Rating(1800.0)
    r.regress_to_mean(table)
    assert table.value("A") == pytest.approx(1500 + 300 * (2 / 3))


def test_a_long_gap_in_the_schedule_triggers_the_regression():
    strong = [game("A", "B", 40, 0, day=d) for d in range(10)]
    unbroken = r.fit(strong, "nfl")
    across_seasons = r.fit(strong + [game("C", "D", 20, 17, day=200)], "nfl")
    assert across_seasons.value("A") < unbroken.value("A")


def test_fitting_a_league_recovers_who_is_good():
    """The end-to-end property: feed it a league where A > B > C and it says so."""
    strength = {"A": 35, "B": 24, "C": 13}
    games, day = [], 0
    for _ in range(12):
        for home in strength:
            for away in strength:
                if home != away:
                    games.append(game(home, away,
                                      strength[home], strength[away], day))
                    day += 1
    table = r.fit(games, "nfl")
    assert [team for team, _ in table.ranked()] == ["A", "B", "C"]


def test_every_registered_sport_has_settings():
    from sonar import playmaker
    for sport in playmaker.list_sports():
        assert r.config_for(sport.key).k > 0


def test_the_sports_with_borrowed_settings_are_marked_as_such():
    """Honest bookkeeping: a stand-in must not read as a published figure."""
    assert r.UNTUNED == {"ncaaf", "mma"}
    assert "nfl" not in r.UNTUNED and "nba" not in r.UNTUNED


def test_mma_has_no_home_advantage():
    """No venue effect, so the corner ESPN happens to list first must not be
    handed an edge by the model."""
    assert r.config_for("mma").home_advantage == 0.0


def test_a_fighter_s_rating_moves_further_than_a_team_s():
    """Two or three bouts a year against eighty-odd games: each has to count
    for more, or a fighter's rating never leaves where it started."""
    assert r.config_for("mma").k > r.config_for("nba").k


def test_college_football_carries_a_bigger_home_field_than_the_nfl():
    assert r.config_for("ncaaf").home_advantage > r.config_for("nfl").home_advantage


def test_the_sport_that_can_draw_is_configured_for_it():
    assert r.config_for("intl_football").draws
    assert not r.config_for("nfl").draws


# --------------------------------------------------------------------------- #
# Pythagorean
# --------------------------------------------------------------------------- #
def test_scoring_as_much_as_you_concede_is_a_coin_flip():
    assert r.pythagorean(400, 400, 2.37) == pytest.approx(0.5)


def test_outscoring_the_opposition_predicts_winning():
    assert r.pythagorean(500, 300, 2.37) > 0.5


def test_a_tighter_scoring_sport_takes_a_higher_exponent():
    """Which is why the NBA's is 13.91 and the NFL's is 2.37 — basketball
    scores cluster far more tightly."""
    assert r.PYTHAGOREAN_EXPONENTS["nba"] > r.PYTHAGOREAN_EXPONENTS["nfl"]


def test_no_exponent_is_invented_for_a_sport_without_one():
    """Guessing one would make the cross-check worse than not having it."""
    assert set(r.PYTHAGOREAN_EXPONENTS) == {"nfl", "nba"}
    table = r.fit([game("A", "B", 3, 1)], "intl_football")
    assert r.pythagorean_for(table, "A", "intl_football") is None


def test_the_cross_check_reads_a_fitted_table():
    table = r.fit([game("A", "B", 30, 10), game("A", "B", 28, 14, day=1)], "nfl")
    assert 0.5 < r.pythagorean_for(table, "A", "nfl") <= 1.0


# --------------------------------------------------------------------------- #
# Scoring — the gate
# --------------------------------------------------------------------------- #
def test_perfect_foresight_scores_zero():
    score = sc.score_predictions([(1.0, 1.0), (0.0, 0.0)] * 200)
    assert score.brier == pytest.approx(0.0)


def test_a_coin_flip_on_everything_scores_a_quarter():
    score = sc.score_predictions([(0.5, 1.0), (0.5, 0.0)] * 200)
    assert score.brier == pytest.approx(0.25)


def test_log_loss_punishes_confident_mistakes_harder_than_brier():
    timid = sc.score_predictions([(0.6, 0.0)] * 400)
    bold = sc.score_predictions([(0.99, 0.0)] * 400)
    assert bold.log_loss / timid.log_loss > bold.brier / timid.brier


def test_certainty_never_costs_an_infinite_loss():
    assert sc.score_predictions([(1.0, 0.0)] * 400).log_loss < float("inf")


def test_skill_is_measured_against_the_base_rate_not_against_half():
    """A league where the home side wins 70% of the time makes 'always home'
    look clever. Skill has to net that out."""
    pairs = [(0.7, 1.0)] * 700 + [(0.7, 0.0)] * 300
    assert sc.score_predictions(pairs).skill == pytest.approx(0.0, abs=1e-9)


def test_a_model_worse_than_the_base_rate_is_dropped():
    pairs = [(0.2, 1.0)] * 700 + [(0.2, 0.0)] * 300
    assert sc.score_predictions(pairs).verdict == "DROP"


def test_too_little_history_is_not_a_verdict():
    assert sc.score_predictions([(0.9, 1.0)] * 10).verdict == "INSUFFICIENT"
    assert sc.MIN_GAMES > 100


def test_calibration_buckets_report_the_gap():
    score = sc.score_predictions([(0.85, 1.0)] * 300 + [(0.85, 0.0)] * 700)
    bucket = next(b for b in score.buckets if b.low == 0.8)
    assert bucket.predicted == pytest.approx(0.85)
    assert bucket.realised == pytest.approx(0.3)
    assert bucket.gap < 0, "over-confident, and the sign should say so"


# --------------------------------------------------------------------------- #
# The rule this whole module exists for
# --------------------------------------------------------------------------- #
def test_an_unmeasured_model_cannot_size_a_bet():
    thin = sc.score_predictions([(0.9, 1.0)] * 10)
    est = sc.calibrated_estimate(0.9, thin)
    assert est.source == sc.UNVALIDATED
    assert not est.can_size


def test_a_model_that_lost_to_the_base_rate_cannot_size_a_bet():
    bad = sc.score_predictions([(0.2, 1.0)] * 700 + [(0.2, 0.0)] * 300)
    assert bad.verdict == "DROP"
    assert not sc.calibrated_estimate(0.7, bad).can_size


def test_a_measured_model_may_size_and_says_how_wide_it_is():
    good = sc.score_predictions([(0.9, 1.0)] * 900 + [(0.1, 0.0)] * 900)
    assert good.verdict == "KEEP"
    est = sc.calibrated_estimate(0.62, good, "nfl")
    assert est.can_size
    assert est.low < 0.62 < est.high
    assert "nfl" in est.basis


def test_a_weak_result_is_sized_more_cautiously_than_a_strong_one():
    pairs = [(0.9, 1.0)] * 900 + [(0.1, 0.0)] * 900
    strong = sc.score_predictions(pairs)
    est = sc.calibrated_estimate(0.62, strong)
    assert est.width <= 2 * strong.calibration_error + 1e-9


def test_walk_forward_never_scores_a_game_it_has_already_seen():
    """Out of sample by construction: every prediction comes from a table that
    has only seen earlier games."""
    games = [game("A", "B", 30, 10, day=d) for d in range(300)]
    score = sc.walk_forward(games, "nfl", burn_in=100)
    assert score.games == 200


def test_the_burn_in_is_not_scored():
    games = [game("A", "B", 30, 10, day=d) for d in range(150)]
    assert sc.walk_forward(games, "nfl", burn_in=100).games == 50


def test_a_summary_reads_as_a_sentence():
    score = sc.score_predictions([(0.9, 1.0)] * 900 + [(0.1, 0.0)] * 900)
    assert "KEEP" in score.summary and "Brier" in score.summary


# --------------------------------------------------------------------------- #
# Fetching a window, and noticing when the answer was cut short
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, payload):
        import json
        self._body = json.dumps(payload).encode()
    def read(self, *a):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


_SERIAL = [0]


def _payload(n, day="2026-01-01T00:00Z"):
    """`n` completed fixtures, all distinct — so deduplication cannot hide a
    window that was or was not split."""
    base = _SERIAL[0]
    _SERIAL[0] += n
    return {"events": [
        {"date": day, "competitions": [{
            "date": day,
            "status": {"type": {"completed": True}},
            "competitors": [
                {"homeAway": "home", "score": 3, "team": {"abbreviation": f"H{i}"}},
                {"homeAway": "away", "score": 1, "team": {"abbreviation": f"A{i}"}},
            ]}]} for i in range(base, base + n)]}


def _serve(monkeypatch, sizes):
    """Answer successive requests with the given event counts, recording spans."""
    _SERIAL[0] = 0
    calls = []
    queue = list(sizes)

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return _FakeResponse(_payload(queue.pop(0) if queue else 0))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return calls




def test_a_whole_year_is_asked_for_before_months_are(monkeypatch):
    """A sport here can be fourteen competitions. Thirty-day windows made six
    years of international football over a thousand requests; a year per league
    is eighty-four, and the sparse competitions never need months at all."""
    calls = _serve(monkeypatch, [3])
    res.fetch_range("nba", dt.date(2025, 3, 1), dt.date(2025, 4, 1), pause=0)
    assert len(calls) == 1
    assert "dates=2025" in calls[0]


def test_a_capped_year_falls_back_to_months(monkeypatch):
    """ESPN truncates and says nothing — no cursor, no total, no error. A
    response holding exactly the limit has lost fixtures, and short history
    that looks healthy is worse than slow history."""
    calls = _serve(monkeypatch, [res.PAGE_LIMIT] + [1] * 12)
    res.fetch_range("nba", dt.date(2025, 1, 1), dt.date(2025, 12, 31), pause=0)
    assert len(calls) == 13, "one year, then its twelve months"
    assert "dates=202501" in calls[1] and "dates=202512" in calls[12]


def test_results_outside_the_window_asked_for_are_dropped(monkeypatch):
    """A year is fetched whole, so it carries fixtures either side of the
    range the caller wanted."""
    def fake_urlopen(request, timeout=None):
        return _FakeResponse({"events": [
            {"date": f"2025-0{m}-15T00:00Z", "competitions": [{
                "date": f"2025-0{m}-15T00:00Z",
                "status": {"type": {"completed": True}},
                "competitors": [
                    {"homeAway": "home", "score": 3, "team": {"abbreviation": f"H{m}"}},
                    {"homeAway": "away", "score": 1, "team": {"abbreviation": f"A{m}"}},
                ]}]} for m in (1, 5, 9)]})
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    got = res.fetch_range("nba", dt.date(2025, 4, 1), dt.date(2025, 6, 30), pause=0)
    assert [g.date.month for g in got] == [5]


def test_a_400_is_taken_as_an_empty_window_not_an_error(monkeypatch):
    """A league with nothing in a given year answers 400. Retrying is pointless
    and treating it as a failure would lose the years around it."""
    import urllib.error
    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    monkeypatch.setattr("urllib.request.urlopen", lambda r, timeout=None: (_ for _ in ()).throw(
        urllib.error.HTTPError(r.full_url, 400, "Bad Request", {}, None)))
    assert res.fetch_range("nba", DAY, DAY, pause=0) == []
    assert slept == [], "a 400 should not be retried"


def test_a_sport_with_many_leagues_fetches_each_of_them(monkeypatch):
    calls = _serve(monkeypatch, [1] * 200)
    res.fetch_range("intl_football", DAY, DAY + dt.timedelta(days=30), pause=0)
    paths = {c.split("/sports/")[1].split("/scoreboard")[0] for c in calls}
    assert paths == set(playmaker.get_sport("intl_football").espn_paths)


def test_the_same_fixture_from_two_windows_is_only_counted_once(monkeypatch):
    """ESPN returns a fixture in every window that touches it."""
    def fake_urlopen(request, timeout=None):
        return _FakeResponse({"events": [
            {"date": "2026-01-01T00:00Z", "competitions": [{
                "date": "2026-01-01T00:00Z",
                "status": {"type": {"completed": True}},
                "competitors": [
                    {"homeAway": "home", "score": 3, "team": {"abbreviation": "H"}},
                    {"homeAway": "away", "score": 1, "team": {"abbreviation": "A"}},
                ]}]}]})
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    got = res.fetch_range("nba", DAY, DAY + dt.timedelta(days=200), pause=0)
    assert len(got) == 1, "the same fixture from two windows must deduplicate"


def test_a_throttled_request_backs_off_rather_than_hammering(monkeypatch):
    """403 and 429 both mean slow down. Retrying at full speed is how you get
    blocked for longer."""
    import urllib.error
    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))

    def refuse(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    assert res.fetch_range("nba", DAY, DAY, pause=0) == []
    assert slept and max(slept) >= res.THROTTLED_PAUSE_S
