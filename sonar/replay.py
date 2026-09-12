"""Trade history one setup at a time, with the future withheld.

The Lab tab's replay grades the *model*. This grades **you**. The app's whole
position on the asset board is that direction is the user's call, and until now
there was no way to find out whether those calls were any good — the algorithm
gets a hit rate and an error bar, the human gets nothing.

Why the lookahead guarantee is the whole design
-----------------------------------------------
A discretionary replay is trivially easy to build wrong, and wrong here does not
crash — it flatters. If any part of the future leaks into what you are shown,
the exercise becomes a machine for discovering you would have bought Nvidia, and
it *feels* like evidence while being worth nothing.

So :class:`Session` never holds anything it should not show. :meth:`current`
slices the price series at the cursor and hands out a copy; the bars after it
are not in the returned object at all, so a UI cannot render them by accident.
:meth:`decide` is the only thing that looks forward, and only after a call is
locked in. There is a test that reaches into the returned setup and asserts the
future is genuinely absent rather than merely unused.

The money
---------
Each decision is sized so that being wrong costs the same fixed cash amount,
which is how the live book sizes too — risk, not notional. That makes P&L
comparable across a volatile coin and a quiet currency pair, which raw position
size would not. A win pays ``rr`` times the amount risked, because the target
sits that much further away than the stop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import scoring
from .assets import _MOM_SCALE, _W
from .backtest import Bars, _resolve, _vol

LONG, SHORT, SKIP = "LONG", "SHORT", "SKIP"

# Matches backtest.run_symbol, so the setups a person sees are the same ones the
# model was graded on rather than a differently-generated set.
MIN_LOOKBACK = 30
MAX_HOLD_MULTIPLE = 4


@dataclass(frozen=True)
class Setup:
    """One decision point, carrying nothing from after it.

    ``closes`` stops at the cursor. That is not a convention — it is the reason
    this class exists rather than passing the whole ``Bars`` around.
    """

    symbol: str
    index: int
    t: int
    price: float
    momentum: float
    volatility: float
    confidence: float
    model_direction: str          # what the algorithm would have done
    target_long: float
    stop_long: float
    target_short: float
    stop_short: float
    rr: float
    p_profit: float
    closes: list[float] = field(default_factory=list)

    def plan_for(self, direction: str) -> tuple[float, float]:
        return ((self.target_long, self.stop_long) if direction == LONG
                else (self.target_short, self.stop_short))

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "closes"}
        d["spark"] = [round(c, 4) for c in self.closes[-40:]]
        return d


@dataclass
class Decision:
    """What was chosen, and what happened afterwards."""

    index: int
    t: int
    symbol: str
    choice: str                   # LONG | SHORT | SKIP
    model_direction: str
    confidence: float
    outcome: str | None = None    # TARGET | STOP | TIMEOUT | None when skipped
    model_outcome: str | None = None
    bars_held: int = 0
    pnl: float = 0.0              # yours, in currency
    model_pnl: float = 0.0


class Session:
    """A replay over one instrument. Stateful, and deliberately not rewindable.

    Going back would let a decision be retaken once its outcome is known, which
    is the same lookahead problem wearing a different hat.
    """

    def __init__(self, bars: Bars, horizon_days: int = 5, step: int = 3,
                 stake: float = 100.0, start: int | None = None,
                 k_target: float = scoring.K_TARGET,
                 k_stop: float = scoring.K_STOP) -> None:
        self.bars = bars
        self.horizon_days = horizon_days
        self.step = max(1, step)
        self.stake = stake            # cash at risk per decision, not notional
        self.k_target, self.k_stop = k_target, k_stop
        self.decisions: list[Decision] = []
        self.started = int(time.time())
        floor = max(MIN_LOOKBACK, horizon_days + 1)
        self.i = max(floor, start if start is not None else floor)

    # -- the cursor -------------------------------------------------------- #
    def _usable(self, i: int) -> bool:
        if i >= len(self.bars.close) - 2:
            return False
        past = self.bars.close[:i + 1]
        if len(past) <= self.horizon_days or _vol(past[-30:]) <= 0:
            return False
        return past[-1] != past[-(self.horizon_days + 1)]

    def current(self) -> Setup | None:
        """The setup at the cursor, with everything after it withheld."""
        while self.i < len(self.bars.close) - 2 and not self._usable(self.i):
            self.i += self.step
        if not self._usable(self.i):
            return None

        i = self.i
        past = self.bars.close[:i + 1]          # inclusive of today only
        vol = _vol(past[-30:])
        mom = past[-1] / past[-(self.horizon_days + 1)] - 1
        price = past[-1]
        long_plan = scoring.build_plan(price, vol, self.horizon_days, LONG,
                                       k_target=self.k_target, k_stop=self.k_stop)
        short_plan = scoring.build_plan(price, vol, self.horizon_days, SHORT,
                                        k_target=self.k_target, k_stop=self.k_stop)
        scale = _MOM_SCALE.get(self.horizon_days, 0.10)
        comp = {"momentum": min(1.0, abs(mom) / scale),
                "volatility": min(1.0, vol / 0.03)}
        conf = round(100 * sum(_W[k] * comp.get(k, 0.0) for k in _W), 1)
        return Setup(
            symbol=self.bars.symbol, index=i, t=self.bars.time[i],
            price=price, momentum=mom, volatility=vol, confidence=conf,
            model_direction=LONG if mom > 0 else SHORT,
            target_long=long_plan.target, stop_long=long_plan.stop,
            target_short=short_plan.target, stop_short=short_plan.stop,
            rr=long_plan.rr, p_profit=long_plan.p_profit,
            closes=list(past),                  # a copy, ending at the cursor
        )

    # -- the decision ------------------------------------------------------ #
    def decide(self, choice: str) -> Decision | None:
        """Lock a call in and resolve it. The only method that looks forward."""
        setup = self.current()
        if setup is None:
            return None
        choice = choice.upper()
        if choice not in (LONG, SHORT, SKIP):
            raise ValueError(f"choice must be LONG, SHORT or SKIP, not {choice!r}")

        max_bars = self.horizon_days * MAX_HOLD_MULTIPLE
        d = Decision(index=setup.index, t=setup.t, symbol=setup.symbol,
                     choice=choice, model_direction=setup.model_direction,
                     confidence=setup.confidence)

        if choice != SKIP:
            target, stop = setup.plan_for(choice)
            d.outcome, d.bars_held = _resolve(self.bars, setup.index, choice,
                                              target, stop, max_bars)
            d.pnl = self._pnl(d.outcome, setup.rr)

        # The model's call on the same setup, always — otherwise skipping every
        # hard one would look like skill.
        m_target, m_stop = setup.plan_for(setup.model_direction)
        d.model_outcome, _ = _resolve(self.bars, setup.index,
                                      setup.model_direction, m_target, m_stop,
                                      max_bars)
        d.model_pnl = self._pnl(d.model_outcome, setup.rr)

        self.decisions.append(d)
        self.i += self.step
        return d

    def _pnl(self, outcome: str | None, rr: float) -> float:
        """Risk-based, so a coin and a currency pair are comparable.

        Being wrong costs ``stake``; being right pays ``rr`` times it. A setup
        that never resolves inside the hold window pays nothing — it is an
        unresolved position, not a scratch.
        """
        if outcome == "TARGET":
            return round(self.stake * rr, 2)
        if outcome == "STOP":
            return round(-self.stake, 2)
        return 0.0

    # -- the scorecard ----------------------------------------------------- #
    def scorecard(self) -> dict:
        """You against the model, on identical setups.

        Reported with an error bar because fifty discretionary calls is a small
        sample and the difference between 46% and 54% over that many trades is
        noise. The app refuses to claim an edge it cannot measure; the same rule
        applies to its user.
        """
        import math

        taken = [d for d in self.decisions if d.choice != SKIP]
        resolved = [d for d in taken if d.outcome in ("TARGET", "STOP")]
        m_resolved = [d for d in self.decisions
                      if d.model_outcome in ("TARGET", "STOP")]

        def rate(rows, key):
            if not rows:
                return None
            return sum(1 for d in rows if getattr(d, key) == "TARGET") / len(rows)

        you, model = rate(resolved, "outcome"), rate(m_resolved, "model_outcome")
        se = (math.sqrt(max(you * (1 - you), 1e-9) / len(resolved))
              if you is not None and resolved else None)
        agreed = sum(1 for d in taken if d.choice == d.model_direction)

        return {
            "n_setups": len(self.decisions),
            "n_taken": len(taken),
            "n_skipped": len(self.decisions) - len(taken),
            "n_resolved": len(resolved),
            "your_hit_rate": None if you is None else round(you, 4),
            "your_std_error": None if se is None else round(se, 4),
            "model_hit_rate": None if model is None else round(model, 4),
            "predicted": round(1.0 / (1.0 + self.k_target / self.k_stop), 4),
            "your_pnl": round(sum(d.pnl for d in taken), 2),
            "model_pnl": round(sum(d.model_pnl for d in self.decisions), 2),
            "stake": self.stake,
            "agreed_with_model": agreed,
            "verdict": self._verdict(you, se, len(resolved)),
        }

    def _verdict(self, you: float | None, se: float | None, n: int) -> str:
        base = 1.0 / (1.0 + self.k_target / self.k_stop)
        if you is None or n < 20:
            return (f"{n} resolved call{'s' if n != 1 else ''} — too few to say "
                    "anything. Twenty is the floor, and even then the bar is wide.")
        if se and abs(you - base) <= 2 * se:
            return (f"{you * 100:.1f}% against a {base * 100:.1f}% baseline, "
                    f"inside ±{2 * se * 100:.1f}. No evidence your calls beat the "
                    "barrier maths — which is the same answer the model gets.")
        # Every verdict that draws a conclusion states the bar it drew it
        # against, including the unflattering ones. A result reported without
        # its uncertainty is the same mistake whichever way it points.
        bar = f"±{2 * se * 100:.1f}" if se else "no error bar"
        if you > base:
            return (f"{you * 100:.1f}% against a {base * 100:.1f}% baseline "
                    f"({bar}) on {n} calls — outside the bar. Worth repeating on "
                    "a different instrument before believing it.")
        return (f"{you * 100:.1f}% against a {base * 100:.1f}% baseline ({bar}) "
                f"on {n} calls — significantly worse than the barrier maths.")
