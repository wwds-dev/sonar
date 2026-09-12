"""Scheduled institutional events.

Central banks are the rare catalyst that is public and on a calendar. The risk
is the opposite of the news component's: the Fed's press feed is mostly
administrative — enforcement actions, supervision, personnel — and counting all
of it as market-moving would repeat the volume-is-not-signal mistake.
"""

import time

from sonar import institutions
from sonar.institutions import Event


def _e(title, kind="release", age_h=1.0, inst="Federal Reserve"):
    return Event(title=title, link="", institution=inst, kind=kind,
                 ts=int(time.time() - age_h * 3600))


def test_policy_language_is_recognised():
    assert _e("FOMC statement on the federal funds rate").policy
    assert _e("Bank Rate maintained at 4%", inst="Bank of England").policy
    assert _e("Minutes of the Federal Open Market Committee").policy


def test_administrative_releases_are_not_policy():
    """The majority of what the Fed publishes. Counting it would drown the signal."""
    assert not _e("Agencies seek comment on third-party risk management guidance").policy
    assert not _e("Federal Reserve Board announces termination of enforcement actions").policy


def test_a_speech_counts_as_a_principal_but_not_as_policy():
    sp = _e("Waller, The Economic Outlook", kind="speech")
    assert sp.principal and sp.kind == "speech"
    assert not institutions._POLICY.search(sp.title)


def test_pressure_is_quiet_with_nothing_recent():
    assert institutions.pressure([])["level"] == "Quiet"


def test_pressure_rises_with_policy_traffic():
    evs = [_e("FOMC statement", kind="policy") for _ in range(3)]
    p = institutions.pressure(evs)
    assert p["level"] == "Heavy" and p["score"] == 1.0


def test_speeches_alone_are_distinguished_from_policy():
    p = institutions.pressure([_e("Powell speaks on the outlook", kind="speech")])
    assert p["level"] == "Speeches only" and p["n_policy"] == 0


def test_old_events_do_not_count_as_pressure():
    assert institutions.pressure([_e("FOMC statement", kind="policy", age_h=500)]
                                 )["level"] == "Quiet"


def test_pressure_asserts_no_direction():
    """A rate decision widens the distribution; it does not pick a tail."""
    p = institutions.pressure([_e("FOMC statement", kind="policy")])
    assert not (set(p) & {"direction", "lean", "side", "bullish", "bearish"})


def test_every_source_declares_an_institution_and_kind():
    for name, (url, inst, kind) in institutions.SOURCES.items():
        assert url.startswith("https://") and inst and kind in (
            "policy", "release", "speech"), name


def test_a_dead_source_yields_nothing_rather_than_raising(monkeypatch):
    monkeypatch.setattr(institutions.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert institutions._fetch_one("Fed press") == []
