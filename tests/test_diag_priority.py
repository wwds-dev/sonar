"""The priority-measurement harness never touches the live agent.

docs/specs/starved-engine.md A4: ``scripts/diag_priority.py`` loads two
throwaway launchd jobs beside the live agent on the owner's Mac. These pin its
guards (labels, paths, ports, market hours), the plists it writes, its cleanup,
the numbers and the health whitelist. No real ``launchctl``, ``curl`` or
``osascript`` runs here: they are replaced in the module or on PATH.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import plistlib
import signal
import socket
import subprocess
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("diag_priority",
                                                  ROOT / "scripts" / "diag_priority.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


diag = _load()
NY = dt.timezone(dt.timedelta(hours=-4))      # EDT, for building test instants


@pytest.fixture
def scratch():
    d = diag.make_scratch()
    yield d
    if d.exists():
        import shutil
        shutil.rmtree(d)


class Cmd:
    """Records every external command; answers like launchctl/ps/curl.
    ``calls`` keep the program as given; ``verbs`` and the answers go by its
    base name. A ``print_out`` value may be a list: one answer per call."""

    def __init__(self, listed=(), print_out=None, curl_out="\n200 0.010", bootstrap_rc=0,
                 bootout_raises=None):
        self.calls, self.listed, self.curl_out = [], list(listed), curl_out
        self.print_out = print_out or {}
        self.bootstrap_rc, self.bootout_raises = bootstrap_rc, bootout_raises

    def __call__(self, args, timeout=30):
        self.calls.append(list(args))
        prog = os.path.basename(args[0])
        out, rc = "", 0
        if prog == "launchctl" and args[1] == "list":
            out = "PID\tStatus\tLabel\n" + "".join(f"1\t0\t{x}\n" for x in self.listed)
        elif prog == "launchctl" and args[1] == "print":
            lbl = args[2].rsplit("/", 1)[-1]
            out = self.print_out.get(lbl, "")
            if isinstance(out, list):
                out = out.pop(0) if len(out) > 1 else out[0]
            rc = 0 if out else 113
        elif prog == "launchctl" and args[1] == "bootstrap":
            rc = self.bootstrap_rc
        elif prog == "launchctl" and args[1] == "bootout" and self.bootout_raises:
            raise self.bootout_raises
        elif prog == "ps":
            out = "0:01.00\n"
        elif prog == "curl":
            out = self.curl_out
        return subprocess.CompletedProcess(args, rc, out, "")

    def verbs(self, verb):
        return [c for c in self.calls if os.path.basename(c[0]) == "launchctl" and c[1] == verb]


# --------------------------------------------------------------------------- #
# Labels
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["com.netrunner3000.sonar", "", "com.netrunner3000.sonar-diag.",
                                 "com.netrunner3000.sonar-diag.STD", "com.netrunner3000.sonar.std",
                                 "com.netrunner3000.sonar-diag.std/../x",
                                 "com.netrunner3000.sonar-diag.std\n",
                                 "xcom.netrunner3000.sonar-diag.std"])
def test_only_diag_labels_pass(bad):
    with pytest.raises(diag.Refused):
        diag.check_label(bad)


def test_the_two_variants_get_diag_labels():
    assert diag.label("bg") == "com.netrunner3000.sonar-diag.bg"
    assert diag.label("probe-std") == "com.netrunner3000.sonar-diag.probe-std"


def test_bootout_never_reaches_launchctl_with_the_live_label(monkeypatch):
    cmd = Cmd()
    monkeypatch.setattr(diag, "_cmd", cmd)
    with pytest.raises(diag.Refused):
        diag.bootout("com.netrunner3000.sonar")
    assert cmd.calls == []
    diag.bootout("com.netrunner3000.sonar-diag.std")
    assert cmd.calls == [["/bin/launchctl", "bootout",
                          f"gui/{os.getuid()}/com.netrunner3000.sonar-diag.std"]]


def test_bootstrap_refuses_a_plist_naming_the_live_label(monkeypatch, scratch):
    cmd = Cmd()
    monkeypatch.setattr(diag, "_cmd", cmd)
    p = scratch / "x.plist"
    p.write_bytes(plistlib.dumps({"Label": "com.netrunner3000.sonar"}))
    with pytest.raises(diag.Refused):
        diag.bootstrap(p, scratch)
    assert cmd.calls == []


def test_bootstrap_refuses_a_plist_outside_the_scratch_dir(monkeypatch, scratch, tmp_path):
    cmd = Cmd()
    monkeypatch.setattr(diag, "_cmd", cmd)
    p = tmp_path / "x.plist"
    p.write_bytes(plistlib.dumps({"Label": "com.netrunner3000.sonar-diag.std"}))
    with pytest.raises(diag.Refused):
        diag.bootstrap(p, scratch)
    assert cmd.calls == []


def test_write_plist_refuses_a_live_label(scratch):
    p = diag.engine_plist("std", scratch)
    p["Label"] = "com.netrunner3000.sonar"
    with pytest.raises(diag.Refused):
        diag.write_plist(p, scratch)
    assert list(scratch.iterdir()) == []


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rel", ["Library/LaunchAgents/com.netrunner3000.sonar-diag.std.plist",
                                 "Library/LaunchAgents",
                                 "Library/Application Support/SONAR/state.json",
                                 "Library/Application Support/SONAR-diag/x"])
def test_live_places_are_refused(tmp_path, rel):
    with pytest.raises(diag.Refused):
        diag.check_outside_live(tmp_path / rel, home=tmp_path)


def test_the_real_home_is_guarded_by_default():
    with pytest.raises(diag.Refused):
        diag.check_outside_live(Path.home() / "Library" / "LaunchAgents" / "x.plist")
    with pytest.raises(diag.Refused):
        diag.check_outside_live(Path("~/Library/Application Support/SONAR"))


def test_a_symlink_into_launchagents_is_refused(tmp_path):
    (tmp_path / "Library" / "LaunchAgents").mkdir(parents=True)
    link = tmp_path / "innocent"
    link.symlink_to(tmp_path / "Library" / "LaunchAgents")
    with pytest.raises(diag.Refused):
        diag.check_outside_live(link / "x.plist", home=tmp_path)


def test_the_scratch_dir_is_a_sonar_diag_dir_in_the_temp_dir(scratch, tmp_path):
    assert scratch.name.startswith("sonar-diag-")
    assert scratch.parent == Path(tempfile.gettempdir()).resolve()
    for bad in (tmp_path, Path(tempfile.gettempdir()) / "other", scratch / "sonar-diag-x"):
        with pytest.raises(diag.Refused):
            diag.check_scratch(bad)


def test_paths_must_lie_inside_the_scratch_dir(scratch, tmp_path):
    assert diag.check_inside(scratch / "std" / "data", scratch) == scratch / "std" / "data"
    for bad in (tmp_path / "x", scratch / ".." / "x", scratch.parent):
        with pytest.raises(diag.Refused):
            diag.check_inside(bad, scratch)


# --------------------------------------------------------------------------- #
# Plists
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("variant,ptype,nice,port", [("bg", "Background", 5, "8788"),
                                                     ("std", "Standard", None, "8789")])
def test_engine_plists(scratch, variant, ptype, nice, port):
    p = diag.engine_plist(variant, scratch)
    assert p["Label"] == f"com.netrunner3000.sonar-diag.{variant}"
    assert p["ProcessType"] == ptype
    assert p.get("Nice") == nice and (nice is not None or "Nice" not in p)
    assert p["ProgramArguments"][1:] == [str(ROOT / "main.py"), "--headless", "--host",
                                         "127.0.0.1", "--port", port]
    assert p["RunAtLoad"] is True and "KeepAlive" not in p
    env = p["EnvironmentVariables"]
    assert env["SONAR_ALARM"] == "off"
    for k in ("FINNHUB_API_KEY", "TWELVEDATA_API_KEY", "ALPHAVANTAGE_API_KEY",
              "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "APCA_API_KEY_ID",
              "APCA_API_SECRET_KEY"):
        assert env[k] == "", k
    assert env["SONAR_DATA"] == str(scratch / variant / "data")
    assert env["SONAR_BACKUP_DIR"] == str(scratch / variant / "backup")
    for key in ("StandardOutPath", "StandardErrorPath"):
        assert Path(p[key]).is_relative_to(scratch)
    assert "8787" not in json.dumps(p)


def test_written_plists_land_in_the_scratch_dir_and_round_trip(scratch):
    path = diag.write_plist(diag.engine_plist("std", scratch), scratch)
    assert path.parent == scratch
    with open(path, "rb") as f:
        assert plistlib.load(f) == diag.engine_plist("std", scratch)
    assert (scratch / "std" / "data").is_dir() and (scratch / "std" / "backup").is_dir()


@pytest.mark.parametrize("variant,ptype", [("bg", "Background"), ("std", "Standard")])
def test_probe_plists_share_their_engines_job_class(scratch, variant, ptype):
    p = diag.probe_plist(variant, scratch)
    e = diag.engine_plist(variant, scratch)
    assert p["Label"] == f"com.netrunner3000.sonar-diag.probe-{variant}"
    assert (p["ProcessType"], p.get("Nice")) == (e["ProcessType"], e.get("Nice"))
    assert p["ProgramArguments"][1:2] == ["-I"]
    assert p["ProgramArguments"][3:6] == ["probe", variant, "10"]
    assert Path(p["ProgramArguments"][-1]).is_relative_to(scratch)


# --------------------------------------------------------------------------- #
# Cleanup, with a fake launchctl on PATH
# --------------------------------------------------------------------------- #
FAKE_LAUNCHCTL = """#!/bin/sh
echo "$*" >> "$CALLS"
if [ "$1" = list ]; then
  printf 'PID\\tStatus\\tLabel\\n'
  printf '123\\t0\\tcom.netrunner3000.sonar\\n'
  printf '124\\t0\\tcom.netrunner3000.sonar-diag.bg\\n'
  printf -- '-\\t0\\tcom.netrunner3000.sonar-diag.probe-std\\n'
  printf '125\\t0\\tcom.example.other\\n'
  printf '126\\t0\\tcom.netrunner3000.sonar-diagnostics\\n'
