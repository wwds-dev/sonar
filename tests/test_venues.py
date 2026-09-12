"""Where a row could actually be traded — and where it could not.

The screener scores an index, two futures contracts and a delisted coin
alongside ordinary shares. Nine of twenty-six rows cannot be bought as shown,
which is a third of the board, so "you cannot trade this" is the normal case
here rather than an edge case.

These tests exist because the failure mode is silent: a wrong mapping does not
crash anything, it just tells someone to place an order that will not work.
"""

from sonar import venues
from sonar.assets import WATCHLIST


def test_every_watchlist_row_has_a_mapping():
    """Silence would read as 'buy it anywhere', which is the wrong default."""
    for sym, _name, cls, _kw in WATCHLIST:
        v = venues.where(sym, cls)
        assert v is not venues._UNKNOWN, f"{sym} has no venue mapping"


def test_an_index_is_not_presented_as_buyable():
    v = venues.where("^GSPC", "Index")
    assert v.proxy and "UCITS" in v.instrument
    assert "cannot be bought" in v.note


def test_us_domiciled_etfs_are_flagged_as_closed_to_eu_retail():
    """PRIIPs blocks SPY/VOO/QQQ for EU retail. Naming them without that is a
    recommendation to try something that will be refused at the broker."""
    for sym in ("^GSPC", "^IXIC", "^DJI"):
        assert "PRIIPs" in venues.where(sym, "Index").note


def test_futures_are_not_presented_as_retail_instruments():
    for sym in ("GC=F", "CL=F"):
        v = venues.where(sym, "Commodity")
        assert v.proxy and "futures contract" in v.note


def test_the_oil_etc_roll_caveat_is_stated():
    """An oil ETC is not a buy-and-hold on the oil price, and the gap is large
    enough over a year that omitting it would mislead."""
    assert "roll" in venues.where("CL=F", "Commodity").note


def test_monero_is_marked_untradeable_rather_than_merely_awkward():
    v = venues.where("XMR-USD", "Crypto")
    assert v.tradeable is False
    assert v.venues == "", "an untradeable row must not list venues"
    assert "Kraken" in v.note and "Binance" in v.note


def test_the_untradeable_summary_leads_with_the_refusal():
    assert venues.where("XMR-USD", "Crypto").summary().startswith("Not tradeable")


def test_currency_exchange_is_distinguished_from_an_fx_position():
    """The mistake this prevents: Revolut converting EUR to USD is not being
    long USD, and the apps that do the first are assumed to do the second."""
    v = venues.where("EURUSD=X", "Forex")
    assert "not the same trade" in v.note
    assert "Revolut" in v.note and "Revolut" not in v.venues


def test_ordinary_shares_are_direct_and_unqualified():
    v = venues.where("AAPL", "Equity")
    assert v.tradeable and not v.proxy


def test_coverage_counts_what_is_actionable():
    c = venues.coverage()
    assert c["n"] == len(WATCHLIST)
    assert c["untradeable"] == ["XMR-USD"]
    assert set(c["proxied"]) >= {"^GSPC", "GC=F", "EURUSD=X"}
    assert c["direct"] + len(c["proxied"]) + len(c["untradeable"]) == c["n"]


def test_the_check_date_is_carried_so_staleness_is_visible():
    """Exchanges delist and regulations arrive; a list with no date reads as
    permanently current."""
    assert venues.CHECKED
    assert venues.where("AAPL", "Equity").as_dict()["checked"] == venues.CHECKED
