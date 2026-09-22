"""Tests for the tradeable universe and the Wikipedia mapping.

The bug worth guarding is silent. Pageviews are counted per *article*, and a
redirect keeps its own near-zero count — "Amazon.com Inc" reports 0 views a day
while "Amazon (company)" reports 6,670. Feeding a redirect into the attention
proxy yields a flat, empty series that still looks like data, and the study
built on it would answer confidently and wrongly.
"""

from sonar import universe


def test_screener_names_become_searchable():
    assert universe.clean_name("Apple Inc. Common Stock") == "Apple Inc"
    assert universe.clean_name("Alphabet Inc. Class A Common Stock") == "Alphabet Inc"
    assert universe.clean_name("Alcoa Corporation Common Stock") == "Alcoa Corporation"


def test_non_common_instruments_are_excluded():
    """Warrants expire and rights vanish; neither has a usable price history."""
    for junk in ("Artius II Acquisition Inc. Rights",
                 "Some Corp Warrant", "Bank X 6.5% Preferred Stock",
                 "Thing Inc. Units"):
        assert universe._EXCLUDE.search(junk) or not universe._COMMON.search(junk)


def test_ordinary_shares_are_kept():
    for good in ("Apple Inc. Common Stock", "Shell plc American Depositary Shares",
                 "Linde plc Ordinary Shares"):
        assert universe._COMMON.search(good)
        assert not universe._EXCLUDE.search(good)


def test_only_plain_tickers_are_accepted():
    assert universe._CLEAN_TICKER.match("AAPL")
    assert universe._CLEAN_TICKER.match("F")
    assert not universe._CLEAN_TICKER.match("BRK.A")
    assert not universe._CLEAN_TICKER.match("RDS/B")
    assert not universe._CLEAN_TICKER.match("TOOLONG")


def test_market_cap_parsing_survives_formatting():
    assert universe._money("40274795214.00") == 40274795214.0
    assert universe._money("$1,234.50") == 1234.5
    assert universe._money("") == 0.0
    assert universe._money(None) == 0.0


# --------------------------------------------------------------------------- #
# fetch_universe, with the network stubbed at urlopen
# --------------------------------------------------------------------------- #
import io
import json
import time

import pytest


@pytest.fixture
def screener(monkeypatch):
    """Answer the Nasdaq screener with a canned payload."""
    payload: dict = {"data": {"rows": []}}

    def fake_urlopen(req, timeout=0):
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(universe.urllib.request, "urlopen", fake_urlopen)
    return payload


def row(sym, name, cap="10,000,000,000.00", sector="Tech", country="US"):
    return {"symbol": sym, "name": name, "marketCap": cap,
            "sector": sector, "country": country}


def test_the_universe_is_filtered_sorted_and_cleaned(screener):
    screener["data"]["rows"] = [
        row("AAPL", "Apple Inc. Common Stock", "$3,000,000,000,000"),
        row("SHEL", "Shell plc American Depositary Shares", "200,000,000,000"),
        row("TINY", "Tiny Corp Common Stock", "1,000,000"),     # below the floor
        row("WARR", "Some Corp Warrant", "9,000,000,000"),      # not common stock
        row("BRK.A", "Berkshire Hathaway Inc. Common Stock",    # punctuated ticker
            "900,000,000,000"),
    ]
    out = universe.fetch_universe(refresh=True)
    assert [r["symbol"] for r in out] == ["AAPL", "SHEL"], \
        "largest first, junk and micro-caps gone"
    assert out[0]["name"] == "Apple Inc", "screener suffixes are cleaned"


def test_the_universe_is_cached_and_the_cache_expires(screener, monkeypatch):
    screener["data"]["rows"] = [row("AAPL", "Apple Inc. Common Stock")]
    first = universe.fetch_universe(refresh=True)
    screener["data"]["rows"] = []                       # the network moves on…
    assert universe.fetch_universe() == first, "…but the cache answers"
    # `universe.time` is the shared stdlib module, so the fake must close over
    # the real clock or it calls itself.
    real_time = time.time
    monkeypatch.setattr(universe.time, "time",
                        lambda: real_time() + universe.CACHE_TTL + 1)
    assert universe.fetch_universe() == [], "an expired cache refetches"


