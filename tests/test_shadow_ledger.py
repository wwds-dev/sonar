"""The write-once look ledger, and slow resolvers left without a price.

docs/specs/shadow-ledger.md, Verification plan L-1 to L-18 (L-14, the robust
rule's cost in power, sits with V-12 in test_calibration.py). Each test is
named after the mutant it kills. Synthetic books only, and every engine test
runs on a scratch SONAR_DATA (`scratch_data`, which refuses the live
directory): nothing here reads the real book or computes a real outcome.
"""

from __future__ import annotations

import copy
import itertools
import json
import os
import random
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from conftest import LIVE_DATA, LiveDataRefused, refuse_live_data, use_scratch_data
from sonar import calibration, core, paths
from sonar.portfolio import Portfolio, Position

DAY = 86_400.0
B = calibration.SHADOW_BOUNDARY
ROW = {"symbol": "AAA", "name": "Alpha", "price": 100.0, "volatility": 0.02,
       "confidence": 60.0, "cls": "Equity"}


def _utc(y, m, d, h=12) -> float:
    return datetime(y, m, d, h, tzinfo=timezone.utc).timestamp()


NOW = _utc(2026, 10, 12)


# --------------------------------------------------------------------------- #
# Synthetic positions and cohorts
# --------------------------------------------------------------------------- #
def pos(i, conf=50.0, day=0.0, direction="LONG", **kw) -> Position:
    """A week protocol entry at 100, stop 2 away, target 3 away, opened at
    15:00 UTC on ``day``."""
    long_ = direction == "LONG"
    base = dict(id=str(i), symbol="AAA", name="Alpha", direction=direction, units=1.0,
                entry=100.0, target=103.0 if long_ else 97.0, stop=98.0 if long_ else 102.0,
                opened_at=day * DAY + 15 * 3600, cash_at_risk=2.0, confidence=conf, rr=1.5,
                p_profit=0.4, horizon="week", asset_class="Equity", protocol=True)
    base.update(kw)
    return Position(**base)


def shut(p: Position, outcome: str, at: float) -> Position:
    exit_ = {"TARGET": p.target, "STOP": p.stop}.get(outcome, 100.5)
    p.closed_at, p.exit, p.outcome, p.pnl = at, exit_, outcome, 1.0
    return p


def daily(first: int, last: int, close=lambda d: 100.0) -> list:
    """One bar a day at the US session start, 13:30 UTC."""
    return [(d * DAY + 13.5 * 3600, float(close(d))) for d in range(first, last + 1)]


def days_after(t: float, *offsets) -> list[str]:
    return [calibration._utc_day(t + o * DAY) for o in offsets]


SOURCE = {"time": "bar", "target": "book", "stop": "book", "left": "hand", "no_risk": "fill"}


def member(i, state="time", r=0.0, conf=None, r_stop=-1.0, r_target=1.5) -> dict:
    """A readout entry, with every field the ledger records."""
    graded = state in calibration.SHADOW_GRADED
    return {"id": f"{i:04d}", "symbol": "AAA", "direction": "LONG",
            "confidence": float(i % 80) if conf is None else conf, "opened_at": float(i),
            "t_due": float(i), "t_days": 28.0, "rr": 1.5, "booked": None, "state": state,
            "exit": 101.0 if graded else None, "r": r if graded else None, "gap": False,
            "ref": [0.374, 0.574], "source": SOURCE.get(state), "entry": 100.0,
            "stop": 98.0, "target": 103.0, "r_stop": r_stop, "r_target": r_target,
            "closed_at": None, "t_bar": 1.0 if graded else None,
            "t_cut": 2.0 if graded else None}


def rising(n=45, slope=0.03, seed=5) -> list[dict]:
    """``n`` graded members whose R climbs with score: look 1 crosses up."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        x = rng.uniform(0, 80)
        out.append(member(i, r=slope * (x - 40) + rng.gauss(0, 0.6), conf=x))
    return out


# --------------------------------------------------------------------------- #
# The engine on a scratch data directory
# --------------------------------------------------------------------------- #
def _cohort(lv, n=45, per_symbol=False, close=None):
    """``n`` protocol entries 31-75 days old, scores 0, 1.5, 3, ... — every
    one past T. ``per_symbol`` gives each its own symbol (S0, S1, ...), so
    ``close(i)`` can set entry i's closes. Saved, so a restart sees it."""
    model, _ = lv.book.enter(dict(ROW), "LONG", 5, "week", risk_fraction=0.0025, protocol=True)
    lv.book.open.remove(model)
    for i in range(n):
        sym = f"S{i}" if per_symbol else "AAA"
        lv.book.open.append(replace(model, id=f"{sym}-{i:02d}", symbol=sym,
                                    opened_at=NOW - (75 - i) * DAY, confidence=1.5 * i))
    lv.book.save()


def flat(level=100.0, first=NOW - 100 * DAY, days=120, scale=1.0):
    """Daily closes at ``level``, inside both barriers (stop 95.5, target 106.7)."""
    return [(first + k * DAY, scale * level) for k in range(days)]


def wavy(first=NOW - 100 * DAY, days=120, scale=1.0, phase=0):
    """Closes that differ day to day, inside both barriers. ``phase`` restates
    them, unevenly; ``scale`` rescales them, as a split does."""
    return [(first + k * DAY, scale * (100.0 + (((k + phase) * 7) % 11 - 5) * 0.3))
            for k in range(days)]


def rising_close(i):
    """Entry i's closes: R rises with its score, with some scatter, so look 1
    crosses up. Every close stays inside the barriers."""
    return 100.0 + (i - 22) * 0.06 + ((i * 7) % 5 - 2) * 0.05