fi
exit 0
"""


def test_cleanup_boots_out_only_diag_labels_and_removes_only_the_scratch_dir(
        monkeypatch, tmp_path, scratch):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "launchctl").write_text(FAKE_LAUNCHCTL)
    (fake / "launchctl").chmod(0o755)
    calls = tmp_path / "calls"
    monkeypatch.setattr(diag, "LAUNCHCTL", str(fake / "launchctl"))
    monkeypatch.setenv("CALLS", str(calls))
    (scratch / "std" / "data").mkdir(parents=True)
    keep = tmp_path / "sonar-diag-keep"
    keep.mkdir()

    gone = diag.cleanup(scratch)
    assert gone == {"com.netrunner3000.sonar-diag.bg": 0,
                    "com.netrunner3000.sonar-diag.probe-std": 0}
    lines = calls.read_text().splitlines()
    outs = [ln for ln in lines if ln.startswith("bootout")]
    uid = os.getuid()
    assert outs == [f"bootout gui/{uid}/com.netrunner3000.sonar-diag.bg",
                    f"bootout gui/{uid}/com.netrunner3000.sonar-diag.probe-std"]
    assert not any("bootstrap" in ln for ln in lines)
    assert not scratch.exists()

    diag.cleanup(keep)                      # not under the temp dir: left alone
    assert keep.exists()


def test_cleanup_closes_the_follower(monkeypatch):
    monkeypatch.setattr(diag, "_cmd", Cmd())

    class Proc:
        def __init__(self):
            self.done = None

        def poll(self):
            return self.done

        def terminate(self):
            self.done = -15

        def wait(self, t):
            return self.done

    p = Proc()
    diag.cleanup(None, p)
    assert p.done == -15


# --------------------------------------------------------------------------- #
# Ports and market hours
# --------------------------------------------------------------------------- #
def test_the_live_port_and_a_busy_port_are_refused():
    with pytest.raises(diag.Refused):
        diag.check_ports([8787], free=lambda p: True)
    with pytest.raises(diag.Refused):
        diag.check_ports([8788], free=lambda p: False)
    diag.check_ports([8788, 8789], free=lambda p: True)


def test_port_free_sees_a_listener():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    try:
        assert not diag.port_free(s.getsockname()[1])
    finally:
        s.close()


@pytest.mark.parametrize("when,want", [
    (dt.datetime(2026, 10, 19, 10, 0, tzinfo=NY), True),      # Monday
    (dt.datetime(2026, 10, 19, 9, 29, tzinfo=NY), False),
    (dt.datetime(2026, 10, 19, 9, 30, tzinfo=NY), True),
    (dt.datetime(2026, 10, 19, 16, 0, tzinfo=NY), False),
    (dt.datetime(2026, 10, 23, 15, 59, tzinfo=NY), True),     # Friday
    (dt.datetime(2026, 10, 24, 12, 0, tzinfo=NY), False),     # Saturday
    (dt.datetime(2026, 10, 19, 14, 0, tzinfo=dt.timezone.utc), True),   # 10:00 New York
])
def test_market_hours(when, want):
    assert diag.market_open(when) is want


def test_a_window_running_into_the_open_is_refused():
    start = dt.datetime(2026, 10, 19, 8, 45, tzinfo=NY)
    with pytest.raises(diag.Refused):
        diag.check_market_hours(start, 80)
    diag.check_market_hours(start, 40)
    diag.check_market_hours(start, 80, force=True)
    with pytest.raises(diag.Refused):
        diag.check_market_hours(dt.datetime(2026, 10, 19, 12, 0, tzinfo=NY), 60)


def test_run_refuses_in_market_hours_before_touching_launchd(monkeypatch):
    cmd = Cmd()
    monkeypatch.setattr(diag, "_cmd", cmd)
    monkeypatch.setattr(diag, "market_open", lambda t: True)
    monkeypatch.setattr(diag, "make_scratch", lambda: pytest.fail("made a scratch dir"))
    assert diag.main(["run"]) == 2
    assert cmd.calls == []


def test_run_refuses_busy_ports_before_touching_launchd(monkeypatch):
    cmd = Cmd()
    monkeypatch.setattr(diag, "_cmd", cmd)
    monkeypatch.setattr(diag, "market_open", lambda t: False)
    monkeypatch.setattr(diag, "port_free", lambda p: False)
    assert diag.main(["run"]) == 2
    assert cmd.calls == []


def test_run_refuses_an_output_file_in_application_support(monkeypatch):
    cmd = Cmd()
    monkeypatch.setattr(diag, "_cmd", cmd)
    monkeypatch.setattr(diag, "market_open", lambda t: False)
    out = Path.home() / "Library" / "Application Support" / "SONAR" / "m.md"
    assert diag.main(["run", "--out", str(out)]) == 2
    assert cmd.calls == [] and not out.exists()


# --------------------------------------------------------------------------- #
# The whitelist and curl
# --------------------------------------------------------------------------- #
HEALTH = {"ok": False, "mode": "daemon", "last_poll_age_s": 4.5, "last_error": "secret text",
          "problems": [{"kind": "poll", "text": "no successful price poll"},
                       {"kind": "Bad Kind", "text": "x"}, "junk"],
          "bankroll": 10432.17, "equity": 1, "pnl": -3.2, "positions": [{"symbol": "AAPL"}],
          "build": {"version": "v2.363"},
          "notify": {"ntfy": {"state": "not configured", "reason": "off (SONAR_ALARM)"},
                     "banner": {"state": "unavailable", "failures": 3}}}


def test_the_health_whitelist_drops_every_other_key():
    w = diag.whitelist(json.dumps(HEALTH))
    assert w == {"ok": False, "last_poll_age_s": 4.5, "kinds": ["poll"], "alarm_off": True,
                 "banner_failures": 3, "banner_attempts": None}
    assert "10432" not in json.dumps(w) and "AAPL" not in json.dumps(w)


@pytest.mark.parametrize("body", [None, "", "not json", "[1]", '{"ok": "yes", '
                                  '"last_poll_age_s": "9", "problems": 3, "notify": 1}',
                                  '{"last_poll_age_s": NaN}', '{"last_poll_age_s": true}'])
def test_the_whitelist_survives_junk(body):
    w = diag.whitelist(body)
    assert w["ok"] is None and w["last_poll_age_s"] is None and w["kinds"] == []


def test_a_live_alarm_reason_is_not_off():
    h = dict(HEALTH, notify={"ntfy": {"reason": "ok"}})
    assert diag.whitelist(json.dumps(h))["alarm_off"] is False


def test_state_and_config_bodies_are_discarded(monkeypatch):
    cmd = Cmd(curl_out="\n200 0.250")
    monkeypatch.setattr(diag, "_cmd", cmd)
    for ep in ("/api/state", "/api/config"):
        row = diag.sample(8789, ep, 1.0, 60.0)
        assert row == {"t": 1.0, "port": 8789, "endpoint": ep, "ms": 250.0, "code": 200,
                       "load": 60.0}
    for c in cmd.calls:
        assert c[c.index("-o") + 1] == os.devnull
        assert c[c.index("-m") + 1] == "60"


def test_health_keeps_only_the_whitelist(monkeypatch):
    monkeypatch.setattr(diag, "_cmd", Cmd(curl_out=json.dumps(HEALTH) + "\n503 1.5"))
    row = diag.sample(8789, "/api/health", 0, 55)
    assert row["ms"] == 1500.0 and row["code"] == 503 and row["poll_age_s"] == 4.5
    assert set(row) == {"t", "port", "endpoint", "ms", "code", "load", "poll_age_s", "kinds",
                        "alarm_off", "banner_failures", "banner_attempts"}


def test_no_answer_is_not_a_latency(monkeypatch):
    monkeypatch.setattr(diag, "_cmd", Cmd(curl_out="\n000 0.002"))
    r = diag.fetch(8789, "/api/health", True)
    assert r["code"] == 0 and r["ms"] is None


def test_only_health_is_ever_read_from_the_live_port(monkeypatch):
    cmd = Cmd()
    monkeypatch.setattr(diag, "_cmd", cmd)
    for ep in ("/api/state", "/api/config", "/api/trade"):
        with pytest.raises(diag.Refused):
            diag.fetch(8787, ep, False)
    assert cmd.calls == []


# --------------------------------------------------------------------------- #
# watch (measure 4) on the live port
# --------------------------------------------------------------------------- #
def test_watch_writes_whitelisted_rows_and_flags_an_alarm_that_is_off(tmp_path, capsys):
    clock = [1_000_000.0]
    out = tmp_path / "w.jsonl"
    s = diag.watch(8787, 300, 900 / 86400, out, clock=lambda: clock[0],
                   sleep=lambda s: clock.__setitem__(0, clock[0] + s),
                   fetcher=lambda: {"code": 200, "ms": 120.0, "body": json.dumps(HEALTH)})
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert len(rows) == 4 and s["n"] == 4          # at 0, 300, 600 and 900 s
    text = out.read_text()
    assert "10432" not in text and "AAPL" not in text and "secret" not in text
    assert all(set(r) == {"t", "port", "ms", "code", "ok", "poll_age_s", "kinds", "alarm_off",
                          "banner_failures", "banner_attempts"} for r in rows)
    assert s["alarm_off_seen"] and s["samples_with_poll_or_scan_problem"] == 4
    assert capsys.readouterr().out.count("WARNING") == 1


def test_watch_refuses_an_output_in_application_support(tmp_path):
    with pytest.raises(diag.Refused):
        diag.watch(8787, 300, 1, Path.home() / "Library" / "Application Support" / "w.jsonl",
                   fetcher=lambda: pytest.fail("fetched"))


# --------------------------------------------------------------------------- #
# Numbers
# --------------------------------------------------------------------------- #
def test_percentile_is_nearest_rank():
    xs = list(range(1, 21))
    assert diag.percentile(xs, 50) == 10 and diag.percentile(xs, 95) == 19
    assert diag.percentile(xs, 100) == 20 and diag.percentile([None, 7], 95) == 7
    assert diag.percentile([], 50) is None


def test_longest_run():
    assert diag.longest_run([1, 1, 0, 1, 1, 1, 0]) == 3 and diag.longest_run([]) == 0


@pytest.mark.parametrize("text,want", [("0:01.50", 1.5), ("1:02:03.5", 3723.5),
                                       ("2-00:00:01", 172801.0), ("", None), ("x", None)])
def test_cputime_parses(text, want):
    assert diag.parse_cputime(text) == want


def test_job_info_reads_pid_and_spawn_type(monkeypatch):
    out = "\tstate = running\n\tpid = 4242\n\tspawn type = daemon (3)\n"
    monkeypatch.setattr(diag, "_cmd", Cmd(print_out={"com.netrunner3000.sonar": out}))
    assert diag.job_info("com.netrunner3000.sonar") == {
        "pid": 4242, "spawn_type": "daemon (3)", "nice": None, "loaded": True}


def _rows(std_ms, bg_ms, load=80.0, age=4.0, state_ms=300.0):
    rows = []
    for i, (s, b) in enumerate(zip(std_ms, bg_ms)):
        rows.append({"t": i * 30, "port": 8789, "endpoint": "/api/health", "ms": s, "code": 200,
                     "load": load, "poll_age_s": age})
        rows.append({"t": i * 30, "port": 8788, "endpoint": "/api/health", "ms": b, "code": 200,
                     "load": load, "poll_age_s": age})
        rows.append({"t": i * 30, "port": 8789, "endpoint": "/api/state", "ms": state_ms,
                     "code": 200, "load": load})
    return rows


GOOD_PROBES = {"std": [{"elapsed_s": 0.5, "rc": 0}] * 10, "bg": [{"elapsed_s": 12, "rc": 0}] * 10}
CPU = {"std": {"pct": 0.4}, "bg": {"pct": 0.3}}
LIVE = {"pid": 7, "spawn_type": "background (5)"}


def test_a_good_hour_passes_every_bar():
    s = diag.summarise(_rows([300.0] * 20, [2000.0] * 20), GOOD_PROBES, CPU, LIVE, LIVE)
    assert all(s["bars"].values()), s["bars"]
    assert s["load"]["valid"] == "valid"


@pytest.mark.parametrize("change,bar", [
    (dict(std=[1500.0] * 20), "std health p50 <= 1 s"),
    (dict(std=[300.0] * 18 + [4000.0] * 2), "std health p95 <= 3 s"),
    (dict(std=[300.0] * 19 + [None]), "std health max < 10 s"),
    (dict(bg=[500.0] * 20), "std health p95 <= half of bg"),
    (dict(age=30.0), "std poll age p95 <= 12 s"),
    (dict(age=130.0), "std poll age never > 120 s"),
])
def test_each_bar_can_fail(change, bar):
    rows = _rows(change.get("std", [300.0] * 20), change.get("bg", [2000.0] * 20),
                 age=change.get("age", 4.0))
    s = diag.summarise(rows, GOOD_PROBES, CPU, LIVE, LIVE)
    assert s["bars"][bar] is False


def test_probe_cpu_and_live_pid_bars_can_fail():
    rows = _rows([300.0] * 20, [2000.0] * 20)
    slow = {"std": [{"elapsed_s": 0.5, "rc": 0}] * 9 + [{"elapsed_s": 15.0, "rc": None}]}
    s = diag.summarise(rows, slow, {"std": {"pct": 6.0}}, LIVE, dict(LIVE, pid=8))
    assert not s["bars"]["std probe: 0 of 10 over 10 s"]
    assert not s["bars"]["std CPU <= 5 % of a core"]
    assert not s["bars"]["live agent pid unchanged"]
    assert not diag.summarise(rows, {"std": GOOD_PROBES["std"][:9]}, CPU, LIVE,
                              LIVE)["bars"]["std probe: 0 of 10 over 10 s"]


def test_a_light_load_is_not_determined():
    rows = _rows([300.0] * 10, [2000.0] * 10, load=30.0)
    s = diag.summarise(rows, GOOD_PROBES, CPU, LIVE, LIVE)
    assert s["load"]["valid"] == "not determined"
    assert "not determined" in diag.render(s, rows, {"start": "a", "end": "b"}, {})


def test_the_follower_proxy_counts_slow_state_samples():
    rows = _rows([300.0] * 5, [2000.0] * 5)
    for r, ms in zip([r for r in rows if r["endpoint"] == "/api/state"],
                     [2500.0, None, 2100.0, 100.0, 2600.0]):
        r["ms"] = ms
    fp = diag.summarise(rows, GOOD_PROBES, CPU, LIVE, LIVE)["follower_proxy"]
    assert fp == {"over_2s": 4, "longest_run": 3}


# --------------------------------------------------------------------------- #
# probe
# --------------------------------------------------------------------------- #
def test_probe_posts_n_banners_and_records_a_timeout(tmp_path):
    seen = []

    def run(args, **kw):
        seen.append(args)
        if len(seen) == 2:
            raise subprocess.TimeoutExpired(args, kw["timeout"])
        return subprocess.CompletedProcess(args, 0)

    out = tmp_path / "p.jsonl"
    assert diag.probe("std", 3, out, run=run, sleep=lambda s: None) == 0
    recs = diag.read_probes(out)
    assert len(recs) == 3 and [r["rc"] for r in recs] == [0, None, 0]
    assert seen[0][0] == "/usr/bin/osascript" and seen[0][-1] == "SONAR diag 1"
    with pytest.raises(diag.Refused):
        diag.probe("Bad;tag", 1, out, run=run)


# --------------------------------------------------------------------------- #
# run, end to end with launchd, curl and the clock faked
# --------------------------------------------------------------------------- #
LIVE_PRINT = "\tpid = 7\n\tspawn type = background (5)\n"
PRINTED = {"com.netrunner3000.sonar": LIVE_PRINT,
           "com.netrunner3000.sonar-diag.bg": "\tpid = 11\n\tspawn type = background (5)\n",
           "com.netrunner3000.sonar-diag.std": "\tpid = 12\n\tspawn type = daemon (3)\n"}
LOADED = ["com.netrunner3000.sonar-diag.bg", "com.netrunner3000.sonar-diag.std",
          "com.netrunner3000.sonar"]


@pytest.fixture
def rig(monkeypatch, tmp_path):
    """Everything ``run`` touches, faked: launchctl/ps (``Cmd``), the HTTP
    fetch, the clock, the load, the venv python and the Anthropic profile.
    No real launchd, no real wait, no dependency on this checkout's .venv."""
    r = types.SimpleNamespace(made=[], ports=[], cmd=Cmd(print_out=dict(PRINTED), listed=LOADED),
                              health=HEALTH, out=tmp_path / "m.md", on_fetch=None, clock=[0.0])
    real_make = diag.make_scratch
    monkeypatch.setattr(diag, "make_scratch", lambda: r.made.append(real_make()) or r.made[-1])
    monkeypatch.setattr(diag, "_cmd", lambda *a, **k: r.cmd(*a, **k))

    def fetch(port, path, keep_body, timeout=60):
        r.ports.append((port, path))
        if r.on_fetch:
            r.on_fetch(len(r.ports))
        return {"code": 200, "ms": 200.0 if port == 8789 else 2500.0,
                "body": json.dumps(r.health) if keep_body else None}
    monkeypatch.setattr(diag, "fetch", fetch)
    monkeypatch.setattr(diag, "market_open", lambda t: False)
    monkeypatch.setattr(diag, "port_free", lambda p: True)
    monkeypatch.setattr(diag, "read_probes", lambda p: [{"elapsed_s": 1.0, "rc": 0}] * 10)
    py = tmp_path / "venv-python"
    py.write_text("")
    monkeypatch.setattr(diag, "VENV_PYTHON", py)
    monkeypatch.setattr(diag, "ANTHROPIC_PROFILE", tmp_path / "no-such-profile")
    clock = r.clock
    monkeypatch.setattr(diag, "time", types.SimpleNamespace(
        monotonic=lambda: clock[0], time=lambda: 1_790_000_000 + clock[0],
        sleep=lambda s: clock.__setitem__(0, clock[0] + max(s, 0.001)),
        strftime=lambda f: "00:00:00"))
    monkeypatch.setattr(os, "getloadavg", lambda: (90.0, 0, 0))
    r.run = lambda *extra: diag.main(["run", "--minutes", "2", "--every", "30", "--stagger",
                                      "60", "--out", str(r.out), *extra])
    return r