def test_a_dead_screener_is_an_empty_list_not_a_crash(monkeypatch):
    def boom(req, timeout=0):
        raise OSError("no route")
    monkeypatch.setattr(universe.urllib.request, "urlopen", boom)
    assert universe.fetch_universe(refresh=True) == []


# --------------------------------------------------------------------------- #
# Wikipedia resolution, with the network stubbed at _wiki_get
# --------------------------------------------------------------------------- #
def test_canonical_title_follows_the_redirect(monkeypatch):
    """The bug this module exists to avoid: a redirect keeps its own near-zero
    pageview count, so the attention series must be built on the target."""
    monkeypatch.setattr(universe, "_wiki_get", lambda url: {
        "query": {"pages": {"12": {"title": "Amazon (company)"}}}})
    assert universe.canonical_title("Amazon.com Inc") == "Amazon_(company)"


def test_a_missing_article_is_none_not_a_guess(monkeypatch):
    monkeypatch.setattr(universe, "_wiki_get", lambda url: {
        "query": {"pages": {"-1": {"missing": ""}}}})
    assert universe.canonical_title("No Such Company Xyz") is None


def test_wiki_article_rejects_a_search_that_wandered_off(monkeypatch):
    """A loose match maps a ticker onto an unrelated article and then reports
    its pageviews as the company's coverage — the first significant word of
    the name must survive into the title."""
    monkeypatch.setattr(universe, "_wiki_get",
                        lambda url: [None, ["Diesel fuel"]])
    assert universe.wiki_article("Ripple Labs") is None


def test_wiki_article_accepts_a_match_and_canonicalises_it(monkeypatch):
    calls = []

    def fake(url):
        calls.append(url)
        if "opensearch" in url:
            return [None, ["Apple Inc."]]
        return {"query": {"pages": {"1": {"title": "Apple Inc."}}}}

    monkeypatch.setattr(universe, "_wiki_get", fake)
    assert universe.wiki_article("Apple Inc") == "Apple_Inc."


def test_canonical_titles_follows_the_alias_chain(monkeypatch):
    """requested -> normalised -> redirected, as the API reports them."""
    monkeypatch.setattr(universe, "_wiki_get", lambda url: {"query": {
        "normalized": [{"from": "amazon.com inc", "to": "Amazon.com Inc"}],
        "redirects": [{"from": "Amazon.com Inc", "to": "Amazon (company)"}],
        "pages": {"1": {"title": "Amazon (company)"}},
    }})
    out = universe.canonical_titles(["amazon.com inc"])
    assert out == {"amazon.com inc": "Amazon_(company)"}


def test_canonical_titles_drops_what_never_lands_on_a_page(monkeypatch):
    monkeypatch.setattr(universe, "_wiki_get", lambda url: {"query": {
        "pages": {"-1": {"title": "Ghost Corp", "missing": ""}}}})
    assert universe.canonical_titles(["Ghost Corp"]) == {}


def test_a_redirect_loop_cannot_hang_the_resolver(monkeypatch):
    monkeypatch.setattr(universe, "_wiki_get", lambda url: {"query": {
        "redirects": [{"from": "A", "to": "B"}, {"from": "B", "to": "A"}],
        "pages": {}}})
    assert universe.canonical_titles(["A"]) == {}


def test_article_map_caches_misses_so_they_are_not_re_asked(monkeypatch):
    """A None is cached too: re-asking Wikipedia for every unmappable name on
    every run is how a study spends its time asleep in rate-limit backoff."""
    asked = []

    def fake_article(name):
        asked.append(name)
        return None

    monkeypatch.setattr(universe, "wiki_article", fake_article)
    universe.article_map([("XX", "Unmappable Co")])
    universe.article_map([("XX", "Unmappable Co")])
    assert asked == ["Unmappable Co"], "the miss was cached after the first ask"


def test_article_map_fast_batches_then_falls_back(monkeypatch):
    monkeypatch.setattr(universe, "canonical_titles",
                        lambda names: {"Apple Inc": "Apple_Inc."})
    monkeypatch.setattr(universe, "wiki_article",
                        lambda name: "Stray_Article" if name == "Stray Co" else None)
    out = universe.article_map_fast(
        [("AAPL", "Apple Inc"), ("STRY", "Stray Co"), ("NOPE", "Unfindable")],
        refresh=True)
    assert out == {"AAPL": "Apple_Inc.", "STRY": "Stray_Article"}