class Fetch:
    """`assets.fetch_bars` by plan: ``answer(symbol)``; records each call."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, symbol, rng=None):
        self.calls.append(symbol)
        return self.answer(symbol)


def _fetch(monkeypatch, answer):
    stub = Fetch(answer)
    monkeypatch.setattr(core.assets, "fetch_bars", stub)
    return stub


def _restart() -> core.Live:
    """A new holder on the same data directory: what an install or a crash
    and relaunch gives (the old one is simply dropped)."""
    lv = core.Live()
    lv._take_the_book()
    return lv


def _ledger_file():
    return paths.user_data_base() / core.SHADOW_LEDGER_FILE


def _book_json():
    return json.loads((paths.user_data_base() / "portfolio.json").read_text())


def _stamp(p):
    return p.read_bytes(), p.stat().st_mtime_ns


def _texts(shadow, now=NOW):
    pytest.importorskip("PySide6")
    from ui.app import shadow_texts
    t = shadow_texts(shadow, False, now, 28.0)
    return t, "\n".join(t.values())


def _no_result_shown(shadow):
    """S4 on screen: no z, no crossing, no 'the test ends here'."""
    t, everything = _texts(shadow)
    assert "crossed the line" not in everything and "The test ends here" not in everything
    assert "recorded" not in t["status"] or "not recorded" in t["status"]
    assert "z = " not in t["status"]
    return t


@pytest.fixture
def live(scratch_data):
    return core.Live()


# --------------------------------------------------------------------------- #
# L-1, L-2, L-3: what is recorded survives a restart
# --------------------------------------------------------------------------- #
def test_l1_ledger_not_read_a_restart_with_every_fetch_failing_shows_the_same_look(
        live, monkeypatch):
    """S1. The look is evaluated and recorded; the holder is dropped and a new
    one started on the same directory, with every fetch failing. It shows
    the same look — members, z, crossing and recorded date. Kills: the
    ledger not read (the restarted holder would wait for prices instead)."""
    _cohort(live)
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    look = live.shadow["looks"][0]
    assert look["evaluated"] and look["recorded"] and look["recorded_at"] == NOW
    assert live.shadow["ledger"] == {"created_at": NOW, "error": None, "reason": None,
                                     "refused": 0}
    recorded = json.loads(_ledger_file().read_text())["looks"]["1"]

    _fetch(monkeypatch, lambda s: None)
    again = _restart()
    again._shadow_pass(NOW + 3 * DAY)
    assert again.shadow["looks"][0] == look
    assert again.shadow["entries"] == live.shadow["entries"]
    assert json.loads(_ledger_file().read_text())["looks"]["1"] == recorded
    assert again.shadow["mismatches"] == [] and again.shadow["ledger"]["error"] is None
    assert again.shadow["ledger"]["refused"] == 0


@pytest.mark.parametrize("closes", [dict(scale=0.5), dict(phase=3)],
                         ids=["every old close rescaled 2:1", "every old close restated"])
def test_l2_recomputing_over_the_record_rewritten_closes_change_nothing(live, monkeypatch,
                                                                       closes):
    """S1 with the provider's history rewritten after the record: a 2:1
    split (refused by the split guard, so a recomputation would wait) and a
    restatement the guard lets through (a recomputation would grade every
    entry at different closes). Kills: recomputing over the record."""
    _cohort(live)
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    look = live.shadow["looks"][0]
    fresh = calibration.shadow_time_stop(
        live.book.open, [], {"AAA": wavy(**closes)}, NOW + 3 * DAY)
    assert fresh["looks"][0]["z"] != look["z"]        # the mutant would show this
    _fetch(monkeypatch, lambda s: wavy(**closes))
    again = _restart()
    again._shadow_pass(NOW + 3 * DAY)
    assert again.shadow["looks"][0] == look


def test_l3_entries_not_persisted_a_decided_entry_survives_a_restart_with_no_bars(
        live, monkeypatch):
    """S2: one entry graded long before any look is due; restarted with no
    bars, it keeps its outcome. Kills: entries not persisted."""
    _cohort(live, n=1)
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    (entry,) = live.shadow["entries"]
    assert entry["state"] == "time" and entry["source"] == "bar"
    assert not live.shadow["looks"][0]["evaluated"]
    stub = _fetch(monkeypatch, lambda s: None)
    again = _restart()
    again._shadow_pass(NOW + DAY)
    assert again.shadow["entries"] == [entry] and stub.calls == []   # decided: not asked
    rec = json.loads(_ledger_file().read_text())["entries"][entry["id"]]
    assert rec["decided_at"] == NOW and rec["build"] == live.build["version"]
    assert {k: rec[k] for k in ("state", "r", "exit", "t_bar", "t_cut")} == \
        {k: entry[k] for k in ("state", "r", "exit", "t_bar", "t_cut")}


# --------------------------------------------------------------------------- #
# L-4: write-once, a property test
# --------------------------------------------------------------------------- #
def _random_entry(rng, i):
    state = rng.choice(calibration.SHADOW_GRADED + calibration.SHADOW_EXCLUDED
                       + calibration.SHADOW_PENDING)
    e = member(i, state=state, r=rng.uniform(-1, 1.5), conf=rng.uniform(0, 80))
    return {**e, "id": f"p{i}"}


def _random_readout(rng, n):
    entries = [_random_entry(rng, rng.randrange(3 * n)) for _ in range(n)]
    uniq = list({e["id"]: e for e in entries}.values())
    looks = []
    for k, n_k in enumerate(calibration.SHADOW_LOOKS, start=1):
        ev = rng.random() < 0.5
        crossed = rng.random() < .2
        members = ([calibration._member(member(i, r=rng.gauss(0, 1))) for i in range(n_k - 1)]
                   + [calibration._member(member(n_k, state="left"))])
        looks.append({"k": k, "n": n_k, "evaluated": ev, "recorded": False,
                      "z": 3.0 if crossed else rng.gauss(0, 1),
                      "z_lo": 2.5 if crossed else None, "z_hi": 4.0 if crossed else None,
                      "method": "vertices" if crossed else None, "crossed": crossed,
                      "design_closed": False, "used": n_k - 1, "n_excluded": 1,
                      "members": members if ev else None})
    tries = {f"p{rng.randrange(3 * n)}": sorted(days_after(NOW, *rng.sample(range(9), 2)))
             for _ in range(3)}
    return {"entries": uniq, "looks": looks, "price_tries": tries}


def test_l4_overwrite_on_merge_merge_never_changes_what_is_recorded():
    """S3, as a property over 300 random old ledgers and readouts that reuse
    their ids with other states, values and looks. Kills: overwrite on merge
    (of an entry, a look, a constant, an erratum or the header), or a merge
    that writes into `old`."""
    rng = random.Random(12)
    for _ in range(300):
        old = calibration.ledger_new(NOW, "v-old")
        old["errata"] = [{"id": "p1", "reason": "bad tick", "r": 0.1, "date": "2026-11-01"}]
        old["constants"]["boundary"] = rng.choice([B, 2.0])       # even a stale constant
        for _ in range(rng.randrange(3)):
            old, _added = calibration.ledger_merge(old, _random_readout(rng, 8),
                                                   NOW - rng.randrange(100) * DAY, "v-old")
        frozen = copy.deepcopy(old)
        new, added = calibration.ledger_merge(old, _random_readout(rng, 8), NOW, "v-new")
        assert old == frozen
        for key in ("schema", "ledger_id", "created_at", "created_by", "constants", "errata"):
            assert new[key] == old[key], key
        for section in ("entries", "looks"):
            assert all(new[section][k] == v for k, v in old[section].items()), section
        fresh = {k: v for k, v in new["entries"].items() if k not in old["entries"]}
        looks = {k: v for k, v in new["looks"].items() if k not in old["looks"]}
        assert added == len(fresh) + len(looks)
        assert all(v["state"] in calibration.SHADOW_FINAL and v["decided_at"] == NOW
                   and v["build"] == "v-new" for v in fresh.values())
        assert all(v["evaluated_at"] == NOW for v in looks.values())
        assert not set(new["price_tries"]) & set(new["entries"])
        for pid, days in old["price_tries"].items():               # tries only grow...
            assert pid in new["entries"] or set(days) <= set(new["price_tries"][pid])
        assert calibration.ledger_parse(json.dumps(new))[1] is None  # ...and it parses back


def test_l4_a_recorded_look_or_evaluated_again_is_never_added_twice():
    """Kills: adding a look the readout marks as recorded, or one already in
    the ledger under its key."""
    led = calibration.ledger_new(NOW, "v")
    r1 = calibration.shadow_with_ledger({"entries": rising()}, led)
    led, added = calibration.ledger_merge(led, r1, NOW, "v")
    assert added == 46 and set(led["looks"]) == {"1"}
    r2 = calibration.shadow_with_ledger({"entries": rising(slope=-0.03)}, led)
    assert r2["looks"][0]["recorded"] is True
    again, added = calibration.ledger_merge(led, r2, NOW + DAY, "v")
    assert again["looks"] == led["looks"]


# --------------------------------------------------------------------------- #
# L-5: a check that disagrees is shown, and the record kept
# --------------------------------------------------------------------------- #
def _recorded(entries, now=NOW):
    led = calibration.ledger_new(now, "v")
    led, _ = calibration.ledger_merge(led, calibration.shadow_with_ledger(
        {"entries": entries}, led), now, "v")
    return led


def test_l5_mismatch_replaces_the_record_members_and_constants_are_flagged():
    """Kills: a mismatch that replaces the record. An entry opened earlier
    than the recorded members (say, a restored old position) changes look
    1's membership; a changed constant changes the settings. Both are
    listed; the recorded z and crossing are what is shown."""
    entries = rising()
    led = _recorded(entries)
    rec = led["looks"]["1"]
    early = dict(member(9999, r=-1.0, conf=79.0), opened_at=-5.0)
    out = calibration.shadow_with_ledger({"entries": entries + [early]}, led)
    assert out["mismatches"] == [{"k": 1, "why": "members", "recorded_at": NOW}]
    shown = out["looks"][0]
    assert (shown["z"], shown["crossed"], shown["recorded_at"]) == \
        (rec["z"], rec["crossed"], NOW)
    assert calibration.shadow_looks(entries + [early])[0]["z"] != rec["z"]

    changed = copy.deepcopy(led)
    changed["constants"]["grace_days"] = 7
    out = calibration.shadow_with_ledger({"entries": entries}, changed)
    assert out["mismatches"] == [{"k": 1, "why": "constants", "recorded_at": NOW}]
    assert out["looks"][0]["z"] == rec["z"]
    t, _all = _texts({**_full_readout(out), "mismatches": out["mismatches"]})
    assert "The test's fixed settings have changed since look 1 was recorded" in t["warn"]


def _full_readout(partial):
    """The fields shadow_texts reads, around a partial readout."""
    base = calibration.shadow_time_stop([], [], {}, NOW)
    return {**base, **partial, "n_entered": 45, "n_reached": 45, "computed_at": NOW}


def test_l5_the_plain_and_expert_mismatch_lines_name_what_differs(monkeypatch):
    pytest.importorskip("PySide6")
    from ui import words
    d = _full_readout({"looks": [], "mismatches": [
        {"k": 1, "why": "members", "recorded_at": NOW},
        {"k": 2, "why": "z", "recorded_at": NOW}]})
    warn = _texts(d)[0]["warn"]
    assert "look 1 comes out differently (which entries it counts)" in warn
    assert "look 2 comes out differently (the z figure)" in warn
    assert "the result recorded on" in warn and "is kept" in warn
    monkeypatch.setattr(words, "_mode", words.EXPERT)
    warn = _texts(d)[0]["warn"]
    assert "look 1: check differs (members)" in warn and "look 2: check differs (z)" in warn


# --------------------------------------------------------------------------- #
# L-6, L-7, L-15: a ledger that cannot be read, written or found
# --------------------------------------------------------------------------- #
def _crossing_holder(live, monkeypatch):
    """A holder whose look 1 crosses up, recorded."""
    _cohort(live, per_symbol=True)
    _fetch(monkeypatch, lambda s: flat(rising_close(int(s[1:]))))
    live._shadow_pass(NOW)
    assert live.shadow["looks"][0]["crossed"] and live.shadow["looks"][0]["recorded"]


@pytest.mark.parametrize("damage", ["garbage", "truncated", "schema 2", "another id",
                                    "a string R", "marker damaged"])
def test_l6_overwrite_of_a_bad_file_and_result_shown(live, monkeypatch, damage):
    """S4. An unreadable file, another schema, a wrong id, one wrong type, or
    a damaged marker: the file is never written (bytes and mtime unchanged),
    `ledger_error` is "read", and no look is shown as a result — though the
    same closes would cross. Kills: overwriting a bad file; showing a
    result without a record."""
    _crossing_holder(live, monkeypatch)
    f = _ledger_file()
    good = json.loads(f.read_text())
    if damage == "garbage":
        f.write_bytes(b"\x00\xffnot json")
    elif damage == "truncated":
        f.write_text(f.read_text()[:200])
    elif damage == "schema 2":
        f.write_text(json.dumps({**good, "schema": 2}))
    elif damage == "another id":
        f.write_text(json.dumps({**good, "ledger_id": "00000000-0000-4000-8000-000000000000"}))
    elif damage == "a string R":
        pid = next(iter(good["entries"]))
        good["entries"][pid]["r"] = "0.4"
        f.write_text(json.dumps(good))
    else:
        book = _book_json()
        book["shadow_ledger"] = {"ledger_id": good["ledger_id"]}
        (paths.user_data_base() / "portfolio.json").write_text(json.dumps(book))
    before = _stamp(f)
    marker = _book_json().get("shadow_ledger")
    again = _restart()
    for k in range(3):
        again._shadow_pass(NOW + k * DAY)
    assert _stamp(f) == before and _book_json().get("shadow_ledger") == marker
    led = again.shadow["ledger"]
    assert led["error"] == "read" and led["reason"]
    assert all(not lk["recorded"] for lk in again.shadow["looks"])
    assert again.shadow["looks"][0]["evaluated"]      # worked out, and not a result
    t = _no_result_shown(again.shadow)
    # Domain r2 P3-1: the look may well be recorded; the record cannot be used.
    assert t["status"] == "Look 1 of 3: not shown as a result while the record cannot be used."
    assert "could not be read" in t["warn"] and "Record kept since" not in t["note"]


def test_l6_a_read_error_clears_once_the_file_is_put_back(live, monkeypatch):
    """Build note: a holder that cannot read the ledger reads it again each
    pass (never writes it), so putting the right file back is enough."""
    _crossing_holder(live, monkeypatch)
    f = _ledger_file()
    good = f.read_text()
    f.write_text("{")
    again = _restart()
    again._shadow_pass(NOW + DAY)
    assert again.shadow["ledger"]["error"] == "read"
    f.write_text(good)
    again._shadow_pass(NOW + 2 * DAY)
    assert again.shadow["ledger"]["error"] is None and again.shadow["looks"][0]["recorded"]


def test_l7_publish_blocked_and_unrecorded_result_shown(live, monkeypatch):
    """A failed write leaves the readout up with `ledger_error: "write"` and
    no unrecorded result; the next pass writes. Kills: blocking the publish
    on a failed write, and showing a look that was not recorded."""
    _cohort(live, per_symbol=True)
    _fetch(monkeypatch, lambda s: flat(rising_close(int(s[1:]))))
    real = paths.write_atomically

    def failing(path, text):
        if os.path.basename(path) == core.SHADOW_LEDGER_FILE:
            raise PermissionError("read-only volume")
        return real(path, text)

    monkeypatch.setattr(paths, "write_atomically", failing)
    live._shadow_pass(NOW)
    sh = live.shadow
    assert sh["n_reached"] == 45 and sh["ledger"]["error"] == "write"
    assert sh["ledger"]["reason"] == "PermissionError"
    assert sh["looks"][0]["evaluated"] and not sh["looks"][0]["recorded"]
    assert sh["looks"][0]["crossed"]                     # what would have been shown
    assert not _ledger_file().exists()
    assert _book_json()["shadow_ledger"]["ledger_id"]    # the marker went first
    t = _no_result_shown(sh)
    assert "could not be recorded (PermissionError); the next pass tries again" in t["warn"]
    monkeypatch.setattr(paths, "write_atomically", real)
    live._shadow_pass(NOW + 3600)
    sh = live.shadow
    assert sh["ledger"]["error"] is None and sh["looks"][0]["recorded"]
    assert sh["looks"][0]["recorded_at"] == NOW + 3600
    assert json.loads(_ledger_file().read_text())["ledger_id"] == \
        _book_json()["shadow_ledger"]["ledger_id"]
    t, _all = _texts(sh)
    assert "crossed the line" in t["status"]


def test_l7_a_failed_marker_write_starts_nothing(live, monkeypatch):
    """Marker first: when portfolio.json cannot be saved, no file is written
    either, and the next pass starts both."""
    _cohort(live, n=3)
    _fetch(monkeypatch, lambda s: wavy())
    real = live.book.save

    def boom():
        raise OSError("disk full")

    monkeypatch.setattr(live.book, "save", boom)
    live._shadow_pass(NOW)
    assert live.shadow["ledger"]["error"] == "write" and not _ledger_file().exists()
    assert live.book.shadow_ledger is None
    monkeypatch.setattr(live.book, "save", real)
    live._shadow_pass(NOW + 60)
    assert live.shadow["ledger"]["error"] is None and _ledger_file().exists()


def test_l15_silent_fresh_start_a_deleted_ledger_is_missing(live, monkeypatch):
    """S5. Marker present, file deleted, restart: `ledger_error: "missing"`,
    no new file, no new record, the marker untouched. Kills: a silent fresh
    start."""
    _crossing_holder(live, monkeypatch)
    marker = _book_json()["shadow_ledger"]
    _ledger_file().unlink()
    again = _restart()
    for k in range(2):
        again._shadow_pass(NOW + core.SHADOW_LEDGER_RETRY_S + k * DAY)
    assert not _ledger_file().exists()
    assert _book_json()["shadow_ledger"] == marker
    assert again.shadow["ledger"] == {"created_at": marker["created_at"], "error": "missing",
                                      "reason": None, "refused": 0}
    assert not any(lk["recorded"] for lk in again.shadow["looks"])
    t = _no_result_shown(again.shadow)
    assert "The record of results is missing, though this book had one since" in t["warn"]
    assert "restore it from the daily backup" in t["warn"]


def _crash_after_the_anchors(lv):
    """What a kill between the anchors and the file leaves: a marker and a
    sidecar for an empty record, created at NOW, and no file."""
    anchor = {"ledger_id": "00000000-0000-4000-8000-00000000000a", "created_at": NOW,
              "looks": 0, "entries": 0}
    lv.book.shadow_ledger = dict(anchor)
    lv.book.save()
    (paths.user_data_base() / core.SHADOW_SIDECAR_FILE).write_text(json.dumps(anchor))
    return anchor


@pytest.mark.parametrize("age,made", [(core.SHADOW_LEDGER_RETRY_S - 1, True),
                                      (core.SHADOW_LEDGER_RETRY_S + 1, False)])
def test_l15_a_young_marker_with_no_file_is_a_crash_and_is_made_once_more(live,
                                                                          monkeypatch,
                                                                          age, made):
    """Failure modes table: an anchor under ten minutes old that counts
    nothing, with no file, is a crash between the writes; the file is made
    with its id. Older, it is "missing"."""
    _cohort(live, n=3)
    anchor = _crash_after_the_anchors(live)
    _fetch(monkeypatch, lambda s: wavy())
    again = _restart()
    again._shadow_pass(NOW + age)
    assert again.shadow["ledger"]["error"] == (None if made else "missing")
    assert _ledger_file().exists() is made
    if made:
        led = json.loads(_ledger_file().read_text())
        assert (led["ledger_id"], led["created_at"]) == (anchor["ledger_id"], NOW)
        assert len(led["entries"]) == 3


def test_l15_a_young_marker_that_counts_records_is_missing_not_remade(live, monkeypatch):
    """Security P3-3 with the 10-minute rule: an anchor that counts recorded
    entries had a file, so a file gone within ten minutes is "missing"."""
    _cohort(live, n=3)
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    assert _book_json()["shadow_ledger"]["entries"] == 3
    _ledger_file().unlink()
    again = _restart()
    again._shadow_pass(NOW + 60)
    assert again.shadow["ledger"]["error"] == "missing" and not _ledger_file().exists()


def test_l15_restoring_the_file_clears_missing(live, monkeypatch):
    _cohort(live, n=3)
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    f = _ledger_file()
    keep = f.read_text()
    f.unlink()
    again = _restart()
    again._shadow_pass(NOW + DAY)
    assert again.shadow["ledger"]["error"] == "missing"
    f.write_text(keep)
    again._shadow_pass(NOW + DAY + 60)
    assert again.shadow["ledger"]["error"] is None


def test_a_ledger_with_no_marker_is_taken_as_this_books(live, monkeypatch):
    """Build note: a file with no marker (a portfolio.json restored from
    before the marker) is read, never replaced, and the marker is written
    back from it: the sidecar names it."""
    _cohort(live, n=3)
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    led = json.loads(_ledger_file().read_text())
    book = _book_json()
    del book["shadow_ledger"]
    (paths.user_data_base() / "portfolio.json").write_text(json.dumps(book))
    again = _restart()
    again._shadow_pass(NOW + DAY)
    assert again.shadow["ledger"]["error"] is None
    assert _book_json()["shadow_ledger"] == {"ledger_id": led["ledger_id"],
                                             "created_at": led["created_at"],
                                             "looks": 0, "entries": 3}
    assert json.loads(_ledger_file().read_text())["entries"] == led["entries"]


def test_the_day_is_backed_up_before_its_first_overwrite(live, monkeypatch):
    """Architecture: `paths.daily_backup` of the file before a write, as for
    portfolio.json. The day's first overwrite is the pass that starts the
    record (its empty file is written at once, code review P3-2), so the
    day's copy is that empty file; a later write the same day keeps it."""
    _cohort(live, n=2)
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    model = replace(live.book.open[0], id="late", opened_at=NOW - 50 * DAY)
    live.book.open.append(model)
    live._shadow_pass(NOW + 60)
    baks = sorted(paths.user_data_base().glob(core.SHADOW_LEDGER_FILE + ".bak.*"))
    assert len(baks) == 1
    first = json.loads(baks[0].read_text())
    assert first["entries"] == {} and first["ledger_id"] == _book_json()["shadow_ledger"][
        "ledger_id"]
    assert "late" in json.loads(_ledger_file().read_text())["entries"]


