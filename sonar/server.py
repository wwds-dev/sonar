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
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import horizon, llm, risk
from .core import Live

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


class Handler(BaseHTTPRequestHandler):
    live: Live = None  # set on the class before serving

    def log_message(self, *a):        # quiet
        pass

    def _send(self, code, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json")

    def _read_json_body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}
        except (ValueError, OSError):
            return {}

    def do_POST(self):
        if self.path.startswith("/api/config"):
            body = self._read_json_body()
            self._json(self.live.configure(body.get("risk"), body.get("horizon"),
                                           protocol=body.get("protocol")))
            return
        if self.path.startswith("/api/read"):
            body = self._read_json_body()
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
            body = self._read_json_body()
            direction = str(body.get("direction", "")).upper()
            if direction not in ("LONG", "SHORT"):
                self._json({"ok": False, "position": None,
                            "message": "direction must be LONG or SHORT"}, 400)
                return
            self._json(self.live.trade(str(body.get("symbol", "")), direction))
            return
        if self.path.startswith("/api/close"):
            body = self._read_json_body()
            self._json(self.live.close_position(str(body.get("id", ""))))
            return
        self._send(404, b"not found", "text/plain")

    def do_GET(self):
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


def main(host: str = "127.0.0.1", port: int = 8787,
         risk_name: str | None = None, horizon_name: str | None = None,
         role: str = "daemon") -> None:
    live = Live(risk_name=risk_name, horizon_name=horizon_name)
    # The address goes into the engine lock, so a window that loses the race
    # for it can follow this engine here rather than open with nothing.
    threading.Thread(target=live.run, args=(role,),
                     kwargs={"url": f"http://{host}:{port}"}, daemon=True).start()
    Handler.live = live
    srv = PaperServer((host, port), Handler)
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
