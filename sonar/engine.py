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
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d))
        tmp.replace(self.path)

    # ---- core loop ------------------------------------------------------- #
    def tick(self, candle, market, sigma: float) -> _model.Signal | None:
        """Process one observation. Returns the current model signal (or None
        if there's no live market to price against)."""
        if candle is None:
            return self.last_signal

        # rollover: a new hour started, so last hour's candle is final.
        if self.current_hour is not None and candle.open_time != self.current_hour:
            # settle against the just-closed hour using the new candle's open,
            # which equals the previous candle's close on a contiguous feed.
            self.finalize(self.current_hour, close_price=candle.open)
        self.current_hour = candle.open_time

        if market is None:
            return self.last_signal

        tau = self._tau(market.end_time)
        sig = _model.evaluate(candle.price, candle.open, sigma, tau,
                              market.implied_up)
        self.last_signal = sig
        self._maybe_enter(candle, market, sig)
        return sig

    def _tau(self, end_time: int) -> float:
        left = end_time - time.time()
        return max(0.0, min(1.0, left / 3600.0))

    def _maybe_enter(self, candle, market, sig: _model.Signal) -> None:
        if self.open_position is not None:      # one position per hour
            return
        r = self.risk
        if not (r.enter_tau_min <= sig.tau <= r.enter_tau_max):
            return
        if sig.abs_edge < r.edge_threshold:
            return

        if sig.side == "UP":
            price = min(0.99, (market.best_ask or market.implied_up) + SLIPPAGE)
            model_side_prob = sig.model_up
        else:
            up_bid = market.best_bid or market.implied_up
            price = min(0.99, (1.0 - up_bid) + SLIPPAGE)
            model_side_prob = 1.0 - sig.model_up

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
                pnl=pnl, settled_at=r["open_time"] + 3600,
                open_price=r["open"], close_price=r["close"]))
            self.equity.append({"t": r["open_time"] + 3600, "v": self.bankroll,
                                "kind": "backtest"})
        self.save()

    # ---- reporting ------------------------------------------------------- #
    def stats(self) -> dict:
        settled = [t for t in self.trades if t.pnl is not None]
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
            "win_rate": round(len(wins) / len(settled) * 100, 1) if settled else 0.0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
            "best": round(max(pnls), 2) if pnls else 0.0,
            "worst": round(min(pnls), 2) if pnls else 0.0,
            "risk_profile": self.risk.name,
        }

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
    return Trade(**{k: v for k, v in d.items() if k in fields})
