#!/usr/bin/env python3
"""Measure the agent's launchd priority side by side, without touching the agent.

docs/specs/starved-engine.md, measures 2, 3 and 5 (Architecture A4). Two
throwaway launchd jobs run this checkout's engine at the same time:
``com.netrunner3000.sonar-diag.bg`` (the old ``Background`` + ``Nice 5``) on
port 8788 and ``com.netrunner3000.sonar-diag.std`` (``Standard``, no ``Nice``)
on 8789, each in its own scratch ``SONAR_DATA``. The harness samples both for
an hour and writes a numbers-only file.

    python3 -I scripts/diag_priority.py run [--follower] [--force]
    python3 -I scripts/diag_priority.py probe <tag> <n> --out FILE
    python3 -I scripts/diag_priority.py watch --port 8787 --every 300 --days 7
    python3 -I scripts/diag_priority.py cleanup [--dir D]

The live agent (``com.netrunner3000.sonar``, port 8787) is read, never touched:
``run`` only reads its pid and spawn type with ``launchctl print``, and every
``bootstrap``/``bootout`` here goes through :func:`check_label`, which refuses
any label outside ``com.netrunner3000.sonar-diag.*``. Plists are written only
under a fresh ``mkdtemp(prefix="sonar-diag-")``, never in
``~/Library/LaunchAgents``; nothing is read from or written to
``~/Library/Application Support``.

What is kept from a response is a whitelist (:func:`whitelist`): ``ok``,
``last_poll_age_s``, the problem kinds, whether the push alarm is off, and the
banner's failure and attempt counts. The ``/api/state`` and ``/api/config`` bodies are
discarded unread. No book, P&L or score field is ever parsed (domain P2-2).

Stdlib only, so it runs under ``python3 -I`` with no venv.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import plistlib
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LIVE_LABEL = "com.netrunner3000.sonar"
LIVE_PORT = 8787
LABEL_PREFIX = "com.netrunner3000.sonar-diag."
LABEL_RE = re.compile(r"^com\.netrunner3000\.sonar-diag\.[a-z-]+$")
SCRATCH_PREFIX = "sonar-diag-"

#: The two job classes under test. ``bg`` is today's live plist, ``std`` the new one.
VARIANTS = {
    "bg": {"port": 8788, "ProcessType": "Background", "Nice": 5},
    "std": {"port": 8789, "ProcessType": "Standard"},
}

#: Market-data keys, which no code reads since the unwired provider module was
#: deleted (the provider-wiring spec in docs/specs), and the LLM's (sonar/llm.py,
#: which reads only the process environment). A per-job empty value overrides
#: any ``launchctl setenv`` global, so a diag job runs keyless whatever is set
#: (A3, P3-b).
BLANK_KEYS = ("FINNHUB_API_KEY", "TWELVEDATA_API_KEY", "ALPHAVANTAGE_API_KEY",
              "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
              # Nothing calls the paper broker today; an empty value also wins
              # over alpaca.load_env()'s setdefault from .env (security P3-4).
              "APCA_API_KEY_ID", "APCA_API_SECRET_KEY")
#: What /api/health says when SONAR_ALARM keeps the engine off the phone (A2).
OFF_REASON = "off (SONAR_ALARM)"
ENV_CHECK = BLANK_KEYS + ("SONAR_ALARM",)

#: The bars of measure 2 and 3.
HEALTH_P50_MS, HEALTH_P95_MS, HEALTH_MAX_MS = 1000, 3000, 10000
POLL_P95_S, POLL_MAX_S = 12.0, 120.0
PROBE_SLOW_S = 10.0
CPU_MAX_PCT = 5.0
LOAD_VALID, LOAD_SHARE = 50.0, 0.60
FOLLOW_TIMEOUT_MS = 2000.0          # core.FOLLOW_TIMEOUT, for the follower proxy

PROBE_GAP_S, PROBE_CAP_S = 2.0, 15.0
#: The Background engine took 3-24 s to answer and about 47 s to spawn in the
#: diagnosis, so the alarm-off check waits this long, still failing closed.
ALARM_CHECK_S = 120.0
ALARM_REQUEST_S = 30
#: A sample with no answer counts as this in the percentiles: it is slower than
#: any answer, so failures push p95 up instead of vanishing from it.
NO_ANSWER_MS = math.inf
BOOTOUT_TIMEOUT_S = 90

#: Absolute paths, as for osascript: never whatever is first on PATH.
LAUNCHCTL, PS, CURL = "/bin/launchctl", "/bin/ps", "/usr/bin/curl"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
#: An ``ant auth login`` profile lets the LLM read bill with every key blank
#: (sonar/llm.py available()), so the harness refuses while it exists.
ANTHROPIC_PROFILE = Path.home() / ".config" / "anthropic"


class Refused(Exception):
    """A guard said no. The harness exits non-zero and changes nothing more."""


def say(msg: str) -> None:
    print(f"diag {time.strftime('%H:%M:%S')}: {msg}", flush=True)


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #
def check_label(label: str) -> str:
    """``label`` if it is a diag label; never the live agent's."""
    if label == LIVE_LABEL or not LABEL_RE.fullmatch(label or ""):
        raise Refused(f"refusing label {label!r}: only {LABEL_PREFIX}* is ever touched")
    return label


