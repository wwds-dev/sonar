"""Daily state-file backups.

`state.json` and `portfolio.json` are the experiment's output, they live
outside git, and the writer overwrites them on every change — one corrupt
write or stray delete loses weeks of record. `paths.daily_backup` keeps the
last seven days beside the file; these tests pin the once-a-day semantics,
the pruning, and that a failed backup never blocks the save it protects.
"""

import json

from sonar import engine as eng
from sonar import paths


def test_the_first_save_of_a_day_keeps_yesterdays_file(tmp_path):
    f = tmp_path / "state.json"
    f.write_text('{"v": 1}')
    bak = paths.daily_backup(f, today="2026-09-20")
    assert bak is not None and bak.read_text() == '{"v": 1}'


def test_one_backup_per_day_no_matter_how_often_saved(tmp_path):
    f = tmp_path / "state.json"
    f.write_text('{"v": 1}')
    assert paths.daily_backup(f, today="2026-09-20") is not None
    f.write_text('{"v": 2}')
    assert paths.daily_backup(f, today="2026-09-20") is None
    assert (tmp_path / "state.json.bak.2026-09-20").read_text() == '{"v": 1}', \
        "the day's backup is the first known-good copy, not the latest write"


def test_a_new_day_makes_a_new_backup(tmp_path):
    f = tmp_path / "state.json"
    f.write_text('{"v": 1}')
    paths.daily_backup(f, today="2026-09-20")
    f.write_text('{"v": 2}')
    assert paths.daily_backup(f, today="2026-09-21") is not None
    assert (tmp_path / "state.json.bak.2026-09-21").read_text() == '{"v": 2}'


def test_only_the_newest_seven_days_are_kept(tmp_path):
    f = tmp_path / "state.json"
    f.write_text("{}")
    for day in range(1, 11):                      # ten days of backups
        paths.daily_backup(f, today=f"2026-09-{day:02d}")
    kept = sorted(p.name for p in tmp_path.glob("state.json.bak.*"))
    assert len(kept) == paths.BACKUP_KEEP
    assert kept[0] == "state.json.bak.2026-09-04", "the oldest go first"


def test_a_missing_file_is_not_an_error(tmp_path):
    assert paths.daily_backup(tmp_path / "absent.json") is None


def test_the_engine_saves_leave_a_daily_backup_behind(tmp_path):
    """The wiring, not just the helper: an engine that has saved at least
    twice in a day has yesterday's file beside it."""
    e = eng.Engine(tmp_path / "state.json")
    e.save()
    e.save()
    baks = list(tmp_path.glob("state.json.bak.*"))
    assert len(baks) == 1
    assert json.loads(baks[0].read_text())["bankroll"] == e.bankroll
