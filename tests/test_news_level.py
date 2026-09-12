"""The news level must discriminate, and must not be a direction.

Two failures this guards against. First, a label that fires on everything:
derived from the saturating ``coverage`` score, two-thirds of the board read
"Spike", which looks like information and is not. Second, the return of a
directional claim — momentum's lean was removed on evidence and must not creep
back in through this field.
"""

import time
from types import SimpleNamespace

from sonar.assets import news_level


def h(age_hours: float | None):
    return SimpleNamespace(dated=age_hours is not None,
                           age_hours=age_hours if age_hours is not None else 9999.0)


def test_nothing_matched_is_quiet():
    assert news_level([]) == "Quiet"


def test_one_stale_story_is_only_normal():
    assert news_level([h(40), h(60)]) == "Normal"


def test_a_single_fresh_story_is_elevated():
    assert news_level([h(2), h(40)]) == "Elevated"


def test_three_fresh_stories_are_a_spike():
    assert news_level([h(1), h(2), h(3)]) == "Spike"


def test_busy_day_without_fresh_news_is_elevated_not_spike():
    assert news_level([h(10), h(12), h(20)]) == "Elevated"


def test_undated_headlines_cannot_manufacture_a_spike():
    """A feed with no timestamps must not be read as breaking news."""
    assert news_level([h(None)] * 4) == "Normal"


def test_level_is_never_a_direction():
    for case in ([], [h(1)], [h(1), h(2), h(3)], [h(40)]):
        assert news_level(case) not in ("Bullish", "Bearish", "Neutral")


# --- keyword matching -------------------------------------------------- #

def hl(title, age=1.0):
    import re
    toks = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'&-]+", title)}
    return SimpleNamespace(dated=True, age_hours=age, _tokens=toks, title=title)


def test_ambiguous_word_alone_does_not_match():
    """'ripple effect' is not news about XRP — this actually happened."""
    from sonar.assets import _match_news
    news = [hl("California's diesel prices jumped, and the ripple effect is real")]
    assert _match_news(news, {"ripple", "xrp"}) == []


def test_ambiguous_word_with_crypto_context_does_match():
    from sonar.assets import _match_news
    news = [hl("Ripple wins court case, XRP token surges on crypto exchange")]
    assert len(_match_news(news, {"ripple", "xrp"})) == 1


def test_specific_name_matches_without_a_chaperone():
    from sonar.assets import _match_news
    news = [hl("Nvidia beats expectations again")]
    assert len(_match_news(news, {"nvidia"})) == 1


def test_generic_crypto_story_no_longer_covers_every_coin():
    """One broad article used to be 'fresh coverage' for nine assets at once."""
    from sonar.assets import WATCHLIST
    coins = [kw for s, _n, c, kw in WATCHLIST if c == "Crypto" and s != "BTC-USD"]
    assert not any("crypto" in kw for kw in coins)


# --- source diversity ------------------------------------------------------ #
def _h(source, origin, state=False):
    from sonar.news import Headline
    return Headline(title=f"story from {source}", link="", source=source,
                    category="political", ts=int(time.time()),
                    origin=origin, state=state)


def test_every_feed_declares_an_origin():
    """A feed with no origin silently counts as US press and skews the spread."""
    from sonar.news import FEEDS
    assert all(f.origin for f in FEEDS.values())


def test_the_wire_is_not_only_western():
    """The point of the non-Western sources: a geopolitical signal built on one
    bloc measures what that bloc is talking about."""
    from sonar.news import FEEDS
    western = {"us", "uk", "eu"}
    assert {f.origin for f in FEEDS.values()} - western, "no non-Western origins"


def test_state_outlets_are_marked():
    from sonar.news import FEEDS
    assert any(f.state for f in FEEDS.values())
    assert not FEEDS["Reuters"].state


def test_spread_counts_distinct_blocs():
    from sonar.news import bloc_spread
    out = bloc_spread([_h("Reuters", "uk"), _h("Al Jazeera", "mena"),
                       _h("SCMP", "china")])
    assert out["n_blocs"] == 3
    assert out["blocs"] == ["china", "mena", "uk"]


def test_one_bloc_shouting_is_not_three_blocs_agreeing():
    from sonar.news import bloc_spread
    one = bloc_spread([_h("TASS", "russia", True)] * 5)
    many = bloc_spread([_h("Reuters", "uk"), _h("AP", "us"), _h("SCMP", "china")])
    assert one["n_blocs"] == 1 and many["n_blocs"] == 3, \
        "headline count alone cannot separate these; spread must"


def test_state_only_coverage_is_flagged():
    from sonar.news import bloc_spread
    assert bloc_spread([_h("TASS", "russia", True),
                        _h("Global Times", "china", True)])["state_only"] is True
    assert bloc_spread([_h("TASS", "russia", True),
                        _h("Reuters", "uk")])["state_only"] is False


def test_empty_matches_do_not_claim_spread():
    from sonar.news import bloc_spread
    assert bloc_spread([])["n_blocs"] == 0