# --------------------------------------------------------------------------- #
# L-8: followers and read-only engines
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role", ["follower", "read-only"])
def test_l8_a_follower_writes_neither_the_file_nor_the_marker(live, monkeypatch, role):
    """Kills: a follower (or a waiting window) that writes."""
    _cohort(live, n=3)
    stub = _fetch(monkeypatch, lambda s: wavy())
    if role == "follower":
        live.following = "http://127.0.0.1:1"
    else:
        live.read_only = True
    before = {p.name: _stamp(p) for p in paths.user_data_base().iterdir() if p.is_file()}
    live._shadow_pass(NOW)
    after = {p.name: _stamp(p) for p in paths.user_data_base().iterdir() if p.is_file()}
    assert after == before and stub.calls == []
    assert not _ledger_file().exists() and "shadow_ledger" not in _book_json()
    assert live._ledger is None


# --------------------------------------------------------------------------- #
# L-9, L-10: the grace before "no price"
# --------------------------------------------------------------------------- #
def test_l9_grace_constants_are_pinned():
    """Amendment 1 §4. Changing one needs a new ADR; the ledger stores them."""
    assert calibration.SHADOW_PRICE_GRACE_DAYS == 28
    assert calibration.SHADOW_PRICE_TRIES == 3
    assert calibration.SHADOW_TRY_AFTER_DAYS == 7
    assert calibration.SHADOW_VERTEX_K_MAX == 12
    c = calibration.ledger_constants()
    assert (c["grace_days"], c["grace_tries"], c["try_after_days"], c["vertex_k_max"]) == \
        (28, 3, 7, 12)
    assert c["looks"] == [45, 101, 201] and c["boundary"] == B and c["t_days"]["week"] == 28.0


