"""SONAR core — the headless engine driver.

This is the part that knows how to poll real markets, drive the paper engine and
keep a consistent snapshot. It has **no** opinion about how that state reaches a
human: the stdlib HTTP daemon (``sonar.server``) and the native app (``ui/``)
both drive this same object.

That split exists because SONAR is fundamentally a daemon whose value needs
uptime — the equity curve only means something if positions settle on the hours
they were priced for. Keeping the driver separate from any UI means closing a
window never has to mean losing an hour.
"""

from __future__ import annotations

import json
import threading
import time

from dataclasses import asdict

from . import (assets, enginelock, feeds, horizon, llm, macro, model, news,
               paths, risk, scanner)
from .engine import Engine
from . import calibration, events, portfolio, scoring


def trade_dict(t) -> dict | None:
    return asdict(t) if t is not None else None

PRICE_EVERY = 4.0            # seconds between price polls
MARKET_EVERY = 15.0         # seconds between Polymarket polls
VOL_EVERY = 600.0           # seconds between volatility refreshes
SCAN_EVERY = 90.0           # seconds between multi-market scans
SPARK_MAX = 220             # price points kept for the sparkline


class Live:
    """Shared state between the polling thread and the HTTP handlers."""

    def __init__(self, risk_name: str | None = None,
                 horizon_name: str | None = None) -> None:
        self.lock = threading.Lock()
        # Set by stop() to end run()'s loop. Qt aborts the whole process if a
        # QThread is still running when it is destroyed, so the loop this drives
        # must be able to finish on request — see ui/app.py's shutdown().
        self._stop = threading.Event()
        # Single-writer guard around the paper engine (see enginelock.py).
        self.engine_lock = None
        self.read_only = False
        self.conflict = ""
        self.horizon = horizon.get(horizon_name)
        paths.ensure_dirs()
        self.engine = Engine(paths.state_file(), risk=risk.get(risk_name))
        if risk_name:
            # Explicitly asked for on the command line — that wins, and is
            # persisted so the bankroll records what it is now being sized under.
            self.risk = risk.get(risk_name)
            self.engine.set_risk(self.risk)
        else:
            # Nothing asked for: keep whatever the bankroll was built under.
            self.risk = self.engine.risk
        self.snapshot: dict = {"status": "starting"}
        self.spark: list[dict] = []
        self.sigma = 0.0045
        self._last_market = None
        self._market_at = 0.0
        self._vol_at = 0.0
        self.news = news.NewsCache()
        self.events = events.EventsCache()
        self.asset_scanner = assets.AssetScanner(events=self.events)
        # The general paper book: any instrument, long or short. Kept in its own
        # file so the hourly BTC engine's bankroll stays a separate experiment.
        self.book = portfolio.Portfolio(paths.user_data_base() / "portfolio.json")
        self.scan: dict = {"status": "starting", "suggestions": []}
        self.assets: dict = {"status": "starting", "assets": []}
        self.positions: dict = {"stats": self.book.stats(), "open": [], "closed": []}
        self.calibration: dict = calibration.report(self.book.closed)
        self._scan_at = 0.0
        self.macro = macro.MacroCache()
        self.reader = llm.LLMReader()
        self.last_read: dict | None = None

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
        hz, profile = self.horizon, self.risk
        try:
            markets = feeds.scan_markets(top=150, closing=80)
            payload = scanner.suggestions_payload(markets, heads, limit=40,
                                                  hz=hz, profile=profile)
            payload["status"] = "live"
            with self.lock:
                self.scan = payload
        except Exception as exc:
            with self.lock:
                self.scan.setdefault("suggestions", [])
                self.scan["error"] = str(exc)
        try:
            ap = self.asset_scanner.payload(heads, hz=hz, profile=profile)
            self._mark_book(ap)
            with self.lock:
                self.assets = ap
        except Exception:
            pass
        self._scan_at = time.time()

    # -- the paper book ---------------------------------------------------- #
    def _mark_book(self, asset_payload: dict) -> None:
        """Mark open positions against the new prices and close any that hit a
        barrier, then feed the resulting outcomes back into the score.

        This is the loop that makes the screener falsifiable: positions resolve,
        calibration measures whether high scores actually won, and the measured
        drift — and only that — is allowed to move P(profit) off its baseline.
        """
        prices = {a["symbol"]: a["price"] for a in asset_payload.get("assets", [])}
        if not prices:
            return
        self.book.mark(prices)
        report = calibration.report(self.book.closed)
        # Nothing is claimed below the sample threshold; report() enforces that.
        self.asset_scanner.edge_sigma = report["implied_edge_sigma"]
        self.asset_scanner.calibrated = report["calibrated"]
        with self.lock:
            self.calibration = report
            self.positions = {"stats": self.book.stats(prices),
                              "open": self.book.open_rows(prices),
                              "closed": [asdict(p) for p in self.book.closed[-40:]][::-1]}

    def trade(self, symbol: str, direction: str) -> dict:
        """Open a paper position on a screener row. Paper money only."""
        with self.lock:
            rows = list(self.assets.get("assets", []))
        asset = next((a for a in rows if a["symbol"] == symbol), None)
        if asset is None:
            return {"ok": False, "message": f"unknown symbol {symbol}"}
        pos, msg = self.book.enter(
            asset, direction, self.horizon.momentum_days, self.horizon.name,
            risk_fraction=self.risk.max_stake_fraction / 8.0)
        self._mark_book({"assets": rows})
        return {"ok": pos is not None, "message": msg,
                "position": asdict(pos) if pos else None}

    def close_position(self, pos_id: str) -> dict:
        with self.lock:
            rows = list(self.assets.get("assets", []))
        prices = {a["symbol"]: a["price"] for a in rows}
        pos = next((p for p in self.book.open if p.id == pos_id), None)
        if pos is None:
            return {"ok": False, "message": "no such open position"}
        closed = self.book.close(pos.id, prices.get(pos.symbol, pos.entry), "MANUAL")
        self._mark_book({"assets": rows})
        return {"ok": True, "message": f"closed {closed.symbol}",
                "position": asdict(closed)}

    # -- configuration ----------------------------------------------------- #
    def configure(self, risk_name: str | None, horizon_name: str | None) -> dict:
        """Apply a risk profile and/or horizon, then rescan so the boards
        reflect the change immediately rather than after the next 90s tick."""
        changed = False
        if risk_name and risk.get(risk_name).name != self.risk.name:
            self.risk = risk.get(risk_name)
            self.engine.set_risk(self.risk)
            changed = True
        if horizon_name and horizon.get(horizon_name).name != self.horizon.name:
            self.horizon = horizon.get(horizon_name)
            changed = True
        if changed:
            self._rescan()
        return self.config()

    def config(self) -> dict:
        ok, why = llm.available()
        return {
            "risk": self.risk.as_dict(),
            "horizon": self.horizon.as_dict(),
            "risk_options": [p.as_dict() for p in risk.PROFILES.values()],
            "horizon_options": [h.as_dict() for h in horizon.HORIZONS.values()],
            "llm": {"available": ok, "detail": why, "model": llm.MODEL},
        }

    # -- the narrative track ----------------------------------------------- #
    def read(self, kind: str, ident: str) -> dict:
        """Run one LLM read for a selected opportunity.

        Deliberately on demand and one at a time: running this across the whole
        board on every scan would cost real money for no benefit. The API call
        happens outside the lock so the polling thread is never blocked on it.
        """
        subject, numbers, heads, hour_key = self._read_subject(kind, ident)
        if subject is None:
            return {"error": f"unknown {kind}: {ident}"}

        read = self.reader.read(
            subject=subject, kind=kind, numbers=numbers, headlines=heads,
            risk_name=self.risk.name, horizon_label=self.horizon.label,
        ).as_dict()

        with self.lock:
            self.last_read = read
            # Only the hourly BTC market settles against a candle, so it is the
            # only place a conviction can later be scored.
            if kind == "btc" and hour_key is not None:
                self.engine.attach_llm_read(hour_key, read)
        return read

    def _read_subject(self, kind: str, ident: str):
        """Assemble the measurements for a subject. Numbers only — the model is
        given the arithmetic layer's output, never asked to invent it."""
        with self.lock:
            snap, scan, asset_payload = self.snapshot, self.scan, self.assets

        if kind == "btc":
            candle, sig = snap.get("candle"), snap.get("signal")
            market = snap.get("market")
            if not candle or not sig:
                return None, {}, [], None
            return ("BTC/USD hourly up-or-down", {
                "open": candle["open"], "price": candle["price"],
                "change_pct": candle["change_pct"],
                "hourly_volatility_sigma": snap.get("sigma"),
                "model_p_up": sig["model_up"],
                "market_p_up": sig["market_up"],
                "model_edge_vs_market": sig["edge"],
                "model_favours": sig["side"],
                "fraction_of_hour_remaining": sig["tau"],
                "market_volume_usd": (market or {}).get("volume"),
            }, self._recent_headlines("crypto"), candle.get("open_time"))

        if kind == "market":
            for s in scan.get("suggestions", []):
                if s["id"] == ident:
                    return (s["question"], {
                        "category": s["category"],
                        "market_yes_price": s["yes_price"],
                        "hours_until_resolution": s["hours_left"],
                        "volume_24h_usd": s["volume24h"],
                        "confidence_score_0_100": s["confidence"],
                        "model_p_up": s.get("model_up"),
                        "model_edge_vs_market": s.get("edge"),
                        "news_sentiment": s.get("news_sentiment"),
                    }, s.get("headlines", []), None)
            return None, {}, [], None

        if kind == "asset":
            for a in asset_payload.get("assets", []):
                if a["symbol"] == ident:
                    nums = {
                        "class": a["cls"],
                        "price": a["price"],
                        "currency": a["currency"],
                        "change_1d": a["day_change"],
                        f'change_{a["momentum_days"]}d': a["momentum"],
                        "daily_volatility": a["volatility"],
                        "confidence_score_0_100": a["confidence"],
                        "heuristic_lean": a["lean"],
                        "news_sentiment": a.get("news_sentiment"),
                    }
                    nums.update(self._macro_numbers())
                    return (f'{a["name"]} ({a["symbol"]})', nums,
                            a.get("headlines", []), None)
            return None, {}, [], None

        return None, {}, [], None

    def _macro_numbers(self) -> dict:
        """Macro context for the read — long horizons only.

        Rates, the curve and volatility are noise on an hourly view and the
        dominant term on a yearly one. Including them at short horizons would
        just pad the prompt with irrelevance; omitting them at long horizons
        would leave the model to invent the regime, which is exactly what the
        old Oracle agent had to do.
        """
        if not self.horizon.macro:
            return {}
        m = self.macro.get()
        return {
            "macro_regime": m.regime,
            "macro_10y_yield_pct": m.ten_year,
            "macro_curve_10y_2y_pp": m.curve_spread,
            "macro_fed_funds_pct": m.fed_funds,
            "macro_vix": m.vix,
            "macro_real_10y_pct": m.real_10y,
            "macro_cpi_yoy_pct": None if m.cpi_yoy is None else round(m.cpi_yoy * 100, 2),
            "macro_unemployment_pct": m.unemployment,
        }

    def _recent_headlines(self, category: str) -> list[dict]:
        try:
            heads = self.news.headlines()
        except Exception:
            return []
        return [{"title": h.title, "source": h.source,
                 "age_h": round(h.age_hours, 1) if h.dated else None}
                for h in heads if h.category == category][:6]

    def run(self, role: str = "app") -> None:
        """Drive the engine until :meth:`stop` is called.

        Refuses to poll if another SONAR already holds the engine lock. Two
        engines settling the same hour into one state file would double-count
        the portfolio, and it would do so silently — so this returns instead,
        leaving the caller displaying whatever the real engine writes.
        """
        self.engine_lock = enginelock.EngineLock(role=role)
        if not self.engine_lock.acquire():
            self.read_only = True
            self.conflict = enginelock.describe_conflict(self.engine_lock)
            with self.lock:
                self.snapshot = {"status": "read-only", "detail": self.conflict}
            return
        try:
            self.warmup()
            while not self._stop.is_set():
                try:
                    self._poll()
                except Exception as exc:           # keep the loop alive
                    with self.lock:
                        self.snapshot = {"status": "error", "detail": str(exc)}
                # wait(), not sleep(): a quit lands immediately instead of
                # blocking shutdown for the rest of the poll interval.
                self._stop.wait(PRICE_EVERY)
        finally:
            # Hand the lock back on the way out. A crash could never do this,
            # which left a stale holder and sent the next launch to read-only.
            self.engine_lock.release()

    def stop(self) -> None:
        """Ask :meth:`run` to finish. Safe to call from another thread, and
        safe to call when the loop was never started."""
        self._stop.set()

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
            "open_position": trade_dict(eng.open_position),
            "equity": eng.equity[-400:],
            "trades": [trade_dict(t) for t in eng.trades[-40:]][::-1],
            # Whether the narrative track's stated convictions have tracked
            # reality. Empty until enough reads have been attached and settled.
            "llm_calibration": eng.llm_calibration(),
        }
        # The macro regime is noise on an hourly view and the dominant term
        # on a yearly one, so it rides along only at horizons where it matters.
        if self.horizon.macro:
            snap["macro"] = self.macro.get().as_dict()
        snap["risk"] = self.risk.as_dict()
        snap["horizon"] = self.horizon.as_dict()
        snap["llm_read"] = self.last_read
        return snap


