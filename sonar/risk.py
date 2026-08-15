"""Risk tolerance — how much *you* stake, never how something *scores*.

This module exists because SONAR already had a risk appetite; it was just
hardcoded as four constants at the top of :mod:`sonar.engine`. A ``RiskProfile``
names those constants and lets you switch between sensible presets.

The important boundary
----------------------
Risk tolerance and confidence are **orthogonal**, and mixing them would break
both:

* **Confidence** (``assets.py``) measures *the market* — momentum, volatility,
  catalysts, news coverage. It is a property of the world and must read the
  same no matter who is looking at it.
* **Risk tolerance** (this module) measures *you*. It decides how much of the
  bankroll to put behind a given edge, and how picky to be about what is worth
  showing at all.

So a profile is applied strictly *after* scoring. It changes what you **stake**
(``kelly_fraction``, ``max_stake_fraction``, ``edge_threshold``, entry timing)
and what you **see** (the ``max_daily_vol`` filter). It never
mutates a confidence number — if it did, the same market would score
differently for a cautious user than a reckless one, and the score would stop
being a measurement of anything.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RiskProfile:
    """A named set of staking and filtering parameters.

    Sizing (used by the paper engine)
        ``edge_threshold``      only bet when ``|model - market|`` exceeds this
        ``kelly_fraction``      fraction of full Kelly to bet
        ``max_stake_fraction``  hard cap on one hour's stake, as a share of bankroll
        ``enter_tau_min/max``   window of remaining-hour in which entry is allowed

    Filtering (used by the asset screener — visibility only, never scoring)
        ``max_daily_vol``       hide assets whose daily vol exceeds this (fraction)
    """

    name: str
    edge_threshold: float
    kelly_fraction: float
    max_stake_fraction: float
    enter_tau_min: float
    enter_tau_max: float = 0.80
    max_daily_vol: float = float("inf")

    def kelly_stake(self, bankroll: float, model_side_prob: float,
                    price: float) -> float:
        """Capped fractional-Kelly stake for backing a side priced at ``price``
        (0..1) that the model gives ``model_side_prob`` of winning."""
        if price <= 0 or price >= 1:
            return 0.0
        f = (model_side_prob - price) / (1.0 - price)   # full Kelly
        f = max(0.0, f) * self.kelly_fraction
        f = min(f, self.max_stake_fraction)
        return round(bankroll * f, 2)

    def as_dict(self) -> dict:
        d = asdict(self)
        # JSON has no infinity; expose the "no cap" case as null.
        if d["max_daily_vol"] == float("inf"):
            d["max_daily_vol"] = None
        return d


CONSERVATIVE = RiskProfile(
    name="conservative",
    edge_threshold=0.07,        # demand a fat disagreement before acting
    kelly_fraction=0.25,        # quarter-Kelly
    max_stake_fraction=0.03,
    enter_tau_min=0.25,         # leave real time for the thesis to play out
    max_daily_vol=0.04,
)

MODERATE = RiskProfile(
    name="moderate",
    edge_threshold=0.04,        # the original hardcoded defaults
    kelly_fraction=0.5,         # half-Kelly
    max_stake_fraction=0.08,
    enter_tau_min=0.12,
)

AGGRESSIVE = RiskProfile(
    name="aggressive",
    edge_threshold=0.025,
    kelly_fraction=0.75,
    max_stake_fraction=0.15,
    enter_tau_min=0.08,
)

PROFILES = {p.name: p for p in (CONSERVATIVE, MODERATE, AGGRESSIVE)}
DEFAULT = MODERATE


def get(name: str | None) -> RiskProfile:
    """Look up a profile by name, falling back to the moderate default."""
    if not name:
        return DEFAULT
    return PROFILES.get(str(name).strip().lower(), DEFAULT)
