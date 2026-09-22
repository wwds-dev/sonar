"""The version shown beside the wordmark, and the honesty of its staleness check.

Three things here are worth pinning rather than trusting.

The **format**, because it is user-facing and sits next to the name: a build
number that stopped zero-padding, or a major that leaked a dotted suffix, would
look like a bug in the app rather than in a version string.

The **staleness verdict**, because its failure mode is silent. Claiming "up to
date" with nothing to compare against is worse than saying nothing — it is the
answer being relied on when someone checks whether the app they just opened
contains the change they asked for. That exact question is why this feature
exists.

The **agreement with the dashboard**, because two places computing a version is
how they come to disagree. The Lab Project Monitor derives the same string from
the same two inputs; a test that they match is cheaper than finding out from a
screenshot that they do not.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from sonar import version as app_version

ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r"^v\d+\.\d{3,}$")


@pytest.fixture(autouse=True)
def _clear_cache():
    """`info()` is cached for the process; these tests change what it reads."""
    app_version.info.cache_clear()
    yield
    app_version.info.cache_clear()


class TestFormat:
    def test_version_reads_as_a_version(self):
        assert VERSION_RE.match(app_version.version_string()), (
            f"{app_version.version_string()!r} is not v<major>.<build>")

    @pytest.mark.parametrize("build,expected", [
        (7, "v2.007"), (42, "v2.042"), (100, "v2.100"), (1234, "v2.1234"),
    ])
    def test_build_is_zero_padded_to_three(self, monkeypatch, build, expected):
        """v2.7 reads as a draft; v2.007 reads as a build.

        Driven with small numbers on purpose. Asserting only against the current
        build tests nothing — 100 is already three digits, so deleting the
        padding entirely would still pass.
        """
        monkeypatch.setattr(app_version, "_read_major", lambda: "2")
        monkeypatch.setattr(app_version, "_git_build",
                            lambda *a, **k: {"build": build, "commit": "x",
                                             "date": "", "source": "git"})
        monkeypatch.setattr(app_version, "_baked", lambda: None)
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: False)
        app_version.info.cache_clear()
        assert app_version.info()["version"] == expected

    def test_the_major_comes_from_the_VERSION_file(self):
        declared = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        assert declared, "VERSION is empty"
        assert app_version.info()["major"] == declared.lstrip("vV").split(".")[0]

    def test_the_VERSION_file_is_one_plain_number(self):
        """It is read by three different programs — the app, the stamp script
        and the dashboard — none of which should have to parse prose."""
        text = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        assert text.isdigit(), f"VERSION should be a bare integer, got {text!r}"

    def test_build_matches_the_repository(self):
        """The number is the commit count — not a number someone maintains."""
        count = subprocess.run(["git", "rev-list", "--count", "HEAD"],
                               cwd=str(ROOT), capture_output=True,
                               text=True).stdout.strip()
        if not count.isdigit():
            pytest.skip("no git metadata in this checkout")
        assert app_version.info()["build"] == int(count)


class TestStalenessIsHonest:
    def test_an_unstamped_build_does_not_claim_to_be_current(self, monkeypatch):
        """Driven through the real `info()` by removing both of its sources,
        rather than by replacing `info` itself — a stub would also stub out the
        `build is None` branch that is the thing under test."""
        monkeypatch.setattr(app_version, "_baked", lambda: None)
        monkeypatch.setattr(app_version, "_git_build", lambda *a, **k: None)
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: True)
        app_version.info.cache_clear()
        verdict = app_version.staleness()
        assert verdict["known"] is False and verdict["current"] is False
        assert "no version stamp" in verdict["detail"]

    def test_no_checkout_is_reported_as_unknown_not_as_current(self, monkeypatch):
        """A packaged app on a machine with no source is the normal case, and
        the one where a confident "up to date" would be a lie."""
        monkeypatch.setattr(app_version, "_git_build", lambda *a, **k: None)
        monkeypatch.setattr(app_version, "_baked",
                            lambda: {"build": 90, "commit": "old",
                                     "date": "", "source": "baked"})
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: True)
        app_version.info.cache_clear()
        verdict = app_version.staleness()
        assert verdict["known"] is False
        assert verdict["current"] is False
        assert "cannot be known" in verdict["detail"]

    def test_a_bundle_behind_the_checkout_says_how_far(self, monkeypatch):
        monkeypatch.setattr(app_version, "_baked",
                            lambda: {"build": 90, "commit": "old",
                                     "date": "", "source": "baked"})
        monkeypatch.setattr(app_version, "_git_build",
                            lambda *a, **k: {"build": 97, "commit": "new",
                                             "date": "", "source": "git"})
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: True)
        app_version.info.cache_clear()
        verdict = app_version.staleness()
        assert verdict["known"] and not verdict["current"]
        assert verdict["behind"] == 7
        assert "7 commits behind" in verdict["detail"]
        assert "v2.097" in verdict["detail"], "say which build would be current"

    def test_a_bundle_finds_the_checkout_its_stamp_points_at(self, monkeypatch, tmp_path):
        """Without this a PyInstaller bundle can only ever say "cannot be
        known": there is no .git anywhere inside it. Correct, and useless on the
        machine the app is developed on, where the source is right there."""
        monkeypatch.setattr(app_version, "_baked",
                            lambda: {"build": 90, "commit": "old", "date": "",
                                     "source": "baked", "root": str(ROOT)})
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: True)
        # A bundle's PROJECT_ROOT is inside the .app and has no .git, which is
        # the whole reason _checkout_root exists. Point it at an empty directory
        # rather than stubbing _git_build, so the real lookup runs.
        monkeypatch.setattr(app_version, "PROJECT_ROOT", tmp_path)
        app_version.info.cache_clear()
        verdict = app_version.staleness()
        assert verdict["known"] is True, verdict["detail"]
        assert verdict["behind"] > 0, "the checkout is well past build 90"

    def test_a_stamped_root_that_is_gone_is_not_invented(self, monkeypatch, tmp_path):
        """A bundle copied to another machine. The recorded path will not exist
        there, and the answer has to go back to "cannot be known"."""
        monkeypatch.setattr(app_version, "_baked",
                            lambda: {"build": 90, "commit": "old", "date": "",
                                     "source": "baked",
                                     "root": str(tmp_path / "gone")})
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: True)
        # Both lookups are real: PROJECT_ROOT is a bundle-like directory with no
        # .git, and the recorded root does not exist. Stubbing _git_build to
        # None made this pass whatever _checkout_root returned, so it tested
        # nothing -- which a mutation deleting that path check proved by not
        # failing anything.
        monkeypatch.setattr(app_version, "PROJECT_ROOT", tmp_path)
        app_version.info.cache_clear()
        verdict = app_version.staleness()
        assert verdict["known"] is False
        assert "cannot be known" in verdict["detail"]

    def test_a_current_bundle_says_so(self, monkeypatch):
        monkeypatch.setattr(app_version, "_baked",
                            lambda: {"build": 100, "commit": "c",
                                     "date": "", "source": "baked"})
        monkeypatch.setattr(app_version, "_git_build",
                            lambda *a, **k: {"build": 100, "commit": "c",
                                             "date": "", "source": "git"})
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: True)
        app_version.info.cache_clear()
        assert app_version.staleness()["current"] is True

    def test_a_bundle_ahead_of_the_checkout_is_not_reported_as_behind(self, monkeypatch):
        """Possible after a checkout is rolled back. Negative "behind" would
        render as "-3 commits behind", which reads as a fault in the app."""
        monkeypatch.setattr(app_version, "_baked",
                            lambda: {"build": 103, "commit": "c",
                                     "date": "", "source": "baked"})
        monkeypatch.setattr(app_version, "_git_build",
                            lambda *a, **k: {"build": 100, "commit": "o",
                                             "date": "", "source": "git"})
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: True)
        app_version.info.cache_clear()
        verdict = app_version.staleness()
        assert verdict["behind"] == 0 and verdict["current"] is True


class TestFrozenPrefersItsOwnStamp:
    def test_a_bundle_reports_the_build_it_was_made_from(self, monkeypatch):
        """Not the checkout's. A package sitting next to a newer source tree is
        still the package that was built, and saying otherwise would make the
        staleness check meaningless."""
        monkeypatch.setattr(app_version, "_baked",
                            lambda: {"build": 90, "commit": "baked",
                                     "date": "", "source": "baked"})
        monkeypatch.setattr(app_version, "_git_build",
                            lambda *a, **k: {"build": 100, "commit": "live",
                                             "date": "", "source": "git"})
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: True)
        app_version.info.cache_clear()
        assert app_version.info()["build"] == 90

    def test_a_checkout_prefers_live_git_over_a_leftover_stamp(self, monkeypatch):
        """So an edit shows up on the next launch without re-stamping."""
        monkeypatch.setattr(app_version, "_baked",
                            lambda: {"build": 90, "commit": "baked",
                                     "date": "", "source": "baked"})
        monkeypatch.setattr(app_version, "_git_build",
                            lambda *a, **k: {"build": 100, "commit": "live",
                                             "date": "", "source": "git"})
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: False)
        app_version.info.cache_clear()
        assert app_version.info()["build"] == 100

    def test_neither_available_is_shown_rather_than_guessed(self, monkeypatch):
        monkeypatch.setattr(app_version, "_baked", lambda: None)
        monkeypatch.setattr(app_version, "_git_build", lambda *a, **k: None)
        monkeypatch.setattr(app_version.paths, "is_frozen", lambda: False)
        app_version.info.cache_clear()
        got = app_version.info()
        assert got["build"] is None
        assert got["version"].endswith("???")
        assert got["source"] == "unknown"


class TestTheDashboardCannotDisagree:
    def test_the_monitor_derives_the_same_string(self):
        """Two implementations of one scheme is how they drift apart.

        `regenerate_dashboard_v2.derive_version()` reads the same VERSION file
        and the same commit count. If this ever fails, one of them changed and
        the dashboard is now describing a version the app does not show.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_lab_monitor", ROOT.parent.parent / "regenerate_dashboard_v2.py")
        if spec is None or spec.loader is None:
            pytest.skip("Lab Project Monitor not present beside this checkout")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        derived, qualifier = module.derive_version(str(ROOT))
        if derived is None:
            pytest.skip("no git metadata for the monitor to derive from")
        assert derived == app_version.version_string(), (
            f"the dashboard would show {derived} while the app shows "
            f"{app_version.version_string()}")
        assert qualifier == "current"


