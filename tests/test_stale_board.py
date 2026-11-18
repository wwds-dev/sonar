"""A price-source outage is refused and made loud (docs/specs/readiness-h1-h2.md, H2).

A failed Yahoo fetch keeps the old row on the board, and a rescan that fetched
nothing still re-stamps the scan time. So during an outage the board kept a
price on every row, paper entries (a click, or Protocol mode's daily ones)
opened at it, and /api/health stayed green. Now an entry on a row older than
``assets.BOARD_STALE_S`` is refused, Protocol leaves such rows out, and a board
mostly that old is a ``data`` health problem the watchdog alarms.
"""

from __future__ import annotations

import random

import pytest

from sonar import alarm, assets, core, server
from sonar.core import Live

NOW = 1_800_000_000.0
STALE = assets.BOARD_STALE_S


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    lv = Live()
    lv._protocol_rng = random.Random(11)
    return lv


def row(i: int, age: float = 60.0, confidence: float | None = None) -> dict:
    return {"symbol": f"S{i:02d}", "name": f"Asset {i}", "cls": "Equity",
            "price": 100.0, "volatility": 0.02,
            "confidence": float(i if confidence is None else confidence),
            "data_age_s": age}


def board(rows: list[dict], generated: float) -> dict:
    return {"status": "live", "generated": generated, "n": len(rows), "assets": rows}


# --------------------------------------------------------------------------- #
# The age of a row is its fetch age plus the time since the board was built
# --------------------------------------------------------------------------- #
def test_row_age_counts_the_time_since_the_scan():
    assert assets.row_age_s({"data_age_s": 120.0}, NOW - 300.0, NOW) == 420.0
    assert assets.row_age_s({"data_age_s": 120.0}, None, NOW) == 120.0
    assert assets.row_age_s({}, NOW, NOW) == 0.0
    assert assets.row_age_s({"data_age_s": 5.0}, NOW + 10.0, NOW) == 5.0   # clock skew: never younger


# --------------------------------------------------------------------------- #
# A manual trade
# --------------------------------------------------------------------------- #
def test_a_trade_on_a_stale_price_is_refused_and_nothing_is_booked(live, monkeypatch):
    monkeypatch.setattr(core.time, "time", lambda: NOW)
    live.assets = board([row(1, age=STALE + 60.0)], generated=NOW)
    r = live.trade("S01", "LONG")
    assert r["ok"] is False and r["position"] is None
    assert "S01's price is 61 min old" in r["message"] and "not entered" in r["message"]
    assert live.book.open == []


def test_a_trade_on_a_fresh_price_still_enters(live, monkeypatch):
    monkeypatch.setattr(core.time, "time", lambda: NOW)
    live.assets = board([row(1, age=600.0)], generated=NOW - 60.0)
    r = live.trade("S01", "LONG")
    assert r["ok"] is True and len(live.book.open) == 1


def test_a_stalled_rescan_cannot_make_an_old_price_look_young(live, monkeypatch):
    """Fetched 50 min before a scan that was itself 20 min ago: 70 min old."""
    monkeypatch.setattr(core.time, "time", lambda: NOW)
    live.assets = board([row(1, age=50 * 60.0)], generated=NOW - 20 * 60.0)
    r = live.trade("S01", "SHORT")
    assert r["ok"] is False and "70 min old" in r["message"]


# --------------------------------------------------------------------------- #
# Protocol mode
# --------------------------------------------------------------------------- #
def test_protocol_leaves_stale_rows_out_of_the_ranking(live, monkeypatch):
    monkeypatch.setattr(core.time, "time", lambda: NOW)
    rows = [row(i) for i in range(44)]
    rows[43]["data_age_s"] = STALE + 1.0            # the top row is stale
    rows[0]["data_age_s"] = STALE + 1.0             # and the bottom one
    live._protocol_scan(board(rows, generated=NOW))
    syms = {p.symbol for p in live.book.open}
    assert "S43" not in syms and "S00" not in syms
    assert len(syms) == core.PROTOCOL_TOP + core.PROTOCOL_BOTTOM


def test_a_mostly_stale_board_keeps_the_protocol_day_open(live, monkeypatch):
    """An outage (or the minutes after a wake) is a thin screen: nothing is
    entered and the day is not used up, so the next fresh rescan enters."""
    monkeypatch.setattr(core.time, "time", lambda: NOW)
    rows = [row(i, age=STALE + 1.0) for i in range(44)]
    live._protocol_scan(board(rows, generated=NOW))
    assert live.book.open == [] and live._protocol_last_day != core.time.strftime("%Y-%m-%d")
    live._protocol_scan(board([row(i) for i in range(44)], generated=NOW))
    assert len(live.book.open) == core.PROTOCOL_TOP + core.PROTOCOL_BOTTOM


# --------------------------------------------------------------------------- #
# Health and the alarm
# --------------------------------------------------------------------------- #
def _driving(live):
    live._running, live._driving_since, live.last_poll_ok_at = True, NOW - 600.0, NOW - 5.0
    live._scan_at = NOW - 30.0                      # rescanned: the old check is satisfied
    return live


def _kinds(live, at=NOW):
    return [p["kind"] for p in live.health(at)["problems"]]


def test_a_board_mostly_over_an_hour_old_is_a_data_problem(live):
    _driving(live)
    live.assets = board([row(i, age=STALE + 1.0) for i in range(6)]
                        + [row(i, age=60.0) for i in range(6, 10)], generated=NOW)
    (p,) = live.health(NOW)["problems"]
    assert p["kind"] == "data" and p["text"].startswith("6 of 10 board prices are over an hour old")


def test_exactly_half_stale_is_not_a_problem(live):
    _driving(live)
    live.assets = board([row(i, age=STALE + 1.0) for i in range(5)]
                        + [row(i, age=60.0) for i in range(5, 10)], generated=NOW)
    assert _kinds(live) == []


def test_a_board_that_aged_since_its_scan_is_judged_now(live):
    _driving(live)
    live.assets = board([row(i, age=30 * 60.0) for i in range(10)], generated=NOW - 40 * 60.0)
    assert _kinds(live) == ["data"]
    assert _kinds(live, NOW - 20 * 60.0) == []      # the same board twenty minutes earlier


def test_an_empty_board_is_not_a_data_problem(live):
    _driving(live)
    live.assets = {"status": "starting", "assets": []}
    assert _kinds(live) == []


class Thread:
    def is_alive(self):
        return True


def test_stale_board_prices_alarm_after_ten_minutes_then_recover(live):
    sent = []
    dog = server.Watchdog(live, Thread(), notify=lambda t, b: sent.append((t, b)),
                          exit_fn=lambda c: None, log=lambda m: None)
    _driving(live)
    live.assets = board([row(i, age=STALE + 1.0) for i in range(10)], generated=NOW)
    dog.step(NOW)
    assert sent == []
    later = NOW + server.ALARM_AFTER_S["data"] + 1
    live.last_poll_ok_at, live._scan_at = later - 5.0, later - 30.0
    dog.step(later)
    assert len(sent) == 1 and "board prices are over an hour old" in sent[0][1]
    live.assets = board([row(i) for i in range(10)], generated=later)
    dog.step(later + 15)
    assert len(sent) == 2 and sent[1][0] == "SONAR (paper) is working again"


def test_the_push_names_stale_prices_in_fixed_words():
    title, body, priority = alarm.render(
        alarm.Event("data", open_kinds=(("data", 660.0),)), "v2.999", {})
    assert body.startswith("board prices are stale for at least 11 min")
    assert priority == alarm.PRIORITY_ALARM
