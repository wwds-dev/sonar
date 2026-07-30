"""SONAR server — a zero-dependency live paper-trading terminal.

Runs a background thread that polls real market data, drives the paper engine,
and publishes a JSON snapshot; a tiny stdlib HTTP server serves that snapshot to
the dashboard at ``/``.

    python3 -m sonar.server            # then open http://127.0.0.1:8787

No pip install, no API keys. Paper money only.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import assets, feeds, model, news, scanner
from .engine import Engine

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
DATA = ROOT / "data"

PRICE_EVERY = 4.0            # seconds between price polls
MARKET_EVERY = 15.0         # seconds between Polymarket polls
VOL_EVERY = 600.0           # seconds between volatility refreshes
SCAN_EVERY = 90.0           # seconds between multi-market scans
SPARK_MAX = 220             # price points kept for the sparkline


class Live:
    """Shared state between the polling thread and the HTTP handlers."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.engine = Engine(DATA / "state.json")
        self.snapshot: dict = {"status": "starting"}
        self.spark: list[dict] = []
        self.sigma = 0.0045
        self._last_market = None
        self._market_at = 0.0
        self._vol_at = 0.0
        self.news = news.NewsCache()
        self.asset_scanner = assets.AssetScanner()
        self.scan: dict = {"status": "starting", "suggestions": []}
        self.assets: dict = {"status": "starting", "assets": []}
        self._scan_at = 0.0

    # -- background loop --------------------------------------------------- #
    def warmup(self) -> None:
        try:
            rows = feeds.historical_decision_points(hours=36)
            if rows:
                self.engine.seed_backtest(rows)
        except Exception:
            pass
        self.sigma = model.hourly_sigma(feeds.recent_hourly_returns())
        self._vol_at = time.time()
        self._rescan()

    def _rescan(self) -> None:
        """Refresh the multi-market scan and the real-asset screen (heavier,
        runs rarely). Fetches headlines once and shares them across both."""
        try:
            heads = self.news.headlines()
        except Exception:
            heads = []
        try:
            markets = feeds.scan_markets(top=150, closing=80)
            payload = scanner.suggestions_payload(markets, heads, limit=40)
            payload["status"] = "live"
            with self.lock:
                self.scan = payload
        except Exception as exc:
            with self.lock:
                self.scan.setdefault("suggestions", [])
                self.scan["error"] = str(exc)
        try:
            ap = self.asset_scanner.payload(heads)
            with self.lock:
                self.assets = ap
        except Exception:
            pass
        self._scan_at = time.time()

    def run(self) -> None:
        self.warmup()
        while True:
            try:
                self._poll()
            except Exception as exc:               # keep the loop alive
                with self.lock:
                    self.snapshot = {"status": "error", "detail": str(exc)}
            time.sleep(PRICE_EVERY)

    def _poll(self) -> None:
        now = time.time()
        candle = feeds.hourly_candle()

        if now - self._vol_at > VOL_EVERY:
            self.sigma = model.hourly_sigma(feeds.recent_hourly_returns())
            self._vol_at = now

        if now - self._scan_at > SCAN_EVERY:
            self._rescan()

        if now - self._market_at > MARKET_EVERY or self._last_market is None:
            m = feeds.current_market()
            if m is not None:
                self._last_market = m
                self._market_at = now
        market = self._last_market

        if candle is not None:
            self.spark.append({"t": int(now), "p": candle.price})
            self.spark = self.spark[-SPARK_MAX:]

        with self.lock:
            sig = self.engine.tick(candle, market, self.sigma)
            self.snapshot = self._build(candle, market, sig, now)

    # -- snapshot builder -------------------------------------------------- #
    def _build(self, candle, market, sig, now) -> dict:
        eng = self.engine
        snap: dict = {
            "status": "live",
            "now": int(now),
            "sigma": round(self.sigma, 6),
        }
        if candle is not None:
            snap["candle"] = {
                "open": candle.open, "price": candle.price,
                "high": candle.high, "low": candle.low,
                "change": round(candle.change, 2),
                "change_pct": round(candle.change_pct, 4),
                "is_up": candle.is_up, "source": candle.source,
                "open_time": candle.open_time,
            }
        if market is not None:
            secs_left = max(0, int(market.end_time - now))
            snap["market"] = {
                "title": market.title, "slug": market.slug,
                "implied_up": round(market.implied_up, 4),
                "best_bid": market.best_bid, "best_ask": market.best_ask,
                "volume": round(market.volume, 2),
                "end_time": market.end_time, "seconds_left": secs_left,
                "bids": [[p, s] for p, s in market.bids],
                "asks": [[p, s] for p, s in market.asks],
            }
        if sig is not None:
            snap["signal"] = {
                "model_up": round(sig.model_up, 4),
                "market_up": round(sig.market_up, 4),
                "edge": round(sig.edge, 4), "side": sig.side,
                "abs_edge": round(sig.abs_edge, 4), "tau": round(sig.tau, 4),
            }
            if candle is not None:
                snap["lattice"] = model.lattice_distribution(
                    candle.price, candle.open, self.sigma, sig.tau)

        snap["spark"] = self.spark[-SPARK_MAX:]
        snap["portfolio"] = {
            "stats": eng.stats(),
            "open_position": _trade_dict(eng.open_position),
            "equity": eng.equity[-400:],
            "trades": [_trade_dict(t) for t in eng.trades[-40:]][::-1],
        }
        return snap


def _trade_dict(t) -> dict | None:
    if t is None:
        return None
    from dataclasses import asdict
    return asdict(t)


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

    def do_GET(self):
        if self.path.startswith("/api/state"):
            with self.live.lock:
                body = json.dumps(self.live.snapshot).encode()
            self._send(200, body, "application/json")
            return
        if self.path.startswith("/api/scan"):
            with self.live.lock:
                body = json.dumps(self.live.scan).encode()
            self._send(200, body, "application/json")
            return
        if self.path.startswith("/api/assets"):
            with self.live.lock:
                body = json.dumps(self.live.assets).encode()
            self._send(200, body, "application/json")
            return
        if self.path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if self.path in ("/docs", "/docs/", "/docs.html"):
            html = (STATIC / "docs.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if self.path in ("/scan", "/scan/", "/scanner", "/scan.html"):
            html = (STATIC / "scan.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain")


def main(host: str = "127.0.0.1", port: int = 8787) -> None:
    live = Live()
    threading.Thread(target=live.run, daemon=True).start()
    Handler.live = live
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"SONAR paper terminal  ->  http://{host}:{port}")
    print("Live BTC data + real Polymarket odds. Paper money only. Ctrl-C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="SONAR paper-trading terminal")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    main(args.host, args.port)