def _boots(r):
    return [Path(c[3]).name for c in r.cmd.verbs("bootstrap")]


def test_a_whole_run_touches_only_diag_jobs_and_keeps_only_numbers(rig):
    assert rig.run() == 0
    assert all(p != 8787 for p, _ in rig.ports), "a request reached the live agent"
    assert all(c[0] in ("/bin/launchctl", "/bin/ps") for c in rig.cmd.calls), "PATH lookup"
    for c in rig.cmd.verbs("bootout"):
        assert c[2].rsplit("/", 1)[-1].startswith("com.netrunner3000.sonar-diag.")
    assert _boots(rig) == ["com.netrunner3000.sonar-diag.bg.plist",
                           "com.netrunner3000.sonar-diag.std.plist",
                           "com.netrunner3000.sonar-diag.probe-bg.plist",
                           "com.netrunner3000.sonar-diag.probe-std.plist"]
    assert [c[2].rsplit("/", 1)[-1] for c in rig.cmd.verbs("print")].count(
        "com.netrunner3000.sonar") == 2, "live pid read before and after"
    text = rig.out.read_text()
    for bad in ("10432", "AAPL", "bankroll", "secret", "pnl", "equity"):
        assert bad not in text
    assert "Window (UTC)" in text and "| std health p95 <= 3 s | pass |" in text
    assert "background (5)" in text and "daemon (3)" in text
    assert not rig.made[0].exists(), "the scratch dir was left behind"
    assert not Path(str(rig.out) + ".partial").exists(), "the partial file outlived a good run"


