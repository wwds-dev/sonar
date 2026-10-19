"""SONAR HTTP daemon — the headless way to run the terminal.

A tiny stdlib HTTP server over :class:`sonar.core.Live`. The native app in
``ui/`` drives that same object directly; this module exists for running SONAR
headless (a spare machine, a launchd job) and for anything that wants the JSON.

    python3 -m sonar.server            # then open http://127.0.0.1:8787

No pip install, no API keys, paper money only — unless you enable the optional
LLM read, which is the one path that needs a key.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess  # noqa: F401  (tests patch server.subprocess.run for the banner)
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import alarm, horizon, llm, paths, risk
from .core import Live

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


MAX_BODY = 64 * 1024                 # every request body here is a few dozen bytes
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class Handler(BaseHTTPRequestHandler):
    """The daemon's routes. Paper money, but the book is the experiment.

    Any web page the owner visits could reach this port: a cross-site POST with
    a text/plain body needs no preflight, so a page could open and close paper
    positions or flip the protocol, and a DNS-rebinding page could read every
    route. So every request must name this server in its Host header (a
    rebinding page names its own domain), and a write must come as JSON
    (forcing the preflight this server never grants) from no foreign Origin.
    """

    live: Live = None  # set on the class before serving
    notifier = None     # the agent's alarm channels, for /api/health; None in tests
    timeout = 10        # a client that opens a socket and stalls does not hold a thread

    def log_message(self, *a):        # quiet
        pass

    def _send(self, code, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _own_hosts(self) -> set[str]:
        host, port = self.server.server_address[:2]
        names = LOOPBACK | {host}
        own = {f"[{n}]:{port}" if ":" in n else f"{n}:{port}" for n in names}
        if port in (80, 443):        # clients leave a default port out of Host
            own |= {f"[{n}]" if ":" in n else n for n in names}
        return own

    def _refused(self, write: bool) -> bool:
        """Answer and return True if this request may not be served."""
        own = self._own_hosts()
        if self.headers.get("Host", "") not in own:
            self._json({"error": "unknown host"}, 403)
            return True
        if not write:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{h}" for h in own}:
            self._json({"error": "cross-origin write refused"}, 403)
            return True
        ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._json({"error": "send JSON (Content-Type: application/json)"}, 415)
            return True
        return False

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json")

    def _read_json_body(self) -> dict | None:
        """The request's JSON object, ``{}`` for no body, ``None`` (already
        answered) for one that is too big, malformed or not an object."""
        if self.headers.get("Transfer-Encoding"):
            # Not read here; answering 200 as if it were empty lost the payload.
            self._json({"error": "send a Content-Length, not a chunked body"}, 411)
            return None
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > MAX_BODY:
            self._json({"error": f"body must be 0-{MAX_BODY} bytes"}, 413 if n > 0 else 400)
            return None
        try:
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except (ValueError, OSError):
            body = None
        if not isinstance(body, dict):
            self._json({"error": "body must be a JSON object"}, 400)
            return None
        return body

    def do_POST(self):
        if self._refused(write=True):
            return
        body = self._read_json_body()
        if body is None:
            return
        if self.path.startswith("/api/config"):
            self._json(self.live.configure(body.get("risk"), body.get("horizon"),
                                           protocol=body.get("protocol")))
            return
        if self.path.startswith("/api/read"):
            kind = str(body.get("kind", "btc"))
            if kind not in ("btc", "asset"):
                self._json({"error": "bad kind"}, 400)
                return
            self._json(self.live.read(kind, str(body.get("id", ""))))
            return
        # The book's two actions, for a window that follows this engine
        # (core.Live._wait_for_lock): it holds the lock, so it holds the pen.
        # Paper money, and the server binds to localhost by default.
        if self.path.startswith("/api/trade"):
            direction = str(body.get("direction", "")).upper()
            if direction not in ("LONG", "SHORT"):
                self._json({"ok": False, "position": None,
                            "message": "direction must be LONG or SHORT"}, 400)
                return
            self._json(self.live.trade(str(body.get("symbol", "")), direction))
            return
        if self.path.startswith("/api/undo"):
            self._json(self.live.undo(str(body.get("id", "")), str(body.get("kind", ""))))
            return
        if self.path.startswith("/api/close"):
            self._json(self.live.close_position(str(body.get("id", ""))))
            return
        self._send(404, b"not found", "text/plain")

    def do_GET(self):
        if self._refused(write=False):
            return
        if self.path.startswith("/api/health"):
            # Judged now, not when the last snapshot was built: 503 when the
            # engine is not doing its job, so a check needs no JSON to tell.
            h = agent_health(self.live, self.notifier)
            self._json(h, 200 if h["ok"] else 503)
            return
        if self.path.startswith("/api/config"):
            self._json(self.live.config())
            return
        if self.path.startswith("/api/state"):
            with self.live.lock:
                self._json(self.live.snapshot)
            return
        if self.path.startswith("/api/assets"):
            with self.live.lock:
                self._json(self.live.assets)
            return
        if self.path.startswith("/api/macro"):
            self._json(self.live.macro.get().as_dict())
            return
        # What a following window needs beyond the snapshot and the board:
        # the paper book as the engine marks it, and what the scans raised.
        if self.path.startswith("/api/book"):
            with self.live.lock:
                self._json({"positions": self.live.positions,
                            "calibration": self.live.calibration,
                            "shadow": self.live.shadow,
                            "protocol_on": self.live.protocol_on})
            return
        if self.path.startswith("/api/wire"):
            with self.live.lock:
                self._json({"alerts": self.live.alerts, "inst": self.live.inst})
            return

        page = {"/": "index.html", "/index.html": "index.html",
                "/docs": "docs.html", "/docs/": "docs.html",
                "/docs.html": "docs.html",
                "/testplan": "testplan.html", "/testplan/": "testplan.html",
                "/testplan.html": "testplan.html"}.get(self.path)
        if page:
            self._send(200, (STATIC / page).read_bytes(), "text/html; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain")


class PaperServer(ThreadingHTTPServer):
    """The daemon's HTTP server, with a backlog worth having.

    ``socketserver`` listens with a backlog of 5. That is the number of
    connections the *kernel* will hold before the accept loop reaches them, so
    past it a connection is refused with an RST before any of this code runs —
    threading the handlers does not help, because the request never arrives.

    It is reachable in normal use: the daemon serves a browser and the poll
    thread at the same time, and a page that fetches several endpoints at once
    opens several connections at once. Measured at twelve simultaneous
    requests, one was reset every run.
    """

    request_queue_size = 64


# How long a problem must last before it becomes a notification. A stalled
# poll is worth knowing about in minutes; "no hour settled" needs over an hour,
# because after the Mac wakes from a night's sleep it stays true until the next
# hour settles, and that is not a fault.
ALARM_AFTER_S = {"loop": 0.0, "poll": 600.0, "scan": 600.0, "settle": 75 * 60.0}
WATCH_EVERY = 15.0


NOTIFY_SCRIPT = alarm.NOTIFY_SCRIPT
_plain = alarm.plain


def notify_macos(title: str, body: str) -> None:
    """A macOS notification from the agent itself, which has no window to show
    anything in. Now :class:`alarm.BannerChannel`, kept for its callers. Best
    effort: a failure is logged, never raised."""
    banner = alarm.BannerChannel()
    if not banner.configured or banner.send(title, body):
        return
    if banner.why.startswith("refused"):
        print(f"SONAR {alarm.ts()}: notification {banner.why}", file=sys.stderr, flush=True)
    else:
        print(f"SONAR {alarm.ts()}: could not post a notification ({banner.why})",
              file=sys.stderr, flush=True)


STOPPED_NOTICE_EVERY = 3600.0      # a crash loop restarts every minute; say it once an hour
#: How long the exit-3 path waits for the "stopped" notice: one 10 s attempt
#: plus slack, and only when the notice is due (at most once an hour).
STOP_FLUSH_S = 12.0


def _alarm_file() -> Path:
    return paths.user_data_base() / "alarm.json"


def _stopped_notice_due(now: float) -> bool:
    """Has an hour passed since the last *delivered* "SONAR stopped" notice,
    across restarts? Kept beside the book, since each restart is a new process."""
    last = paths.read_preferences(_alarm_file()).get("stopped_at")
    return not (isinstance(last, (int, float)) and 0 <= now - last < STOPPED_NOTICE_EVERY)


def _stopped_notice_sent(now: float) -> None:
    """Record a "stopped" notice that got through. With ntfy configured that
    means it reached the phone (a banner alone does not count); with no topic,
    that the banner posted it. If it did not get through, the next restart
    tries again, and a crash loop still gets at most one notice through an hour.
    Merged into the file, not written over it: the heartbeat's day is there too."""
    alarm.merge_json(_alarm_file(), {"stopped_at": now})