def label(variant: str) -> str:
    return check_label(LABEL_PREFIX + variant)


def forbidden_roots(home: Path | None = None) -> list[Path]:
    home = Path(home or Path.home())
    return [(home / "Library" / "LaunchAgents").resolve(),
            (home / "Library" / "Application Support").resolve()]


def _under(path: Path, root: Path) -> bool:
    """``path`` is ``root`` or below it, ignoring letter case: the Mac's disk
    is case-insensitive, so ``library/application support`` is the same place."""
    a = [x.casefold() for x in path.parts]
    b = [x.casefold() for x in root.parts]
    return a[:len(b)] == b


def check_outside_live(path: Path, home: Path | None = None) -> Path:
    """``path`` resolved, if it is not in LaunchAgents or Application Support."""
    p = Path(path).expanduser().resolve()
    for root in forbidden_roots(home):
        if _under(p, root):
            raise Refused(f"refusing {p}: it is under {root}")
    return p


def check_scratch(d: Path, home: Path | None = None) -> Path:
    """The scratch dir: a ``sonar-diag-*`` dir directly under the temp dir."""
    p = check_outside_live(d, home)
    tmp = Path(tempfile.gettempdir()).resolve()
    if not p.name.startswith(SCRATCH_PREFIX) or p.parent != tmp:
        raise Refused(f"refusing scratch dir {p}: not {tmp}/{SCRATCH_PREFIX}*")
    return p


def check_inside(path: Path, d: Path, home: Path | None = None) -> Path:
    """``path`` resolved, if it lies under the scratch dir ``d``."""
    p = check_outside_live(path, home)
    if not _under(p, check_scratch(d, home)):
        raise Refused(f"refusing {p}: not under the scratch dir {d}")
    return p


def make_scratch() -> Path:
    d = Path(tempfile.mkdtemp(prefix=SCRATCH_PREFIX))
    try:
        return check_scratch(d)
    except Refused:
        d.rmdir()                         # just made and empty: nothing left behind
        raise


def port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def check_ports(ports, free=None) -> None:
    free = free or port_free
    for port in ports:
        if port == LIVE_PORT:
            raise Refused(f"refusing port {port}: it is the live agent's")
        if not free(port):
            raise Refused(f"port {port} is in use; stop whatever holds it first (a diag job "
                          "left over from a killed run: diag_priority.py cleanup)")


def market_open(now: _dt.datetime) -> bool:
    """US equity hours, Mon-Fri 09:30-16:00 America/New_York. Holidays count
    as open: the guard errs towards refusing."""
    from zoneinfo import ZoneInfo
    ny = now.astimezone(ZoneInfo("America/New_York"))
    return ny.weekday() < 5 and _dt.time(9, 30) <= ny.time() < _dt.time(16, 0)


def check_market_hours(start: _dt.datetime, minutes: float, force: bool = False) -> None:
    """Refuse a window that starts in, or runs into, US market hours."""
    if force:
        return
    end = start + _dt.timedelta(minutes=minutes)
    t = start
    while t <= end:
        if market_open(t):
            raise Refused(f"the window {start:%Y-%m-%d %H:%M}Z-{end:%H:%M}Z touches US market "
                          "hours (Mon-Fri 09:30-16:00 New York); run later or pass --force")
        t += _dt.timedelta(minutes=5)
    if market_open(end):
        raise Refused("the window ends inside US market hours; run earlier or pass --force")