def test_a_changed_live_pid_fails_the_run(rig):
    rig.cmd.print_out["com.netrunner3000.sonar"] = [LIVE_PRINT, "\tpid = 8\n"]
    assert rig.run() == 1
    assert "live agent pid unchanged | FAIL" in rig.out.read_text()


def test_a_run_aborts_if_an_engine_could_push(rig):
    rig.health = dict(HEALTH, notify={"ntfy": {"state": "ok", "reason": "ok"}})
    assert rig.run() == 2
    assert _boots(rig) == ["com.netrunner3000.sonar-diag.bg.plist"], \
        "std started after bg failed the check"
    assert rig.cmd.verbs("bootout"), "bg was not booted out"
    assert rig.clock[0] >= diag.ALARM_CHECK_S >= 120, "gave up before the startup deadline"
    assert not rig.made[0].exists() and not rig.out.exists()


def test_the_alarm_check_gives_a_slow_engine_time():
    assert diag.ALARM_CHECK_S >= 120 and diag.ALARM_REQUEST_S >= 30
    seen = []
    clock = [0.0]
    diag_fetch = diag.fetch
    try:
        diag.fetch = lambda port, path, keep, timeout=60: seen.append(timeout) or {
            "code": 200, "ms": 1.0, "body": json.dumps(HEALTH)}
        diag.wait_alarm_off(8789, clock=lambda: clock[0], sleep=lambda s: None)
    finally:
        diag.fetch = diag_fetch
    assert seen == [diag.ALARM_REQUEST_S]