def _held_look(now, tries, fetched=(), bars=None):
    """44 entries settled by the book before T, and one open (score 40) whose
    symbol has no closes: look 1 waits on it."""
    book = [shut(pos(f"c{i:02d}", conf=float(i * 1.8), day=i * 0.02),
                 "TARGET" if i % 3 else "STOP", (i * 0.02 + 3) * DAY) for i in range(44)]
    slow = pos("slow", conf=40.0, day=1.5, symbol="ZZZ")
    r = calibration.shadow_time_stop([slow], book, {"ZZZ": bars or []}, now,
                                     tries={"slow": tries}, fetched=set(fetched))
    return r, next(e for e in r["entries"] if e["id"] == "slow"), calibration.shadow_due(slow)


def test_l9_grace_left_at_7_and_attempts_ignored_a_member_holds_its_look():
    """S6. Kills: the grace left at 7 days; the tries ignored; a try counted
    before t_T + 7 days. Its look is held, with the date it waits until."""
    t_due = _held_look(0.0, [])[2]
    tries3 = days_after(t_due, 7, 8, 9)
    for now, tries, state in [
            (t_due + 10 * DAY, tries3, "wait_price"),              # grace 7: no_price
            (t_due + 29 * DAY, tries3[:2], "wait_price"),          # tries ignored: no_price
            (t_due + 29 * DAY, days_after(t_due, 1, 2, 3), "wait_price"),   # too early
            (t_due + 29 * DAY, tries3, "no_price")]:
        r, e, _ = _held_look(now, tries)
        assert e["state"] == state, (now, tries)
        look = r["looks"][0]
        assert look["evaluated"] is (state == "no_price")
        if state == "wait_price":
            assert look["price_until"] == pytest.approx(t_due + 28 * DAY)
        else:
            assert look["n_excluded"] == 1 and look["n_filled"] == 1 and look["used"] == 44


def test_l9_today_counts_only_when_the_symbol_was_fetched_and_after_t_plus_7():
    t_due = _held_look(0.0, [])[2]
    now = t_due + 29 * DAY
    two = days_after(t_due, 7, 8)
    r, e, _ = _held_look(now, two, fetched={"ZZZ"})
    assert e["state"] == "no_price" and r["price_tries"]["slow"] == two + [
        calibration._utc_day(now)]
    r, e, _ = _held_look(now, two, fetched={"AAA"})
    assert e["state"] == "wait_price" and r["price_tries"]["slow"] == two
    r, e, _ = _held_look(t_due + 5 * DAY, [], fetched={"ZZZ"})
    assert e["state"] == "wait_price" and "slow" not in r["price_tries"]


def test_l9_a_member_graded_inside_the_grace_releases_the_look():
    t_due = _held_look(0.0, [])[2]
    bars = daily(-5, 45, close=lambda d: 100.5)
    r, e, _ = _held_look(t_due + 10 * DAY, [], bars=bars)
    assert e["state"] == "time" and r["looks"][0]["evaluated"] and r["looks"][0]["used"] == 45


def test_l10_calendar_only_grace_a_holder_off_for_weeks_waits_after_one_failed_fetch(
        live, monkeypatch):
    """S6 / validator P2-5: an entry 32 days past T, a holder back after four
    weeks off, one failed fetch: still waiting. The tried days are kept in
    the ledger, across a restart, and the third distinct day makes it final.
    Kills: a calendar-only grace."""
    _cohort(live, n=1)
    live.book.open[0].opened_at = NOW - 60 * DAY
    live.book.save()
    _fetch(monkeypatch, lambda s: None)
    live._shadow_pass(NOW)
    (e,) = live.shadow["entries"]
    assert e["state"] == "wait_price"
    live._shadow_pass(NOW + 3600)                              # same day: no new try
    pid = e["id"]
    assert json.loads(_ledger_file().read_text())["price_tries"] == {pid: ["2026-10-12"]}
    live._shadow_pass(NOW + DAY)
    assert live.shadow["entries"][0]["state"] == "wait_price"
    again = _restart()
    again._shadow_pass(NOW + 2 * DAY)
    assert again.shadow["entries"][0]["state"] == "no_price"
    assert again.shadow["price_tries"][pid] == ["2026-10-12", "2026-10-13", "2026-10-14"]
    assert pid not in json.loads(_ledger_file().read_text())["entries"]   # not final for good


# --------------------------------------------------------------------------- #
# L-11, L-12: the extreme fills and the robust rule
# --------------------------------------------------------------------------- #
def _with_filled(slope, filled, seed=7, sign=1.0):
    rng = random.Random(seed)
    es = []
    for i in range(45 - len(filled)):
        x = rng.uniform(0, 80)
        es.append(member(i, r=sign * slope * (x - 40) + rng.gauss(0, 0.6), conf=x))
    for j, (x, lo, hi) in enumerate(filled):
        es.append(dict(member(100 + j, state="no_price" if j % 2 else "left", conf=x,
                              r_stop=lo, r_target=hi), opened_at=float(j)))
    return es


def _vertices(es):
    used = [e for e in es if e["state"] in calibration.SHADOW_GRADED]
    filled = [e for e in es if e["state"] in calibration.SHADOW_FILLED]
    xs = [e["confidence"] for e in used + filled]
    return [calibration.hc3_z(xs, [e["r"] for e in used] + list(v))
            for v in itertools.product(*[(e["r_stop"], e["r_target"]) for e in filled])]


@pytest.mark.parametrize("sign", [1.0, -1.0], ids=["up", "down"])
def test_l11_corners_at_minus_1_and_rr_and_one_corner_only(sign):
    """S7 on a hand-built cohort with known vertices. Two members left out at
    the extreme scores; z is well past the line. With each member's own
    barriers — one filled at 97 against a plan of 100, so its R at the
    target is 6.5 — one vertex falls inside the line: not crossed. With the
    barriers at −1 / +R:R every vertex is past it: crossed. Kills: corners
    at −1 / +rr; a rule that checks one corner only. Downward, the wide
    member sits at the other end of the scores, where its target pulls the
    slope back up."""
    lo_x, hi_x = (5.0, 75.0) if sign > 0 else (75.0, 5.0)
    wide = _with_filled(0.025, [(lo_x, -1.0, 6.5), (hi_x, -1.0, 1.5)], sign=sign)
    plan = _with_filled(0.025, [(lo_x, -1.0, 1.5), (hi_x, -1.0, 1.5)], sign=sign)
    for es, crossed in ((wide, False), (plan, True)):
        look = calibration.shadow_looks(es)[0]
        vs = _vertices(es)
        assert look["z_lo"] == pytest.approx(min(vs), rel=1e-12)
        assert look["z_hi"] == pytest.approx(max(vs), rel=1e-12)
        assert look["method"] == "vertices" and look["n_filled"] == 2
        assert look["past_line"] and abs(look["z"]) > 4
        assert look["crossed"] is crossed
        assert crossed is all(sign * v >= B for v in vs)
        assert any(sign * v >= B for v in vs)              # one corner alone would cross
        assert look["design_closed"] is False
    assert calibration.shadow_looks(wide)[1]["design_closed"] is False


def test_l11_each_members_barriers_come_from_its_own_fill():
    """Domain P2-2: a LONG planned 100 / 95 / 110 that fills at 97 has R −1 at
    its stop and +6.5 at its target, not +R:R."""
    p = pos("f", entry=97.0, stop=95.0, target=110.0, rr=2.0)
    r = calibration.shadow_time_stop([p], [], {}, p.opened_at + DAY)
    e = r["entries"][0]
    assert e["r_stop"] == pytest.approx(-1.0) and e["r_target"] == pytest.approx(6.5)
    s = pos("s", direction="SHORT", entry=103.0, stop=105.0, target=90.0)
    e = calibration.shadow_time_stop([s], [], {}, s.opened_at + DAY)["entries"][0]
    assert e["r_stop"] == pytest.approx(-1.0) and e["r_target"] == pytest.approx(6.5)