# --------------------------------------------------------------------------- #
# launchctl, ps, curl
# --------------------------------------------------------------------------- #
def _cmd(args, timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def domain() -> str:
    return f"gui/{os.getuid()}"


def bootstrap(plist_path: Path, d: Path) -> None:
    """Load a diag plist. Only a file under ``d`` whose Label is a diag label."""
    p = check_inside(plist_path, d)
    with open(p, "rb") as f:
        check_label(plistlib.load(f).get("Label", ""))
    r = _cmd([LAUNCHCTL, "bootstrap", domain(), str(p)])
    if r.returncode:
        raise Refused(f"launchctl bootstrap {p.name} failed ({r.returncode}): "
                      f"{(r.stderr or '').strip()[:200]}")


def bootout(lbl: str) -> int | None:
    """``launchctl bootout``'s return code; None if it hung or could not run.
    Never raises past the label check, so one stuck job cannot stop cleanup."""
    target = f"{domain()}/{check_label(lbl)}"
    try:
        return _cmd([LAUNCHCTL, "bootout", target], timeout=BOOTOUT_TIMEOUT_S).returncode
    except (subprocess.TimeoutExpired, OSError):
        return None


def loaded_diag_labels() -> list[str]:
    """Every loaded ``sonar-diag.*`` label, from ``launchctl list``."""
    try:
        r = _cmd([LAUNCHCTL, "list"])
    except (subprocess.TimeoutExpired, OSError):
        return []
    out = []
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if parts and LABEL_RE.fullmatch(parts[-1]):
            out.append(parts[-1])
    return out


def job_info(lbl: str) -> dict:
    """``pid`` and ``spawn type`` from ``launchctl print``; read-only, so the
    live label is allowed here and only here."""
    r = _cmd([LAUNCHCTL, "print", f"{domain()}/{lbl}"])
    info = {"pid": None, "spawn_type": None, "nice": None, "loaded": r.returncode == 0}
    for line in (r.stdout or "").splitlines():
        k, _, v = line.strip().partition(" = ")
        if k == "pid" and v.strip().isdigit():
            info["pid"] = int(v)
        elif k == "spawn type":
            info["spawn_type"] = v.strip()
        elif k == "nice":
            info["nice"] = v.strip()
    return info


def parse_cputime(text: str) -> float | None:
    """``ps -o cputime=`` ("1:02.34", "1:02:03.45" or "2-01:02:03") as seconds."""
    t = (text or "").strip()
    if not t:
        return None
    days = 0
    if "-" in t:
        d, t = t.split("-", 1)
        days = int(d)
    try:
        parts = [float(x) for x in t.split(":")]
    except ValueError:
        return None
    secs = 0.0
    for x in parts:
        secs = secs * 60 + x
    return days * 86400 + secs


def cputime(pid: int | None) -> float | None:
    if not pid:
        return None
    return parse_cputime(_cmd([PS, "-o", "cputime=", "-p", str(pid)]).stdout)


def fetch(port: int, path: str, keep_body: bool, timeout: float = 60) -> dict:
    """One ``curl`` sample: ms, HTTP code, and the body only if asked for."""
    if port == LIVE_PORT and path != "/api/health":
        raise Refused("only /api/health is ever read from the live agent")
    args = [CURL, "-s", "-m", str(int(timeout)), "-w", r"\n%{http_code} %{time_total}"]
    if not keep_body:
        args += ["-o", os.devnull]
    args.append(f"http://127.0.0.1:{port}{path}")
    try:
        r = _cmd(args, timeout=timeout + 10)
        out = r.stdout or ""
    except subprocess.TimeoutExpired:
        out = ""
    body, _, tail = out.rpartition("\n")
    code, ms = 0, None
    m = re.fullmatch(r"(\d{3}) ([0-9.]+)", tail.strip())
    if m and m.group(1) != "000":         # 000: no answer at all (refused, timed out)
        code, ms = int(m.group(1)), round(float(m.group(2)) * 1000, 1)
    return {"code": code, "ms": ms, "body": body if keep_body else None}


def whitelist(body: str | None) -> dict:
    """The only fields kept from a health body. Everything else is dropped
    unread: a health answer is not supposed to carry money, but this does not
    rely on that."""
    out = {"ok": None, "last_poll_age_s": None, "kinds": [], "alarm_off": None,
           "banner_failures": None, "banner_attempts": None}
    try:
        h = json.loads(body or "")
    except ValueError:
        return out
    if not isinstance(h, dict):
        return out
    if isinstance(h.get("ok"), bool):
        out["ok"] = h["ok"]
    age = h.get("last_poll_age_s")
    if isinstance(age, (int, float)) and not isinstance(age, bool) and math.isfinite(age):
        out["last_poll_age_s"] = float(age)
    probs = h.get("problems")
    if isinstance(probs, list):
        out["kinds"] = sorted({p["kind"] for p in probs if isinstance(p, dict)
                               and isinstance(p.get("kind"), str)
                               and re.fullmatch(r"[a-z]{1,20}", p["kind"])})
    notify = h.get("notify")
    if isinstance(notify, dict):
        ntfy, banner = notify.get("ntfy"), notify.get("banner")
        if isinstance(ntfy, dict):
            out["alarm_off"] = ntfy.get("reason") == OFF_REASON
        if isinstance(banner, dict):
            for key in ("failures", "attempts"):
                v = banner.get(key)
                if isinstance(v, int) and not isinstance(v, bool):
                    out[f"banner_{key}"] = v
    return out


def sample(port: int, endpoint: str, t: float, load: float) -> dict:
    """One row of the table: health keeps its whitelist, the rest no body."""
    health = endpoint == "/api/health"
    r = fetch(port, endpoint, keep_body=health)
    row = {"t": round(t, 1), "port": port, "endpoint": endpoint, "ms": r["ms"],
           "code": r["code"], "load": round(load, 1)}
    if health:
        w = whitelist(r["body"])
        row.update({"poll_age_s": w["last_poll_age_s"], "kinds": w["kinds"],
                    "alarm_off": w["alarm_off"], "banner_failures": w["banner_failures"],
               "banner_attempts": w["banner_attempts"]})
    return row


def global_env() -> dict:
    """``launchctl getenv`` for the keys and SONAR_ALARM: a global value
    reaches every job, the live agent too (domain P3-a)."""
    out = {}
    for k in ENV_CHECK:
        v = (_cmd([LAUNCHCTL, "getenv", k]).stdout or "").strip()
        out[k] = "set" if v else "empty"
    return out


# --------------------------------------------------------------------------- #
# Plists
# --------------------------------------------------------------------------- #
def engine_plist(variant: str, d: Path, python: Path | None = None,
                 main_py: Path | None = None) -> dict:
    """The throwaway engine's launchd job: the checkout's ``main.py
    --headless`` on its own port, data, backups and logs under ``d``, the
    push alarm off and every key blank."""
    v = VARIANTS[variant]
    base = d / variant
    data, backup, logs = base / "data", base / "backup", base / "logs"
    for p in (data, backup, logs):
        check_inside(p, d)
    env = {"SONAR_DATA": str(data), "SONAR_BACKUP_DIR": str(backup), "SONAR_ALARM": "off"}
    env.update({k: "" for k in BLANK_KEYS})
    p = {"Label": label(variant),
         "ProgramArguments": [str(python or VENV_PYTHON),
                              str(main_py or ROOT / "main.py"), "--headless",
                              "--host", "127.0.0.1", "--port", str(v["port"])],
         "WorkingDirectory": str(ROOT),
         "EnvironmentVariables": env,
         "RunAtLoad": True,
         "StandardOutPath": str(logs / "agent.out.log"),
         "StandardErrorPath": str(logs / "agent.err.log"),
         "ProcessType": v["ProcessType"]}
    if "Nice" in v:
        p["Nice"] = v["Nice"]
    return p


def probe_plist(variant: str, d: Path, n: int = 10, python: str | None = None) -> dict:
    """The banner probe in the same job class as its engine (diagnosis §4)."""
    v = VARIANTS[variant]
    base = d / f"probe-{variant}"
    out = check_inside(base / "probe.jsonl", d)
    p = {"Label": label(f"probe-{variant}"),
         "ProgramArguments": [python or sys.executable, "-I", str(Path(__file__).resolve()),
                              "probe", variant, str(n), "--out", str(out)],
         "WorkingDirectory": str(check_inside(base, d)),
         "EnvironmentVariables": {k: "" for k in BLANK_KEYS},
         "RunAtLoad": True,
         "StandardOutPath": str(base / "out.log"),
         "StandardErrorPath": str(base / "err.log"),
         "ProcessType": v["ProcessType"]}
    if "Nice" in v:
        p["Nice"] = v["Nice"]
    return p


def write_plist(p: dict, d: Path) -> Path:
    check_label(p["Label"])
    path = check_inside(d / f"{p['Label']}.plist", d)
    for key in ("StandardOutPath", "StandardErrorPath"):
        Path(check_inside(Path(p[key]), d)).parent.mkdir(parents=True, exist_ok=True)
    for key in ("SONAR_DATA", "SONAR_BACKUP_DIR"):
        if key in p["EnvironmentVariables"]:
            check_inside(Path(p["EnvironmentVariables"][key]), d).mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(p, f)
    return path


# --------------------------------------------------------------------------- #
# Numbers
# --------------------------------------------------------------------------- #
def percentile(values, q: float) -> float | None:
    """Nearest-rank percentile (q in 0-100); None for no values."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    k = max(1, math.ceil(q / 100 * len(xs)))
    return xs[k - 1]


def longest_run(flags) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def latencies(rows) -> list[float]:
    """Every sample's ms, a non-answer as :data:`NO_ANSWER_MS` (review P2-2):
    dropping them would let 10 % timeouts leave p95 looking fine."""
    return [NO_ANSWER_MS if r["ms"] is None or r["code"] == 0 else r["ms"] for r in rows]


def _stats(rows) -> dict:
    vals = latencies(rows)
    return {"n": len(rows), "failed": sum(1 for r in rows if r["ms"] is None or r["code"] == 0),
            "p50": percentile(vals, 50), "p95": percentile(vals, 95),
            "max": max(vals) if vals else None}


def summarise(rows, probes: dict, cpu: dict, live_before: dict, live_after: dict) -> dict:
    """The per-port, per-endpoint statistics and every bar, pass or fail."""
    s = {"endpoints": {}, "poll": {}, "probes": {}, "cpu": cpu, "bars": {}}
    for variant, v in VARIANTS.items():
        port = v["port"]
        mine = [r for r in rows if r["port"] == port]
        for ep in sorted({r["endpoint"] for r in mine}):
            s["endpoints"][(variant, ep)] = _stats([r for r in mine if r["endpoint"] == ep])
        ages = [r.get("poll_age_s") for r in mine if r["endpoint"] == "/api/health"]
        s["poll"][variant] = {"p95": percentile(ages, 95),
                              "max": max((a for a in ages if a is not None), default=None)}
        recs = probes.get(variant) or []
        s["probes"][variant] = {"n": len(recs),
                                "slow": sum(1 for p in recs if p.get("elapsed_s", 0) > PROBE_SLOW_S
                                            or p.get("rc") is None)}
    loads = [r["load"] for r in rows if r["endpoint"] == "/api/health"]
    share = (sum(1 for x in loads if x >= LOAD_VALID) / len(loads)) if loads else 0.0
    s["load"] = {"share_ge_50": round(share, 3), "min": min(loads, default=None),
                 "max": max(loads, default=None),
                 "valid": "valid" if share >= LOAD_SHARE else "not determined"}
    state = [r for r in rows if r["port"] == VARIANTS["std"]["port"]
             and r["endpoint"] == "/api/state"]
    s["follower_proxy"] = {"over_2s": sum(1 for r in state if r["ms"] is None
                                          or r["ms"] > FOLLOW_TIMEOUT_MS),
                           "longest_run": longest_run(r["ms"] is None or r["ms"] > FOLLOW_TIMEOUT_MS
                                                      for r in state)}
    s["live"] = {"before": live_before, "after": live_after,
                 "unchanged": live_before.get("pid") == live_after.get("pid")}
    s["bars"] = bars(s)
    return s


def _le(x, bar) -> bool:
    return x is not None and x <= bar


def bars(s: dict) -> dict:
    std = s["endpoints"].get(("std", "/api/health")) or {}
    bg = s["endpoints"].get(("bg", "/api/health")) or {}
    out = {
        "std health p50 <= 1 s": _le(std.get("p50"), HEALTH_P50_MS),
        "std health p95 <= 3 s": _le(std.get("p95"), HEALTH_P95_MS),
        "std health max < 10 s": std.get("max") is not None and std["max"] < HEALTH_MAX_MS
        and not std.get("failed"),
        "std poll age p95 <= 12 s": _le(s["poll"]["std"]["p95"], POLL_P95_S),
        # A provider failure logged at the time excuses an excess (spec measure 2);
        # the harness does not read the log, so an excess fails here for a person to check.
        "std poll age never > 120 s": _le(s["poll"]["std"]["max"], POLL_MAX_S),
        "std probe: 0 of 10 over 10 s": s["probes"]["std"]["n"] == 10
        and s["probes"]["std"]["slow"] == 0,
        "std health p95 <= half of bg": std.get("p95") is not None and bg.get("p95") is not None
        and std["p95"] <= bg["p95"] / 2,
        "std CPU <= 5 % of a core": _le((s["cpu"].get("std") or {}).get("pct"), CPU_MAX_PCT),
        "live agent pid unchanged": bool(s["live"]["unchanged"]),
    }
    return out


def _fmt(x, unit="") -> str:
    return "n/a" if x is None else f"{x:g}{unit}"


def render(s: dict, rows, window: dict, meta: dict) -> str:
    """The evidence file: latency, poll age, load and CPU only (domain P2-2)."""
    lines = ["# starved-engine: side-by-side measurement", "",
             "Written by `scripts/diag_priority.py run` (docs/specs/starved-engine.md A4). "
             "Numbers only: no book, P&L or score field was read.", "",
             f"- Window (UTC): {window['start']} to {window['end']}",
             f"- Job classes: bg = `ProcessType Background` + `Nice 5` (port 8788); "
             f"std = `ProcessType Standard`, no `Nice` (port 8789)",
             f"- Engines: {meta.get('engines', 'n/a')}",
             f"- Diag spawn types: {meta.get('spawn', 'n/a')}",
             f"- Live agent before: pid {s['live']['before'].get('pid')}, spawn type "
             f"{s['live']['before'].get('spawn_type')}; after: pid "
             f"{s['live']['after'].get('pid')}, spawn type {s['live']['after'].get('spawn_type')}",
             f"- `launchctl getenv` (global): {meta.get('global_env', 'n/a')}",
             f"- Follower: {meta.get('follower', 'none')}",
             f"- Load (1 min): {_fmt(s['load']['min'])}-{_fmt(s['load']['max'])}; share of "
             f"samples at >= 50: {s['load']['share_ge_50']:.0%} -> **{s['load']['valid']}**",
             "", "## Summary", "",
             "| job | endpoint | N | failed | p50 ms | p95 ms | max ms |", "|---|---|---|---|---|---|---|"]
    for (variant, ep), st in sorted(s["endpoints"].items()):
        lines.append(f"| {variant} | `{ep}` | {st['n']} | {st['failed']} | {_fmt(st['p50'])} | "
                     f"{_fmt(st['p95'])} | {_fmt(st['max'])} |")
    lines += ["", "| job | poll age p95 s | poll age max s | probes over 10 s | CPU % of a core |",
              "|---|---|---|---|---|"]
    for variant in VARIANTS:
        pr, cp = s["probes"][variant], s["cpu"].get(variant) or {}
        lines.append(f"| {variant} | {_fmt(s['poll'][variant]['p95'])} | "
                     f"{_fmt(s['poll'][variant]['max'])} | {pr['slow']} of {pr['n']} | "
                     f"{_fmt(cp.get('pct'))} |")
    fp = s["follower_proxy"]
    lines += ["", f"Follower proxy (std `/api/state` over 2.0 s): {fp['over_2s']} samples; "
              f"longest consecutive run {fp['longest_run']}. Owner spot checks at minutes "
              "0/15/30/45/60: not continuously observed.", "",
              "## Bars (measure 2 and 3)", "", "| bar | result |", "|---|---|"]
    for name, ok in s["bars"].items():
        lines.append(f"| {name} | {'pass' if ok else 'FAIL'} |")
    if s["load"]["valid"] != "valid":
        lines += ["", "Load was under 50 for too much of the hour: the result is **not "
                  "determined** and the run is to be repeated."]
    lines += ["", "## Samples", "", "| t s | port | endpoint | ms | code | poll age s | load |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['t']:g} | {r['port']} | `{r['endpoint']}` | {_fmt(r['ms'])} | "
                     f"{r['code']} | {_fmt(r.get('poll_age_s'))} | {r['load']:g} |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# probe
# --------------------------------------------------------------------------- #
NOTIFY_SCRIPT = ("on run argv", "display notification (item 1 of argv) "
                 "with title (item 2 of argv)", "end run")


def probe(tag: str, n: int, out: Path, run=None, sleep=None) -> int:
    """Post ``n`` "SONAR diag <i>" banners 2 s apart, each capped at 15 s,
    one JSON line each: start, elapsed, rc (None if it hit the cap)."""
    if not re.fullmatch(r"[a-z-]{1,20}", tag):
        raise Refused(f"bad probe tag {tag!r}")
    out = check_outside_live(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    run, sleep = run or subprocess.run, sleep or time.sleep
    with open(out, "a") as f:
        for i in range(1, n + 1):
            args = ["/usr/bin/osascript"]
            for line in NOTIFY_SCRIPT:
                args += ["-e", line]
            args += ["--", f"diag {tag} {i}", f"SONAR diag {i}"]
            start = time.time()
            t0 = time.monotonic()
            try:
                rc = run(args, capture_output=True, text=True, timeout=PROBE_CAP_S).returncode
            except subprocess.TimeoutExpired:
                rc = None
            f.write(json.dumps({"tag": tag, "i": i, "start": start,
                                "elapsed_s": round(time.monotonic() - t0, 3), "rc": rc,
                                "load": round(os.getloadavg()[0], 1)}) + "\n")
            f.flush()
            if i < n:
                sleep(PROBE_GAP_S)
    return 0


def read_probes(path: Path) -> list[dict]:
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append({"elapsed_s": float(rec.get("elapsed_s") or 0), "rc": rec.get("rc")})
    return out


# --------------------------------------------------------------------------- #
# cleanup
# --------------------------------------------------------------------------- #
def scratch_dirs() -> list[Path]:
    """Every ``sonar-diag-*`` dir left in the temp dir, each through the guard."""
    out = []
    for d in sorted(Path(tempfile.gettempdir()).glob(SCRATCH_PREFIX + "*")):
        try:
            if d.is_dir() and not d.is_symlink():
                out.append(check_scratch(d))
        except Refused:
            pass
    return out


def cleanup(d: Path | None = None, follower=None) -> dict[str, int | None]:
    """Boot out every loaded diag label, close the follower, then delete
    ``d`` if it is a scratch dir, or with no ``d`` every scratch dir a killed
    run left behind. Nothing is copied out first. Returns each label's
    ``bootout`` return code (None: it hung or could not run)."""
    if follower is not None and follower.poll() is None:
        follower.terminate()
        try:
            follower.wait(10)
        except subprocess.TimeoutExpired:
            follower.kill()
    gone = {}
    for lbl in loaded_diag_labels():
        try:
            gone[lbl] = bootout(lbl)
        except Refused:                   # cannot happen: listed labels match; never stop here
            continue
    targets = scratch_dirs() if d is None else [d]
    for t in targets:
        try:
            p = check_scratch(t)
        except Refused as exc:
            say(f"not deleting: {exc}")
        else:
            shutil.rmtree(p, ignore_errors=True)
    return gone


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def _utc(t: float) -> str:
    return _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def wait_alarm_off(port: int, within: float = ALARM_CHECK_S, clock=None, sleep=None) -> None:
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    deadline = clock() + within
    while True:
        w = whitelist(fetch(port, "/api/health", True, timeout=ALARM_REQUEST_S)["body"])
        if w["alarm_off"]:
            return
        if clock() >= deadline:
            raise Refused(f"port {port} does not report ntfy {OFF_REASON!r}; "
                          "stopping before it can push")
        sleep(2)


def wait_first_scan(port: int, cap: float, clock=None, sleep=None) -> bool:
    """Until the engine has polled once and lists no ``scan`` problem."""
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    deadline = clock() + cap
    while clock() < deadline:
        w = whitelist(fetch(port, "/api/health", True)["body"])
        if w["last_poll_age_s"] is not None and "scan" not in w["kinds"]:
            return True
        sleep(10)
    return False


def write_nofollow(path: Path, text: str, append: bool = False) -> None:
    """Write ``path`` (already resolved and checked) without following a
    symlink planted there after the check (security P3-5)."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_APPEND if append else os.O_TRUNC)
    fd = os.open(path, flags, 0o644)
    with os.fdopen(fd, "a" if append else "w") as f:
        f.write(text)


SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


def run(args) -> int:
    start = _dt.datetime.now(_dt.timezone.utc)
    check_market_hours(start, args.minutes + 2 * args.stagger / 60, args.force)
    out = check_outside_live(Path(args.out))
    partial = check_outside_live(out.with_name(out.name + ".partial"))
    check_ports([v["port"] for v in VARIANTS.values()])
    if ANTHROPIC_PROFILE.exists():
        raise Refused(f"{ANTHROPIC_PROFILE} exists: with it a diag engine or the follower could "
                      "bill an LLM read with every key blank. Move it aside for the run.")
    python = VENV_PYTHON
    if not python.exists():
        raise Refused(f"{python} not found; the engines run from this checkout")
    d = make_scratch()
    follower = None

    def stop(signum, frame):
        raise KeyboardInterrupt
    previous = {sig: signal.getsignal(sig) for sig in SIGNALS}
    for sig in SIGNALS:                               # HUP too: a closed terminal tab
        signal.signal(sig, stop)
    try:
        live_before = job_info(LIVE_LABEL)
        genv = global_env()
        say(f"scratch {d}; live agent pid {live_before['pid']}, "
            f"spawn type {live_before['spawn_type']}; global env {genv}")
        if genv["SONAR_ALARM"] == "set":
            say("WARNING: SONAR_ALARM is set globally (launchctl setenv). The live plist pins "
                "it on, but unset it anyway.")
        t_start = time.time()
        for variant in VARIANTS:                      # staggered: cold scans never overlap
            bootstrap(write_plist(engine_plist(variant, d, python), d), d)
            port = VARIANTS[variant]["port"]
            wait_alarm_off(port)
            if not wait_first_scan(port, args.stagger):
                raise Refused(f"{variant}'s first scan did not finish within {args.stagger:g} s; "
                              "stopping rather than overlap two cold scans (raise --stagger)")
            say(f"{variant} up on {port}; first scan done")
        pids = {v: job_info(label(v)) for v in VARIANTS}
        for variant in VARIANTS:
            wait_alarm_off(VARIANTS[variant]["port"])
        if args.follower:
            env = {**os.environ, "SONAR_DATA": str(d / "std" / "data"),
                   "SONAR_BACKUP_DIR": str(d / "std" / "backup"), "SONAR_ALARM": "off",
                   **{k: "" for k in BLANK_KEYS}}
            follower = subprocess.Popen([str(python), str(ROOT / "main.py")], cwd=ROOT, env=env)
            ans = input("Does the window show it follows 127.0.0.1:8789? Type y to start: ")
            if ans.strip().lower() != "y":
                raise Refused("the follower was not confirmed on 127.0.0.1:8789")
        # Again, now: the starts and the follower prompt may have taken a while.
        check_market_hours(_dt.datetime.now(_dt.timezone.utc), args.minutes, args.force)
        cpu0 = {v: (cputime(pids[v]["pid"]), time.monotonic()) for v in VARIANTS}
        window_start = time.time()
        write_nofollow(partial, "")
        rows, t0, probed = [], time.monotonic(), False
        total = args.minutes * 60
        while (now := time.monotonic() - t0) < total:
            load = os.getloadavg()[0]
            for v in VARIANTS.values():
                for ep in ("/api/health", "/api/config", "/api/state"):
                    row = sample(v["port"], ep, now, load)
                    rows.append(row)
                    write_nofollow(partial, json.dumps(row) + "\n", append=True)
            if not probed and now >= total / 2:
                for variant in VARIANTS:
                    bootstrap(write_plist(probe_plist(variant, d), d), d)
                probed = True
                say("probes started")
            time.sleep(max(0.0, args.every - ((time.monotonic() - t0) - now)))
        window_end = time.time()
        cpu = {}
        for v in VARIANTS:
            c1, w1 = cputime(pids[v]["pid"]), time.monotonic()
            c0, w0 = cpu0[v]
            cpu[v] = {"pct": None if c0 is None or c1 is None
                      else round(100 * (c1 - c0) / (w1 - w0), 2)}
        time.sleep(PROBE_CAP_S * 2)                   # let the last probe finish
        probes = {v: read_probes(d / f"probe-{v}" / "probe.jsonl") for v in VARIANTS}
        live_after = job_info(LIVE_LABEL)
        s = summarise(rows, probes, cpu, live_before, live_after)
        meta = {"engines": f"this checkout, {python} main.py --headless",
                "spawn": ", ".join(f"{v} {pids[v]['spawn_type']}" for v in VARIANTS),
                "global_env": ", ".join(f"{k} {genv[k]}" for k in ENV_CHECK),
                "follower": "on std (8789), launched from the checkout" if args.follower
                else "none"}
        window = {"start": _utc(window_start), "end": _utc(window_end)}
        write_nofollow(out, render(s, rows, window, meta))
        partial.unlink(missing_ok=True)
        say(f"window (UTC) {window['start']} to {window['end']}; "
            f"engines up from {_utc(t_start)}. Log it in the 30-day run record.")
        say(f"written {out}; load {s['load']['valid']}")
        failed = [k for k, ok in s["bars"].items() if not ok]
        if not s["live"]["unchanged"]:
            say("the live agent's pid changed during the run")
            return 1
        say("all bars pass" if not failed else "FAIL: " + "; ".join(failed))
        return 0
    finally:
        # A second Ctrl-C (or TERM, HUP) must not cut the cleanup short.
        for sig in SIGNALS:
            signal.signal(sig, signal.SIG_IGN)
        try:
            gone = cleanup(d, follower)
            say("bootout: " + (", ".join(f"{k} rc={v}" for k, v in gone.items()) or "nothing")
                + f"; deleted {d}")
            if partial.exists():
                say(f"samples so far are in {partial}")
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


# --------------------------------------------------------------------------- #
# watch (measure 4)
# --------------------------------------------------------------------------- #
def watch_summary(rows) -> dict:
    ms = latencies(rows)
    attempts = [r["banner_attempts"] for r in rows if r.get("banner_attempts") is not None]
    fails = [r["banner_failures"] for r in rows if r.get("banner_failures") is not None]
    return {"n": len(rows), "p50": percentile(ms, 50), "p95": percentile(ms, 95),
            "max": max(ms, default=None),
            "http_503": sum(1 for r in rows if r["code"] == 503),
            "no_answer": sum(1 for r in rows if r["ms"] is None or r["code"] == 0),
            # Samples, not alarms: one outage shows in every sample it spans.
            "samples_with_poll_or_scan_problem": sum(
                1 for r in rows if {"poll", "scan"} & set(r.get("kinds") or [])),
            "alarm_off_seen": any(r.get("alarm_off") for r in rows),
            # Counts reset at an agent restart; these are the last values seen.
            "banner_failures": fails[-1] if fails else None,
            "banner_attempts": attempts[-1] if attempts else None}


def watch(port: int, every: float, days: float, out: Path, clock=None,
          sleep=None, fetcher=None) -> dict:
    """Health only, read-only, every ``every`` s for ``days``; whitelisted
    rows appended to ``out`` as JSON lines."""
    out = check_outside_live(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    clock, sleep = clock or time.time, sleep or time.sleep
    fetcher = fetcher or (lambda: fetch(port, "/api/health", True))
    rows, end = [], clock() + days * 86400
    warned = False
    while True:
        t = clock()
        r = fetcher()
        w = whitelist(r["body"])
        row = {"t": _utc(t), "port": port, "ms": r["ms"], "code": r["code"],
               "ok": w["ok"], "poll_age_s": w["last_poll_age_s"], "kinds": w["kinds"],
               "alarm_off": w["alarm_off"], "banner_failures": w["banner_failures"],
               "banner_attempts": w["banner_attempts"]}
        rows.append(row)
        with open(out, "a") as f:
            f.write(json.dumps(row) + "\n")
        if w["alarm_off"] and not warned:
            say(f"WARNING: port {port} reports ntfy {OFF_REASON!r}: its phone alarm is "
                "off. On the live agent that is a fault (launchctl getenv SONAR_ALARM).")
            warned = True
        if clock() + every > end:
            break
        sleep(every)
    s = watch_summary(rows)
    say(f"watch done: {json.dumps(s)}")
    return s


# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="the side-by-side hour (measures 2, 3, 5)")
    r.add_argument("--minutes", type=float, default=60)
    r.add_argument("--every", type=float, default=30)
    r.add_argument("--stagger", type=float, default=600)
    r.add_argument("--out", default=str(ROOT / "docs" / "audit" / "starved-engine-measurement.md"))
    r.add_argument("--follower", action="store_true")
    r.add_argument("--force", action="store_true", help="run inside US market hours")
    p = sub.add_parser("probe", help="the banner probe (diagnosis §4)")
    p.add_argument("tag")
    p.add_argument("n", type=int)
    p.add_argument("--out", required=True)
    w = sub.add_parser("watch", help="read-only health sampling (measure 4)")
    w.add_argument("--port", type=int, default=LIVE_PORT)
    w.add_argument("--every", type=float, default=300)
    w.add_argument("--days", type=float, default=7)
    w.add_argument("--out", default=str(Path.home() / "Library" / "Logs" / "SONAR"
                                        / "diag-watch.jsonl"))
    c = sub.add_parser("cleanup", help="boot out every sonar-diag.* job")
    c.add_argument("--dir")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "run":
            return run(a)
        if a.cmd == "probe":
            return probe(a.tag, a.n, Path(a.out))
        if a.cmd == "watch":
            say(f"global env {global_env()}")
            watch(a.port, a.every, a.days, Path(a.out))
            return 0
        gone = cleanup(Path(a.dir) if a.dir else None)
        say(f"booted out {gone or 'nothing'}")
        return 0
    except Refused as exc:
        print(f"diag: refused: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
