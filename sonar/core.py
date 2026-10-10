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
import random
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from . import (alerts as alerts_mod, assets, enginelock, feeds, horizon,
               institutions, llm, macro, model, news, paths, risk)
from .engine import Engine
from .research import hourlyvol
from . import calibration, events, portfolio, scoring


def trade_dict(t) -> dict | None:
    return asdict(t) if t is not None else None

PRICE_EVERY = 4.0            # seconds between price polls
MARKET_EVERY = 15.0         # seconds between Polymarket polls
# Hourly, because the estimate only changes when a candle closes: every input
# to it is a *closed* hour, so the old 600s cadence refetched the same answer
# six times. (It was sized for a trailing std; the estimator is now the
# EWMA x hour-of-day forecast measured in sonar/research/hourlyvol.py.)
VOL_EVERY = 3600.0          # seconds between volatility refreshes
SCAN_EVERY = 90.0           # seconds between asset-screen refreshes
BACKGROUND_TICK = 1.0       # how often the background thread looks for due work
BACKGROUND_JOIN = 20.0      # how long a quit waits for a rescan in flight
SEED_RETRY_EVERY = 300.0    # seconds between attempts to seed the account history
SEED_MAX_TRIES = 6          # partial answers tolerated before giving up
# Following another engine (see Live._wait_for_lock): the holder's snapshot
# is mirrored on the fast cadence, its board, book and alerts on the slow one,
# and the lock is re-checked on the slowest — a `ps` per check, so not often.
FOLLOW_EVERY = 2.0
FOLLOW_SLOW_EVERY = 10.0
LOCK_RETRY_EVERY = 15.0
# Health (see Live.health): a driving engine with no successful poll for this
# long is in trouble — a poll runs every PRICE_EVERY seconds.
HEALTH_MAX_POLL_AGE = 120.0
HEALTH_START_GRACE = 180.0     # the first poll follows two history fetches
POLL_ERROR_LOG_EVERY = 15      # log the 1st failed poll, then every 15th (~1/min)
FOLLOW_TIMEOUT = 2.0        # seconds per request to the holder, on localhost
SPARK_MAX = 220             # price points kept for the sparkline

# How long a volatility-scaled target/stop actually takes to resolve, measured
# over 6,771 non-overlapping historical setups (sonar.backtest.timing). Shown
# instead of a predicted sell date, because the exit is a *price*, not a day.
HOLD_MEDIAN_DAYS = 6
HOLD_P25_DAYS = 3
HOLD_P75_DAYS = 10

# --- the calibration protocol (off by default) ----------------------------- #
# The calibration table grades positions, and positions only exist when a
# person clicks buy or short — so on an untraded install the table stays empty
# forever, and on a traded one it grades discretion rather than the score.
# Protocol mode replaces discretion with a rule: once a day, open fixed-small
# paper positions on the top and bottom of the confidence ranking, direction
# chosen by COIN FLIP. Random on purpose: the score claims notability, never
# direction — five studies found none — and a coin flip isolates exactly the
# claim the calibration table exists to test. Measurement, not a strategy.
PROTOCOL_RISK = 0.0025          # of book equity per position; ~40 open ≈ 10%
PROTOCOL_TOP = 5                # highest-confidence rows entered per day...
PROTOCOL_BOTTOM = 5             # ...and lowest, as the control group
PROTOCOL_MAX_OPEN = 40          # hard cap on concurrently open protocol rows
PROTOCOL_MIN_ROWS = 40          # a half-fetched screen is not a ranking