class TestItDoesNotCostTheUIThread:
    def test_info_is_cached(self):
        """It shells out to git. Called once per process, not per repaint."""
        app_version.info.cache_clear()
        app_version.info()
        before = app_version.info.cache_info().hits
        for _ in range(50):
            app_version.info()
        assert app_version.info.cache_info().hits - before == 50

    def test_nothing_on_a_timer_asks_for_the_version(self):
        """`refresh()` runs on a QTimer several times a minute. A git call in
        that path is the UI-thread mistake this app has already made twice."""
        import inspect

        from ui.app import MainWindow

        src = inspect.getsource(MainWindow.refresh)
        for forbidden in ("version_string", "staleness", "tooltip", "version_mod"):
            assert forbidden not in src, (
                f"refresh() calls {forbidden}; the version shells out to git "
                "and refresh() runs on a timer")


class TestTheChangelogTracksRealBuilds:
    """BUILD is derived, so a changelog entry names a build that does not exist
    when it is written — the one the commit being made will produce. That is
    `count + 1`, and it is deterministic. What it is not is *checked*, unless
    something checks it: a forgotten amend leaves the file naming a build that
    never happened, and nobody notices until they try to match a version in a
    screenshot to an entry that is off by one.
    """

    def _newest_entry(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        found = re.findall(r"^## v(\d+)\.(\d+)", text, re.M)
        return found

    def test_there_is_an_entry(self):
        assert self._newest_entry(), "CHANGELOG.md has no ## vN.NNN entry"

    def test_the_newest_entry_is_not_ahead_of_the_repository(self):
        major, build = self._newest_entry()[0]
        current = app_version.info()["build"]
        if current is None:
            pytest.skip("no git metadata in this checkout")
        assert int(build) <= current, (
            f"CHANGELOG's newest entry is v{major}.{build}, but the repository "
            f"is only at build {current}. Either the entry was written for a "
            "commit that was never made, or it needs amending into the commit "
            "that carries it.")

    def test_entries_are_newest_first(self):
        """A changelog that is not in order is one nobody can read the top of."""
        builds = [(int(a), int(b)) for a, b in self._newest_entry()]
        assert builds == sorted(builds, reverse=True), (
            f"CHANGELOG entries are out of order: {builds}")

    def test_the_arc_matches_the_VERSION_file(self):
        major = self._newest_entry()[0][0]
        declared = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        assert major == declared.lstrip("vV").split(".")[0], (
            "the newest changelog entry is on a different arc than VERSION")