def test_l11_above_twelve_the_two_slope_extremes_are_used():
    """k > 12: the fills that are the slope's exact extremes, split at the
    regression's mean score (validator Q1b)."""
    rng = random.Random(3)
    filled = [(rng.uniform(0, 80), -1.0, rng.uniform(1.0, 3.0)) for _ in range(13)]
    es = _with_filled(0.02, filled)
    lo, hi, method = calibration.extreme_z(es)
    assert method == "slopes"
    used = [e for e in es if e["state"] in calibration.SHADOW_GRADED]
    fl = [e for e in es if e["state"] in calibration.SHADOW_FILLED]
    xs = [e["confidence"] for e in used + fl]
    mx = sum(xs) / len(xs)
    base = [e["r"] for e in used]
    top = calibration.hc3_z(xs, base + [e["r_target"] if e["confidence"] > mx else e["r_stop"]
                                         for e in fl])
    bottom = calibration.hc3_z(xs, base + [e["r_stop"] if e["confidence"] > mx
                                            else e["r_target"] for e in fl])
    assert (lo, hi) == pytest.approx((min(top, bottom), max(top, bottom)), rel=1e-12)
    assert top > bottom


def test_l11_unknown_barriers_never_cross():
    es = _with_filled(0.05, [(5.0, -1.0, None)])
    look = calibration.shadow_looks(es)[0]
    assert look["past_line"] and look["z_lo"] is None and look["crossed"] is False


def test_l11_the_fast_hc3_is_hc3():
    rng = random.Random(8)
    for _ in range(50):
        n = rng.randrange(3, 60)
        x = [rng.uniform(0, 80) for _ in range(n)]
        z_of = calibration._hc3_z_at(x)
        for _ in range(5):
            y = [rng.gauss(0, 1) for _ in range(n)]
            assert z_of(y) == calibration.hc3_z(x, y)
    assert calibration._hc3_z_at([5.0] * 4)([1, 2, 3, 4]) is None


def _v2_260_looks(entries):
    """shadow_looks as v2.260 shipped it (git 59eb13f), for L-12."""
    order = sorted(entries, key=lambda e: (e["opened_at"], e["id"]))
    out, closed_at_look = [], None
    for k, n in enumerate(calibration.SHADOW_LOOKS, start=1):
        members = order[:n]
        graded = [e for e in members if e["state"] in calibration.SHADOW_GRADED]
        excluded = sum(1 for e in members if e["state"] in ("left", "no_price"))
        entered = len(members)
        final = entered == n and len(graded) + excluded == n
        evaluated = final and closed_at_look is None
        z = (calibration.hc3_z([e["confidence"] for e in graded], [e["r"] for e in graded])
             if evaluated else None)
        crossed = bool(evaluated and z is not None and abs(z) >= B)
        out.append({"k": k, "n": n, "entered": entered, "n_missing": n - entered,
                    "due": max(e["t_due"] for e in members) if entered == n else None,
                    "used": len(graded), "n_excluded": excluded,
                    "n_waiting": sum(1 for e in members if e["state"] == "waiting"),
                    "n_wait_price": sum(1 for e in members if e["state"] == "wait_price"),
                    "evaluated": evaluated, "z": z, "crossed": crossed,
                    "design_closed": closed_at_look is not None})
        if crossed:
            closed_at_look = k
    return out


def test_l12_the_rule_changes_the_no_exclusion_case_never():
    """With nothing left out, the extremes are not computed, and every look
    is v2.260's: 400 random cohorts, some crossing, some still waiting.
    Kills: a robust rule that changes the no-exclusion case."""
    rng = random.Random(21)
    crossings = 0
    for _ in range(400):
        slope = rng.choice([0.0, 0.01, 0.03])
        n = rng.choice([30, 45, 120, 201, 230])
        es = []
        for i in range(n):
            x = rng.uniform(0, 80)
            state = rng.choice(["time", "target", "stop"] * 8 + ["waiting"])
            es.append(member(i, state=state, conf=x, r=slope * (x - 40) + rng.gauss(0, 0.8)))
        new, old = calibration.shadow_looks(es), _v2_260_looks(es)
        for a, b in zip(new, old, strict=True):
            assert {k: a[k] for k in b} == b
            assert (a["z_lo"], a["z_hi"], a["method"], a["n_filled"]) == (None, None, None, 0)
            assert a["recorded"] is False and a["past_line"] == (
                a["evaluated"] and a["z"] is not None and abs(a["z"]) >= B)
        crossings += any(lk["crossed"] for lk in new)
    assert crossings > 20


# --------------------------------------------------------------------------- #
# L-13: no stop distance at fill
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("p", [
    pos("long-below", entry=97.0, stop=98.0), pos("short-above", direction="SHORT",
                                                  entry=103.0, stop=102.0),
    pos("at-stop", entry=98.0, stop=98.0)], ids=lambda p: p.id)
def test_l13_abs_risk_and_old_filing_a_fill_at_or_past_its_stop_is_no_risk(p):
    """Signed distance d·(entry − stop) ≤ 0 is `no_risk` at once — before T,
    with no price asked for — final, and never filled in at the extremes.
    Kills: `abs()` risk (a LONG filled below its stop would get R −1 at a
    stop above it); the old filing under no_price."""
    r = calibration.shadow_time_stop([p], [], {}, p.opened_at + DAY)
    e = r["entries"][0]
    assert (e["state"], e["source"], e["r"], e["r_stop"], e["r_target"]) == \
        ("no_risk", "fill", None, None, None)
    assert r["n_no_risk"] == 1 and r["n_no_price"] == 0
    assert calibration.shadow_decided(r) == {p.id: e}
    assert not calibration.shadow_needs_bars(p, p.opened_at + 60 * DAY)


def test_l13_no_risk_is_left_out_of_the_extremes():
    es = rising(44) + [dict(member(500, state="no_risk", conf=79.0, r_stop=None,
                                   r_target=None), opened_at=50.0)]
    look = calibration.shadow_looks(es)[0]
    assert look["evaluated"] and look["n_excluded"] == 1 and look["n_filled"] == 0
    assert (look["z_lo"], look["z_hi"], look["method"]) == (None, None, None)
    assert look["crossed"] is (abs(look["z"]) >= B) is True


# --------------------------------------------------------------------------- #
# L-16, L-17: errata, and a late grade
# --------------------------------------------------------------------------- #
def test_l16_erratum_rewrites_the_result_never(live, monkeypatch):
    """An erratum a person adds is shown beside its look; `crossed` and
    `design_closed` do not move, and the file's errata are never written
    by the code. Kills: an erratum that rewrites the result."""
    _crossing_holder(live, monkeypatch)
    f = _ledger_file()
    led = json.loads(f.read_text())
    pid = led["looks"]["1"]["members"][3]["id"]
    erratum = {"id": pid, "reason": "bad tick <b>on</b> the T bar", "r": -1.0,
               "date": "2026-11-02"}
    led["errata"].append(erratum)
    f.write_text(json.dumps(led, indent=1))
    again = _restart()
    late = replace(again.book.open[0], id="late", opened_at=NOW - 40 * DAY)
    again.book.open.append(late)                              # so the pass writes
    again._shadow_pass(NOW + DAY)
    sh = again.shadow
    assert sh["errata"] == [{**erratum, "looks": [1]}]
    assert sh["looks"][0]["crossed"] and sh["looks"][0]["recorded"]
    assert [lk["design_closed"] for lk in sh["looks"]] == [False, True, True]
    after = json.loads(f.read_text())
    assert after["errata"] == [erratum] and after["looks"] == led["looks"]
    assert "late" in after["entries"]
    t, _all = _texts(sh)
    assert "crossed the line" in t["status"]
    assert ("Erratum 2 Nov: a result counted in look 1 was later found wrong (bad tick b on "
            "/b the T bar); corrected R -1.00. As fixed in advance, the recorded look is "
            "kept, and it may rest on this error.") in t["warn"]
    assert "<" not in t["warn"]                               # through llm._clean


def test_l17_cross_look_state_leak_a_late_grade_counts_in_a_later_look_only():
    """Validator P3-5: a member final as `no_price` in look 1 is graded later
    and counts in look 2; look 1 stays as recorded, and its check shows "z".
    Kills: a cross-look state leak (look 1 rewritten, or look 2 frozen with
    the old state)."""
    book = [shut(pos(f"e{i:03d}", conf=float((i * 37) % 80), day=float(i), symbol="AAA"),
                 "TARGET" if i % 3 else "STOP", (i + 3) * DAY) for i in range(101)]
    x = pos("e010", conf=40.0, day=10.0, symbol="XXX")
    book[10] = x
    held, done = [x], book[:10] + book[11:]
    t_due = calibration.shadow_due(x)
    now1 = 75 * DAY
    r1 = calibration.shadow_time_stop(held, done, {}, now1,
                                      tries={"e010": days_after(t_due, 7, 8, 9)})
    assert r1["looks"][0]["evaluated"] and not r1["looks"][1]["evaluated"]
    refused: list = []
    led, _ = calibration.ledger_merge(calibration.ledger_new(now1, "v"), r1, now1, "v", refused)
    assert "e010" not in led["entries"] and refused == []     # no_price: not final
    rec1 = copy.deepcopy(led["looks"]["1"])
    assert {m["id"]: m["state"] for m in rec1["members"]}["e010"] == "no_price"

    now2 = 140 * DAY
    bars = {"XXX": daily(-5, 139, close=lambda d: 100.8)}
    r2 = calibration.shadow_time_stop(held, done, bars, now2, ledger=led)
    one, two = r2["looks"][0], r2["looks"][1]
    assert (one["z"], one["used"], one["recorded_at"]) == (rec1["z"], 44, now1)
    assert two["evaluated"] and two["used"] == 101 and not two["recorded"]
    assert {m["id"]: m["state"] for m in two["members"]}["e010"] == "time"
    assert r2["mismatches"] == [{"k": 1, "why": "z", "recorded_at": now1}]
    led2, _ = calibration.ledger_merge(led, r2, now2, "v")
    assert led2["looks"]["1"] == rec1 and led2["looks"]["2"]["used"] == 101


