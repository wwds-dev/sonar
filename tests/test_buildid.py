"""Whether a build can be named (docs/specs/build-traceability.md A1-A7).

`scripts/buildid.py` is the one guard: the verdict the install gate trusts, the
CI pin parser, the nested repos' remote, the print-only release tag, and the
ledger's build string (with its frozen copy in `sonar/version.py`). Every git
case runs against a temporary repository; nothing here reads or writes the
real one's refs or tags.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from sonar import version as app_version

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "buildid.py"
SYS_PY = "/usr/bin/python3"          # the floor: 3.9 on this Mac (A1)


def _load():
    spec = importlib.util.spec_from_file_location("buildid", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bid = _load()

PIN_M = "b3fa3e21af616e03ebbcb9b2813111fb5856a022"
PIN_P = "1162ba5e46c737cebf1edc21c7f74beacb825d5c"
OUTER = "9aa9bd1" + "0" * 33


def clean() -> dict:
    return {"major": "2", "build": 364, "commit": "9aa9bd1", "sha": OUTER, "date": "",
            "dirty": False, "outer_dirty": False,
            "nested": {"macro": {"commit": "b3fa3e2", "sha": PIN_M, "dirty": False},
                       "playmaker": {"commit": "1162ba5", "sha": PIN_P, "dirty": False}},
            "pins": {"macro": PIN_M, "playmaker": PIN_P},
            "traceable": True, "untraceable": [], "source": "baked", "root": "/x"}


def with_(**changes) -> dict:
    s = clean()
    for path, value in changes.items():
        keys = path.split("__")
        at = s
        for k in keys[:-1]:
            at = at[k]
        if value is DROP:
            at.pop(keys[-1])
        else:
            at[keys[-1]] = value
    return s


DROP = object()
COPY = {"commit": "", "sha": "", "dirty": None}


# --------------------------------------------------------------------------- #
# verdict (A4)
# --------------------------------------------------------------------------- #
def test_a_full_clean_stamp_at_the_pins_is_traceable():
    assert bid.verdict(clean()) == []


@pytest.mark.parametrize("stamp,want", [
    (with_(dirty=True, outer_dirty=True), ["outer: built from a tree with uncommitted changes"]),
    (with_(dirty=True, outer_dirty=None), ["outer: whether the tree was clean is unknown"]),
    (with_(outer_dirty="false"), ["outer: whether the tree was clean is unknown"]),
    # A stamp older than `outer_dirty`: the summary `dirty` stands in.
    (with_(outer_dirty=DROP, dirty=True), ["outer: built from a tree with uncommitted changes"]),
    (with_(outer_dirty=DROP, dirty=None), ["outer: whether the tree was clean is unknown"]),
    (with_(outer_dirty=DROP, dirty=DROP), ["outer: whether the tree was clean is unknown"]),
    (with_(outer_dirty=DROP, dirty="false"), ["outer: whether the tree was clean is unknown"]),
    # Summary dirty with no cause named anywhere: still not clean.
    (with_(dirty=True), ["dirty: the stamp says dirty or unknown but names no cause"]),
    (with_(dirty=None), ["dirty: the stamp says dirty or unknown but names no cause"]),
    (with_(commit=""), ["outer: no commit"]),
    (with_(commit="1234567"), [f"outer: commit 1234567 is not sha {OUTER[:9]}"]),
    (with_(nested__macro__commit="1234567"), [f"macro: commit 1234567 is not sha {PIN_M[:9]}"]),
    (with_(sha="9aa9bd1"), ["outer: no commit"]),
    (with_(sha=DROP), ["outer: no commit"]),
    (with_(nested={}), ["macro: not in the stamp (sonar/macro missing at build time, or skipped by an older stamper)",
                        "playmaker: not in the stamp (sonar/playmaker missing at build time, or skipped by an older stamper)"]),
    (with_(nested__playmaker=DROP),
     ["playmaker: not in the stamp (sonar/playmaker missing at build time, or skipped by an older stamper)"]),
    (with_(nested__macro=dict(COPY)),
     ["macro: a copy with no git history; its code cannot be named"]),
    (with_(nested__macro__dirty=True), ["macro: uncommitted changes"]),
    (with_(nested__playmaker__dirty=None), ["playmaker: whether it is clean is unknown"]),
    (with_(pins={}), ["pins: the stamp records no CI pins"]),
    (with_(pins=DROP), ["pins: the stamp records no CI pins"]),
    (with_(pins={}, pins_error="cannot read the CI pins (boom)"),
     ["pins: cannot read the CI pins (boom)"]),
    (with_(pins__playmaker="1162ba5"), ["pins: no valid CI pin for playmaker"]),
    (with_(nested__macro__sha="c" * 40, nested__macro__commit="ccccccc"),
     [f"macro: stamp {'c' * 9}, CI pins {PIN_M[:9]}"]),
    (with_(nested__playmaker__sha=DROP), [f"playmaker: stamp (none), CI pins {PIN_P[:9]}"]),
])
def test_each_reason_alone(stamp, want):
    assert bid.verdict(stamp) == want


def test_outer_dirty_nested_clean_is_refused():
    # Domain P1-1: the nested "dirty": false entries cannot stand in for the
    # top-level key, which the old grep let them do.
    s = with_(dirty=True, outer_dirty=True)
    assert '"dirty": false' in json.dumps(s)
    assert bid.verdict(s) == ["outer: built from a tree with uncommitted changes"]


def test_a_dirty_nested_repo_is_not_also_a_dirty_outer_tree():
    # Domain P3-2: the summary `dirty` is true, the outer tree is clean.
    s = with_(dirty=True, nested__playmaker__dirty=True)
    assert bid.verdict(s) == ["playmaker: uncommitted changes"]


def test_the_stamps_own_traceable_flag_is_ignored():
    s = with_(nested={}, traceable=True, untraceable=[])
    assert len(bid.verdict(s)) == 2


def test_the_v2_340_stamp_is_refused_on_every_ground_it_has():
    v340 = {"build": 340, "commit": "8e7d024", "dirty": False, "nested": {},
            "source": "baked", "root": "/x"}
    assert bid.verdict(v340) == [
        "outer: no commit",
        "macro: not in the stamp (sonar/macro missing at build time, or skipped by an older stamper)",
        "playmaker: not in the stamp (sonar/playmaker missing at build time, or skipped by an older stamper)",
        "pins: the stamp records no CI pins"]


def test_the_reasons_come_in_a_fixed_order():
    s = with_(dirty=True, outer_dirty=True, commit="", nested__macro=dict(COPY),
              nested__playmaker__dirty=True, pins={})
    assert bid.verdict(s) == [
        "outer: built from a tree with uncommitted changes", "outer: no commit",
        "macro: a copy with no git history; its code cannot be named",
        "playmaker: uncommitted changes", "pins: the stamp records no CI pins"]


def test_the_names_are_the_apps_nested_repos():
    assert bid.NAMES == app_version.NESTED_REPOS


# --------------------------------------------------------------------------- #
# the CI pins (A3)
# --------------------------------------------------------------------------- #
def test_the_real_workflow_parses():
    found = bid.pins((ROOT / ".github/workflows/tests.yml").read_text())
    assert set(found) == {"sonar/macro", "sonar/playmaker"}
    assert found["sonar/macro"][0] == "wwds-dev/sonar_macro"
    assert all(len(sha) == 40 for _, sha in found.values())


def _yml(*steps: str) -> str:
    return "jobs:\n  t:\n    steps:\n" + "".join(steps)


def _step(lines: list[str]) -> str:
    return "      - uses: actions/checkout@v7\n        with:\n" + \
        "".join(f"          {line}\n" for line in lines)


M = ["repository: wwds-dev/sonar_macro", f"ref: {PIN_M}", "path: sonar/macro"]
P = ["repository: wwds-dev/sonar_playmaker", f"ref: {PIN_P}", "path: sonar/playmaker"]
WANT = {"sonar/macro": ("wwds-dev/sonar_macro", PIN_M),
        "sonar/playmaker": ("wwds-dev/sonar_playmaker", PIN_P)}


@pytest.mark.parametrize("macro", [
    M,
    [M[2], M[0], M[1]],                                             # reordered
    ['repository: "wwds-dev/sonar_macro"', f"ref: '{PIN_M}'", 'path: "sonar/macro"'],
    [M[0] + "   # moved owner", f"ref: {PIN_M}  # 2026-10-12", M[2]],
])
def test_reordered_quoted_and_commented_steps_parse(macro):
    text = _yml("      - uses: actions/checkout@v7\n        with:\n          fetch-depth: 0\n",
                _step(macro), "      # path: sonar/macro (a comment is not a step)\n",
                _step(P))
    assert bid.pins(text) == WANT


@pytest.mark.parametrize("macro,why", [
    ([M[0], "ref: b3fa3e2", M[2]], "not a full 40-hex"),
    (["repository: someone/sonar_macro", M[1], M[2]], "is not wwds-dev/sonar_macro"),
    (["repository: wwds-dev/sonar_playmaker", M[1], M[2]], "is not wwds-dev/sonar_macro"),
    ([M[1], M[2]], "is not wwds-dev/sonar_macro"),
    ([M[0], M[1], M[2], M[1]], "twice"),
])
def test_bad_steps_fail_closed(macro, why):
    with pytest.raises(ValueError, match=why):
        bid.pins(_yml(_step(macro), _step(P)))


def test_a_path_checked_out_twice_at_different_pins_or_missing_fails_closed():
    other = [M[0], f"ref: {'d' * 40}", M[2]]
    with pytest.raises(ValueError, match="twice, at different pins"):
        bid.pins(_yml(_step(M), _step(other), _step(P)))
    with pytest.raises(ValueError, match="sonar/playmaker"):
        bid.pins(_yml(_step(M)))


def test_the_same_pins_in_several_jobs_are_allowed():
    # Code review P3-3.
    two_jobs = _yml(_step(M), _step(P)) + "  lint:\n    steps:\n" + _step(M) + _step(P)
    assert bid.pins(two_jobs) == WANT


def test_a_duplicate_key_outside_the_pin_steps_does_not_matter():
    # Code review P3-3: one odd step elsewhere must not break every caller.
    odd = "      - name: x\n        run: a\n        run: b\n"
    assert bid.pins(_yml(odd, _step(M), _step(P))) == WANT


@pytest.mark.parametrize("extra,why", [
    # Security P3-1: fake keys in a run block would parse as a pin.
    ("      - run: |\n          repository: wwds-dev/sonar_macro\n          ref: " + "d" * 40
     + "\n          path: sonar/macro\n", "not a plain actions/checkout"),
    ("      - uses: actions/checkout@v7\n        with: {repository: wwds-dev/sonar_macro, "
     "path: sonar/macro}\n", "flow mapping"),
    ("      - uses: actions/checkout@v7\n        with:{repository: x}\n", "flow mapping"),
    ("      - name: other\n        run: git clone https://github.com/wwds-dev/sonar_macro\n",
     "outside a pin step"),
    ("      - run: cp -r x sonar/playmaker\n", "outside a pin step"),
])
def test_a_workflow_ci_could_read_differently_fails_closed(extra, why):
    with pytest.raises(ValueError, match=why):
        bid.pins(_yml(_step(M), _step(P), extra))


def test_a_mention_before_any_step_fails_closed():
    with pytest.raises(ValueError, match="outside any step"):
        bid.pins("env:\n  X: sonar/macro\n" + _yml(_step(M), _step(P)))


def test_pins_shell_output_under_the_system_python():
    r = subprocess.run([SYS_PY, "-I", str(SCRIPT), "pins", "--shell",
                        str(ROOT / ".github/workflows/tests.yml")],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    rows = [line.split() for line in r.stdout.splitlines()]
    want = bid.pins((ROOT / ".github/workflows/tests.yml").read_text())
    assert rows == [[p, *want[p]] for p in ("sonar/macro", "sonar/playmaker")]


# --------------------------------------------------------------------------- #
# remote-url (A5)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("origin,want", [
    ("https://github.com/wwds-dev/sonar.git", "https://github.com/wwds-dev/sonar_macro.git"),
    ("https://github.com/wwds-dev/sonar", "https://github.com/wwds-dev/sonar_macro.git"),
    ("git@github.com:wwds-dev/sonar.git", "git@github.com:wwds-dev/sonar_macro.git"),
    ("ssh://git@github.com/wwds-dev/sonar.git", "ssh://git@github.com/wwds-dev/sonar_macro.git"),
    ("file:///tmp/x/remotes/wwds-dev/sonar.git", "file:///tmp/x/remotes/wwds-dev/sonar_macro.git"),
    ("", "https://github.com/wwds-dev/sonar_macro.git"),
    ("not a url", "https://github.com/wwds-dev/sonar_macro.git"),
])
def test_remote_url_keeps_the_outer_transport(origin, want):
    assert bid.remote_url(origin, "wwds-dev/sonar_macro") == want


def test_remote_url_refuses_a_bad_repository():
    with pytest.raises(ValueError):
        bid.remote_url("https://github.com/wwds-dev/sonar.git", "--upload-pack=x")


@pytest.mark.parametrize("origin", [
    "https://ghp_secret@github.com/wwds-dev/sonar.git",
    "https://user:ghp_secret@github.com/wwds-dev/sonar.git",
    "HTTP://x-access-token:s3cret@github.com/wwds-dev/sonar.git",
    "ssh://git:s3cret@github.com/wwds-dev/sonar.git",
])
def test_a_credentialed_origin_is_refused_and_not_echoed(origin):
    # Code review P3-4, security P3-2: the URL would land in the saved report.
    with pytest.raises(ValueError, match="carries credentials") as exc:
        bid.remote_url(origin, "wwds-dev/sonar_macro")
    assert "secret" not in str(exc.value) and "s3cret" not in str(exc.value)
    r = subprocess.run([SYS_PY, "-I", str(SCRIPT), "remote-url", origin, "wwds-dev/sonar_macro"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 1 and "ecret" not in r.stdout + r.stderr


@pytest.mark.parametrize("origin", ["--upload-pack=touch /tmp/x", "-ufoo",
                                    "ext::sh -c touch% /tmp/x", "fd::3"])
def test_an_origin_git_would_read_as_an_option_or_helper_is_refused(origin):
    # Security P3-5.
    with pytest.raises(ValueError, match="not a plain URL"):
        bid.remote_url(origin, "wwds-dev/sonar_macro")


# --------------------------------------------------------------------------- #
# build_id (A7, ADR 0002 Amendment 2): one table, both copies
# --------------------------------------------------------------------------- #
NESTED = {"macro": {"commit": "b3fa3e2", "sha": PIN_M, "dirty": False},
          "playmaker": {"commit": "1162ba5", "sha": PIN_P, "dirty": False}}
PINS = {"macro": PIN_M, "playmaker": PIN_P}


def prov(**kw) -> dict:
    p = {"version": "v2.364", "commit": "9aa9bd1", "dirty": False, "source": "baked",
         "nested": copy.deepcopy(NESTED)}
    p.update(kw)
    return p


BUILD_IDS = [
    (prov(), PINS, "v2.364+9aa9bd1/m:b3fa3e2/p:1162ba5"),
    (prov(dirty=True), PINS, "v2.364~+9aa9bd1/m:b3fa3e2/p:1162ba5"),
    (prov(dirty=None), PINS, "v2.364~+9aa9bd1/m:b3fa3e2/p:1162ba5"),
    (prov(), None, "v2.364!+9aa9bd1/m:b3fa3e2/p:1162ba5"),            # pins unknown
    (prov(), {"macro": "c" * 40, "playmaker": PIN_P}, "v2.364!+9aa9bd1/m:b3fa3e2/p:1162ba5"),
    (prov(dirty=None, nested={"macro": COPY, "playmaker": NESTED["playmaker"]}), PINS,
     "v2.364~!+9aa9bd1/m:?/p:1162ba5"),                              # a copy
    (prov(nested={"playmaker": NESTED["playmaker"]}), PINS,
     "v2.364!+9aa9bd1/m:-/p:1162ba5"),                               # absent
    (prov(commit=""), PINS, "v2.364+?/m:b3fa3e2/p:1162ba5"),
    (prov(version=None), PINS, "unknown+9aa9bd1/m:b3fa3e2/p:1162ba5"),  # MV P3-2
    ({}, None, "unknown~!+?/m:-/p:-"),
    (None, None, "unknown~!+?/m:-/p:-"),
    ({"version": "v2.340", "commit": "8e7d024", "dirty": False, "nested": {}}, None,
     "v2.340!+8e7d024/m:-/p:-"),                                     # what v2.340 would write
    (prov(commit="0123456789abcdef"), PINS, "v2.364+0123456789ab/m:b3fa3e2/p:1162ba5"),
]


@pytest.mark.parametrize("fn", [bid.build_id, app_version.build_id], ids=["scripts", "sonar"])
@pytest.mark.parametrize("p,pins,want", BUILD_IDS)
def test_build_id_table(fn, p, pins, want):
    got = fn(copy.deepcopy(p), pins)
    assert got == want
    assert got.isascii() and len(got) <= 64


@pytest.mark.parametrize("fn", [bid.build_id, app_version.build_id], ids=["scripts", "sonar"])
def test_build_id_worst_case_fits_with_both_marks(fn):
    long12 = "0123456789ab"
    p = prov(version="v2.1234567", commit=long12 * 2, dirty=True,
             nested={n: {"commit": long12 * 2, "sha": "", "dirty": True} for n in NESTED})
    got = fn(p, PINS)
    assert len(got) == 55 and got.startswith("v2.1234567~!+")
    assert got.endswith("/p:" + long12)


@pytest.mark.parametrize("fn", [bid.build_id, app_version.build_id], ids=["scripts", "sonar"])
def test_at_the_64_char_edge_commits_shorten_and_the_marks_stay(fn):
    # MV P3-1: a version long enough that 12-hex fields would pass 64 by one.
    # The commits shorten; the marks right after the version survive; nothing
    # at the end is cut.
    long12 = "0123456789ab"
    nested = {n: {"commit": long12, "sha": "", "dirty": False} for n in NESTED}
    version = "v" + "9" * 19                         # with 12-hex fields: 65 chars
    p = prov(version=version, commit=long12, dirty=True, nested=nested)
    assert len(f"{version}~!+{long12}/m:{long12}/p:{long12}") == 65
    got = fn(p, PINS)
    assert len(got) <= 64 and got.startswith(version + "~!+")
    assert got == f"{version}~!+{long12[:11]}/m:{long12[:11]}/p:{long12[:11]}"


@pytest.mark.parametrize("fn", [bid.build_id, app_version.build_id], ids=["scripts", "sonar"])
def test_build_id_leading_token_is_the_old_value(fn):
    import re
    for p, pins, _ in BUILD_IDS:
        if p and p.get("version"):
            assert re.split(r"[~!+]", fn(copy.deepcopy(p), pins))[0] == p["version"]


# --------------------------------------------------------------------------- #
# check-stamp, as the gate runs it
# --------------------------------------------------------------------------- #
def _check(tmp_path, stamp, *extra, py=SYS_PY):
    f = tmp_path / "stamp.json"
    f.write_text(stamp if isinstance(stamp, str) else json.dumps(stamp))
    return subprocess.run([py, "-I", str(SCRIPT), "check-stamp", str(f), *extra],
                          capture_output=True, text=True, timeout=30)


def test_check_stamp_exit_codes(tmp_path):
    assert _check(tmp_path, clean()).returncode == 0
    r = _check(tmp_path, with_(nested={}))
    assert r.returncode == 3 and "macro: not in the stamp" in r.stdout
    for corrupt in ("{not json", "[1, 2]", ""):
        r = _check(tmp_path, corrupt)
        assert r.returncode == 2, corrupt
    r = subprocess.run([SYS_PY, "-I", str(SCRIPT), "check-stamp"], capture_output=True,
                       text=True, timeout=30)
    assert r.returncode == 2                                        # argparse


def _git(cwd, *args):
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True,
                          text=True).stdout.strip()


def _repo(at: Path) -> str:
    at.mkdir(parents=True, exist_ok=True)
    _git(at, "init", "-q", "-b", "master")
    (at / "f").write_text("x\n")
    _git(at, "add", "f")
    _git(at, "commit", "-qm", "one")
    return _git(at, "rev-parse", "HEAD")


def _stamp_at(outer: str, shas: dict) -> dict:
    s = with_(sha=outer, commit=outer[:7], pins=dict(shas))
    for n in bid.NAMES:
        s["nested"][n].update(sha=shas[n], commit=shas[n][:7])
    return s


def test_check_stamp_with_repo_wants_every_commit_on_origin(tmp_path):
    proj = tmp_path / "proj"
    outer = _repo(proj)
    shas = {n: _repo(proj / "sonar" / n) for n in bid.NAMES}
    s = _stamp_at(outer, shas)
    r = _check(tmp_path, s, "--repo", str(proj))
    assert r.returncode == 3
    assert r.stdout.splitlines() == [
        f"outer {outer[:9]} is not on any origin ref as of the last fetch",
        f"macro {shas['macro'][:9]} is not on any origin ref as of the last fetch",
        f"playmaker {shas['playmaker'][:9]} is not on any origin ref as of the last fetch"]
    for where in (proj, proj / "sonar" / "macro", proj / "sonar" / "playmaker"):
        _git(where, "update-ref", "refs/remotes/origin/master", "HEAD")
    assert _check(tmp_path, s, "--repo", str(proj)).returncode == 0
    # Without --repo the check is pure: no origin reason at all.
    assert _check(tmp_path, s).returncode == 0


def test_a_commit_missing_from_the_repo_is_not_on_origin(tmp_path):
    proj = tmp_path / "proj"
    _repo(proj)
    _git(proj, "update-ref", "refs/remotes/origin/master", "HEAD")
    s = with_(nested={}, sha="d" * 40, commit="ddddddd")
    r = _check(tmp_path, s, "--repo", str(proj))
    assert f"outer {'d' * 9} is not on any origin ref as of the last fetch" in r.stdout


def test_a_nested_dir_that_is_not_a_repo_cannot_be_checked(tmp_path):
    # git would walk up to the outer repo and answer for it: not asked.
    proj = tmp_path / "proj"
    _repo(proj)
    _git(proj, "update-ref", "refs/remotes/origin/master", "HEAD")
    (proj / "sonar" / "macro").mkdir(parents=True)
    head = _git(proj, "rev-parse", "HEAD")
    s = with_(sha=head, commit=head[:7])
    r = _check(tmp_path, s, "--repo", str(proj))
    assert r.returncode == 3
    assert f"macro {PIN_M[:9]}: whether it is on origin cannot be checked here" in r.stdout
    assert "is not on any origin ref" not in r.stdout


def test_a_worktree_with_copies_asks_the_main_checkouts_nested_repos(tmp_path):
    # Code review P3-5: re-running the installer from a worktree that holds
    # copies must not refuse a bundle built in the main checkout.
    main = tmp_path / "main"
    outer = _repo(main)
    _git(main, "update-ref", "refs/remotes/origin/master", "HEAD")
    shas = {n: _repo(main / "sonar" / n) for n in bid.NAMES}
    for n in bid.NAMES:
        _git(main / "sonar" / n, "update-ref", "refs/remotes/origin/master", "HEAD")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", str(wt))
    (wt / "sonar" / "macro").mkdir(parents=True)                # a copy here
    s = _stamp_at(outer, shas)
    r = _check(tmp_path, s, "--repo", str(wt))
    assert r.returncode == 0, r.stdout
    # Not on origin in the main checkout either: refused.
    _git(main / "sonar" / "playmaker", "update-ref", "-d", "refs/remotes/origin/master")
    r = _check(tmp_path, s, "--repo", str(wt))
    assert r.returncode == 3
    assert r.stdout.splitlines() == [
        f"playmaker {shas['playmaker'][:9]} is not on any origin ref as of the last fetch"]


# --------------------------------------------------------------------------- #
# tag-command (A6), print-only
# --------------------------------------------------------------------------- #
@pytest.fixture
def history(tmp_path):
    """master: one - two - merge(side); side: one - s1. origin/master = merge."""
    r = tmp_path / "hist"
    _repo(r)
    one = _git(r, "rev-parse", "HEAD")
    _git(r, "checkout", "-qb", "side")
    (r / "s").write_text("s\n")
    _git(r, "add", "s")
    _git(r, "commit", "-qm", "s1")
    s1 = _git(r, "rev-parse", "HEAD")
    _git(r, "checkout", "-q", "master")
    (r / "t").write_text("t\n")
    _git(r, "add", "t")
    _git(r, "commit", "-qm", "two")
    two = _git(r, "rev-parse", "HEAD")
    _git(r, "merge", "-q", "--no-ff", "-m", "merge", "side")
    merge = _git(r, "rev-parse", "HEAD")
    _git(r, "update-ref", "refs/remotes/origin/master", merge)
    return {"repo": r, "one": one, "s1": s1, "two": two, "merge": merge}


def _tag(h, sha, *, build=None, major="2", py=SYS_PY):
    s = with_(sha=sha, commit=sha[:7], major=major)
    s["build"] = build if build is not None else int(_git(h["repo"], "rev-list", "--count", sha))
    f = h["repo"].parent / "stamp.json"
    f.write_text(json.dumps(s))
    return subprocess.run([py, "-I", str(SCRIPT), "tag-command", str(f), "--repo",
                           str(h["repo"])], capture_output=True, text=True, timeout=30)


def test_a_first_parent_commit_gets_a_tag_command(history):
    r = _tag(history, history["merge"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (f'git tag -a v2.004 {history["merge"]} -m "v2.004; macro {PIN_M[:9]}, '
            f'playmaker {PIN_P[:9]}"') in r.stdout
    assert "git push origin v2.004" in r.stdout
    assert _git(history["repo"], "tag") == "", "print-only: no tag was made"


def test_a_side_branch_commit_gets_no_tag_command(history):
    r = _tag(history, history["s1"])
    assert r.returncode == 0
    assert "is not on first-parent master" in r.stdout and "git tag" not in r.stdout
    assert "No release tag proposed" in r.stdout


def test_an_existing_tag_on_another_commit_is_refused(history):
    _git(history["repo"], "tag", "-a", "v2.004", history["two"], "-m", "x")
    r = _tag(history, history["merge"])
    assert r.returncode == 1
    assert (f"tag v2.004 already names {history['two'][:9]}; this build is "
            f"{history['merge'][:9]}") in r.stdout
    assert "git tag -a" not in r.stdout


def test_a_tag_on_the_same_commit_is_said_and_not_proposed(history):
    _git(history["repo"], "tag", "-a", "v2.004", history["merge"], "-m", "x")
    r = _tag(history, history["merge"])
    assert r.returncode == 0 and "v2.004 already tags this commit" in r.stdout
    assert "git tag -a" not in r.stdout


def test_only_on_local_master_says_push_first(history):
    _git(history["repo"], "update-ref", "refs/remotes/origin/master", history["two"])
    r = _tag(history, history["merge"])
    assert "not on origin/master as of the last fetch; push master first" in r.stdout
    assert "git tag -a v2.004" in r.stdout


def test_no_origin_master_falls_back_to_local_master(history):
    _git(history["repo"], "update-ref", "-d", "refs/remotes/origin/master")
    r = _tag(history, history["merge"])
    assert "no origin/master here" in r.stdout and "git tag -a v2.004" in r.stdout


def test_an_untraceable_build_gets_no_tag_command(history, tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps(with_(nested={}, sha=history["merge"], commit=history["merge"][:7])))
    r = subprocess.run([SYS_PY, "-I", str(SCRIPT), "tag-command", str(f), "--repo",
                        str(history["repo"])], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "No release tag proposed: this build cannot be traced" in r.stdout
    assert "git tag" not in r.stdout


def test_a_build_number_that_is_not_the_commits_count_is_refused(history):
    # Code review P3-1: the number and the sha were read at two moments.
    r = _tag(history, history["merge"], build=3)
    assert r.returncode == 1
    assert f"{history['merge'][:9]} has rev-list --count 4, but the stamp says build 3" in r.stdout
    assert "git tag -a" not in r.stdout


@pytest.mark.parametrize("major", ["2; rm -rf ~", "", "v2", "2.1"])
def test_a_major_that_is_not_digits_is_refused(history, major):
    # Security P3-8a: it goes into a printed shell command.
    r = _tag(history, history["merge"], major=major)
    assert r.returncode == 2 and "no valid major/build" in r.stdout and "git tag" not in r.stdout


def _retro(h, version, commit):
    return subprocess.run([SYS_PY, "-I", str(SCRIPT), "tag-command", "--retroactive", version,
                           commit, "--repo", str(h["repo"])], capture_output=True, text=True,
                          timeout=30)


def test_retroactive_prints_the_nested_code_unknown_tag(history):
    r = _retro(history, "2.004", history["merge"][:7])
    assert r.returncode == 0, r.stdout
    assert (f'git tag -a v2.004 {history["merge"]} -m "v2.004 (retroactive); nested code '
            'unknown"') in r.stdout
    assert "cannot be recovered" in r.stdout


@pytest.mark.parametrize("version,commit_key,why", [
    ("2.005", "merge", "has rev-list --count 4, not 5"),
    ("2.004", None, "is not a commit"),
    ("x", "merge", "expected"),
])
def test_retroactive_refuses_a_number_that_does_not_fit(history, version, commit_key, why):
    commit = history[commit_key][:7] if commit_key else "abcdef1"
    r = _retro(history, version, commit)
    assert r.returncode != 0 and why in r.stdout


def test_retroactive_refuses_an_option_for_a_commit(history):
    r = _retro(history, "2.004", "--all")
    assert r.returncode != 0 and "git tag" not in r.stdout
