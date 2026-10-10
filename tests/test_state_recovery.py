"""An unreadable state file is recovered from its backups, never overwritten.

`state.json` and `portfolio.json` are the experiment's output and live nowhere
else. Until 2026-10-10 a file that existed but did not parse loaded as nothing
at all: the engine started on a blank $10,000, and its first save replaced the
only copy of the record with that blank — the daily backups kept the old book
for at most seven more days, for whoever noticed in time. Demonstrated on a
copy of the live book before the fix: a truncated portfolio.json loaded as
cash 10,000 / 0 open / 0 closed, and the next save wrote exactly that.
"""

from __future__ import annotations

import json

import pytest

from sonar import paths
from sonar.engine import Engine
from sonar.portfolio import Portfolio

GOOD = {"starting_cash": 10_000.0, "cash": 7_500.0, "open": [], "closed": [],
        "equity_log": [{"t": 1, "v": 10_000.0}]}


def _write(path, data) -> None:
    path.write_text(data if isinstance(data, str) else json.dumps(data))


@pytest.mark.parametrize("junk", ['{"starting_cash": 10000, "cash": 24', "", "[]",
                                  "null", "\x00\x00\x00"],
                         ids=["truncated", "empty", "a list", "null", "binary"])
def test_an_unreadable_book_loads_the_newest_good_backup(tmp_path, junk):
    book = tmp_path / "portfolio.json"
    _write(tmp_path / "portfolio.json.bak.2026-10-08", {**GOOD, "cash": 1.0})
    _write(tmp_path / "portfolio.json.bak.2026-10-09", GOOD)
    _write(book, junk)
    pf = Portfolio(book)
    assert pf.cash == 7_500.0, "not the newest backup that parses"
    kept = list(tmp_path.glob("portfolio.json.unreadable.*"))
    assert len(kept) == 1 and kept[0].read_text() == junk, "the original bytes are kept"


def test_the_first_save_after_recovery_does_not_touch_the_kept_original(tmp_path):
    book = tmp_path / "portfolio.json"
    _write(tmp_path / "portfolio.json.bak.2026-10-09", GOOD)
    _write(book, "{truncated")
    pf = Portfolio(book)
    pf.save()
    assert json.loads(book.read_text())["cash"] == 7_500.0
    assert next(tmp_path.glob("portfolio.json.unreadable.*")).read_text() == "{truncated"


def test_a_corrupt_newest_backup_is_skipped_for_an_older_good_one(tmp_path):
    _write(tmp_path / "portfolio.json.bak.2026-10-08", GOOD)
    _write(tmp_path / "portfolio.json.bak.2026-10-09", "{also broken")
    _write(tmp_path / "portfolio.json", "{broken")
    assert Portfolio(tmp_path / "portfolio.json").cash == 7_500.0


def test_with_no_good_backup_it_starts_clean_and_keeps_the_original(tmp_path, capsys):
    _write(tmp_path / "portfolio.json", "{broken")
    pf = Portfolio(tmp_path / "portfolio.json")
    assert pf.cash == pf.starting_cash and pf.open == [] and pf.closed == []
    assert list(tmp_path.glob("portfolio.json.unreadable.*"))
    assert "no backup parses" in capsys.readouterr().err


def test_a_missing_file_is_a_first_run_not_a_recovery(tmp_path, capsys):
    assert paths.read_state(tmp_path / "portfolio.json") is None
    assert list(tmp_path.iterdir()) == []
    assert capsys.readouterr().err == ""


def test_a_good_file_is_read_and_left_alone(tmp_path):
    _write(tmp_path / "portfolio.json", GOOD)
    assert paths.read_state(tmp_path / "portfolio.json") == GOOD
    assert sorted(p.name for p in tmp_path.iterdir()) == ["portfolio.json"]


def test_the_engine_recovers_its_state_the_same_way(tmp_path):
    state = tmp_path / "state.json"
    _write(tmp_path / "state.json.bak.2026-10-09",
           {"bankroll": 75_144.6, "starting_bankroll": 10_000.0, "trades": [],
            "scorelog": [{"model_up": 0.6, "market_up": 0.5, "outcome": 1.0}] * 190})
    _write(state, '{"bankroll": 7')
    eng = Engine(state)
    assert eng.bankroll == 75_144.6
    assert len(eng.scorelog) == 190, "the model-vs-market sample came back"


def test_a_position_written_by_a_newer_build_still_loads(tmp_path):
    """Rolling the bundle back, or the agent's checkout running a commit
    behind the app, reads a book with fields it has never heard of. That was a
    TypeError nothing caught, and the app did not start."""
    pf = Portfolio(tmp_path / "portfolio.json")
    pos, why = pf.enter({"symbol": "AAA", "name": "A", "price": 100.0,
                         "volatility": 0.02, "confidence": 50.0}, "LONG", 4, "week")
    assert pos, why
    d = json.loads((tmp_path / "portfolio.json").read_text())
    d["open"][0]["field_from_the_future"] = {"x": 1}
    _write(tmp_path / "portfolio.json", d)
    again = Portfolio(tmp_path / "portfolio.json")
    assert [p.symbol for p in again.open] == ["AAA"]
    assert not list(tmp_path.glob("*.unreadable.*")), "a readable file is not quarantined"


# --------------------------------------------------------------------------- #
# the small preference files a person may open in an editor
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("junk", ["[]", "null", "7", '"on"', "{truncated", ""],
                         ids=["list", "null", "number", "string", "truncated", "empty"])
def test_a_junk_protocol_file_opens_with_protocol_off(tmp_path, monkeypatch, junk):
    """A JSON list here reached .get on a list and Live() raised — the app
    did not start."""
    from sonar.core import Live
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    _write(tmp_path / "protocol.json", junk)
    assert Live().protocol_on is False


@pytest.mark.parametrize("junk", ["[]", "null", "7", "{truncated"],
                         ids=["list", "null", "number", "truncated"])
def test_a_junk_providers_file_leaves_every_provider_on(tmp_path, monkeypatch, junk):
    from sonar import providers
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    _write(tmp_path / "providers.json", junk)
    assert all(providers.is_enabled(p) for p in ("binance", "yahoo", "anything"))
    providers.set_enabled("yahoo", False)
    assert providers.is_enabled("yahoo") is False


def test_the_protocol_switch_is_written_in_one_step(tmp_path, monkeypatch):
    """It keeps the calibration sample filling; a write cut short used to read
    back as "off" with nothing on screen to say so."""
    from sonar.core import Live
    monkeypatch.setattr("sonar.paths.user_data_base", lambda: tmp_path)
    writes = []
    real = paths.write_atomically
    monkeypatch.setattr(paths, "write_atomically",
                        lambda p, text: (writes.append(p), real(p, text)))
    live = Live()
    live.set_protocol(True)
    assert writes and writes[-1].name == "protocol.json"
    assert Live().protocol_on is True
    assert not list(tmp_path.glob("*.tmp")), "the temporary file is renamed, not left"