@pytest.mark.parametrize("health", [
    dict(HEALTH, last_poll_age_s=None, problems=[]),                     # never polled
    dict(HEALTH, problems=[{"kind": "scan", "text": "not rescanned"}]),  # polled, scan open
])
def test_a_first_scan_that_misses_the_cap_stops_before_std(rig, health):
    rig.health = health
    assert rig.run() == 2
    assert _boots(rig) == ["com.netrunner3000.sonar-diag.bg.plist"], "cold scans overlapped"
    assert not rig.made[0].exists()


def test_a_failed_bootstrap_stops_the_run_and_cleans_up(rig):
    rig.cmd.bootstrap_rc = 5
    assert rig.run() == 2
    assert len(_boots(rig)) == 1 and rig.cmd.verbs("bootout")
    assert not rig.made[0].exists() and not rig.out.exists()


def test_market_hours_are_checked_again_before_the_hour(rig, monkeypatch):
    calls = []

    def check(start, minutes, force=False):
        calls.append(minutes)
        if len(calls) == 2:
            raise diag.Refused("the open arrived while waiting")
    monkeypatch.setattr(diag, "check_market_hours", check)
    assert rig.run() == 2
    assert calls == [2 + 2 * 60 / 60, 2]
    assert not any(path == "/api/config" for _, path in rig.ports), "the hour started"
    assert "probe" not in " ".join(_boots(rig))


