"""Risk, reward, and an honest probability of profit.

The confidence score answers "is this worth looking at". It deliberately does
not answer the question people actually want answered, which is "will I make
money". This module answers that one — and the answer is more interesting than
a number, because the maths says something uncomfortable and true.

The setup
---------
Pick a **target** and a **stop** scaled to how much the thing actually moves.
With ``sigma_h`` the expected move over your horizon, put the target at
``k_target * sigma_h`` and the stop at ``k_stop * sigma_h``. Then

    reward:risk  =  k_target / k_stop

Now ask: what is the chance price touches the target before the stop? For a
driftless random walk that is the gambler's-ruin result — the probability of
reaching ``+a`` before ``-b`` is ``b / (a + b)``. So

    P(profit)  =  k_stop / (k_target + k_stop)  =  1 / (1 + R:R)

**Risk:reward and probability of profit are the same number wearing different
clothes.** Doubling your target does not make you money, it just halves how
often you get paid. Multiply it out and the expected value is exactly zero:

    EV = P·target − (1−P)·stop
       = [b/(a+b)]·a − [a/(a+b)]·b
       = 0

That zero is the whole point. No arrangement of targets and stops creates
profit. Only **drift** — a real edge — does. So this module reports EV honestly
as ~0 until an edge has been *measured*, and refuses to invent one.

Drift, once earned
------------------
With drift ``mu`` over the horizon, the barrier probability becomes

    P = (1 − exp(−2·m·k_stop)) / (1 − exp(−2·m·(k_target + k_stop)))

where ``m = mu / sigma_h`` is the edge in sigma units (a Sharpe-like number over
the horizon). At ``m = 0`` this collapses back to ``k_stop/(k_target+k_stop)``,
as it must. ``m`` is only ever supplied by :mod:`sonar.calibration`, from
realised outcomes. Nothing here guesses it.
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass

# Default barrier placement, in units of the horizon's expected move. Slightly
# asymmetric: a target further out than the stop, which is the usual shape of a
# momentum trade — and which the maths immediately taxes with a lower hit rate.
K_TARGET = 1.5
K_STOP = 1.0

# Beyond this, exp() overflows long before the answer changes meaningfully.
_M_CLAMP = 20.0


@dataclass(frozen=True)
class Plan:
    """A concrete, checkable trade plan for one instrument."""

    direction: str            # "LONG" | "SHORT"
    entry: float
    target: float
    stop: float
    sigma_h: float            # expected move over the horizon, in price
    rr: float                 # reward : risk
    p_profit: float           # probability of touching target before stop
    ev_per_unit: float        # expected value per unit risked
    calibrated: bool          # was p_profit shifted by a *measured* edge?
    edge_sigma: float         # m, the drift used (0.0 when uncalibrated)

    @property
    def reward_pct(self) -> float:
        return abs(self.target - self.entry) / self.entry if self.entry else 0.0

    @property
    def risk_pct(self) -> float:
        return abs(self.entry - self.stop) / self.entry if self.entry else 0.0


def barrier_probability(k_target: float, k_stop: float,
                        edge_sigma: float = 0.0) -> float:
    """P(touch target before stop) for a random walk with drift ``edge_sigma``.

    ``edge_sigma`` is drift measured in horizon-sigmas. Zero — the honest
    default — gives the pure gambler's-ruin answer ``k_stop/(k_target+k_stop)``.
    """
    if k_target <= 0 or k_stop <= 0:
        return 0.0
    m = max(-_M_CLAMP, min(_M_CLAMP, edge_sigma))
    if abs(m) < 1e-9:                       # driftless: the clean closed form
        return k_stop / (k_target + k_stop)
    try:
        num = 1.0 - math.exp(-2.0 * m * k_stop)
        den = 1.0 - math.exp(-2.0 * m * (k_target + k_stop))
        if abs(den) < 1e-12:
            return k_stop / (k_target + k_stop)
        p = num / den
    except OverflowError:
        return 1.0 if m > 0 else 0.0
    return max(0.0, min(1.0, p))


# --------------------------------------------------------------------------- #
# The same question with a clock on it
# --------------------------------------------------------------------------- #
# The backtest watches a setup for a limited number of bars, then gives up on
# it. ``barrier_probability`` is the answer with no time limit; a far target
# that has not been reached yet when the window closes is not a loss, it is a
# setup that never resolved — and those are mostly far-target setups, so the
# resolved ones hit their target *less* often than ``1/(1+R:R)``. Comparing a
# resolved hit rate against the untimed figure reads a market with nothing in
# it as a signal that loses (docs/adr/0001).
#
# Units: the walk starts at 0 with unit variance per horizon, the target sits
# at +k_target and the stop at −k_stop, and the window lasts ``horizons``
# horizons. The two-sided first-passage probabilities come from the image
# (method-of-reflections) series, which converges fast at the short windows a
# backtest uses — the eigenfunction series cancels catastrophically there and
# returned negative probabilities at T = 0.004.

_SQRT2 = math.sqrt(2.0)
_LOG_SQRT_2PI = 0.5 * math.log(2.0 * math.pi)


def _log_ncdf(z: float) -> float:
    """log Φ(z), finite far into the lower tail."""
    if z > -30.0:
        return math.log(0.5 * math.erfc(-z / _SQRT2))
    # Mills-ratio expansion: erfc underflows long before the tail is useless.
    return (-0.5 * z * z - math.log(-z) - _LOG_SQRT_2PI
            + math.log1p(-1.0 / (z * z) + 3.0 / z ** 4))


def _exp_ncdf(a: float, z: float) -> float:
    """e^a · Φ(z) without overflowing either factor."""
    x = a + _log_ncdf(z)
    return math.exp(x) if x > -745.0 else 0.0


def _exit_first_by(x: float, width: float, mu: float, horizons: float) -> float:
    """P(a unit-variance walk with drift ``mu``, started at ``x`` in
    (0, ``width``), leaves through ``width`` before 0, by time ``horizons``).

    Image series for the driftless first-passage density, tilted by Girsanov:
    ``e^{mu(width−x)} Σ_j [G((2j+1)width − x) − G((2j+1)width + x)]`` with
    ``G(d) = e^{−|mu|d} Φ((|mu|T − d)/√T) + e^{|mu|d} Φ((−|mu|T − d)/√T)``.
    """
    rt = math.sqrt(horizons)
    a = abs(mu)
    tilt = mu * (width - x)

    def g(d: float) -> float:
        return (_exp_ncdf(tilt - a * d, (a * horizons - d) / rt)
                + _exp_ncdf(tilt + a * d, (-a * horizons - d) / rt))

    total = 0.0
    for j in range(100_000):
        near = g((2 * j + 1) * width - x)
        total += near - g((2 * j + 1) * width + x)
        if near < 1e-15:
            break
    return total


def barrier_probabilities_within(k_target: float, k_stop: float,
                                 horizons: float,
                                 edge_sigma: float = 0.0) -> tuple[float, float]:
    """``(P(target first by the deadline), P(stop first by the deadline))``.

    ``horizons`` is the window in horizons (bars watched / horizon days). Their
    sum is below one by the chance that neither barrier is touched in time.
    ``horizons=math.inf`` gives the untimed :func:`barrier_probability` split.
    """
    if k_target <= 0 or k_stop <= 0:
        return 0.0, 0.0
    m = max(-_M_CLAMP, min(_M_CLAMP, edge_sigma))
    if math.isinf(horizons):
        p = barrier_probability(k_target, k_stop, m)
        return p, 1.0 - p
    if horizons <= 0:
        return 0.0, 0.0
    return _barrier_probabilities_within(float(k_target), float(k_stop),
                                         float(horizons), float(m))


@functools.lru_cache(maxsize=8192)
def _barrier_probabilities_within(k_target: float, k_stop: float,
                                  horizons: float,
                                  m: float) -> tuple[float, float]:
    width = k_target + k_stop
    p_target = _exit_first_by(k_stop, width, m, horizons)
    p_stop = _exit_first_by(k_target, width, -m, horizons)
    return (max(0.0, min(1.0, p_target)), max(0.0, min(1.0, p_stop)))


def resolved_hit_probability(k_target: float, k_stop: float, horizons: float,
                             edge_sigma: float = 0.0) -> float:
    """P(target first | one of the barriers is touched within ``horizons``).

    The honest baseline for a hit rate counted over resolved setups only.
    At ``horizons=math.inf`` it is :func:`barrier_probability`; at the
    backtest's four-horizon window and 1.5:1 it is 39.46%, not 40%.
    """
    p_t, p_s = barrier_probabilities_within(k_target, k_stop, horizons,
                                            edge_sigma)
    if p_t + p_s <= 0.0:
        # Too short a window for either barrier to register: in the limit the
        # nearer barrier is the one that gets touched.
        if k_target > k_stop:
            return 0.0
        return 1.0 if k_target < k_stop else 0.5
    return p_t / (p_t + p_s)


def expected_value(p_profit: float, k_target: float, k_stop: float) -> float:
    """EV per unit risked. Exactly 0 when ``p_profit`` is the driftless value —
    which is the result worth staring at."""
    if k_stop <= 0:
        return 0.0
    return (p_profit * k_target - (1.0 - p_profit) * k_stop) / k_stop


def horizon_sigma(daily_vol: float, days: int) -> float:
    """Scale a daily volatility to the horizon by root-time."""
    return daily_vol * math.sqrt(max(1, days))


def build_plan(price: float, daily_vol: float, days: int, direction: str,
               k_target: float = K_TARGET, k_stop: float = K_STOP,
               edge_sigma: float = 0.0, calibrated: bool = False) -> Plan:
    """Turn a price and a volatility into a checkable plan.

    Targets and stops are volatility-scaled rather than round numbers: "5% away"
    means something entirely different on gold than on a meme coin, and a plan
    that ignores that is measuring nothing.
    """
    direction = direction.upper()
    sigma_frac = horizon_sigma(daily_vol, days)          # fractional move
    sigma_price = price * sigma_frac
    if direction == "SHORT":
        target = price - k_target * sigma_price
        stop = price + k_stop * sigma_price
    else:
        direction = "LONG"
        target = price + k_target * sigma_price
        stop = price - k_stop * sigma_price

    p = barrier_probability(k_target, k_stop, edge_sigma)
    return Plan(direction=direction, entry=price, target=target, stop=stop,
                sigma_h=sigma_price, rr=k_target / k_stop, p_profit=p,
                ev_per_unit=expected_value(p, k_target, k_stop),
                calibrated=calibrated and abs(edge_sigma) > 1e-9,
                edge_sigma=edge_sigma)


def position_size(bankroll: float, risk_fraction: float, entry: float,
                  stop: float) -> tuple[float, float]:
    """Size so that being stopped out costs a fixed slice of the bankroll.

    Returns ``(units, cash_at_risk)``. This is risk-based sizing rather than
    "spend 8% of the account": two instruments with different volatility get
    different position sizes for the same *loss* if the stop is hit, which is
    the only sizing rule that treats them comparably.
    """
    risk_per_unit = abs(entry - stop)
    if risk_per_unit <= 0 or entry <= 0:
        return 0.0, 0.0
    cash_at_risk = max(0.0, bankroll * risk_fraction)
    units = cash_at_risk / risk_per_unit
    return units, cash_at_risk


def grade(p_profit: float, rr: float, calibrated: bool) -> str:
    """A short, deliberately unexciting label.

    Without a measured edge every setup is "even" by construction, and saying so
    is more useful than inventing a spread of grades from a coin flip.
    """
    if not calibrated:
        return "unproven"
    ev = expected_value(p_profit, rr, 1.0)
    if ev > 0.25:
        return "favourable"
    if ev > 0.05:
        return "slight edge"
    if ev < -0.05:
        return "negative"
    return "even"