class _Callback:
    """The old ``notify=(title, body)`` hook, for callers written before the
    notifier: called inline with the local text, no counts, no heartbeat."""

    undelivered = False

    def __init__(self, notify):
        self.notify = notify

    def send(self, event, local_text=None) -> alarm.Delivery:
        if local_text:
            self.notify(*local_text)
        return alarm.Delivery(delivered=True)

    def states(self) -> dict:
        return {}

    def drain(self, deadline_s: float) -> bool:
        return True

    def redact(self, s: str) -> str:
        return s


def agent_health(live, notifier=None, now: float | None = None) -> dict:
    """``live.health()`` plus the alarm channels, for ``/api/health`` and the
    watchdog. ``core.Live.health`` stays unaware of alarms; the GUI never sends any.

    A failing ntfy channel, or an alarm that failed to reach the phone over a
    configured ntfy channel (whatever the banner did), is a ``notify`` problem
    (503). A failing banner is counted but is not a problem: it is the
    local channel and known to be flaky, and it would turn health red on
    nearly every alarm."""
    h = dict(live.health() if now is None else live.health(now))
    states = notifier.states() if notifier is not None else {}
    if not states:
        return h
    h["notify"] = states
    problems = list(h.get("problems") or [])
    ntfy = states.get("ntfy") or {}
    if ntfy.get("state") == "failing":
        problems.append({"kind": "notify", "text": "the ntfy alarm channel is failing "
                         f"({ntfy.get('failures', 0)} failures)"})
    if getattr(notifier, "undelivered", False):
        problems.append({"kind": "notify", "text": "an alarm did not reach the phone"})
    h["problems"], h["ok"] = problems, not problems
    return h


