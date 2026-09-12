"""Alerts say what changed. They never say what to do about it.

The first test is the one that matters. An alert that shouts BUY on a high
confidence score would be the app's first directional claim, and it would be
made on a blended score whose measured IC is *negative* — so it would point at
the wrong instruments with an air of authority. The rest of this file is about
the other way alerts fail: firing so often that the feature gets ignored.
"""

import time

import pytest

from sonar import alerts
from sonar.alerts import Alert, AlertEngine


def _payload(level="Normal", conf=50.0, vol=0.01, gen=None, cat=None):
    return {"generated": gen if gen is not None else time.time(),
            "assets": [{"symbol": "AAPL", "name": "Apple", "lean": level,
                        "confidence": conf, "volatility": vol,
                        "catalyst": cat or {}}]}


# --- the rule the whole module exists to keep ------------------------------ #
def test_no_alert_can_tell_you_to_trade():
    """Not a style preference: five studies found no directional edge, and the
    blended score's measured IC is negative."""
    eng = AlertEngine()
    eng.scan(_payload())
    out = eng.scan(_payload(level="Spike", conf=90.0, vol=0.05))
    assert out, "nothing fired; the test below would pass vacuously"
    banned = ("buy", "sell", "short", "long", "immediately", "now is",
              "opportunity", "act ")
    for a in out:
        text = (a.message + " " + a.severity).lower()
        for word in banned:
            assert word not in text, f"{word!r} in {a.message!r}"


def test_severity_has_no_urgency_level():
    """No 'urgent' or 'critical'. The measured hold is a median of six days —
    manufactured urgency is the behaviour this project was built against."""
    eng = AlertEngine()
    eng.scan(_payload())
    for a in eng.scan(_payload(level="Spike", conf=90.0)):
        assert a.severity in ("info", "notable")


# --- events, not states ---------------------------------------------------- #
def test_the_first_scan_reports_nothing():
    """It establishes the baseline. Alerting on it means every launch fires a
    screenful of transitions that never happened."""
    assert AlertEngine().scan(_payload(level="Spike", conf=95.0)) == []


def test_a_steady_state_does_not_re_fire():
    eng = AlertEngine()
    eng.scan(_payload())
    first = eng.scan(_payload(level="Spike"))
    assert first
    assert eng.scan(_payload(level="Spike")) == [], "a level re-fired as an event"


def test_a_rise_fires_but_a_fall_does_not():
    eng = AlertEngine()
    eng.scan(_payload(level="Quiet"))
    assert eng.scan(_payload(level="Spike"))
    eng2 = AlertEngine()
    eng2.scan(_payload(level="Spike"))
    assert eng2.scan(_payload(level="Quiet")) == [], "a story fading is not an event"


def test_a_small_rise_is_not_notable_enough_to_fire():
    eng = AlertEngine()
    eng.scan(_payload(level="Quiet"))
    assert eng.scan(_payload(level="Normal")) == []


def test_the_cooldown_stops_a_threshold_oscillating():
    eng = AlertEngine(cooldown=3600)
    eng.scan(_payload(level="Quiet"))
    assert eng.scan(_payload(level="Spike"))
    eng.scan(_payload(level="Quiet"))
    assert eng.scan(_payload(level="Spike")) == [], "flapping produced two alerts"


def test_the_cooldown_expires():
    eng = AlertEngine(cooldown=60)
    now = time.time()
    eng.scan(_payload(level="Quiet"), now=now)
    assert eng.scan(_payload(level="Spike"), now=now)
    eng.scan(_payload(level="Quiet"), now=now + 120)
    assert eng.scan(_payload(level="Spike"), now=now + 240)


# --- what each detector measures ------------------------------------------- #
def test_volatility_fires_against_the_instruments_own_level():
    """An absolute threshold would fire permanently on crypto and never on FX."""
    eng = AlertEngine()
    eng.scan(_payload(vol=0.01))
    out = eng.scan(_payload(vol=0.02))
    assert any(a.kind == "volatility" for a in out)


def test_a_permanently_volatile_instrument_does_not_alert():
    eng = AlertEngine()
    eng.scan(_payload(vol=0.06))
    assert not [a for a in eng.scan(_payload(vol=0.06)) if a.kind == "volatility"]


def test_a_big_score_move_fires():
    eng = AlertEngine()
    eng.scan(_payload(conf=40.0))
    assert any(a.kind == "score" for a in eng.scan(_payload(conf=70.0)))


def test_a_small_score_move_does_not():
    eng = AlertEngine()
    eng.scan(_payload(conf=40.0))
    assert not [a for a in eng.scan(_payload(conf=45.0)) if a.kind == "score"]


def test_an_imminent_catalyst_fires():
    eng = AlertEngine()
    eng.scan(_payload())
    out = eng.scan(_payload(cat={"kind": "earnings", "days_away": 1,
                                 "label": "Q3"}))
    assert any(a.kind == "catalyst" for a in out)


def test_a_distant_catalyst_does_not():
    eng = AlertEngine()
    eng.scan(_payload())
    assert not [a for a in eng.scan(_payload(cat={"kind": "earnings",
                                                  "days_away": 20}))
                if a.kind == "catalyst"]


def test_heavy_policy_traffic_fires_once():
    eng = AlertEngine()
    eng.scan(_payload())
    pol = {"level": "Heavy", "n_policy": 4, "window_h": 72}
    assert [a for a in eng.scan(_payload(), policy=pol) if a.kind == "policy"]
    assert not [a for a in eng.scan(_payload(), policy=pol) if a.kind == "policy"]


def test_quiet_policy_does_not_fire():
    eng = AlertEngine()
    eng.scan(_payload())
    assert eng.scan(_payload(), policy={"level": "Quiet"}) == []


# --- staleness ------------------------------------------------------------- #
def test_an_alert_on_old_data_says_so():
    """An equity outside market hours can be hours stale. An alert that does not
    say so implies an immediacy it does not have."""
    eng = AlertEngine()
    now = time.time()
    eng.scan(_payload(gen=now - 7200), now=now)
    out = eng.scan(_payload(level="Spike", gen=now - 7200), now=now)
    assert out[0].stale
    assert "min old" in out[0].line()


def test_a_fresh_alert_does_not_apologise_for_its_age():
    eng = AlertEngine()
    now = time.time()
    eng.scan(_payload(gen=now), now=now)
    out = eng.scan(_payload(level="Spike", gen=now), now=now)
    assert not out[0].stale and "old" not in out[0].line()


def test_the_log_is_bounded():
    eng = AlertEngine(cooldown=0)
    now = time.time()
    eng.scan(_payload(conf=0.0), now=now)
    for i in range(300):
        eng.scan(_payload(conf=float(i % 2) * 80.0), now=now + i)
    assert len(eng.log) <= 200