def test_an_anthropic_profile_is_refused(rig, tmp_path, monkeypatch):
    prof = tmp_path / "anthropic"
    prof.mkdir()
    monkeypatch.setattr(diag, "ANTHROPIC_PROFILE", prof)
    assert rig.run() == 2
    assert rig.cmd.calls == [] and rig.made == []


ALL_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


@pytest.mark.parametrize("sig", ALL_SIGNALS)
def test_a_signal_mid_run_cleans_up_and_restores_the_handlers(rig, sig):
    # Our own handlers first: a harness that missed one would otherwise leave
    # the default (HUP's kills this test process), and restoring to SIG_DFL
    # instead of "what was there" shows up as a difference.
    caught = []
    mine = {s: (lambda signum, frame: caught.append(signum)) for s in ALL_SIGNALS}
    old = {s: signal.signal(s, h) for s, h in mine.items()}
    try:
        rig.on_fetch = lambda n: os.kill(os.getpid(), sig) if n == 20 else None
        rc = rig.run()
        after = {s: signal.getsignal(s) for s in ALL_SIGNALS}
    finally:
        for s, h in old.items():
            signal.signal(s, h)
    assert rc == 130 and caught == [], "the harness did not handle the signal itself"
    assert after == mine, "the previous handlers were not restored"
    assert sorted(c[2].rsplit("/", 1)[-1] for c in rig.cmd.verbs("bootout")) == [
        "com.netrunner3000.sonar-diag.bg", "com.netrunner3000.sonar-diag.std"]
    assert not rig.made[0].exists()
    partial = Path(str(rig.out) + ".partial")
    rows = [json.loads(x) for x in partial.read_text().splitlines()]
    assert rows and "10432" not in partial.read_text(), "samples so far are kept, numbers only"


