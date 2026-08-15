"""Return horizon — *when* you want the thing to resolve.

SONAR runs on two clocks, and a horizon means something different on each:

* **The hourly engine** (``engine.py``) has no horizon to choose. Polymarket's
  "Bitcoin Up or Down" market *is* one hour; that is fixed by the instrument,
  not by us. Horizon does not apply there.
* **The asset screener** (``assets.py``) genuinely spans days to months, and
  that is where a horizon belongs.

What a horizon changes
----------------------
``assets.py`` — selects which momentum window drives the momentum score and
the directional lean (1-day, 5-day, or 20-day), and sets the holding period the
plan is written against.

As with :mod:`sonar.risk`, this shapes *ranking and visibility*. The component
scores themselves are still measurements.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Horizon:
    """A named holding period.

    ``target_hours``    where the timing score peaks
    ``min_hours``       markets resolving sooner than this are dropped
    ``max_hours``       markets resolving later than this are dropped
    ``momentum_days``   lookback window for asset momentum
    ``chart_range``     Yahoo range needed to cover that window
    ``long_horizon``    see below
    ``macro``           whether the macro regime is material at this horizon

    On ``long_horizon``
    -------------------
    The hourly engine can grade itself because outcomes arrive hourly. A
    six-month call produces one data point every six months, so the calibration
    table in ``engine.llm_calibration()`` cannot meaningfully score it — not
    because the read is worse, but because the feedback loop is too slow to
    measure. Reads at these horizons are still logged with a due date; they just
    stay unscored for a long time, and the UI says so rather than showing an
    empty table that looks broken.
    """

    name: str
    label: str
    target_hours: float
    min_hours: float
    max_hours: float
    momentum_days: int
    chart_range: str = "1mo"
    long_horizon: bool = False
    macro: bool = False

    def timing_score(self, hours_left: float) -> float:
        """Score how well a resolution time matches this horizon (0..1).

        Peaks at ``target_hours`` and falls off symmetrically in log-time, so
        "half the horizon" and "twice the horizon" are penalised equally — the
        right shape when the quantity spans hours to months.
        """
        h = max(hours_left, 0.05)
        # log-distance from target, normalised by the width of the band
        dist = abs(math.log(h / self.target_hours))
        width = max(math.log(self.max_hours / self.target_hours),
                    math.log(self.target_hours / max(self.min_hours, 0.05)))
        if width <= 0:
            return 1.0
        return max(0.0, 1.0 - dist / width)

    def contains(self, hours_left: float) -> bool:
        return self.min_hours <= hours_left <= self.max_hours

    def as_dict(self) -> dict:
        return asdict(self)


INTRADAY = Horizon(
    name="intraday",
    label="Intraday (< 24h)",
    target_hours=6.0,
    min_hours=0.25,
    max_hours=24.0,
    momentum_days=1,
    chart_range="1mo",
)

WEEK = Horizon(
    name="week",
    label="This week (1–7d)",
    target_hours=96.0,          # ~4 days
    min_hours=12.0,
    max_hours=192.0,            # 8 days
    momentum_days=5,
    chart_range="1mo",
)

MONTH = Horizon(
    name="month",
    label="This month (1–6w)",
    target_hours=504.0,         # ~3 weeks
    min_hours=96.0,
    max_hours=1440.0,           # 60 days
    momentum_days=20,
    chart_range="3mo",
)

# --- long horizons: what used to be the Oracle agent ---------------------- #
# Same machinery, longer windows, plus the macro regime — which is noise on an
# hourly view and the dominant term on a yearly one.

QUARTER = Horizon(
    name="quarter",
    label="This quarter (2–6m)",
    target_hours=2160.0,        # ~3 months
    min_hours=720.0,            # 30 days
    max_hours=5040.0,           # ~7 months
    momentum_days=60,
    chart_range="1y",
    long_horizon=True,
    macro=True,
)

YEAR = Horizon(
    name="year",
    label="This year (6–18m)",
    target_hours=8760.0,        # 12 months
    min_hours=3600.0,           # ~5 months
    max_hours=17520.0,          # 24 months
    momentum_days=250,
    chart_range="2y",
    long_horizon=True,
    macro=True,
)

HORIZONS = {h.name: h for h in (INTRADAY, WEEK, MONTH, QUARTER, YEAR)}
DEFAULT = WEEK


def get(name: str | None) -> Horizon:
    """Look up a horizon by name, falling back to the one-week default."""
    if not name:
        return DEFAULT
    return HORIZONS.get(str(name).strip().lower(), DEFAULT)
