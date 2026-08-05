"""Tests for the single-writer engine lock.

The failure this prevents is silent: two engines settling the same hour into one
state file double-count the portfolio and nothing complains. So the tests care
about two things equally — that a second engine is refused, and that a *stale*
lock never blocks a legitimate one forever.
"""

import json
import os

from sonar.enginelock import EngineLock, describe_conflict


def lock(tmp_path, role="app"):
    return EngineLock(tmp_path / "engine.lock", role=role)


def test_first_acquire_succeeds(tmp_path):
    assert lock(tmp_path).acquire() is True


def test_reacquiring_your_own_lock_is_idempotent(tmp_path):
    """Calling acquire twice in one process is success, not a self-conflict."""
    lk = lock(tmp_path)
    assert lk.acquire() is True
    assert lk.acquire() is True
    second = EngineLock(lk.path, role="app")   # same pid, new object
    assert second.acquire() is True


def test_a_live_foreign_holder_blocks(tmp_path):
    p = tmp_path / "engine.lock"
    # PID 1 (launchd) always exists and is never us.
    p.write_text(json.dumps({"pid": 1, "role": "agent", "since": 0}))
    assert EngineLock(p, role="app").acquire() is False


def test_stale_lock_is_reclaimed(tmp_path):
    """A killed engine must not block the next one forever."""
    p = tmp_path / "engine.lock"
    dead = _dead_pid()
    p.write_text(json.dumps({"pid": dead, "role": "app", "since": 0}))
    assert EngineLock(p, role="app").acquire() is True


def test_release_removes_the_file(tmp_path):
    lk = lock(tmp_path)
    lk.acquire()
    assert lk.path.exists()
    lk.release()
    assert not lk.path.exists()


def test_release_by_a_non_owner_leaves_it_alone(tmp_path):
    p = tmp_path / "engine.lock"
    p.write_text(json.dumps({"pid": 1, "role": "agent", "since": 0}))
    other = EngineLock(p, role="app")
    other.held = True                 # pretend we think we hold it
    other.release()
    assert p.exists()                 # someone else's lock survives


def test_context_manager_round_trip(tmp_path):
    p = tmp_path / "engine.lock"
    with EngineLock(p, role="app") as lk:
        assert lk.held and p.exists()
    assert not p.exists()


def test_conflict_message_names_the_holder(tmp_path):
    p = tmp_path / "engine.lock"
    p.write_text(json.dumps({"pid": 1, "role": "agent", "since": 0}))
    msg = describe_conflict(EngineLock(p, role="app"))
    assert "agent" in msg and "read-only" in msg


def test_no_conflict_message_when_free(tmp_path):
    assert describe_conflict(lock(tmp_path)) == ""


def test_unwritable_location_degrades_to_running(tmp_path):
    """A lock we cannot write must not stop the engine entirely."""
    lk = EngineLock(tmp_path / "nonexistent\x00bad" / "engine.lock", role="app")
    assert lk.acquire() is True


def _dead_pid() -> int:
    """A PID that is very unlikely to exist."""
    for candidate in range(99999, 90000, -7):
        try:
            os.kill(candidate, 0)
        except ProcessLookupError:
            return candidate
        except PermissionError:
            continue
    return 99999