def test_a_signal_during_cleanup_is_ignored(rig):
    seen = []
    real = diag.cleanup

    def cleanup(d, follower=None):
        seen.append(signal.getsignal(signal.SIGTERM))
        os.kill(os.getpid(), signal.SIGTERM)          # ignored, not a crash mid-cleanup
        return real(d, follower)
    diag_cleanup = diag.cleanup
    diag.cleanup = cleanup
    try:
        assert rig.run() == 0
    finally:
        diag.cleanup = diag_cleanup
    assert seen == [signal.SIG_IGN] and not rig.made[0].exists()


# --------------------------------------------------------------------------- #
# Review fixes: case, scratch, cleanup without --dir, bootout, percentiles
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rel", ["library/application support/SONAR/x.md",
                                 "LIBRARY/LaunchAgents/x.plist",
                                 "Library/launchagents"])
def test_the_path_guard_ignores_letter_case(tmp_path, rel):
    with pytest.raises(diag.Refused):
        diag.check_outside_live(tmp_path / rel, home=tmp_path)


def test_make_scratch_leaves_nothing_when_refused(monkeypatch):
    made = []
    real = tempfile.mkdtemp
    monkeypatch.setattr(diag.tempfile, "mkdtemp", lambda **k: made.append(real(**k)) or made[-1])

    def refuse(d, home=None):
        raise diag.Refused("no")
    monkeypatch.setattr(diag, "check_scratch", refuse)
    with pytest.raises(diag.Refused):
        diag.make_scratch()
    assert made and not Path(made[0]).exists()


