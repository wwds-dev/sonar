"""The probability model.

The question every hourly market asks is: *will the BTC/USDT 1-hour candle
close at or above its open?* Part-way through the hour we already know the open
``o`` and the current price ``c``; what's uncertain is the move over the time
that's left.

Model that remaining move as a driftless random walk (a geometric Brownian
motion with zero drift — BTC's hourly return is, to a very good approximation, a
martingale). If ``sigma`` is the per-hour volatility of log-returns and ``tau``
is the fraction of the hour still to go, the remaining log-return is
``Normal(0, sigma**2 * tau)``. The candle closes up iff that move exceeds
``ln(o/c)``, so

    P(up) = Phi( ln(c/o) / (sigma * sqrt(tau)) )

That's the whole model. It is a *fair value*, not a crystal ball:

* At the top of the hour (``tau = 1``, ``c = o``) it returns exactly 0.5 — no
  information, no edge.
* As the hour runs out (``tau -> 0``) it collapses to 1 or 0 depending only on
  whether price is currently above or below the open.

Our only disagreement with the market comes from estimating ``sigma`` from
recent *realised* volatility while the market prices in its own *implied*
volatility. When they differ we have a small statistical edge — the same
realised-vs-implied trade quants actually run. It is thin, and over many hours
it is often wrong. The paper P&L is honest about that.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# A floor on remaining time so probabilities stay finite in the final seconds.
_MIN_TAU = 1e-4
# A floor on volatility so a flat vol estimate can't divide-by-zero.
_MIN_SIGMA = 1e-5


def _phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def hourly_sigma(log_returns: list[float], default: float = 0.0045) -> float:
    """Per-hour volatility (std-dev of hourly log-returns).

    ``default`` (~0.45%/hour) is a typical BTC value, used when we don't yet
    have enough samples.
    """
    if len(log_returns) < 5:
        return default
    mean = sum(log_returns) / len(log_returns)
    var = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
    return max(math.sqrt(var), _MIN_SIGMA)


def prob_up(price: float, open_: float, sigma: float, tau: float) -> float:
    """P(candle closes >= open), per the barrier model above."""
    if open_ <= 0 or price <= 0:
        return 0.5
    tau = max(tau, _MIN_TAU)
    sigma = max(sigma, _MIN_SIGMA)
    z = math.log(price / open_) / (sigma * math.sqrt(tau))
    return _phi(z)


@dataclass
class Signal:
    """A model reading for the hour in progress."""

    model_up: float       # our P(up)
    market_up: float      # market P(up) (Polymarket midpoint)
    sigma: float          # per-hour vol used
    tau: float            # fraction of the hour remaining
    edge: float           # model_up - market_up  (>0 => Up looks cheap)

    @property
    def side(self) -> str:
        """Which outcome the model favours vs the market."""
        return "UP" if self.edge >= 0 else "DOWN"

    @property
    def abs_edge(self) -> float:
        return abs(self.edge)


def evaluate(price: float, open_: float, sigma: float, tau: float,
             market_up: float) -> Signal:
    p = prob_up(price, open_, sigma, tau)
    return Signal(model_up=p, market_up=market_up, sigma=sigma, tau=tau,
                  edge=p - market_up)


def lattice_distribution(price: float, open_: float, sigma: float, tau: float,
                         rows: int = 14) -> dict:
    """A small binomial (Galton-board) approximation of the end-of-hour price
    distribution, for the dashboard's probability lattice.

    ``rows`` Bernoulli steps of size ``sigma*sqrt(tau)/sqrt(rows)`` random-walk
    the log-price from ``price`` to the close. Returns per-bin probabilities and
    end prices, plus where the ``open`` barrier falls. Summing the bins at or
    above the open reproduces :func:`prob_up` (to binomial resolution).
    """
    tau = max(tau, _MIN_TAU)
    sigma = max(sigma, _MIN_SIGMA)
    step = sigma * math.sqrt(tau) / math.sqrt(rows)   # per-step log move
    bins = []
    for k in range(rows + 1):                          # k = number of up-steps
        log_move = (2 * k - rows) * step
        end_price = price * math.exp(log_move)
        prob = math.comb(rows, k) / (2 ** rows)        # symmetric binomial
        bins.append({"k": k, "price": round(end_price, 2),
                     "prob": prob, "up": end_price >= open_})
    p_up = sum(b["prob"] for b in bins if b["up"])
    return {"rows": rows, "open": open_, "bins": bins, "p_up": p_up}