# --------------------------------------------------------------------------- #
# Reading the file: strict, all or nothing
# --------------------------------------------------------------------------- #
def _valid_ledger():
    led = _recorded(rising())
    led["price_tries"] = {"x": ["2026-10-20"]}
    led["errata"] = [{"id": "0001", "reason": "r", "r": None, "date": "2026-11-01"}]
    return led


def _mutate(path_, value):
    def apply(d):
        node = d
        for k in path_[:-1]:
            node = node[k]
        if value is KeyError:
            del node[path_[-1]]
        else:
            node[path_[-1]] = value
    return apply


@pytest.mark.parametrize("change", [
    _mutate(("schema",), 2), _mutate(("schema",), True), _mutate(("ledger_id",), "abc"),
    _mutate(("created_at",), "2026"), _mutate(("extra",), 1), _mutate(("errata",), KeyError),
    _mutate(("constants", "boundary"), "2.315"), _mutate(("constants", "looks"), [45, "x"]),
    _mutate(("entries", "0001", "r"), True), _mutate(("entries", "0001", "state"), "maybe"),
    _mutate(("entries", "0001", "ref"), [0.3]), _mutate(("entries", "0001", "gap"), 0),
    _mutate(("entries", "0001", "extra"), 0),
    _mutate(("looks", "1", "crossed"), "yes"), _mutate(("looks", "1", "k"), 2),
    _mutate(("looks", "1", "members"), []), _mutate(("looks", "1", "method"), "guess"),
    _mutate(("entries", "0001", "t_due"), 10 ** 400),
    _mutate(("price_tries", "x"), ["20 Oct"]), _mutate(("errata", 0, "date"), "2026-13-01"),
    _mutate(("errata", 0, "reason"), ""),
], ids=lambda f: "change")
def test_a_wrong_type_anywhere_is_a_read_error_for_the_whole_file(change):
    led = _valid_ledger()
    assert calibration.ledger_parse(json.dumps(led)) == (led, None)
    change(led)
    got, why = calibration.ledger_parse(json.dumps(led))
    assert got is None and why == "LedgerFormatError"


@pytest.mark.parametrize("raw,why", [("{", "JSONDecodeError"), ("[]", "LedgerFormatError"),
                                     ('{"schema": NaN}', "LedgerFormatError"),
                                     ("[" * 100_000, "RecursionError")])
def test_a_file_that_is_not_a_ledger_is_named_by_its_error(raw, why):
    assert calibration.ledger_parse(raw) == (None, why)


@pytest.mark.parametrize("raw,ok", [(None, None), ({"ledger_id": "x", "created_at": 1.0}, False),
                                    ({"ledger_id": "00000000-0000-4000-8000-000000000000"}, False),
                                    ("marker", False),
                                    ({"ledger_id": "00000000-0000-4000-8000-000000000000",
                                      "created_at": 10 ** 400}, False),
                                    ({"ledger_id": "00000000-0000-4000-8000-000000000000",
                                      "created_at": 1.0}, True)])
def test_the_marker_is_checked_too(raw, ok):
    marker, why = calibration.ledger_marker_parse(raw)
    if ok is None:
        assert (marker, why) == (None, None)
    elif ok:
        assert marker == {**raw, "looks": 0, "entries": 0} and why is None
    else:
        assert marker is None and why == "LedgerFormatError"


# --------------------------------------------------------------------------- #
# The marker in portfolio.json
# --------------------------------------------------------------------------- #
def test_the_marker_round_trips_and_an_older_book_still_loads(tmp_path):
    f = tmp_path / "portfolio.json"
    f.write_text(json.dumps({"starting_cash": 10_000.0, "cash": 9_000.0, "open": [],
                             "closed": [], "equity_log": []}))
    old = Portfolio(f)
    assert old.shadow_ledger is None and old.cash == 9_000.0
    old.save()
    assert "shadow_ledger" not in json.loads(f.read_text())
    marker = {"ledger_id": "00000000-0000-4000-8000-000000000000", "created_at": 5.0}
    old.shadow_ledger = marker
    old.save()
    book = Portfolio(f)
    assert book.shadow_ledger == marker
    book.enter(dict(ROW), "LONG", 5, "week")                   # any later save keeps it
    assert json.loads(f.read_text())["shadow_ledger"] == marker


# --------------------------------------------------------------------------- #
# The UI lines (Design)
# --------------------------------------------------------------------------- #
def test_the_waiting_look_says_until_when_and_what_then(monkeypatch):
    pytest.importorskip("PySide6")
    from ui import words
    t_due = _held_look(0.0, [])[2]
    r, _e, _ = _held_look(t_due + 10 * DAY, [])
    now = t_due + 10 * DAY
    status = _texts({**r, "computed_at": now}, now)[0]["status"]
    assert "1 of its 45 entries are still waiting for a closing price" in status
    assert "It waits for them until" in status
    assert "any still without a price then are left out and the look goes ahead" in status
    monkeypatch.setattr(words, "_mode", words.EXPERT)
    status = _texts({**r, "computed_at": now}, now)[0]["status"]
    assert ", then excluded." in status


def test_the_not_robust_look_line_and_the_extremes(monkeypatch):
    """Past the line but not robust: its own sentence, with the caveat, the
    z on its own side of the line, the extremes row, and the next look."""
    pytest.importorskip("PySide6")
    from ui import words
    es = _with_filled(0.025, [(5.0, -1.0, 6.5), (75.0, -1.0, 1.5)])
    led = _recorded(es)
    r = calibration.shadow_with_ledger({"entries": es}, led)
    d = _full_readout(r)
    t, everything = _texts(d)
    assert "is past the line, but not in every extreme case for the 2 left out" in t["status"]
    assert "This look does not count as crossed; the test goes on." in t["status"]
    assert "It is not a trading edge." in t["status"]
    assert "crossed the line" not in everything and "The test ends here" not in everything
    assert t["rows"].count("The 2 left out have no usable result.") == 1
    assert ("the lowest z found was +0.92 and the highest +6.43. These are extreme cases, "
            "not estimates and not limits.") in t["rows"]
    assert "here it does not hold once the left-out entries are counted" in t["status"]
    assert "the score sorted how these past" not in t["status"]   # not SH_CAVEAT_CROSSED
    assert "Record kept since" in t["note"]
    monkeypatch.setattr(words, "_mode", words.EXPERT)
    t, _ = _texts(d)
    assert "extremes not; not crossed (2 excl.)" in t["status"]
    assert "2 excl.: extreme z" in t["rows"] and "(not a bound)" in t["rows"]


def test_a_payload_that_says_recorded_shows_nothing_while_the_ledger_is_blocked():
    """Belt and braces on the window side: a holder's payload whose ledger
    cannot be read shows no result even if a look claims to be recorded."""
    led = _recorded(rising())
    r = calibration.shadow_with_ledger({"entries": rising()}, led)
    d = {**_full_readout(r), "ledger": {"created_at": NOW, "error": "missing", "reason": None}}
    _no_result_shown(d)


def test_no_risk_is_named_in_the_left_out_row(monkeypatch):
    pytest.importorskip("PySide6")
    from ui import words
    d = _full_readout({"looks": [], "n_no_risk": 2})
    assert "2 whose stop was at or past the fill price (no R can be worked out)" in \
        _texts(d)[0]["rows"]
    monkeypatch.setattr(words, "_mode", words.EXPERT)
    assert "2 risk ≤ 0" in _texts(d)[0]["rows"]


# --------------------------------------------------------------------------- #
# L-18: the live data directory is refused
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("where", [LIVE_DATA, LIVE_DATA / "shadow_ledger.json",
                                   "~/Library/Application Support/SONAR",
                                   "~/Library/Application Support/SONAR/../SONAR/x"])
def test_l18_the_fixture_refuses_the_live_data_directory(where, monkeypatch):
    """S8. Compared as paths only: nothing under the live directory is
    listed, read or created by the check."""
    monkeypatch.delenv(paths.DATA_ENV, raising=False)
    with pytest.raises(LiveDataRefused):
        use_scratch_data(where, monkeypatch)
    assert paths.DATA_ENV not in os.environ


def test_l18_a_symlink_into_the_live_directory_is_refused(tmp_path, monkeypatch):
    """A stand-in for the live directory, so not even its path is resolved."""
    import conftest
    stand_in = tmp_path / "live"
    stand_in.mkdir()
    monkeypatch.setattr(conftest, "LIVE_DATA", stand_in)
    link = tmp_path / "data"
    link.symlink_to(stand_in / "sub", target_is_directory=True)
    with pytest.raises(LiveDataRefused):
        refuse_live_data(link)
    assert refuse_live_data(tmp_path / "elsewhere") == tmp_path / "elsewhere"