class Live:
    """Shared state between the polling thread and the HTTP handlers."""

    def __init__(self, risk_name: str | None = None,
                 horizon_name: str | None = None) -> None:
        self.lock = threading.Lock()
        self._rescan_lock = threading.Lock()
        # Set by stop() to end run()'s loop. Qt aborts the whole process if a
        # QThread is still running when it is destroyed, so the loop this drives
        # must be able to finish on request — see ui/app.py's shutdown().
        self._stop = threading.Event()
        # Health bookkeeping for Live.health() and /api/health. A dead loop used
        # to leave the last snapshot on screen saying all was well, and every
        # failed poll was swallowed without a line in any log.
        self._running = False
        self._driving_since: float | None = None
        self.last_poll_ok_at: float | None = None
        self.last_poll_error = ""
        self._poll_failures = 0
        # Set by _poll: did this poll get a fresh price? The feed fetchers turn
        # network errors into None, so a full outage raised nothing and every
        # poll looked successful while no price had arrived for hours.
        self._poll_fresh = True
        # The slow work — the asset scan (26+ charts, 24 feeds, calendars), the
        # hourly σ fetch and the macro series — runs on its own thread. Inline,
        # it stalled the price poll for seconds to minutes: the engine then
        # ticked a stale candle against a fresh market and saw "edges" that
        # were only age. The macro snapshot is read from here by _build, which
        # runs under self.lock; fetching FRED there froze the window.
        self._macro_snap = None
        self._background_thread: threading.Thread | None = None
        # Single-writer guard around the paper engine (see enginelock.py).
        self.engine_lock = None
        self.read_only = False
        self.conflict = ""
        # The URL of the engine this one mirrors while it waits for the lock,
        # or None while it drives. Every action that writes the book checks
        # it and forwards instead: one writer, whoever holds the lock.
        self.following: str | None = None
        self._follow_failures = 0
        # Whether the engine being followed can run an LLM read, as its own
        # /api/config says. The read runs there, so this process's SDK and
        # key are beside the point while following.
        self._holder_llm: tuple[bool, str] | None = None
        self.horizon = horizon.get(horizon_name)
        paths.ensure_dirs()
        self.engine = Engine(paths.state_file(), risk=risk.get(risk_name))
        # A profile asked for on the command line wins, and is persisted so the
        # bankroll records what it is being sized under — but only once this
        # engine holds the lock (see _take_the_book). Saving here wrote the
        # state file from a process that might never drive it.
        self._asked_risk = risk.get(risk_name) if risk_name else None
        if self._asked_risk:
            self.risk = self._asked_risk
            self.engine.risk = self.risk
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
        self.assets: dict = {"status": "starting", "assets": []}
        self.positions: dict = {"stats": self.book.stats(), "open": [], "closed": [],
                                "equity": list(self.book.equity_log)}
        self.calibration: dict = calibration.report(self.book.closed)
        self._seed_tries = 0        # see _seed_account_history
        self._seed_at = 0.0
        self._scan_at = 0.0
        self.macro = macro.MacroCache()
        # Scheduled institutional communication — central banks are the most
        # market-moving thing on a published calendar. A variance input, not
        # a direction: see sonar/institutions.py.
        self.institutions = institutions.InstitutionCache()
        self.inst: dict = {"n": 0, "recent": [], "pressure": {}}
        # Says what changed, never what to do about it — see sonar/alerts.py.
        self.alert_engine = alerts_mod.AlertEngine()
        self.alerts: list[dict] = []
        self.reader = llm.LLMReader()
        self.last_read: dict | None = None
        # The calibration protocol (see the constants above). Off until a
        # person turns it on; the switch and its daily stamp persist so a
        # restart neither forgets the choice nor doubles a day's entries.
        self.protocol_on = False
        self._protocol_last_day = ""
        self._protocol_rng = random.Random()
        self._load_protocol()

    # -- background loop --------------------------------------------------- #
    def warmup(self) -> None:
        try:
            rows = feeds.historical_decision_points(hours=36)
            if rows:
                self.engine.seed_backtest(rows)
        except Exception:
            pass
        self.sigma = self._sigma()
        self._vol_at = time.time()
        if self.horizon.macro:          # usually the disk cache: the first page has it
            try:
                self._macro_snap = self.macro.get()
            except Exception:
                pass
        # Publish a snapshot *before* the asset screen refreshes. The Terminal
        # tab needs only the candle and the hourly market — two fast calls —
        # while _rescan() fetches 26 charts and 14 news feeds. Doing the heavy
        # one first left the whole window sitting on "starting…" for ~11s with
        # everything it needed for the main tab already in hand.
        #
        # _scan_at is set first so this poll skips the scan rather than pulling
        # it forward again; _rescan() re-stamps it immediately after.
        self._scan_at = time.time()
        try:
            self._poll()
        except Exception:
            pass
        self._rescan()

    def _rescan(self) -> None:
        """Refresh the real-asset screen (heavier, so it runs rarely).
        Headlines are fetched once here and shared with the screen.

        One at a time: the engine thread rescans on its cadence and a
        settings change rescans on its own thread, and two at once marked the
        book twice and raced each other's alerts."""
        with self._rescan_lock:
            self._rescan_once()

    def _rescan_if_due(self) -> None:
        """The background's scan: decided inside the lock, so one queued behind
        a settings change's scan does not run a second full scan straight after."""
        with self._rescan_lock:
            if time.time() - self._scan_at > SCAN_EVERY and not self._stop.is_set():
                self._rescan_once()

    def _rescan_once(self) -> None:
        try:
            heads = self.news.headlines()
        except Exception:
            heads = []
        # Warm the calendar here too. Nothing on this thread used to touch it,
        # so the first Wire render after its six-hour TTL expired did the fetch
        # on the UI thread — the one place it must never happen.
        try:
            self.events.payload()
        except Exception:
            pass
        hz, profile = self.horizon, self.risk
        # The multi-market Polymarket board was removed: it mirrored the
        # crowd's own prices with no independent model behind them. Dropping it
        # also drops ~52MB/hour — it was the single largest thing SONAR
        # downloaded, for a screen that could not say anything of its own.

        # Fetch first, then take the lock. `institutions.payload()` goes to
        # the network when its fifteen-minute cache expires — four RSS feeds
        # at a 12s timeout each — and this used to hold `self.lock` for all of
        # it. The UI thread takes that same lock every second in
        # `MainWindow.refresh()`, so the window froze for the length of the
        # fetch: blank, ignoring the close button, then alive again a few
        # seconds later. "Nothing on the UI thread may fetch" was satisfied to
        # the letter — waiting on a lock held across a fetch is the same
        # freeze. The lock covers the assignment, nothing more.
        try:
            inst = self.institutions.payload()
        except Exception:
            inst = None
        if inst is not None:
            with self.lock:
                self.inst = inst
        try:
            ap = self.asset_scanner.payload(heads, hz=hz, profile=profile)
            if self._stop.is_set():
                return     # quitting: the lock may already be someone else's
            self._mark_book(ap)
            if not self._stop.is_set():
                self._seed_account_history()
            if self.protocol_on and not self._stop.is_set():
                try:
                    self._protocol_scan(ap)
                except Exception:
                    pass          # a failed entry must not cost the rescan
            fired = self.alert_engine.scan(ap, (self.inst or {}).get("pressure"))
            with self.lock:
                self.assets = ap
                if fired:
                    self.alerts = self.alert_engine.recent()
        except Exception:
            pass
        self._scan_at = time.time()

    # -- the calibration protocol ------------------------------------------ #
    def _protocol_file(self):
        return paths.user_data_base() / "protocol.json"

    def _load_protocol(self) -> None:
        d = paths.read_preferences(self._protocol_file())
        if not d:
            return
        self.protocol_on = bool(d.get("on"))
        self._protocol_last_day = str(d.get("last_day") or "")

    def _save_protocol(self) -> None:
        # Atomic: this switch is what keeps the calibration sample filling, and
        # a write cut short used to read back as "off" with nothing to say so.
        try:
            paths.write_atomically(self._protocol_file(), json.dumps(
                {"on": self.protocol_on, "last_day": self._protocol_last_day}))
        except OSError:
            pass

    def set_protocol(self, on: bool) -> None:
        """Flip the protocol switch. Takes effect on the next rescan; turning
        it off leaves existing protocol positions to resolve on their own —
        closing them early would censor exactly the outcomes being measured."""
        url = self.following                    # read once: a takeover clears it
        if url:
            self.protocol_on = bool(on)          # what the window shows now
            self._forward(url, "/api/config", {"protocol": bool(on)})
            return
        if self._waiting_without_a_holder_to_follow():
            return
        self.protocol_on = bool(on)
        self._save_protocol()

    def _protocol_open(self) -> int:
        book = self.book
        with book.lock:
            return sum(1 for p in book.open if p.protocol)

    def _protocol_scan(self, asset_payload: dict) -> None:
        """One day's systematic entries: top and bottom of the ranking, coin-
        flip direction, fixed small risk. Runs at most once per calendar day,
        skips anything already held, and stops at the open-position cap."""
        today = time.strftime("%Y-%m-%d")
        if self._protocol_last_day == today:
            return
        rows = [a for a in asset_payload.get("assets", [])
                if a.get("price") and a.get("volatility")]
        if len(rows) < PROTOCOL_MIN_ROWS:
            return                # thin screen — try again next rescan
        book = self.book
        with book.lock:             # the cap is counted and filled in one step
            n_open = sum(1 for p in book.open if p.protocol)
            ranked = sorted(rows, key=lambda a: -a.get("confidence", 0.0))
            for a in ranked[:PROTOCOL_TOP] + ranked[-PROTOCOL_BOTTOM:]:
                if n_open >= PROTOCOL_MAX_OPEN:
                    break
                direction = self._protocol_rng.choice(("LONG", "SHORT"))
                pos, _msg = book.enter(
                    a, direction, self.horizon.momentum_days, self.horizon.name,
                    risk_fraction=PROTOCOL_RISK, protocol=True)
                if pos is not None:
                    n_open += 1
        self._protocol_last_day = today
        self._save_protocol()

    # -- the paper book ---------------------------------------------------- #
    def _mark_book(self, asset_payload: dict, force_point: bool = False,
                   book: portfolio.Portfolio | None = None) -> None:
        """Mark open positions against the new prices and close any that hit a
        barrier, then feed the resulting outcomes back into the score.

        This is the loop that makes the screener falsifiable: positions resolve,
        and calibration measures whether high scores actually won. It reports;
        it never moves P(profit) off its baseline.
        """
        rows = asset_payload.get("assets", [])
        # Merged before the empty test: a board the filter emptied (every row
        # too volatile for the profile, as in a crash) still has prices for the
        # book, and its stops must still be watched.
        prices = self._book_prices({a["symbol"]: a["price"] for a in rows})
        if not prices:
            return
        book = book or self.book
        # The whole pass — publishing included — under the book's lock, so a
        # trade or close on another thread lands before or after it, never
        # inside. Publishing after the lock let an older pass overwrite a newer
        # trade's view: the window showed no position while the book held one.
        # Lock order is book → self.lock (here, trade, close_position) and
        # self.lock → engine; nothing may take the book's lock under self.lock.
        with book.lock:
            payload = self._mark_book_locked(book, rows, prices, force_point)
            with self.lock:
                self.calibration, self.positions = payload

    def _book_prices(self, board: dict[str, float]) -> dict[str, float]:
        """Prices for the book: the board's, plus the last known price of every
        instrument the risk filter hides. A held position used to fall back to
        its entry when its row was hidden — a 30% loss closed as zero, its
        barriers no longer watched, its equity marked flat."""
        # .copy() runs in C under the GIL: the scan inserts into this dict.
        return {**self.asset_scanner.last_prices.copy(), **board}

    def _book_sparks(self, rows: list[dict]) -> dict[str, list[float]]:
        """Recent closes per instrument for the open-position cards, hidden
        rows included — a hidden position was drawn without its history."""
        return {**self.asset_scanner.last_sparks.copy(),
                **{a["symbol"]: a.get("spark") or [] for a in rows}}

    def _mark_book_locked(self, book, rows: list[dict], prices: dict,
                          force_point: bool) -> tuple[dict, dict]:
        # Turn accepted orders into real ones first. Marking a pending position
        # against a barrier would settle a holding that does not exist yet, and
        # the fill price it settles against would be the one we asked for
        # rather than the one we got. No-op for the internal paper book.
        book.poll_fills()
        closed_now = book.mark(prices)
        # The account-value curve: a point an hour, plus one at every step —
        # an entry, an exit, a barrier hit — so a step sits where it happened
        # rather than up to an hour later.
        book.log_equity(prices, force=force_point or bool(closed_now))
        # A report, never an input: P(profit) stays on its 1/(1+R:R) baseline
        # whatever the book's hit rate (owner decision 2026-10-10; see
        # sonar/calibration.py for why a closed book cannot measure drift).
        report = calibration.report(book.closed)
        # Each open row carries its instrument's recent closes, so the landing
        # page can draw the position without a request of its own.
        sparks = self._book_sparks(rows)
        open_rows = book.open_rows(prices)
        for r in open_rows:
            r["spark"] = sparks.get(r["symbol"], [])
        return report, {"stats": book.stats(prices), "open": open_rows,
                        "closed": [asdict(p) for p in book.closed[-40:]][::-1],
                        "equity": list(book.equity_log)}

    def _seed_account_history(self) -> None:
        """Give the account-value curve its past, once.

        The book ran for weeks before it logged its value, and a curve that
        starts today would say "no history" for a month. `seed_equity_log`
        rebuilds the daily history from the book's own records and real daily
        closes; this fetches those closes, on the engine thread, after a scan.
        It runs after `_mark_book`, which may already have written the first
        live point; the seed fills the days *before* that point, never over it.

        The history needs every instrument's closes: built on part of the
        book it would value the missing ones at entry and draw a flatter past
        than happened. So a short answer is not used, and the retry policy is
        shaped by what actually happens to this request — it follows a scan
        that just fetched 129 charts, and Yahoo throttles the burst. Attempts
        are spaced `SEED_RETRY_EVERY` apart; a partial answer costs one of
        `SEED_MAX_TRIES`, an empty one (no network at all) costs nothing.
        """
        book = self.book
        now = time.time()
        if (self._seed_tries >= SEED_MAX_TRIES or now - self._seed_at < SEED_RETRY_EVERY
                or not book.history_wanted()):
            return
        self._seed_at = now
        try:
            symbols = sorted({p.symbol for p in book.open + book.closed})
            with ThreadPoolExecutor(max_workers=assets.FETCH_WORKERS) as ex:
                got = dict(zip(symbols, ex.map(assets.fetch_bars, symbols)))
            bars = {s: b for s, b in got.items() if b}
            if len(bars) < len(symbols):
                self._seed_tries += 1 if bars else 0
                return
            if book.seed_equity_log(bars, now=now):
                with self.lock:
                    self.positions = {**self.positions, "equity": list(book.equity_log)}
        except Exception:
            pass               # the curve can wait; the scan it rides on cannot

    def suggestions(self, limit: int = 8) -> list[dict]:
        """What the news is pointing at right now, and what to do about it.

        Assembled only from things that survived scrutiny, which makes the
        honest answer narrower than the question usually asked of it:

        * **What** — instruments whose coverage is elevated or spiking. The
          backtest put attention at roughly +5 points on the hit rate, its one
          promising component, though short of formal significance.
        * **When to enter** — *now*, because that is when the coverage is. There
          is no best weekday: an apparent Thursday effect reversed in
          commodities and swung from 64% to 29% across instruments, which is
          what seven simultaneous tests on noise look like.
        * **When to exit** — exactly, and better than a date: the target and the
          stop are prices. History says those resolve in a median of 6 trading
          days, a quarter inside 3 and three quarters inside 10.
        * **Which direction** — not stated. Momentum was measured at no edge,
          and coverage says *something is happening*, not which way it goes.
        """
        with self.lock:
            rows = list(self.assets.get("assets", []))
        out = []
        for a in sorted(rows, key=lambda x: -x.get("confidence", 0)):
            if a.get("lean") not in ("Elevated", "Spike"):
                continue
            plan = a.get("plan") or {}
            cat = a.get("catalyst") or {}
            out.append({
                "symbol": a["symbol"], "name": a["name"], "cls": a.get("cls", ""),
                "confidence": a.get("confidence", 0.0),
                "news_level": a.get("lean"),
                "headlines": a.get("headlines", [])[:2],
                "price": a.get("price"),
                "target": plan.get("target"), "stop": plan.get("stop"),
                "rr": plan.get("rr"), "p_profit": plan.get("p_profit"),
                "catalyst": cat.get("label", ""),
                "catalyst_date": cat.get("date", ""),
                "hold_median": HOLD_MEDIAN_DAYS,
                "hold_p25": HOLD_P25_DAYS, "hold_p75": HOLD_P75_DAYS,
            })
            if len(out) >= limit:
                break
        return out

    def trade(self, symbol: str, direction: str) -> dict:
        """Open a paper position on a screener row. Paper money only."""
        url = self.following
        if url:
            return self._forward(url, "/api/trade", {"symbol": symbol, "direction": direction},
                                 refresh_book=True)
        if self._waiting_without_a_holder_to_follow():
            return {"ok": False, "message": self._READ_ONLY, "position": None}
        with self.lock:
            rows = list(self.assets.get("assets", []))
        asset = next((a for a in rows if a["symbol"] == symbol), None)
        if asset is None:
            # Same shape as every other return from here. A caller reading
            # result["position"] should not have to know which failure it hit.
            return {"ok": False, "message": f"unknown symbol {symbol}",
                    "position": None}
        book = self.book
        with book.lock:
            pos, msg = book.enter(
                asset, direction, self.horizon.momentum_days, self.horizon.name,
                risk_fraction=self.risk.max_stake_fraction / 8.0)
            self._mark_book({"assets": rows}, force_point=pos is not None, book=book)
        return {"ok": pos is not None, "message": msg,
                "position": asdict(pos) if pos else None}

    def close_position(self, pos_id: str) -> dict:
        url = self.following
        if url:
            return self._forward(url, "/api/close", {"id": pos_id}, refresh_book=True)
        if self._waiting_without_a_holder_to_follow():
            return {"ok": False, "message": self._READ_ONLY, "position": None}
        with self.lock:
            rows = list(self.assets.get("assets", []))
        prices = self._book_prices({a["symbol"]: a["price"] for a in rows})
        book = self.book
        with book.lock:
            # Found and closed under one lock: a barrier hit on the engine
            # thread between the two used to close it twice and credit twice.
            pos = next((p for p in book.open if p.id == pos_id), None)
            if pos is None:
                return {"ok": False, "message": "no such open position",
                        "position": None}
            price = prices.get(pos.symbol)
            if not price:
                # Never at the entry price: that books whatever happened as zero.
                return {"ok": False, "position": None,
                        "message": f"no price for {pos.symbol} yet — try again "
                                   "after the next scan"}
            closed = book.close(pos.id, price, "MANUAL")
            self._mark_book({"assets": rows}, force_point=True, book=book)
        return {"ok": True, "message": f"closed {closed.symbol}",
                "position": asdict(closed)}

    # -- configuration ----------------------------------------------------- #
    def configure(self, risk_name: str | None, horizon_name: str | None,
                  protocol: bool | None = None) -> dict:
        """Apply a risk profile, horizon and/or protocol switch, then rescan
        so the boards reflect the change immediately rather than after the
        next 90s tick."""
        if self.following:
            url = self.following
            try:
                self._post(url, "/api/config", {"risk": risk_name, "horizon": horizon_name,
                                                "protocol": protocol})
                self._mirror_config(url)
                self._mirror_book(url)
                board = self._fetch(url, "/api/assets")
                if isinstance(board, dict):
                    with self.lock:
                        self.assets = board
            except Exception:
                pass                      # the next mirror round shows what took
            return self.config()
        if self._waiting_without_a_holder_to_follow():
            # A risk change saves the state file and the rescan marks the book;
            # neither is this window's to write while another engine drives.
            return self.config()
        changed = False
        if risk_name and risk.get(risk_name).name != self.risk.name:
            self.risk = risk.get(risk_name)
            self.engine.set_risk(self.risk)
            changed = True
        if horizon_name and horizon.get(horizon_name).name != self.horizon.name:
            self.horizon = horizon.get(horizon_name)
            changed = True
        if protocol is not None and bool(protocol) != self.protocol_on:
            self.set_protocol(bool(protocol))
            changed = True
        if changed:
            self._rescan()
        return self.config()

    def llm_available(self) -> tuple[bool, str]:
        """Whether an LLM read can run — *where it would run*.

        While following, the holder runs every read, so the answer is the
        holder's, and a refusal names it: the launchd agent runs the
        checkout's venv, the window runs the bundle, and the two need not
        have the same SDK. Asking this process instead refused reads the
        holder could run, and misattributed the holder's refusals to this one.
        """
        if not self.following:
            return llm.available()
        where = f"the engine at {self.following.split('//')[-1]} runs the read"
        if self._holder_llm is None:
            return False, f"{where}, and has not said yet whether it can"
        ok, why = self._holder_llm
        return (True, "ready") if ok else (False, f"{where}: {why}")

    def config(self) -> dict:
        ok, why = self.llm_available()
        return {
            "risk": self.risk.as_dict(),
            "horizon": self.horizon.as_dict(),
            "risk_options": [p.as_dict() for p in risk.PROFILES.values()],
            "horizon_options": [h.as_dict() for h in horizon.HORIZONS.values()],
            "llm": {"available": ok, "detail": why, "model": llm.MODEL},
            "protocol": {
                "on": self.protocol_on,
                "last_day": self._protocol_last_day,
                "open": self._protocol_open(),
                "risk_fraction": PROTOCOL_RISK,
                "per_day": PROTOCOL_TOP + PROTOCOL_BOTTOM,
                "max_open": PROTOCOL_MAX_OPEN,
            },
        }

    # -- the narrative track ----------------------------------------------- #
    def read(self, kind: str, ident: str) -> dict:
        """Run one LLM read for a selected opportunity.

        Deliberately on demand and one at a time: running this across the whole
        board on every scan would cost real money for no benefit. The API call
        happens outside the lock so the polling thread is never blocked on it.
        """
        url = self.following
        if url:
            # The holder runs it: it has the hour the read attaches to.
            read = self._forward(url, "/api/read", {"kind": kind, "id": ident})
            with self.lock:
                self.last_read = read
            return read
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
            snap, asset_payload = self.snapshot, self.assets

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
        if not self.horizon.macro or self._macro_snap is None:
            return {}
        m = self._macro_snap
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

    def run(self, role: str = "app", url: str | None = None) -> None:
        """Drive the engine until :meth:`stop` is called.

        Refuses to poll if another SONAR already holds the engine lock. Two
        engines settling the same hour into one state file would double-count
        the portfolio, and it would do so silently. But it does not simply
        return: it waits for the lock, following the holder meanwhile when
        the holder can be followed, and drives the moment the lock is free.
        ``url`` is where *this* engine publishes its state, if it does (the
        daemon's HTTP port); it is written into the lock for the next one.
        """
        self.engine_lock = enginelock.EngineLock(role=role, url=url)
        self._running = True
        try:
            self._run_locked()
        finally:
            self._running = False

    def _run_locked(self) -> None:
        if not self.engine_lock.acquire() and not self._wait_for_lock():
            return                        # asked to stop while waiting
        try:
            while True:
                try:
                    self._take_the_book()
                    break
                except Exception as exc:
                    # Read-only stays on, so nothing writes a half-read book;
                    # say why on screen and try again rather than exit silently.
                    with self.lock:
                        self.snapshot = {"status": "read-only", "detail":
                                         f"could not read the book ({type(exc).__name__}: "
                                         f"{exc}); trying again"}
                    if self._stop.wait(LOCK_RETRY_EVERY):
                        return
            self._driving_since = time.time()
            self.warmup()
            self._background_thread = threading.Thread(
                target=self._background, name="sonar-background", daemon=True)
            self._background_thread.start()
            while not self._stop.is_set():
                self._poll_once()
                # wait(), not sleep(): a quit lands immediately instead of
                # blocking shutdown for the rest of the poll interval.
                self._stop.wait(PRICE_EVERY)
        finally:
            # The background thread writes the book (its scan marks positions):
            # it must be done before the lock goes to someone else.
            bg = self._background_thread
            if bg is not None:
                bg.join(BACKGROUND_JOIN)
            # Hand the lock back on the way out. A crash could never do this,
            # which left a stale holder and sent the next launch to read-only.
            self.engine_lock.release()

    def _background(self) -> None:
        while not self._stop.is_set():
            try:
                self._background_step()
            except Exception as exc:       # the thread must outlive a bad step
                print(f"SONAR {time.strftime('%H:%M:%S')}: background step failed: "
                      f"{' '.join(str(exc).split())}", file=sys.stderr, flush=True)
            self._stop.wait(BACKGROUND_TICK)

    def _background_step(self, now: float | None = None) -> None:
        """Whatever slow work is due: σ hourly, the scan every SCAN_EVERY, the
        macro snapshot whenever the horizon uses it (the cache decides when to
        fetch). Nothing here holds self.lock while it fetches."""
        now = time.time() if now is None else now
        if now - self._vol_at > VOL_EVERY:
            self.sigma = self._sigma()
            self._vol_at = now
        if self.horizon.macro:
            try:
                self._macro_snap = self.macro.get()
            except Exception:
                pass
        if now - self._scan_at > SCAN_EVERY and not self._stop.is_set():
            self._rescan_if_due()

    def _poll_once(self) -> None:
        """One poll, with its outcome recorded for health(). Never raises: the
        loop must outlive a bad poll."""
        try:
            self._poll()
        except Exception as exc:
            self._poll_failed(exc)
            with self.lock:
                self.snapshot = {"status": "error", "detail": str(exc)}
            return
        if self._poll_fresh:
            self.last_poll_ok_at = time.time()
            self._poll_failures = 0
        else:
            self._poll_failed(RuntimeError("no fresh BTC price from Binance or Coinbase"))

    def _poll_failed(self, exc: Exception) -> None:
        self._poll_failures += 1
        self.last_poll_error = " ".join(f"{type(exc).__name__}: {exc}".split())
        if self._poll_failures % POLL_ERROR_LOG_EVERY == 1:
            print(f"SONAR {time.strftime('%Y-%m-%d %H:%M:%S')}: poll failed "
                  f"({self._poll_failures} in a row): {self.last_poll_error}",
                  file=sys.stderr, flush=True)

    def health(self, now: float | None = None) -> dict:
        """Is this engine doing its job, judged now — not when a snapshot was
        built? ``problems`` lists what is wrong, each with a ``kind``: ``loop``
        (the engine loop ended), ``poll`` (driving, but no successful poll for
        HEALTH_MAX_POLL_AGE) or ``settle`` (polling, but no hour settled for
        engine.STALE_AFTER_S). Waiting for or following another engine is not
        a problem here: that engine answers for itself."""
        now = time.time() if now is None else now
        problems: list[dict] = []
        if self.following:
            mode = "following"
        elif self.read_only:
            mode = "waiting"
        elif self._running and self._driving_since is not None:
            mode = "driving"
        elif self._running:
            mode = "starting"
        elif self.engine_lock is None:
            mode = "not started"
        else:
            mode = "stopped"
            if not self._stop.is_set():
                problems.append({"kind": "loop", "text": "the engine loop has stopped"})
        age = None if self.last_poll_ok_at is None else round(now - self.last_poll_ok_at)
        run = None
        if mode == "driving":
            since = self.last_poll_ok_at or self._driving_since
            limit = HEALTH_MAX_POLL_AGE if self.last_poll_ok_at else HEALTH_START_GRACE
            if now - since > limit:
                why = f" (last error: {self.last_poll_error})" if self.last_poll_error else ""
                problems.append({"kind": "poll", "text": "no successful price poll for "
                                 f"{int((now - since) // 60)} min{why}"})
            bg = self._background_thread
            if bg is not None and not bg.is_alive() and not self._stop.is_set():
                problems.append({"kind": "scan", "text": "the background scan has stopped"})
            elif self._scan_at and now - self._scan_at > 3 * SCAN_EVERY:
                problems.append({"kind": "scan", "text": "the board has not been rescanned "
                                 f"for {int((now - self._scan_at) // 60)} min"})
            run = self.engine.run_health(now)
            if run.get("stale"):
                problems.append({"kind": "settle", "text": "no hour has settled for "
                                 f"{int(run.get('last_settled_age_s', 0) // 3600)} h"})
        return {"ok": not problems, "mode": mode, "problems": problems,
                "last_poll_age_s": age, "last_error": self.last_poll_error,
                "run": run}

    def stop(self) -> None:
        """Ask :meth:`run` to finish. Safe to call from another thread, and
        safe to call when the loop was never started."""
        self._stop.set()

    def _take_the_book(self) -> None:
        """Re-read the book from disk now that this engine holds the lock.

        The engine and the paper book were loaded in ``__init__``, before the
        lock. A window that followed the agent for hours still held that
        launch-time copy when it took over, and its first save — a settle, a
        scored hour, a mark — wrote it over every trade the agent had made in
        the meantime. Whatever is on disk at the moment the lock is ours is the
        record; nothing loaded before that moment may be saved over it.
        """
        self.engine = Engine(paths.state_file(), risk=self.risk)
        self.book = portfolio.Portfolio(paths.user_data_base() / "portfolio.json")
        self._load_protocol()
        if self._asked_risk:
            self.engine.set_risk(self._asked_risk)      # persisted, now ours to write
            self._asked_risk = None
        self.risk = self.engine.risk
        report = calibration.report(self.book.closed)
        # Shown until the first scan marks the book: priced off the board this
        # engine last saw (the holder's, while it followed), never written.
        with self.lock:
            rows = list(self.assets.get("assets", []))
        prices = self._book_prices({a["symbol"]: a["price"] for a in rows if a.get("price")})
        sparks = self._book_sparks(rows)
        open_rows = self.book.open_rows(prices)
        for r in open_rows:
            r["spark"] = sparks.get(r["symbol"], [])
        positions = {"stats": self.book.stats(prices), "open": open_rows,
                     "closed": [asdict(p) for p in self.book.closed[-40:]][::-1],
                     "equity": list(self.book.equity_log)}
        with self.lock:
            self.calibration = report
            self.positions = positions
            # The dead holder's mirror, or the "waits for it to stop" notice,
            # must not stay on screen until warmup's first poll — which comes
            # after two history fetches and can take many seconds offline.
            self.snapshot = {"status": "starting"}
        # Only now may actions write: the book they would write is the one on disk.
        self.read_only = False
        self.conflict = ""

    def _waiting_without_a_holder_to_follow(self) -> bool:
        """Read-only with nobody to forward to: a second window, or the moment
        between taking the lock and re-reading the book. Nothing written then
        would survive — the holder is writing the book, or it is about to be
        re-read — so actions refuse instead."""
        return self.read_only and not self.following

    _READ_ONLY = ("another SONAR is driving this book, so this one is read-only "
                  "until it stops")

    # -- following another engine ------------------------------------------ #
    def _wait_for_lock(self) -> bool:
        """Wait for the engine lock; follow its holder while waiting.

        Two SONARs share one book: the window and the launchd agent. The lock
        decides who drives, and whoever does not used to sit beside the
        driver with nothing to show — a window with an empty book, or an
        agent that never drove at all once the window quit. Now the one
        without the lock *follows*: when the holder publishes its state (the
        daemon records its URL in the lock) every page mirrors it, and the
        actions that write the book are forwarded to it; when it does not (a
        second window), this one simply waits. Either way the lock is
        re-tried on `LOCK_RETRY_EVERY`, and the moment it is free — the agent
        stopped, the window quit — this engine takes over without a restart.

        Returns True once the lock is ours, False if :meth:`stop` came first.
        """
        next_check = 0.0
        holder: dict | None = None
        last_slow = 0.0
        while not self._stop.is_set():
            now = time.time()
            if now >= next_check:
                next_check = now + LOCK_RETRY_EVERY
                holder = self.engine_lock.holder()
                if holder is None and self.engine_lock.acquire():
                    # Still read-only: an action taken now would write the
                    # launch-time book. _take_the_book lifts it once the
                    # record on disk has been re-read.
                    self.following = None
                    self._follow_failures = 0
                    return True
                self.read_only = True
                self.conflict = enginelock.describe_conflict(self.engine_lock)
            url = (holder or {}).get("url")
            if url:
                self.following = url
                slow = now - last_slow >= FOLLOW_SLOW_EVERY
                self._mirror(url, slow)
                if slow:
                    last_slow = now
            else:
                self.following = None
                with self.lock:
                    self.snapshot = {"status": "read-only", "detail": self.conflict}
            self._stop.wait(FOLLOW_EVERY)
        return False

    def _mirror(self, url: str, slow: bool) -> None:
        """One round of following: the holder's snapshot every time, the
        heavier payloads on the slow cadence. A failure leaves the last good
        copy in place; three in a row say so in the snapshot, and keep trying."""
        try:
            snap = self._fetch(url, "/api/state")
            snap = dict(snap) if isinstance(snap, dict) else {"status": "starting"}
            snap["following"] = url
            with self.lock:
                self.snapshot = snap
            if slow:
                board = self._fetch(url, "/api/assets")
                wire = self._fetch(url, "/api/wire")
                with self.lock:
                    if isinstance(board, dict):
                        self.assets = board
                    if isinstance(wire, dict):
                        self.alerts = list(wire.get("alerts") or [])
                        self.inst = wire.get("inst") or self.inst
                self._mirror_book(url)
                self._mirror_config(url)
                # The Wire renders from these caches and never fetches on the
                # UI thread; while following, this thread keeps them warm.
                try:
                    self.news.headlines()
                    self.events.payload()
                except Exception:
                    pass
            self._follow_failures = 0
        except Exception as exc:
            self._follow_failures += 1
            if self._follow_failures >= 3:
                with self.lock:
                    self.snapshot = {
                        "status": "read-only", "following": url,
                        "detail": f"{self.conflict} It is not answering at "
                                  f"{url} ({type(exc).__name__}: {exc})."}

    def _mirror_book(self, url: str) -> None:
        book = self._fetch(url, "/api/book")
        if not isinstance(book, dict):
            return
        with self.lock:
            if isinstance(book.get("positions"), dict):
                self.positions = book["positions"]
            if isinstance(book.get("calibration"), dict):
                self.calibration = book["calibration"]
            if "protocol_on" in book:
                self.protocol_on = bool(book["protocol_on"])

    def _mirror_config(self, url: str) -> None:
        cfg = self._fetch(url, "/api/config")
        if not isinstance(cfg, dict):
            return
        name = (cfg.get("risk") or {}).get("name")
        if name and name != self.risk.name:
            self.risk = risk.get(name)
        name = (cfg.get("horizon") or {}).get("name")
        if name and name != self.horizon.name:
            self.horizon = horizon.get(name)
        if "on" in (cfg.get("protocol") or {}):
            self.protocol_on = bool(cfg["protocol"]["on"])
        llm_cfg = cfg.get("llm")
        if isinstance(llm_cfg, dict) and "available" in llm_cfg:
            self._holder_llm = (bool(llm_cfg["available"]),
                                str(llm_cfg.get("detail") or ""))

    @staticmethod
    def _fetch(url: str, path: str):
        with urllib.request.urlopen(url.rstrip("/") + path, timeout=FOLLOW_TIMEOUT) as r:
            return json.loads(r.read())

    @staticmethod
    def _post(url: str, path: str, payload: dict):
        req = urllib.request.Request(
            url.rstrip("/") + path, data=json.dumps(payload).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=FOLLOW_TIMEOUT) as r:
            return json.loads(r.read())

    def _forward(self, url: str, path: str, payload: dict,
                 refresh_book: bool = False) -> dict:
        """Hand an action to the engine being followed: it holds the book.

        A refusal from the network is reported in the same shape as a refusal
        from the book, so the window shows a sentence rather than a traceback.
        ``url`` is the one the caller saw; read again here, a takeover in
        between left None and an AttributeError in the message.
        """
        try:
            result = self._post(url, path, payload)
            if refresh_book:
                self._mirror_book(url)
            return result
        except Exception as exc:
            return {"ok": False, "position": None,
                    "message": f"the engine at {url} did not take it "
                               f"({type(exc).__name__}: {exc})"}

    def _sigma(self) -> float:
        """The per-hour volatility the model prices with.

        The EWMA × hour-of-day forecast, measured at +7.5% QLIKE over the old
        trailing-72 std across 16,078 held-out hours and 6/6 time blocks
        (`sonar/research/hourlyvol.py`, which records the study). Falls back
        down the measured ladder when history is short or the fetch fails:
        plain EWMA inside `forecast()`, then the old trailing estimate here.
        """
        try:
            times, closes = hourlyvol.fetch_hourly(days=62)
            s = hourlyvol.forecast(closes, times, now=time.time())
            if s is not None:
                return s
        except Exception:
            pass
        return model.hourly_sigma(feeds.recent_hourly_returns())

    def _poll(self) -> None:
        # Market first, candle last: the price the engine ticks on is the
        # freshest thing fetched. The slow work runs on the background thread.
        if time.time() - self._market_at > MARKET_EVERY or self._last_market is None:
            m = feeds.current_market()
            if m is not None:
                self._last_market = m
                self._market_at = time.time()
        now = time.time()
        candle = feeds.hourly_candle()
        self._poll_fresh = candle is not None
        hour = self.engine.current_hour          # only this thread writes it
        if candle is not None and hour is not None and candle.open_time < hour:
            # An earlier hour than the engine is on (a lagging fallback feed, a
            # clock a few seconds behind the exchange): the engine ignores it,
            # and so must the screen — last hour's price beside this hour's
            # signal, and an old price on the spark line.
            candle = None

        market = self._last_market
        if (market is not None and candle is not None
                and market.end_time != candle.open_time + 3600):
            # Another hour's market (the series fallback can hand back the next
            # one): the engine refuses it, so the screen must not price it
            # beside this hour's candle either.
            market = None

        if candle is not None:
            self.spark.append({"t": int(now), "p": candle.price})
            self.spark = self.spark[-SPARK_MAX:]

        # After a feed gap the engine needs the missed hour's real close to
        # settle honestly (see Engine._settle_rollover). Fetch it *before*
        # taking the lock: the UI thread blocks on this lock to read the
        # snapshot, and a network call held under it is the same frozen-window
        # failure _refresh_wire() had. On a contiguous feed this fetches
        # nothing. Reading current_hour without the lock is safe — only this
        # thread's tick() ever writes it.
        gap_close: dict[int, float] = {}
        last_hour = self.engine.current_hour
        if (candle is not None and last_hour is not None
                and candle.open_time != last_hour
                and candle.open_time - last_hour != 3600):
            close = feeds.hour_close(last_hour)
            if close is not None:
                gap_close[last_hour] = close

        with self.lock:
            sigma = self.sigma              # one value for the signal and the page
            sig = self.engine.tick(candle, market, sigma,
                                   close_lookup=gap_close.get)
            self.snapshot = self._build(candle, market, sig, now, sigma)

    # -- snapshot builder -------------------------------------------------- #
    def _build(self, candle, market, sig, now, sigma: float | None = None) -> dict:
        eng = self.engine
        snap: dict = {
            "status": "live",
            "now": int(now),
            "sigma": round(self.sigma if sigma is None else sigma, 6),
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
            # Brier: model vs market over every hour watched, traded or not —
            # the direct test of the realised-vs-implied thesis.
            "model_vs_market": eng.model_vs_market(),
            # Coverage, voids and staleness — whether the experiment is
            # actually collecting, which a quiet menu bar cannot show.
            "run_health": eng.run_health(now),
            # Calibrated is not the same as buyable: this prices the model's
            # disagreements at the recorded touch.
            "buyability": eng.buyability(),
        }
        # The macro regime is noise on an hourly view and the dominant term
        # on a yearly one, so it rides along only at horizons where it matters.
        if self.horizon.macro and self._macro_snap is not None:
            snap["macro"] = self._macro_snap.as_dict()
        snap["risk"] = self.risk.as_dict()
        snap["horizon"] = self.horizon.as_dict()
        snap["llm_read"] = self.last_read
        return snap


