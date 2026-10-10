"""CI tests this repo against the nested module repos at pinned commits.

Unpinned, CI checked out whatever their default branch held that day, from an
owner the remotes no longer use, so a past green run could not be reproduced
from this repo's history. This fails when a local module checkout moves past
its pin: commit the module, push it, then update the pin with it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/tests.yml").read_text()


def _pins() -> dict[str, tuple[str, str]]:
    found = re.findall(r"repository:\s*(\S+)\s*\n\s*ref:\s*([0-9a-f]{40})\s*\n\s*path:\s*(\S+)",
                       WORKFLOW)
    return {path: (repo, ref) for repo, ref, path in found}


def test_every_module_is_pinned_to_a_commit_on_the_current_owner():
    pins = _pins()
    assert set(pins) == {"sonar/macro", "sonar/playmaker"}
    assert all(repo.startswith("wwds-dev/") for repo, _ in pins.values())


@pytest.mark.parametrize("path", ["sonar/macro", "sonar/playmaker"])
def test_the_pin_is_the_commit_this_checkout_runs(path):
    repo = ROOT / path
    if not (repo / ".git").exists():
        pytest.skip(f"{path} is not a git checkout here")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert head == _pins()[path][1], (
        f"{path} is at {head[:9]} but CI pins {_pins()[path][1][:9]}: push it and update "
        ".github/workflows/tests.yml")


def test_ci_installs_the_locked_hashed_set():
    assert "--require-hashes -r requirements.lock" in WORKFLOW
    lock = (ROOT / "requirements.lock").read_text()
    assert "pyside6==" in lock and "--hash=sha256:" in lock