def test_l18_the_scratch_directory_is_what_the_engine_uses(scratch_data):
    assert os.environ[paths.DATA_ENV] == str(scratch_data)
    assert paths.user_data_base() == scratch_data.resolve()
    assert core.Live()._shadow_ledger_path().parent == scratch_data.resolve()


# =========================================================================== #
# Fix loop 1 (docs/audit/shadow-ledger-code-reviewer.md, -security-engineer.md,
# -domain-finance-r2.md)
# =========================================================================== #
def _new_book(lv, prefix="NEW", n=45):
    """Book B: ``n`` protocol entries with ids book A never had."""
    model, _ = lv.book.enter(dict(ROW), "LONG", 5, "week", risk_fraction=0.0025, protocol=True)
    lv.book.open.remove(model)
    for i in range(n):
        lv.book.open.append(replace(model, id=f"{prefix}-{i:02d}", symbol=f"S{i}",
                                    opened_at=NOW - (75 - i) * DAY, confidence=1.5 * i))
    lv.book.save()


def _sidecar():
    return paths.user_data_base() / core.SHADOW_SIDECAR_FILE


@pytest.mark.parametrize("sidecar", ["kept", "removed"])
def test_cr_p1_1_another_books_ledger_is_never_adopted(live, monkeypatch, sidecar):
    """Code review P1-1. Book A records a crossing; the book is reset by
    deleting portfolio.json (README's way), with or without the sidecar; book
    B's pass finds a ledger whose positions it does not hold. It is a read
    error naming it as not this book's, and nothing is written. Kills:
    adopting a marker-less ledger without checking it against the book."""
    _crossing_holder(live, monkeypatch)
    (paths.user_data_base() / "portfolio.json").unlink()
    if sidecar == "removed":
        _sidecar().unlink()
    side_before = _stamp(_sidecar()) if _sidecar().exists() else None
    f = _ledger_file()
    before = _stamp(f)
    b = _restart()
    _new_book(b)
    _fetch(monkeypatch, lambda s: wavy())
    b._shadow_pass(NOW + 2 * DAY)
    assert b.shadow["ledger"]["error"] == "read"
    assert b.shadow["ledger"]["reason"] == "LedgerIdError"
    assert _stamp(f) == before and "shadow_ledger" not in _book_json()
    assert (_stamp(_sidecar()) if _sidecar().exists() else None) == side_before
    t = _no_result_shown(b.shadow)
    assert "If the book was reset, the old record has to be moved aside on purpose" in t["warn"]


def test_cr_p1_1_a_marker_less_ledger_of_this_book_is_adopted(live, monkeypatch):
    """The same with this book's own ledger: adopted, and both anchors
    written back from it."""
    _cohort(live, n=3)
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    led = json.loads(_ledger_file().read_text())
    book = _book_json()
    del book["shadow_ledger"]
    (paths.user_data_base() / "portfolio.json").write_text(json.dumps(book))
    _sidecar().unlink()
    again = _restart()
    again._shadow_pass(NOW + DAY)
    want = {"ledger_id": led["ledger_id"], "created_at": led["created_at"], "looks": 0,
            "entries": 3}
    assert again.shadow["ledger"]["error"] is None
    assert _book_json()["shadow_ledger"] == want and json.loads(_sidecar().read_text()) == want


def test_cr_p2_1_an_older_build_drops_the_marker_then_the_file_goes_missing(live,
                                                                            monkeypatch):
    """Code review P2-1 / security P2-2: an older build's save strips the
    marker, then the file is lost. The sidecar still anchors the record:
    "missing", never a fresh start. Kills: the marker as the only anchor."""
    _crossing_holder(live, monkeypatch)
    book = _book_json()
    book.pop("shadow_ledger")
    (paths.user_data_base() / "portfolio.json").write_text(json.dumps(book))
    _ledger_file().unlink()
    for bak in paths.user_data_base().glob("shadow_ledger.json.bak.*"):
        bak.unlink()                                  # the sidecar alone anchors it
    _fetch(monkeypatch, lambda s: wavy())
    again = _restart()
    again._shadow_pass(NOW + 3 * DAY)
    assert again.shadow["ledger"]["error"] == "missing" and not _ledger_file().exists()
    assert "shadow_ledger" not in _book_json()


def test_cr_p2_1_a_backup_alone_is_an_anchor(live, monkeypatch):
    """No marker, no sidecar, no file, but a daily backup: "missing", with
    the undated line."""
    _cohort(live, n=3)
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    assert list(paths.user_data_base().glob("shadow_ledger.json.bak.*"))
    book = _book_json()
    book.pop("shadow_ledger")
    (paths.user_data_base() / "portfolio.json").write_text(json.dumps(book))
    _sidecar().unlink()
    _ledger_file().unlink()
    again = _restart()
    again._shadow_pass(NOW + DAY)
    assert again.shadow["ledger"]["error"] == "missing" and not _ledger_file().exists()
    t, _ = _texts(again.shadow)
    assert "The record of results is missing, though backups of it exist." in t["warn"]


def test_cr_p2_1_an_off_site_backup_is_an_anchor(scratch_data, tmp_path_factory, monkeypatch):
    far = tmp_path_factory.mktemp("offsite")
    (far / "shadow_ledger.json.bak.2026-10-01").write_text("{}")
    monkeypatch.setenv(paths.BACKUP_DIR_ENV, str(far))
    lv = core.Live()
    _cohort(lv, n=1)
    lv._shadow_pass(NOW)
    assert lv.shadow["ledger"]["error"] == "missing" and not _ledger_file().exists()


def test_sec_p2_2_an_unknown_top_level_key_survives_a_save(tmp_path):
    """Security P2-2 (b): a key a later build adds is kept by this one."""
    f = tmp_path / "portfolio.json"
    f.write_text(json.dumps({"starting_cash": 10_000.0, "cash": 10_000.0, "open": [],
                             "closed": [], "equity_log": [], "later_key": {"x": [1, 2]}}))
    book = Portfolio(f)
    book.enter(dict(ROW), "LONG", 5, "week")
    assert json.loads(f.read_text())["later_key"] == {"x": [1, 2]}


def test_sec_p2_1_an_erratum_added_while_the_holder_runs_survives_its_next_write(
        live, monkeypatch):
    """Security P2-1: the holder re-reads a file changed under it and carries
    a person's erratum over. Kills: writing the tenure's copy over it."""
    _crossing_holder(live, monkeypatch)
    f = _ledger_file()
    led = json.loads(f.read_text())
    erratum = {"id": led["looks"]["1"]["members"][3]["id"], "reason": "bad tick", "r": -1.0,
               "date": "2026-11-02"}
    led["errata"].append(erratum)
    f.write_text(json.dumps(led, indent=1))
    live.book.open.append(replace(live.book.open[0], id="late", opened_at=NOW - 40 * DAY))
    live._shadow_pass(NOW + DAY)
    after = json.loads(f.read_text())
    assert "late" in after["entries"] and after["errata"] == [erratum]
    assert live.shadow["errata"] == [{**erratum, "looks": [1]}]


@pytest.mark.parametrize("change", ["another id", "unreadable", "deleted"])
def test_sec_p2_1_a_file_replaced_under_the_holder_is_never_written_over(live, monkeypatch,
                                                                         change):
    _crossing_holder(live, monkeypatch)
    f = _ledger_file()
    led = json.loads(f.read_text())
    if change == "another id":
        f.write_text(json.dumps({**led, "ledger_id": "00000000-0000-4000-8000-00000000000b"}))
    elif change == "unreadable":
        f.write_text("{")
    else:
        f.unlink()
    before = _stamp(f) if f.exists() else None
    live.book.open.append(replace(live.book.open[0], id="late", opened_at=NOW - 40 * DAY))
    live._shadow_pass(NOW + DAY)
    assert (_stamp(f) if f.exists() else None) == before
    assert live.shadow["ledger"]["error"] == ("missing" if change == "deleted" else "read")
    _no_result_shown(live.shadow)


@pytest.mark.parametrize("bad", [dict(symbol="X" * 65), dict(direction="long"),
                                 dict(rr=float("nan"))],
                         ids=["65-character symbol", "lowercase direction", "NaN rr"])
def test_sec_p2_3_a_record_the_reader_would_refuse_is_left_out_and_counted(live,
                                                                           monkeypatch, bad):
    """Security P2-3: one bad entry is refused and counted; the rest are
    recorded, and the file reads back after a restart. Kills: writing what
    the strict reader refuses (unreadable for good), or one bad entry
    blocking every write."""
    _cohort(live, n=3)
    live.book.open[0] = replace(live.book.open[0], **bad)
    live.book.save()
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    assert live.shadow["ledger"]["error"] is None and live.shadow["ledger"]["refused"] == 1
    on_disk = json.loads(_ledger_file().read_text())["entries"]
    assert len(on_disk) == 2 and live.book.open[0].id not in on_disk
    t, _ = _texts(live.shadow)
    assert "1 results could not be recorded" in t["warn"]
    again = _restart()
    again._shadow_pass(NOW + DAY)
    assert again.shadow["ledger"]["error"] is None


