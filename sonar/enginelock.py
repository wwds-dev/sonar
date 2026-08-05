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
import time
from pathlib import Path

from . import paths


class EngineLock:
    """Advisory single-writer lock around the paper engine."""

    def __init__(self, path: Path | None = None, role: str = "app") -> None:
        self.path = path or (paths.user_data_base() / "engine.lock")
        self.role = role
        self.held = False

    # -- inspection -------------------------------------------------------- #
    def read(self) -> dict | None:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _alive(pid: int) -> bool:
        """Is that PID still around? Signal 0 checks without delivering."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True          # exists, owned by someone else
        return True

    def holder(self) -> dict | None:
        """The live holder, or ``None``. Clears a stale lock as a side effect."""
        d = self.read()
        if not d:
            return None
        pid = int(d.get("pid", -1))
        if pid == os.getpid():
            return d
        if not self._alive(pid):
            # Stale: the holder died without releasing. Reclaim it rather than
            # blocking the engine forever.
            try:
                self.path.unlink()
            except OSError:
                pass
            return None
        return d

    # -- lifecycle --------------------------------------------------------- #
    def acquire(self) -> bool:
        """Take the lock, or report who has it. Never blocks.

        Re-entrant: if this process already holds it, that is success, not a
        conflict. ``holder()`` has already cleared any stale file by this point,
        so a surviving ``FileExistsError`` means a live holder won a race.
        """
        existing = self.holder()
        if existing:
            if int(existing.get("pid", -1)) == os.getpid():
                self.held = True          # already ours
                return True
            return False

        payload = json.dumps({"pid": os.getpid(), "role": self.role,
                              "since": time.time()})
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
        if d and int(d.get("pid", -1)) == os.getpid():
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
            f"up {mins:.0f} min). This window is showing its state read-only — "
            f"two engines settling the same hour would corrupt the portfolio.")
