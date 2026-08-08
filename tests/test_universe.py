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