class Watchdog:
    """Keeps the agent honest about whether it is working.

    * The engine runs on a daemon thread; if that thread ends, the HTTP server
      kept the process alive, launchd saw nothing wrong, and nothing traded or
      scored again. Now the process exits non-zero, which launchd's KeepAlive
      restarts (packaging/com.netrunner3000.sonar.plist).
    * A problem from ``Live.health()`` that lasts past its ALARM_AFTER_S sends
      one alarm; recovery sends one more. Nothing repeats in between.
    * Alarms go through the notifier (``sonar/alarm.py``): queued on each
      channel's own thread, so no network or subprocess call happens here
      except the bounded wait before exit. The push carries only fixed
      phrases; the full problem text stays in this log.
    * The banner's title carries "(paper)" like the push (domain P3-E).
    * ``notify`` problems (a failing alarm channel) are health-only: alarming
      about the alarm channel through the alarm channels would loop.
    * Once a day the heartbeat, if one is given, says "alive".
    """

    def __init__(self, live, engine_thread, *, notifier=None, exit_fn=os._exit,
                 log=None, notify=None, heartbeat=None):
        self.live, self.engine_thread = live, engine_thread
        self.notifier = notifier or _Callback(notify or notify_macos)
        self.exit_fn, self.heartbeat = exit_fn, heartbeat
        self.log = log or (lambda msg: print(msg, file=sys.stderr, flush=True))
        self.bad_since: dict[str, float] = {}
        self.alarmed: set[str] = set()     # kinds already told, until they clear
        self._was_alarmed = False

    def say(self, msg: str) -> None:
        """One timestamped, redacted line: exception text can hold a newline."""
        self.log(self.notifier.redact(f"SONAR {alarm.ts()}: {alarm.plain(msg, 2000)}"))

    def step(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        if not self.engine_thread.is_alive() and not self.live._stop.is_set():
            try:
                self.say("the engine thread ended; exiting so launchd restarts the agent")
                if _stopped_notice_due(now):
                    delivery = self.notifier.send(
                        alarm.Event("stopped", urgent=True),
                        (f"{alarm.TITLE} stopped",
                         "The engine loop ended. The agent is restarting."))
                    self.notifier.drain(STOP_FLUSH_S)
                    if getattr(delivery, "delivered", False):
                        _stopped_notice_sent(now)
            finally:
                self.exit_fn(3)               # whatever failed above, launchd restarts us
            return
        h = agent_health(self.live, self.notifier, now)
        texts: dict[str, str] = {}
        for p in h["problems"]:
            texts.setdefault(p["kind"], p["text"])
        kinds = {k: t for k, t in texts.items() if k != "notify"}
        self.bad_since = {k: self.bad_since.get(k, now) for k in kinds}
        self.alarmed &= set(kinds)            # a cleared kind may alarm again later
        # An undelivered alarm stops being a problem once its own kinds have
        # cleared (owner decision (a), Review).
        getattr(self.notifier, "set_open_kinds", lambda kinds: None)(kinds)
        due = {k: text for k, text in kinds.items()
               if k not in self.alarmed
               and now - self.bad_since[k] >= ALARM_AFTER_S.get(k, 600.0)}
        if due:
            self._was_alarmed = True
            self.alarmed |= set(due)
            self.say("needs attention: " + "; ".join(due.values()))
            event = alarm.Event(next(iter(due)), open_kinds=tuple(
                (k, now - self.bad_since[k]) for k in due))
            self.notifier.send(event, (f"{alarm.TITLE} needs attention",
                                       "; ".join(due.values())))
        elif not kinds and self._was_alarmed:
            self._was_alarmed = False
            self.say("working again")
            self.notifier.send(alarm.Event("recovery"),
                               (f"{alarm.TITLE} is working again",
                                "Prices are polling and hours are settling."))
        if self.heartbeat is not None and self.heartbeat.due(now):
            self.heartbeat.mark(now)          # on queueing: one per day, even in a crash loop
            self.notifier.send(alarm.Event("heartbeat", open_kinds=tuple(
                (k, None) for k in texts)))
            self.say("heartbeat queued; open problems: " + (", ".join(texts) or "none"))

    def run(self, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.wait(WATCH_EVERY):
            try:
                self.step()
            except Exception as exc:          # the watchdog must outlive its own bugs
                self.say(f"watchdog step failed ({type(exc).__name__}: {exc})")


class PaperServer6(PaperServer):
    """The same server on ``::1``: the base class binds IPv4 only."""

    address_family = socket.AF_INET6


def lock_url(host: str, port: int) -> str:
    """The address written into the engine lock for a follower: an IPv6 host
    is bracketed, or the URL does not parse."""
    return f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"


def main(host: str = "127.0.0.1", port: int = 8787,
         risk_name: str | None = None, horizon_name: str | None = None,
         role: str = "daemon") -> None:
    if host not in LOOPBACK:
        # Every route answers only to a loopback Host, and nothing here has
        # authentication: off the machine it would be an open door anyway.
        raise SystemExit(f"SONAR serves loopback only; refusing --host {host}")
    live = Live(risk_name=risk_name, horizon_name=horizon_name)
    # Before any thread starts: the Keychain read blocks for at most 5 s, once.
    notifier = alarm.from_keychain(build=(getattr(live, "build", None) or {}).get("version"))
    # The address goes into the engine lock, so a window that loses the race
    # for it can follow this engine here rather than open with nothing.
    engine = threading.Thread(target=live.run, args=(role,),
                              kwargs={"url": lock_url(host, port)}, daemon=True)
    engine.start()
    dog = Watchdog(live, engine, notifier=notifier,
                   heartbeat=alarm.Heartbeat(_alarm_file()))
    threading.Thread(target=dog.run, daemon=True).start()
    Handler.live, Handler.notifier = live, notifier
    srv = (PaperServer6 if ":" in host else PaperServer)((host, port), Handler)
    ok, why = llm.available()
    print(f"SONAR paper terminal  ->  http://{host}:{port}", flush=True)
    print(f"risk={live.risk.name}  horizon={live.horizon.name}", flush=True)
    print(f"LLM read: {'ready (' + llm.MODEL + ')' if ok else 'off — ' + why}",
          flush=True)
    print("Live BTC data + real Polymarket odds. Paper money only. Ctrl-C to stop.",
          flush=True)
    # If another SONAR already holds the engine lock this process waits for
    # it rather than settling the same hour twice, and takes over when it
    # stops — a window closed for the night hands the run back to the agent.
    time.sleep(1.5)
    if getattr(live, "read_only", False):
        print(f"WAITING: {live.conflict}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="SONAR paper-trading terminal")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--risk", default=None, choices=sorted(risk.PROFILES),
                    help="staking appetite (default: whatever the saved "
                         "bankroll was built under, else moderate)")
    ap.add_argument("--horizon", default=None, choices=sorted(horizon.HORIZONS),
                    help="return horizon (default: week)")
    args = ap.parse_args()
    main(args.host, args.port, args.risk, args.horizon)
