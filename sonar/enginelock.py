"""One engine per state file.

The app and the launchd agent drive the same :class:`sonar.core.Live` against
the same ``state.json``. If both run, both settle the same hour and both write
the result — the portfolio double-counts, the equity curve grows two points per
hour, and the calibration table silently fills with duplicates. None of that
announces itself; you would just find the numbers wrong later.

So the engine takes a lock before it starts polling. Whoever gets it drives.
Whoever does not can still *read* the state file and display it — that is the
useful outcome, and it is what makes running the agent plus the app sensible
rather than dangerous.

The lock is a PID file, checked for liveness rather than trusted: a process that
is killed without cleanup leaves the file behind, and a stale lock that blocks
the engine forever would be worse than no lock at all.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from . import paths


def _is_zombie(pid: int) -> bool:
    """Has ``pid`` exited without being reaped?

    Undecidable from ``os.kill`` alone, so ask ``ps``. Any failure answers
    "not a zombie": treating an unknown process as alive keeps the
    single-writer guarantee, which is the safe direction to be wrong in.
    """
    try:
        out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.stdout.strip().startswith("Z")


def _started_at(pid: int) -> float | None:
    """When ``pid`` started (epoch seconds), or None if it cannot be told."""
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=2)
        text = out.stdout.strip()
        return time.mktime(time.strptime(text)) if text else None
    except (OSError, subprocess.SubprocessError, ValueError, OverflowError):
        return None


def _pid_of(record) -> int:
    """The record's pid, or -1 for anything that is not a lock record: a
    non-object file or ``{"pid": null}`` used to raise out of every caller
    and crash-loop the agent at start-up."""
    try:
        return int(record.get("pid", -1))
    except (AttributeError, TypeError, ValueError):
        return -1


class EngineLock:
    """Advisory single-writer lock around the paper engine."""

    def __init__(self, path: Path | None = None, role: str = "app",
                 url: str | None = None) -> None:
        self.path = path or (paths.user_data_base() / "engine.lock")
        self.role = role
        # Where the holder publishes its state, when it does (the daemon's
        # HTTP port). Recorded in the lock so whoever loses the race can
        # follow the winner instead of sitting beside it with nothing to show.
        self.url = url
        self.held = False

    # -- inspection -------------------------------------------------------- #
    def read(self) -> dict | None:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _alive(pid: int) -> bool:
        """Is that PID still around? Signal 0 checks without delivering.

        A zombie does not count. ``os.kill()`` succeeds on a process that has
        exited but not been reaped, and Lab Hub launches SONAR without ever
        waiting on it — so a crashed engine stayed "alive" for as long as the
        launcher lived, and every later launch fell back to read-only with
        nothing on screen to explain why.
        """
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True          # exists, owned by someone else
        return not _is_zombie(pid)

    @classmethod
    def _holds(cls, record: dict) -> bool:
        """Is the process the record names the one that wrote it? A pid is
        reused after a reboot: a stale lock naming a pid some unrelated
        process now has looked alive forever. A process that started after the
        lock was written cannot be its writer."""
        pid = _pid_of(record)
        if not cls._alive(pid):
            return False
        since, started = record.get("since"), _started_at(pid)
        if isinstance(since, (int, float)) and since > 0 and started is not None \
                and started > since + 5.0:       # clock and ps resolution slack
            return False
        return True

    def holder(self) -> dict | None:
        """The live holder, or ``None``. Clears a stale lock as a side effect."""
        d = self.read()
        if not isinstance(d, dict):
            # Missing is "no holder"; a file that is there but is not a lock
            # record (garbage, `null`, a list) is stale, or acquire() would
            # fail on it forever.
            if not self.path.exists():
                return None
            d = {}
        pid = _pid_of(d)
        if pid == os.getpid():
            return d
        if not self._holds(d):
            self._reclaim(d)
            return None
        return d

    def _reclaim(self, stale: dict) -> None:
        """Clear a stale lock — and only that lock. Check-then-unlink let two
        starters both see the same stale file, one create a fresh lock, and the
        other unlink *that*: two drivers. The file is first renamed away (one
        rename wins), and what was moved is checked to be the record that was
        judged stale; if it was a live lock someone just wrote, it goes back."""
        side = self.path.with_name(f"{self.path.name}.stale.{os.getpid()}")
        try:
            os.rename(self.path, side)
        except OSError:
            return                       # someone else cleared it first
        try:
            moved = json.loads(side.read_text())
        except (OSError, ValueError):
            moved = {}
        if moved == stale or not isinstance(moved, dict) or not self._holds(moved):
            side.unlink(missing_ok=True)
            return
        try:                             # a live holder's: put it back, unless taken
            os.link(side, self.path)
        except OSError:
            pass
        side.unlink(missing_ok=True)

    # -- lifecycle --------------------------------------------------------- #
    def acquire(self) -> bool:
        """Take the lock, or report who has it. Never blocks.

        Re-entrant: if this process already holds it, that is success, not a
        conflict. ``holder()`` has already cleared any stale file by this point,
        so a surviving ``FileExistsError`` means a live holder won a race.
        """
        existing = self.holder()
        if existing:
            if _pid_of(existing) == os.getpid():
                self.held = True          # already ours
                return True
            return False

        record = {"pid": os.getpid(), "role": self.role, "since": time.time()}
        if self.url:
            record["url"] = self.url
        payload = json.dumps(record)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # O_EXCL so two starts racing cannot both believe they won.
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                os.write(fd, payload.encode())
            finally:
                os.close(fd)
        except FileExistsError:
            return False                  # lost the race; the winner drives
        except (OSError, ValueError):
            # Cannot write a lock at all (unwritable dir, bad path). Degrade to
            # running unlocked: a lock that cannot be created must not be the
            # reason the engine refuses to start.
            self.held = True
            return True
        self.held = True
        return True

    def release(self) -> None:
        if not self.held:
            return
        d = self.read()
        if d and _pid_of(d) == os.getpid():
            try:
                self.path.unlink()
            except OSError:
                pass
        self.held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


def describe_conflict(lock: EngineLock) -> str:
    """A sentence the UI can show verbatim."""
    d = lock.holder()
    if not d:
        return ""
    role = d.get("role", "another process")
    pid = d.get("pid", "?")
    mins = (time.time() - float(d.get("since", time.time()))) / 60.0
    return (f"Another SONAR engine is already running ({role}, pid {pid}, "
            f"up {mins:.0f} min). Two engines settling the same hour would "
            f"corrupt the portfolio, so this one waits for it to stop and "
            f"takes over then.")
