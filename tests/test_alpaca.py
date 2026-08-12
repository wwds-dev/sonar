"""Tests for the Alpaca paper broker — mostly attempts to make it trade live.

Alpaca's paper and live APIs differ by one hostname. Everything below tries to
get real orders sent: a live URL, a live-looking key, a live host smuggled into
a path, a missing credential. Each must raise rather than degrade into
something that still trades.

No test here contacts Alpaca. They exercise the guards, which is the part that
has to hold when someone later edits a config file in a hurry.
"""

import pytest

from sonar import alpaca


# --- the guard ------------------------------------------------------------ #

def test_paper_host_is_accepted():
    alpaca.assert_paper_only(alpaca.PAPER_BASE, "PKTESTKEY123")


def test_live_host_is_refused():
    with pytest.raises(alpaca.LiveTradingRefused):
        alpaca.assert_paper_only("https://api.alpaca.markets/v2", "PKTESTKEY123")


def test_the_live_host_is_a_substring_of_the_paper_host():
    """Documents the trap that a naive guard falls into.

    "api.alpaca.markets" is contained in "paper-api.alpaca.markets", so a
    substring check for the live host rejects the only safe URL. The guard uses
    exact host equality for this reason.
    """
    assert alpaca.LIVE_HOST in alpaca.PAPER_HOST
    alpaca.assert_paper_only(alpaca.PAPER_BASE, "PKTEST")     # must not raise


def test_lookalike_hosts_are_refused():
    """Anything that is not exactly the paper host, however plausible."""
    for url in ("https://api.alpaca.markets/v2",
                "https://paper-api.alpaca.markets.evil.com/v2",
                "https://alpaca.markets/v2",
                "https://PAPER-API.ALPACA.MARKETS.attacker.net/v2",
                "http://localhost:9999/v2"):
        with pytest.raises(alpaca.LiveTradingRefused):
            alpaca.assert_paper_only(url, "PKTESTKEY123")


def test_live_key_is_refused_even_on_the_paper_host():
    """A live key against the paper URL is still refused.

    Belt and braces: the URL alone is not trusted to establish intent.
    """
    with pytest.raises(alpaca.LiveTradingRefused):
        alpaca.assert_paper_only(alpaca.PAPER_BASE, "AKLIVEKEY123")


def test_unrecognised_key_prefixes_are_treated_as_live():
    """Unknown means unsafe. Wrong in the safe direction."""
    for key in ("", "XX123", "sk_live_abc", "1234"):
        assert alpaca.looks_live(key) is True


def test_paper_keys_are_recognised():
    assert alpaca.looks_live("PKABC123") is False
    assert alpaca.looks_live("pkabc123") is False        # case-insensitive


# --- construction --------------------------------------------------------- #

def test_missing_credentials_raise_rather_than_silently_disable(monkeypatch):
    monkeypatch.delenv(alpaca.KEY_ENV, raising=False)
    monkeypatch.delenv(alpaca.SECRET_ENV, raising=False)
    monkeypatch.setattr(alpaca, "load_env", lambda *a, **k: None)
    with pytest.raises(alpaca.AlpacaUnavailable):
        alpaca.AlpacaPaperBroker(verify=False)


def test_a_live_key_cannot_construct_the_broker(monkeypatch):
    monkeypatch.setattr(alpaca, "load_env", lambda *a, **k: None)
    with pytest.raises(alpaca.LiveTradingRefused):
        alpaca.AlpacaPaperBroker(key_id="AKLIVE", secret="s", verify=False)


def test_broker_reports_itself_as_not_live(monkeypatch):
    monkeypatch.setattr(alpaca, "load_env", lambda *a, **k: None)
    b = alpaca.AlpacaPaperBroker(key_id="PKTEST", secret="s", verify=False)
    assert b.live is False
    assert b.name == "alpaca-paper"


def test_base_url_points_at_paper():
    assert alpaca.PAPER_HOST in alpaca.PAPER_BASE
    assert alpaca.LIVE_HOST not in alpaca.PAPER_BASE.replace(alpaca.PAPER_HOST, "")


# --- orders --------------------------------------------------------------- #

def test_every_request_recheks_the_guard(monkeypatch):
    """A broker mutated after construction must still refuse.

    Guarding only at __init__ would leave a window: anything that later swapped
    the key would keep trading.
    """
    monkeypatch.setattr(alpaca, "load_env", lambda *a, **k: None)
    b = alpaca.AlpacaPaperBroker(key_id="PKTEST", secret="s", verify=False)
    b.key_id = "AKLIVE"                       # tampered with after the fact
    with pytest.raises(alpaca.LiveTradingRefused):
        b._request("/account")


def test_zero_quantity_is_not_sent(monkeypatch):
    monkeypatch.setattr(alpaca, "load_env", lambda *a, **k: None)
    b = alpaca.AlpacaPaperBroker(key_id="PKTEST", secret="s", verify=False)
    sent = []
    monkeypatch.setattr(b, "_request", lambda *a, **k: sent.append(a) or {})
    out = b.execute("AAPL", "LONG", 0.0, 100.0)
    assert "error" in out and not sent, "an empty order reached the API"


def test_direction_maps_to_the_right_side(monkeypatch):
    monkeypatch.setattr(alpaca, "load_env", lambda *a, **k: None)
    b = alpaca.AlpacaPaperBroker(key_id="PKTEST", secret="s", verify=False)
    seen = {}

    def fake(path, method="GET", body=None):
        seen.update(body or {})
        return {"id": "x", "status": "accepted"}

    monkeypatch.setattr(b, "_request", fake)
    b.execute("AAPL", "LONG", 3, 100.0)
    assert seen["side"] == "buy"
    b.execute("AAPL", "SHORT", 3, 100.0)
    assert seen["side"] == "sell"
    b.execute("AAPL", "COVER", 3, 100.0)
    assert seen["side"] == "buy"


# --- availability --------------------------------------------------------- #

def test_available_is_honest_about_a_missing_key(monkeypatch):
    monkeypatch.setattr(alpaca, "load_env", lambda *a, **k: None)
    monkeypatch.delenv(alpaca.KEY_ENV, raising=False)
    monkeypatch.delenv(alpaca.SECRET_ENV, raising=False)
    ok, why = alpaca.available()
    assert ok is False and alpaca.KEY_ENV in why


def test_available_refuses_a_live_key(monkeypatch):
    monkeypatch.setattr(alpaca, "load_env", lambda *a, **k: None)
    monkeypatch.setenv(alpaca.KEY_ENV, "AKLIVEKEY")
    monkeypatch.setenv(alpaca.SECRET_ENV, "secret")
    ok, why = alpaca.available()
    assert ok is False and "paper" in why.lower()


def test_available_accepts_a_paper_key(monkeypatch):
    monkeypatch.setattr(alpaca, "load_env", lambda *a, **k: None)
    monkeypatch.setenv(alpaca.KEY_ENV, "PKPAPERKEY")
    monkeypatch.setenv(alpaca.SECRET_ENV, "secret")
    ok, _why = alpaca.available()
    assert ok is True
