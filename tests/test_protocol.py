"""The calibration protocol — measurement wearing a trading bot's clothes.

The calibration table grades positions, and positions only exist when a
person clicks — so on an unclicked install the table stays empty forever, and
on a clicked one it grades discretion. Protocol mode replaces discretion with
a rule: once a day, fixed-small paper positions on the top and bottom of the
confidence ranking, direction by coin flip.

What these tests pin down is the *measurement* properties: random direction
(never derived from the score), fixed risk, the daily gate, the open-position
cap, off-by-default, and persistence of the switch — because a protocol that
quietly re-enters twice a day or sizes up is no longer measuring anything.
"""

import random

import pytest

from sonar import core


@pytest.fixture
def live():
    lv = core.Live()
    lv._protocol_rng = random.Random(11)          # deterministic coin
    return lv


def screen(n: int = 44) -> dict:
    """A full asset payload: confidence rises with the index."""
    return {"assets": [
        {"symbol": f"S{i:02d}", "name": f"Asset {i}", "cls": "Equity",
         "price": 100.0, "volatility": 0.02, "confidence": float(i)}
        for i in range(n)]}


def test_protocol_is_off_by_default(live):
    """Nothing trades until a person flips the switch. The gate lives at the
    _rescan call site, so the flag being False is the whole protection."""
    assert live.protocol_on is False


def test_the_switch_persists_across_a_restart(live):
    live.set_protocol(True)
    assert core.Live().protocol_on is True
    live.set_protocol(False)
    assert core.Live().protocol_on is False


def test_a_days_entries_are_top_and_bottom_of_the_ranking(live):
    live._protocol_scan(screen())
    opened = live.book.open
    assert len(opened) == core.PROTOCOL_TOP + core.PROTOCOL_BOTTOM
    syms = {p.symbol for p in opened}
    top = {f"S{i:02d}" for i in range(44 - core.PROTOCOL_TOP, 44)}
    bottom = {f"S{i:02d}" for i in range(core.PROTOCOL_BOTTOM)}
    assert syms == top | bottom
    assert all(p.protocol for p in opened)


def test_directions_come_from_the_coin_not_the_score(live):
    """Both directions must appear on the same day's entries — a protocol
    that always buys the top rows would be asserting the direction five
    studies failed to find."""
    live._protocol_scan(screen())
    assert {p.direction for p in live.book.open} == {"LONG", "SHORT"}


def test_the_stake_is_fixed_and_small(live):
    live._protocol_scan(screen())
    for p in live.book.open:
        assert p.cash_at_risk <= live.book.starting_cash * core.PROTOCOL_RISK * 1.01


def test_one_pass_per_day(live):
    live._protocol_scan(screen())
    n = len(live.book.open)
    live._protocol_scan(screen())
    assert len(live.book.open) == n, "the daily stamp gates a second pass"


def test_a_new_day_skips_what_is_already_held(live):
    live._protocol_scan(screen())
    n = len(live.book.open)
    live._protocol_last_day = "2020-01-01"        # yesterday, effectively
    live._protocol_scan(screen())
    assert len(live.book.open) == n, "one position per symbol, as ever"


def test_the_open_cap_is_respected(live, monkeypatch):
    monkeypatch.setattr(core, "PROTOCOL_MAX_OPEN", 3)
    live._protocol_scan(screen())
    assert sum(1 for p in live.book.open if p.protocol) == 3


def test_a_thin_screen_is_not_a_ranking(live):
    live._protocol_scan(screen(n=10))
    assert live.book.open == []
    assert live._protocol_last_day == "", \
        "the day is not spent on a half-fetched screen — it retries next rescan"


def test_configure_flips_the_switch_and_config_reports_it(live, monkeypatch):
    monkeypatch.setattr(core.Live, "_rescan", lambda self: None)
    live.configure(None, None, protocol=True)
    cfg = live.config()
    assert cfg["protocol"]["on"] is True
    assert cfg["protocol"]["per_day"] == core.PROTOCOL_TOP + core.PROTOCOL_BOTTOM


def test_turning_it_off_leaves_open_positions_to_resolve(live):
    live._protocol_scan(screen())
    n = len(live.book.open)
    live.set_protocol(False)
    assert len(live.book.open) == n, \
        "closing early would censor exactly the outcomes being measured"
