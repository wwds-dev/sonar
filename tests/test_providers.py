"""Tests for the provider layer.

The behaviour that matters is what happens when a vendor breaks. Yahoo is
undocumented and has already started refusing one endpoint; the point of this
abstraction is that the app keeps working when that spreads. So most of these
simulate failure and assert the fallback, rather than checking a happy path
that only holds while every vendor is up.
"""

import pytest

from sonar import providers


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Never touch the real provider config."""
    monkeypatch.setattr(providers.paths, "user_data_base", lambda: tmp_path)


def test_registry_has_working_keyless_providers():
    keyless = [p for p in providers.REGISTRY.values() if p.tier == "keyless"]
    assert {p.name for p in keyless} >= {"yahoo", "coingecko", "frankfurter"}
    assert all(p.configured for p in keyless), "keyless must need no setup"


def test_stooq_is_absent():
    """It is in every 'free data' list and returns an HTML block page.

    An adapter would parse that into silence and look like a working fallback.
    """
    assert "stooq" not in providers.REGISTRY


def test_keyed_providers_are_unconfigured_without_a_key(monkeypatch):
    for name in ("finnhub", "twelvedata", "alphavantage"):
        p = providers.REGISTRY[name]
        monkeypatch.delenv(p.env_key, raising=False)
        assert p.configured is False
        assert p.signup, "a keyed provider must say where to get a key"


def test_a_key_makes_a_provider_configured(monkeypatch):
    p = providers.REGISTRY["finnhub"]
    monkeypatch.setenv(p.env_key, "test-key")
    assert p.configured is True


def test_providers_are_on_by_default():
    assert providers.is_enabled("yahoo") is True


def test_a_provider_can_be_switched_off_and_stays_off():
    providers.set_enabled("yahoo", False)
    assert providers.is_enabled("yahoo") is False
    assert "yahoo" not in [p.name for p in providers.candidates(providers.QUOTES)]
    providers.set_enabled("yahoo", True)
    assert providers.is_enabled("yahoo") is True


def test_candidates_are_ordered_by_preference():
    got = providers.candidates(providers.QUOTES)
    prefs = [p.preference for p in got]
    assert prefs == sorted(prefs)


def test_unconfigured_providers_are_never_candidates(monkeypatch):
    for name in ("finnhub", "twelvedata", "alphavantage"):
        monkeypatch.delenv(providers.REGISTRY[name].env_key, raising=False)
    names = [p.name for p in providers.candidates(providers.QUOTES)]
    assert "finnhub" not in names


def test_fetch_falls_through_a_failing_provider(monkeypatch):
    """The whole reason the layer exists."""
    calls = []

    def boom(symbol):
        calls.append("first")
        raise RuntimeError("vendor down")

    def ok(symbol):
        calls.append("second")
        return {"symbol": symbol, "price": 42.0}

    a = providers.Provider(name="a", tier="keyless", capabilities={"quotes"},
                           fetchers={"quotes": boom}, preference=1)
    b = providers.Provider(name="b", tier="keyless", capabilities={"quotes"},
                           fetchers={"quotes": ok}, preference=2)
    monkeypatch.setattr(providers, "REGISTRY", {"a": a, "b": b})
    out = providers.fetch("quotes", "AAPL")
    assert out["price"] == 42.0
    assert out["provider"] == "b"
    assert calls == ["first", "second"]


def test_fetch_skips_a_provider_returning_nothing(monkeypatch):
    a = providers.Provider(name="a", tier="keyless", capabilities={"quotes"},
                           fetchers={"quotes": lambda s: None}, preference=1)
    b = providers.Provider(name="b", tier="keyless", capabilities={"quotes"},
                           fetchers={"quotes": lambda s: {"price": 7.0}},
                           preference=2)
    monkeypatch.setattr(providers, "REGISTRY", {"a": a, "b": b})
    assert providers.fetch("quotes", "X")["price"] == 7.0


def test_fetch_returns_none_when_everything_fails(monkeypatch):
    a = providers.Provider(name="a", tier="keyless", capabilities={"quotes"},
                           fetchers={"quotes": lambda s: None}, preference=1)
    monkeypatch.setattr(providers, "REGISTRY", {"a": a})
    assert providers.fetch("quotes", "X") is None


def test_status_reports_what_is_actually_usable():
    s = providers.status()
    assert s["keyless_available"] >= 3
    assert "quotes" in s["active"] and s["active"]["quotes"]
    for row in s["providers"]:
        assert row["note"], "every provider must say what it is good and bad at"