def test_cleanup_without_a_dir_removes_every_left_over_scratch_dir(monkeypatch, tmp_path):
    # A private temp dir: the real one may hold a measured run's scratch dir.
    private = tmp_path / "T"
    private.mkdir()
    monkeypatch.setattr(diag.tempfile, "tempdir", str(private.resolve()))
    monkeypatch.setattr(diag, "_cmd", Cmd())
    left = [diag.make_scratch(), diag.make_scratch()]
    (left[0] / "std" / "data").mkdir(parents=True)
    other = Path(tempfile.gettempdir()) / "not-sonar-diag"
    other.mkdir(exist_ok=True)
    link = Path(tempfile.gettempdir()) / f"sonar-diag-link-{os.getpid()}"
    target = tmp_path / "target"
    target.mkdir()
    link.symlink_to(target)
    diag.cleanup()
    assert all(d.parent == private.resolve() for d in left)
    assert not any(d.exists() for d in left)
    assert other.exists() and target.exists(), "only sonar-diag-* dirs, never through a link"


def test_a_hung_bootout_is_reported_and_does_not_stop_cleanup(monkeypatch, scratch):
    cmd = Cmd(listed=["com.netrunner3000.sonar-diag.bg", "com.netrunner3000.sonar-diag.std"],
              bootout_raises=subprocess.TimeoutExpired("launchctl", 90))
    monkeypatch.setattr(diag, "_cmd", cmd)
    gone = diag.cleanup(scratch)
    assert gone == {"com.netrunner3000.sonar-diag.bg": None,
                    "com.netrunner3000.sonar-diag.std": None}
    assert len(cmd.verbs("bootout")) == 2 and not scratch.exists()


def test_bootout_reports_the_real_return_code(monkeypatch):
    monkeypatch.setattr(diag, "_cmd", lambda a, timeout=30: subprocess.CompletedProcess(a, 3))
    assert diag.bootout("com.netrunner3000.sonar-diag.bg") == 3


def test_a_bootstrap_failure_is_refused(monkeypatch, scratch):
    monkeypatch.setattr(diag, "_cmd", Cmd(bootstrap_rc=5))
    path = diag.write_plist(diag.engine_plist("std", scratch), scratch)
    with pytest.raises(diag.Refused, match="failed"):
        diag.bootstrap(path, scratch)


def test_ten_percent_non_answers_push_p95_over_the_bar():
    rows = _rows([300.0] * 18 + [None] * 2, [2000.0] * 20)
    for r in rows:
        if r["ms"] is None:
            r["code"] = 0
    state = [r for r in rows if r["endpoint"] == "/api/state"]
    for r in state[:2]:
        r["ms"], r["code"] = None, 0
    s = diag.summarise(rows, GOOD_PROBES, CPU, LIVE, LIVE)
    assert s["endpoints"][("std", "/api/health")]["p95"] > diag.HEALTH_P95_MS
    assert not s["bars"]["std health p95 <= 3 s"]
    assert s["endpoints"][("std", "/api/state")]["p95"] > 1000, "A5's input hides timeouts"


def test_a_market_open_inside_the_window_is_refused():
    # Starts and ends outside the hours, the open lies between: only the loop sees it.
    with pytest.raises(diag.Refused):
        diag.check_market_hours(dt.datetime(2026, 10, 19, 9, 0, tzinfo=NY), 8 * 60)


def test_the_output_is_never_written_through_a_symlink(tmp_path):
    target = tmp_path / "elsewhere"
    link = tmp_path / "m.md"
    link.symlink_to(target)
    with pytest.raises(OSError):
        diag.write_nofollow(link, "x")
    assert not target.exists()


def test_watch_keeps_the_banner_attempts_and_counts_samples(tmp_path):
    h = dict(HEALTH, notify={"banner": {"failures": 3, "attempts": 40}, "ntfy": {"reason": "ok"}})
    clock = [0.0]
    s = diag.watch(8787, 300, 600 / 86400, tmp_path / "w.jsonl", clock=lambda: clock[0],
                   sleep=lambda x: clock.__setitem__(0, clock[0] + x),
                   fetcher=lambda: {"code": 200, "ms": 100.0, "body": json.dumps(h)})
    assert s["banner_failures"] == 3 and s["banner_attempts"] == 40
    assert s["samples_with_poll_or_scan_problem"] == 3 and not s["alarm_off_seen"]