def test_cr_p3_3_what_is_written_is_first_read_back(live, monkeypatch):
    """Code review P3-3: the serialised text goes through ledger_parse
    before write_atomically; a refusal is a "write" problem, nothing written."""
    _cohort(live, n=1)
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    before = _stamp(_ledger_file())
    monkeypatch.setattr(calibration, "ledger_parse", lambda raw: (None, "LedgerFormatError"))
    live.book.open.append(replace(live.book.open[0], id="late", opened_at=NOW - 40 * DAY))
    live._shadow_pass(NOW + DAY)
    assert live.shadow["ledger"]["error"] == "write"
    assert live.shadow["ledger"]["reason"] == "LedgerFormatError"
    assert _stamp(_ledger_file()) == before


@pytest.mark.parametrize("how", ["stop", "lock lost"])
def test_cr_p3_1_a_pass_stopped_mid_fetch_writes_and_publishes_nothing(live, monkeypatch,
                                                                       how):
    """Code review P3-1: a quit, or the engine lock lost, while the fetch is
    in flight: no marker, sidecar or file, and no readout. Kills: writing
    after stop or a handover."""
    _cohort(live, n=3)

    class Lock:
        held = True

    live.engine_lock = Lock()
    live._shadow_ledger_open(live.book, NOW)                  # the record exists...
    before = {p.name: _stamp(p) for p in paths.user_data_base().iterdir() if p.is_file()}
    live.book.open.append(replace(live.book.open[0], id="late", opened_at=NOW - 40 * DAY))

    def answer(s):
        if how == "stop":
            live._stop.set()
        else:
            live.engine_lock.held = False
        return wavy()

    _fetch(monkeypatch, answer)
    live.shadow = None
    live._shadow_pass(NOW)                                    # ...and is not touched
    after = {p.name: _stamp(p) for p in paths.user_data_base().iterdir() if p.is_file()}
    assert after == before and live.shadow is None


def test_cr_p3_2_the_empty_file_is_written_with_the_anchors(live):
    """Code review P3-2: opening a new record writes the marker, the sidecar
    and the empty file before any fetch, so a crash later in the pass leaves
    a file."""
    _cohort(live, n=1)
    live._shadow_ledger_open(live.book, NOW)
    led = json.loads(_ledger_file().read_text())
    assert led["entries"] == {} and led["looks"] == {}
    assert _book_json()["shadow_ledger"]["ledger_id"] == led["ledger_id"]
    assert json.loads(_sidecar().read_text())["ledger_id"] == led["ledger_id"]


@pytest.mark.parametrize("edit", ["added", "removed"])
def test_cr_p3_4_a_changed_constants_key_is_a_mismatch_not_unreadable(edit):
    led = _recorded(rising())
    if edit == "added":
        led["constants"]["new_rule"] = 1
    else:
        del led["constants"]["vertex_k_max"]
    back, why = calibration.ledger_parse(json.dumps(led))
    assert why is None
    out = calibration.shadow_with_ledger({"entries": rising()}, back)
    assert out["mismatches"] == [{"k": 1, "why": "constants", "recorded_at": NOW}]


def test_cr_p3_5_no_left_out_warning_for_a_look_that_is_not_a_result():
    """Code review P3-5: unrecorded, or recorded while the record is
    blocked: no "This look rests on the other 40"."""
    es = [member(i, r=0.1 * (i % 5)) for i in range(40)] + \
         [member(i, state="left") for i in range(40, 45)]
    unrecorded = _full_readout({"looks": calibration.shadow_looks(es), "entries": es})
    led = _recorded(es)
    blocked = {**_full_readout(calibration.shadow_with_ledger({"entries": es}, led)),
               "ledger": {"created_at": NOW, "error": "read", "reason": "JSONDecodeError"}}
    shown = _full_readout(calibration.shadow_with_ledger({"entries": es}, led))
    for d, warned in ((unrecorded, False), (blocked, False), (shown, True)):
        assert ("This look rests on the other 40" in _texts(d)[0]["warn"]) is warned


def test_cr_p3_6_isolated_state_clears_the_data_and_backup_variables():
    assert paths.BACKUP_DIR_ENV not in os.environ and paths.DATA_ENV not in os.environ


def test_sec_p3_1_errata_and_members_are_bounded():
    led = _valid_ledger()
    led["errata"] = [dict(led["errata"][0], id=f"{i:04d}") for i in range(1001)]
    assert calibration.ledger_parse(json.dumps(led))[1] == "LedgerFormatError"
    led["errata"] = led["errata"][:1000]
    assert calibration.ledger_parse(json.dumps(led))[1] is None
    shown = calibration.ledger_errata(led)
    assert len(shown) == 1000 and shown[1]["looks"] == [1]
    d = _full_readout({"looks": [], "errata": shown,
                       "mismatches": [{"k": 1, "why": "z", "recorded_at": NOW}] * 50})
    warn = _texts(d)[0]["warn"]
    assert warn.count("Erratum") == 5 and "995 more errata are in the record." in warn
    assert warn.count("comes out differently") == 3


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_sec_p3_2_a_link_or_special_file_is_unreadable_never_followed(live, monkeypatch,
                                                                      tmp_path_factory, kind):
    """Security P3-2: no symlink is followed and no FIFO is waited on."""
    _cohort(live, n=1)
    f = _ledger_file()
    if kind == "symlink":
        real = tmp_path_factory.mktemp("elsewhere") / "x.json"
        real.write_text(json.dumps(calibration.ledger_new(NOW, "v")))
        f.symlink_to(real)
    elif kind == "fifo":
        os.mkfifo(f)
    else:
        f.mkdir()
    _fetch(monkeypatch, lambda s: wavy())
    live._shadow_pass(NOW)
    assert live.shadow["ledger"]["error"] == "read"


def test_sec_p3_3_a_restored_copy_behind_the_anchors_is_refused(live, monkeypatch):
    """Security P3-3: the day's backup is taken before the write that records
    look 1, so restoring it would let look 1 be evaluated again. The anchors
    count one look: the copy is "older than this book's record"."""
    _crossing_holder(live, monkeypatch)
    (bak,) = paths.user_data_base().glob("shadow_ledger.json.bak.*")
    assert json.loads(bak.read_text())["looks"] == {}
    _ledger_file().write_text(bak.read_text())
    again = _restart()
    again._shadow_pass(NOW + DAY)
    assert again.shadow["ledger"]["error"] == "read"
    assert again.shadow["ledger"]["reason"] == "LedgerBehindError"
    t = _no_result_shown(again.shadow)
    assert "It is older than this book's record" in t["warn"]


@pytest.mark.parametrize("where", ["~/library/application support/sonar",
                                   "~/Library/Application Support/Sonar/x"])
def test_l18_sec_p3_4_any_letter_case_of_the_live_directory_is_refused(where, monkeypatch):
    with pytest.raises(LiveDataRefused):
        use_scratch_data(where, monkeypatch)


def _look_record(k=1, z=3.0, crossed=True, z_lo=None, z_hi=None, filled=False):
    n = calibration.SHADOW_LOOKS[k - 1]
    members = [calibration._member(member(i, r=0.1)) for i in range(n - 1)]
    members.append(calibration._member(member(n, state="left" if filled else "no_risk",
                                              r_stop=None, r_target=None)))
    return {"k": k, "n": n, "evaluated_at": NOW, "build": "v", "z": z, "z_lo": z_lo,
            "z_hi": z_hi, "method": "vertices" if filled else None, "crossed": crossed,
            "design_closed": False, "used": n - 1, "n_excluded": 1, "members": members}


@pytest.mark.parametrize("looks,ok", [
    ({"1": _look_record()}, True),
    ({"1": _look_record(z=1.0)}, False),                                 # crossed below the line
    ({"1": _look_record(filled=True, z_lo=1.0, z_hi=4.0)}, False),       # not robust
    ({"1": _look_record(filled=True, z_lo=2.4, z_hi=4.0)}, True),
    ({"1": {**_look_record(), "n": 46}}, False),                         # not look 1's size
    ({"1": {**_look_record(), "design_closed": True}}, False),
    ({"1": _look_record(), "2": _look_record(k=2, crossed=False, z=0.1)}, False),  # after a crossing
], ids=["crossed", "below the line", "not robust", "robust", "wrong n", "design closed",
        "a look after a crossing"])
def test_sec_p3_7_a_recorded_verdict_must_follow_from_its_figures(looks, ok):
    led = {**calibration.ledger_new(NOW, "v"), "looks": looks}
    assert (calibration.ledger_parse(json.dumps(led))[1] is None) is ok


def test_sec_p3_7_only_a_crossed_that_is_true_is_a_crossing():
    led = _recorded(rising())
    out = calibration.shadow_with_ledger({"entries": rising()}, led)
    out["looks"][0]["crossed"] = "yes"
    t, everything = _texts(_full_readout(out))
    assert "crossed the line" not in everything


def test_domain_r2_p3_3_extremes_that_could_not_be_worked_out_say_so(monkeypatch):
    pytest.importorskip("PySide6")
    from ui import words
    es = _with_filled(0.05, [(5.0, -1.0, None)])          # barriers unknown: no extremes
    looks = calibration.shadow_looks(es)
    look = looks[0]
    assert look["past_line"] and look["z_lo"] is None and look["crossed"] is False
    out = {"looks": [{**look, "recorded": True, "recorded_at": NOW}] + looks[1:], "entries": es}
    d = _full_readout(out)
    status = _texts(d)[0]["status"]
    assert "but the 1 left out could not be filled in, so it does not count as crossed" in status
    monkeypatch.setattr(words, "_mode", words.EXPERT)
    assert "extremes n/a; not crossed (1 excl.)" in _texts(d)[0]["status"]
