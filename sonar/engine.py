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
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import model as _model

# --- strategy parameters -------------------------------------------------- #
STARTING_BANKROLL = 10_000.0
EDGE_THRESHOLD = 0.04        # only bet when |model - market| exceeds this
KELLY_FRACTION = 0.5         # half-Kelly
MAX_STAKE_FRACTION = 0.08    # never risk more than 8% of bankroll on one hour
ENTER_TAU_MAX = 0.80         # skip the noisy first minutes of the hour
ENTER_TAU_MIN = 0.12         # ...and don't chase in the final seconds
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
    # filled on settlement
    result: str | None = None       # "UP" / "DOWN"
    won: bool | None = None
    pnl: float | None = None
    settled_at: float | None = None
    open_price: float | None = None
    close_price: float | None = None


def _kelly_stake(bankroll: float, model_side_prob: float, price: float) -> float:
    """Capped fractional-Kelly stake for backing a side priced at ``price``
    (0..1) that the model gives ``model_side_prob`` of winning."""
    if price <= 0 or price >= 1:
        return 0.0
    f = (model_side_prob - price) / (1.0 - price)   # Kelly fraction
    f = max(0.0, f) * KELLY_FRACTION
    f = min(f, MAX_STAKE_FRACTION)
    return round(bankroll * f, 2)


class Engine:
    def __init__(self, state_path: str | Path,
                 starting_bankroll: float = STARTING_BANKROLL):
        self.path = Path(state_path)
        self.starting_bankroll = starting_bankroll
        self.bankroll = starting_bankroll
        self.open_position: Trade | None = None
        self.current_hour: int | None = None
        self.trades: list[Trade] = []
        self.equity: list[dict] = [{"t": int(time.time()), "v": starting_bankroll,
                                    "kind": "start"}]
        self.last_signal: _model.Signal | None = None
        self._load()

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
        self.trades = [Trade(**t) for t in d.get("trades", [])]
        self.equity = d.get("equity") or self.equity
        op = d.get("open_position")
        self.open_position = Trade(**op) if op else None

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        d = {
            "starting_bankroll": self.starting_bankroll,
            "bankroll": self.bankroll,
            "current_hour": self.current_hour,
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
        if not (ENTER_TAU_MIN <= sig.tau <= ENTER_TAU_MAX):
            return
        if sig.abs_edge < EDGE_THRESHOLD:
            return

        if sig.side == "UP":
            price = min(0.99, (market.best_ask or market.implied_up) + SLIPPAGE)
            model_side_prob = sig.model_up
        else:
            up_bid = market.best_bid or market.implied_up
            price = min(0.99, (1.0 - up_bid) + SLIPPAGE)
            model_side_prob = 1.0 - sig.model_up

        stake = _kelly_stake(self.bankroll, model_side_prob, price)
        if stake < 1.0:
            return
        shares = round(stake / price, 4)
        self.open_position = Trade(
            hour_key=candle.open_time, title=market.title, side=sig.side,
            entry_price=round(price, 4), shares=shares, stake=stake,
            model_up=round(sig.model_up, 4), market_up=round(sig.market_up, 4),
            edge=round(sig.edge, 4), entered_at=time.time(),
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
        }
