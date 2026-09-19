"""Paper-trading engine.

PAPER MONEY ONLY. No exchange, no wallet, no order is ever placed anywhere. The
engine watches the real market, and every hour it may take one simulated
position in the current Polymarket "Bitcoin Up or Down" market, then settles it
against the real candle result. It tracks a fake bankroll so you can see, over
many hours, whether the model's edge is real — usually it is tiny and frequently
negative, which is the honest point.

Trade lifecycle
---------------
1. During an hour, once the model's edge over the market crosses a threshold
   (and there's a sensible amount of time left), we "buy" the favoured side at
   the market's asking price. Size is a capped fractional-Kelly bet.
2. When the hour rolls over, the position is settled against the real BTC/USDT
   candle: a winning share pays 1.00, a losing share pays 0.00.
3. Realised P&L updates the bankroll and the equity curve.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from dataclasses import fields as dataclass_fields
from pathlib import Path

from . import model as _model
from . import risk as _risk

# --- strategy parameters -------------------------------------------------- #
# Sizing and entry-timing parameters now live on a RiskProfile (see risk.py).
# They were always an expression of risk appetite — they were just hardcoded.
# What stays here is the part that isn't a matter of taste.
STARTING_BANKROLL = 10_000.0
SLIPPAGE = 0.005             # half a cent of spread crossing, in probability

# The hour-scoring snapshot is taken at the first reading with at most this
# fraction of the hour remaining. Mid-hour on purpose: at the top the model is
# pinned to 0.5 by construction, and near the close both the model and the
# market collapse to the sign of the move, so neither end can distinguish them.
SCORE_TAU = 0.5
# Hours kept in the model-vs-market score log (~4 months of round-the-clock
# uptime). Enough to answer the question; not an unbounded state file.
SCORELOG_MAX = 3000


@dataclass
class Trade:
    hour_key: int
    title: str
    side: str                # "UP" / "DOWN"
    entry_price: float       # probability paid per share (0..1)
    shares: float
    stake: float
    model_up: float
    market_up: float
    edge: float
    entered_at: float
    risk_profile: str = "moderate"
    # "live" for a real paper trade, "backtest" for a fair-odds warm-up row.
    # The warm-up exists to show variance on the chart, not to pad the record —
    # stats() counts live rows only, and this field is how it tells them apart.
    kind: str = "live"
    # The LLM's stated conviction at entry, when a read was attached. Recorded,
    # never acted on: sizing is the model's edge and the risk profile, nothing
    # else. Logging it is what lets llm_calibration() score it after the fact.
    llm_conviction: int | None = None
    llm_direction: str | None = None
    llm_model: str | None = None
    # filled on settlement
    result: str | None = None       # "UP" / "DOWN"
    won: bool | None = None
    pnl: float | None = None
    settled_at: float | None = None
    open_price: float | None = None
    close_price: float | None = None


class Engine:
    def __init__(self, state_path: str | Path,
                 starting_bankroll: float = STARTING_BANKROLL,
                 risk: _risk.RiskProfile | None = None):
        self.path = Path(state_path)
        self.risk = risk or _risk.DEFAULT
        self.starting_bankroll = starting_bankroll
        self.bankroll = starting_bankroll
        self.open_position: Trade | None = None
        self.current_hour: int | None = None
        self.trades: list[Trade] = []
        self.equity: list[dict] = [{"t": int(time.time()), "v": starting_bankroll,
                                    "kind": "start"}]
        self.last_signal: _model.Signal | None = None
        # An LLM read for the hour in progress, if the user asked for one.
        self.pending_llm: dict | None = None
        # The mid-hour snapshot for the hour in progress, and the settled log
        # of every hour the engine watched — traded or not. See model_vs_market.
        self.pending_score: dict | None = None
        self.scorelog: list[dict] = []
        self._load()

    def set_risk(self, profile: _risk.RiskProfile) -> None:
        """Switch risk profile. Takes effect on the next entry decision; an
        already-open position keeps the profile it was sized under."""
        self.risk = profile
        self.save()

    def attach_llm_read(self, hour_key: int, read: dict) -> None:
        """Record an LLM read for the hour in progress so that, if a position is
        opened, the stated conviction rides along on the Trade and can later be
        scored against the real candle."""
        if read.get("error"):
            return
        self.pending_llm = {
            "hour_key": hour_key,
            "conviction": read.get("conviction"),
            "direction": read.get("direction"),
            "model": read.get("model"),
        }

    # ---- persistence ----------------------------------------------------- #
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            d = json.loads(self.path.read_text())
        except (ValueError, OSError):
            return
        self.bankroll = d.get("bankroll", self.starting_bankroll)
        self.starting_bankroll = d.get("starting_bankroll", self.starting_bankroll)
        self.current_hour = d.get("current_hour")
        # Tolerate state files written before a field existed.
        self.trades = [_trade_from(t) for t in d.get("trades", [])]
        self.equity = d.get("equity") or self.equity
        op = d.get("open_position")
        self.open_position = _trade_from(op) if op else None
        self.pending_score = d.get("pending_score")
        self.scorelog = d.get("scorelog") or []
        if d.get("risk_profile"):
            self.risk = _risk.get(d["risk_profile"])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        d = {
            "starting_bankroll": self.starting_bankroll,
            "bankroll": self.bankroll,
            "current_hour": self.current_hour,
            "risk_profile": self.risk.name,
            "open_position": asdict(self.open_position) if self.open_position else None,
            "trades": [asdict(t) for t in self.trades],
            "equity": self.equity,
            "pending_score": self.pending_score,
            "scorelog": self.scorelog,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d))
        tmp.replace(self.path)

    # ---- core loop ------------------------------------------------------- #
    def tick(self, candle, market, sigma: float,
             close_lookup=None) -> _model.Signal | None:
        """Process one observation. Returns the current model signal (or None
        if there's no live market to price against).

        ``close_lookup`` recovers the real close of a past hour (unix seconds
        in, close price or None out). It is only consulted after a gap in the
        feed — see :meth:`_settle_rollover`."""
        if candle is None:
            return self.last_signal

        # rollover: a new hour started, so last hour's candle is final.
        if self.current_hour is not None and candle.open_time != self.current_hour:
            self._settle_rollover(candle, close_lookup)
        self.current_hour = candle.open_time

        if market is None:
            return self.last_signal

        tau = self._tau(market.end_time)
        sig = _model.evaluate(candle.price, candle.open, sigma, tau,
                              market.implied_up)
        self.last_signal = sig
        self._maybe_score(candle, sig)
        self._maybe_enter(candle, market, sig)
        return sig

    def _settle_rollover(self, candle, close_lookup) -> None:
        """Settle the hour that just ended, against a close that is its own.

        On a contiguous feed the new candle opens exactly one hour after the
        old one, so its open *is* the previous hour's close. After a gap — the
        machine slept, the app restarted, the feed was down — the new candle's
        open is a price from hours after the position's market resolved, and
        settling against it records a result the market never produced (a
        losing hour can book as a win). So the real close is looked up; if it
        cannot be recovered, the position is **voided** rather than settled
        wrongly. Nothing is deducted at entry, so a void leaves the bankroll
        exactly as if the bet had never been taken — a shorter record beats a
        corrupted one, since calibration is the point of keeping it.
        """
        hour = self.current_hour
        if candle.open_time - hour == 3600:
            close = candle.open
        else:
            close = close_lookup(hour) if close_lookup else None
        if close is not None:
            self.finalize(hour, close_price=close)
            self._score_hour(hour, close)
            return
        self.open_position = None
        if self.pending_score and self.pending_score.get("hour_key") == hour:
            self.pending_score = None
        self.save()

    # ---- scoring every hour, not just the traded ones -------------------- #
    def _maybe_score(self, candle, sig: _model.Signal) -> None:
        """Snapshot the model and the market once per hour, mid-hour.

        The paper P&L only ever scores hours where the two disagreed enough to
        trade — which selects for the model's boldest claims and converges at a
        few observations a day. This records *every* hour at the first reading
        past ``SCORE_TAU``, so :meth:`model_vs_market` can compare the two on
        the whole distribution instead of the tail.
        """
        if sig.tau > SCORE_TAU:
            return
        if (self.pending_score
                and self.pending_score.get("hour_key") == candle.open_time):
            return
        self.pending_score = {
            "hour_key": candle.open_time,
            "open": candle.open,
            "model_up": round(sig.model_up, 4),
            "market_up": round(sig.market_up, 4),
            "tau": round(sig.tau, 4),
        }

    def _score_hour(self, hour_key: int, close: float) -> None:
        p, self.pending_score = self.pending_score, None
        if not p or p.get("hour_key") != hour_key:
            return
        p["outcome"] = 1.0 if close >= p["open"] else 0.0
        p["close"] = close
        self.scorelog.append(p)
        self.scorelog = self.scorelog[-SCORELOG_MAX:]
        self.save()

    def _tau(self, end_time: int) -> float:
        left = end_time - time.time()
        return max(0.0, min(1.0, left / 3600.0))

    def _maybe_enter(self, candle, market, sig: _model.Signal) -> None:
        if self.open_position is not None:      # one position per hour
            return
        r = self.risk
        if not (r.enter_tau_min <= sig.tau <= r.enter_tau_max):
            return

        if sig.side == "UP":
            price = min(0.99, (market.best_ask or market.implied_up) + SLIPPAGE)
            model_side_prob = sig.model_up
        else:
            up_bid = market.best_bid or market.implied_up
            price = min(0.99, (1.0 - up_bid) + SLIPPAGE)
            model_side_prob = 1.0 - sig.model_up

        # The threshold is on the *executable* edge — the model's probability
        # for the side minus what a share of it actually costs at the touch —
        # not on the midpoint disagreement. A 4¢ edge at the mid across a 10¢
        # spread is not an edge: gating at the mid let exactly those entries
        # through whenever the book was wide late in the hour, sized small but
        # negative every time.
        if model_side_prob - price < r.edge_threshold:
            return

        stake = r.kelly_stake(self.bankroll, model_side_prob, price)
        if stake < 1.0:
            return
        shares = round(stake / price, 4)

        # Stamp on any LLM read taken for this hour. It does not influence the
        # side or the size — it is carried so it can be graded later.
        llm = self.pending_llm or {}
        if llm.get("hour_key") != candle.open_time:
            llm = {}

        self.open_position = Trade(
            hour_key=candle.open_time, title=market.title, side=sig.side,
            entry_price=round(price, 4), shares=shares, stake=stake,
            model_up=round(sig.model_up, 4), market_up=round(sig.market_up, 4),
            edge=round(sig.edge, 4), entered_at=time.time(),
            risk_profile=r.name,
            llm_conviction=llm.get("conviction"),
            llm_direction=llm.get("direction"),
            llm_model=llm.get("model"),
            open_price=candle.open,
        )
        self.save()

    def finalize(self, hour_key: int, close_price: float,
                 open_price: float | None = None) -> Trade | None:
        """Settle the open position for ``hour_key`` against the real result."""
        pos = self.open_position
        if pos is None or pos.hour_key != hour_key:
            self.open_position = None
            return None

        open_ = open_price if open_price is not None else pos.open_price
        result = "UP" if close_price >= open_ else "DOWN"
        won = (result == pos.side)
        pnl = round(pos.shares * (1.0 - pos.entry_price) if won else -pos.stake, 2)

        pos.result, pos.won, pos.pnl = result, won, pnl
        pos.settled_at = time.time()
        pos.close_price = close_price
        self.bankroll = round(self.bankroll + pnl, 2)
        self.trades.append(pos)
        self.equity.append({"t": int(pos.settled_at), "v": self.bankroll,
                            "kind": "live"})
        self.open_position = None
        self.save()
        return pos

    # ---- honest historical warm-up -------------------------------------- #
    def seed_backtest(self, rows: list[dict]) -> None:
        """Populate the equity curve from real past hours at *fair* odds.

        Each row carries real candle data: ``open``, mid-hour ``price`` and
        ``tau`` at a decision point, real ``close``, and causal ``sigma``. We
        back the model's favoured side but pay the model's *own* fair price, so
        expected value is ~0 by construction. This fills the chart with genuine
        BTC outcomes without inventing any counterparty odds or fake profit — it
        shows variance, not edge. Runs only once, on a fresh bankroll.
        """
        if self.trades or len(self.equity) > 1:
            return
        stake = 100.0
        for r in rows:
            p = _model.prob_up(r["price"], r["open"], r["sigma"], r["tau"])
            side = "UP" if p >= 0.5 else "DOWN"
            price = p if side == "UP" else 1.0 - p       # fair odds
            price = min(0.98, max(0.02, price))
            result = "UP" if r["close"] >= r["open"] else "DOWN"
            won = (result == side)
            shares = stake / price
            pnl = round(shares * (1.0 - price) if won else -stake, 2)
            self.bankroll = round(self.bankroll + pnl, 2)
            self.trades.append(Trade(
                hour_key=r["open_time"], title=r.get("title", "backtest"),
                side=side, entry_price=round(price, 4), shares=round(shares, 4),
                stake=stake, model_up=round(p, 4), market_up=round(price, 4),
                edge=0.0, entered_at=r["open_time"], result=result, won=won,
                pnl=pnl, settled_at=r["open_time"] + 3600, kind="backtest",
                open_price=r["open"], close_price=r["close"]))
            self.equity.append({"t": r["open_time"] + 3600, "v": self.bankroll,
                                "kind": "backtest"})
        self.save()

    # ---- reporting ------------------------------------------------------- #
    def stats(self) -> dict:
        # Live trades only. The fair-odds warm-up seeds the *chart* with real
        # BTC variance, but its rows are synthetic bets at the model's own
        # price — counting them would let a fresh install show a win rate and a
        # P&L built from trades nobody took.
        settled = [t for t in self.trades
                   if t.pnl is not None and t.kind == "live"]
        wins = [t for t in settled if t.won]
        pnls = [t.pnl for t in settled]
        gross_win = sum(p for p in pnls if p > 0)
        gross_loss = -sum(p for p in pnls if p < 0)
        return {
            "bankroll": round(self.bankroll, 2),
            "starting_bankroll": self.starting_bankroll,
            "total_pnl": round(self.bankroll - self.starting_bankroll, 2),
            "return_pct": round((self.bankroll / self.starting_bankroll - 1) * 100, 2),
            "n_trades": len(settled),
            "n_wins": len(wins),
            "n_seeded": sum(1 for t in self.trades if t.kind == "backtest"),
            "win_rate": round(len(wins) / len(settled) * 100, 1) if settled else 0.0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
            "best": round(max(pnls), 2) if pnls else 0.0,
            "worst": round(min(pnls), 2) if pnls else 0.0,
            "risk_profile": self.risk.name,
        }

    # How many scored hours before model_vs_market states a verdict. Hourly
    # outcomes are non-overlapping, so unlike the daily backtest a plain
    # binomial-style standard error is honest here — but a week of hours still
    # says more about that week than about the model.
    SCORE_MIN_SAMPLE = 100

    def model_vs_market(self) -> dict:
        """Brier score of the model against the market, over every hour watched.

        The paper P&L answers this question eventually, but only on the hours
        the engine traded — the ones where the model made its boldest claim —
        and at a few observations a day through bankroll variance. This scores
        both forecasters on *all* hours at the same mid-hour snapshot: the one
        clean test of the realised-vs-implied thesis the whole Terminal tab
        rests on. Lower Brier is better; the verdict uses the paired
        difference and its standard error, so it refuses to call noise a win.
        """
        rows = self.scorelog
        n = len(rows)
        if n == 0:
            return {"n": 0, "min_sample": self.SCORE_MIN_SAMPLE,
                    "verdict": "No settled hours scored yet."}
        model = sum((r["model_up"] - r["outcome"]) ** 2 for r in rows) / n
        market = sum((r["market_up"] - r["outcome"]) ** 2 for r in rows) / n
        base = sum(r["outcome"] for r in rows) / n
        baseline = sum((base - r["outcome"]) ** 2 for r in rows) / n
        diffs = [(r["model_up"] - r["outcome"]) ** 2
                 - (r["market_up"] - r["outcome"]) ** 2 for r in rows]
        mean_d = sum(diffs) / n
        var = (sum((d - mean_d) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0.0
        se = (var / n) ** 0.5
        out = {
            "n": n,
            "min_sample": self.SCORE_MIN_SAMPLE,
            "model_brier": round(model, 4),
            "market_brier": round(market, 4),
            "baseline_brier": round(baseline, 4),
            "brier_diff": round(mean_d, 4),      # negative = model better
            "diff_se": round(se, 4),
        }
        if n < self.SCORE_MIN_SAMPLE:
            out["verdict"] = (f"{n} of {self.SCORE_MIN_SAMPLE} hours scored — "
                              "too few to compare the model to the market.")
        elif mean_d < -2 * se and mean_d < 0:
            out["verdict"] = ("Model beats the market's calibration by more "
                              "than two standard errors over these hours.")
        elif mean_d > 2 * se and mean_d > 0:
            out["verdict"] = ("The market is better calibrated than the model "
                              "— the realised-vol edge is not showing up.")
        else:
            out["verdict"] = ("Model and market are within noise of each "
                              "other, which is what no edge looks like.")
        return out

    def llm_calibration(self) -> dict:
        """Score the LLM's stated convictions against what actually happened.

        This is the honest counterweight to having an LLM in the loop at all.
        The narrative track is uncalibrated by construction — so rather than
        take its confidence at face value, we bucket every logged conviction and
        report the realised hit rate in each bucket, using the same settled
        candles the paper P&L uses.

        A well-calibrated commentator's ``hit_rate`` should climb with the
        bucket. A flat or inverted table means the conviction number carries no
        information, which is exactly the kind of thing that is worth knowing and
        almost never measured.

        Interpret with care until ``n`` per bucket is well into double digits;
        small samples say nothing.
        """
        scored = [t for t in self.trades
                  if t.llm_conviction is not None and t.won is not None]
        buckets = [(0, 25), (25, 50), (50, 75), (75, 101)]
        rows = []
        for lo, hi in buckets:
            in_b = [t for t in scored if lo <= t.llm_conviction < hi]
            hits = [t for t in in_b if t.llm_direction == t.result]
            rows.append({
                "bucket": f"{lo}–{hi - 1 if hi <= 100 else 100}",
                "n": len(in_b),
                "hit_rate": round(len(hits) / len(in_b) * 100, 1) if in_b else None,
                "avg_conviction": (round(sum(t.llm_conviction for t in in_b) / len(in_b), 1)
                                   if in_b else None),
            })
        agree = [t for t in scored if t.llm_direction == t.side]
        return {
            "n_scored": len(scored),
            "buckets": rows,
            # How often the narrative track agreed with the arithmetic one.
            "agreed_with_model_pct": (round(len(agree) / len(scored) * 100, 1)
                                      if scored else None),
            "note": ("Stated conviction is subjective, not a probability. This "
                     "table exists to check whether it tracks reality."),
        }


def _trade_from(d: dict) -> Trade:
    """Build a Trade from persisted JSON, ignoring keys this version dropped and
    defaulting ones it gained. Keeps old state.json files loadable."""
    fields = {f.name for f in dataclass_fields(Trade)}
    t = Trade(**{k: v for k, v in d.items() if k in fields})
    # State written before `kind` existed: the warm-up rows are identifiable by
    # the title seed_backtest stamped on them, so an old book's seeded trades
    # still stay out of the live stats.
    if "kind" not in d and t.title == "backtest":
        t.kind = "backtest"
    return t
