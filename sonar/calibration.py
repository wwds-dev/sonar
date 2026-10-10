"""Does a high score actually win more often?

Every other number in SONAR is a claim. This module is the only thing that
checks them, and it is the difference between a screener and a horoscope.

The method is deliberately dull. Every closed paper position carries the
confidence it was opened on and the probability of profit that was advertised
at the time. Bucket them by score, count how many actually won, and compare:

* **hit rate rising across buckets** — the score carries information.
* **flat** — the score is decoration. It ranks things, but not by anything real.
* **inverted** — the score is worse than useless and should be traded against.

It is a report, never an input. It used to invert the barrier maths into a
"drift" and move every row's ``P(profit)`` with it once twenty positions had
closed. Removed (owner decision, 2026-10-10) after an independent validation
(``docs/audit/model-validation.md``, ``docs/specs/t1-1-calibration-gate.md``):
protocol entries take a coin-flip direction, so a pooled hit rate above the
baseline reflects barrier and jump geometry — a driftless walk watched at
discrete marks already lands at 40.6–41.3% — not a drift a LONG plan could
use; and a gate re-checked after every close trips on a book with no edge
23–37% of the time. :func:`implied_edge` stays for the backtest's readout.

The gates that matter
---------------------
Below :data:`MIN_SAMPLE` graded trades a bucket reports *nothing*. Twelve
resolved positions cannot distinguish skill from a coin, and the temptation to
read a trend into them is exactly how a paper portfolio starts lying. An empty
calibration table is the honest state for a young install, and it says so.

Twenty is enough to *describe* the book. Saying it beat its odds takes a
hit rate whose interval at three standard errors (:data:`Z_CLAIM`) leaves out
the odds the plans advertised — three, not two, because the question is asked
again after every close, and at two a book with no edge eventually "beats its
odds" a quarter to a third of the time.

Only positions that reached a barrier are graded. ``P(profit)`` is the chance
of touching the target before the stop; a position closed by hand while in
profit never touched its target, and counting it as a win (it used to be, on
the sign of its P&L) graded the score on something it does not claim.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import scoring

# Below this, a bucket reports "insufficient data" rather than a hit rate.
# Not a statistical bound so much as a decency threshold: at n=20 the standard
# error on a coin flip is still ~11 points, and the UI says as much.
MIN_SAMPLE = 20

BUCKETS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
GRADED = ("TARGET", "STOP")      # the outcomes P(profit) is a claim about
Z95 = 1.96
Z_CLAIM = 3.0         # re-checked after every close: see the module docstring


def wilson(hits: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """The Wilson score interval for a hit rate: honest at small n and near
    0 or 1, where the plain ±z·se interval spills outside [0, 1]."""
    if n <= 0:
        return None
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = (z / (1 + z * z / n)) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def graded(closed: list) -> list:
    """Positions that reached a barrier — the only ones P(profit) predicts."""
    return [p for p in closed if p.pnl is not None and p.outcome in GRADED]


@dataclass
class Bucket:
    lo: int
    hi: int
    n: int
    wins: int
    expected: float          # what the barrier maths advertised, averaged
    pnl: float

    @property
    def enough(self) -> bool:
        return self.n >= MIN_SAMPLE

    @property
    def hit_rate(self) -> float | None:
        return self.wins / self.n if self.n else None

    @property
    def surprise(self) -> float | None:
        """Realised minus advertised. Positive means it beat its own odds."""
        hr = self.hit_rate
        return None if hr is None else hr - self.expected

    def as_dict(self) -> dict:
        return {"lo": self.lo, "hi": self.hi, "n": self.n, "wins": self.wins,
                "hit_rate": self.hit_rate, "expected": round(self.expected, 4),
                "surprise": self.surprise, "pnl": round(self.pnl, 2),
                "enough": self.enough}


def implied_edge(hit_rate: float, k_target: float = scoring.K_TARGET,
                 k_stop: float = scoring.K_STOP) -> float:
    """Recover the drift (in horizon-sigmas) implied by a realised hit rate.

    Inverts :func:`scoring.barrier_probability`. There is no closed form, so
    bisect — the function is monotonic in the drift, which makes that exact
    enough and completely robust.
    """
    baseline = k_stop / (k_target + k_stop)
    if hit_rate <= 0.0:
        return -10.0
    if hit_rate >= 1.0:
        return 10.0
    if abs(hit_rate - baseline) < 1e-9:
        return 0.0
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if scoring.barrier_probability(k_target, k_stop, mid) < hit_rate:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def buckets(closed: list) -> list[Bucket]:
    """Bucket resolved positions by the confidence they were opened on."""
    out = []
    done = graded(closed)
    for lo, hi in BUCKETS:
        rows = [p for p in done if lo <= (p.confidence or 0) < hi]
        wins = sum(1 for p in rows if p.outcome == "TARGET")
        expected = (sum(p.p_profit for p in rows) / len(rows)) if rows else 0.0
        out.append(Bucket(lo=lo, hi=hi, n=len(rows), wins=wins,
                          expected=expected,
                          pnl=sum(p.pnl or 0.0 for p in rows)))
    return out


def report(closed: list) -> dict:
    """The whole picture: buckets, whether the score ranks, and the edge earned."""
    bs = buckets(closed)
    settled = graded(closed)
    n_manual = sum(1 for p in closed if p.pnl is not None and p.outcome not in GRADED)

    overall_hits = sum(1 for p in settled if p.outcome == "TARGET")
    overall_rate = overall_hits / len(settled) if settled else None
    advertised = (sum(p.p_profit for p in settled) / len(settled)) if settled else None
    interval = wilson(overall_hits, len(settled))           # shown: the 95% range
    strict = wilson(overall_hits, len(settled), Z_CLAIM)    # what a claim needs

    enough = len(settled) >= MIN_SAMPLE
    beyond_noise = bool(enough and strict and advertised is not None
                        and not strict[0] <= advertised <= strict[1])

    # The ranking question, asked of every position rather than of bucket
    # averages: the rank correlation between the confidence a position was
    # opened on and whether it won. None when every position carried the same
    # score — a real state on a book traded off one setup, not an error.
    ic = None
    if enough:
        from .research import stats as _stats
        ic = _stats.spearman(
            [float(p.confidence or 0.0) for p in settled],
            [1.0 if p.outcome == "TARGET" else 0.0 for p in settled])

    return {
        "n_settled": len(settled),
        "n_manual": n_manual,
        "min_sample": MIN_SAMPLE,
        "enough": enough,
        "hit_rate_ci": None if interval is None else [round(v, 4) for v in interval],
        "buckets": [b.as_dict() for b in bs],
        "overall_hit_rate": overall_rate,
        "advertised_rate": advertised,
        "beyond_noise": beyond_noise,
        "score_ic": None if ic is None else round(ic, 4),
        "verdict": _verdict(enough, overall_rate, advertised, ic,
                            len(settled), interval, beyond_noise),
    }


def _verdict(enough: bool, overall: float | None,
             advertised: float | None, ic: float | None, n: int,
             interval: tuple[float, float] | None = None,
             beyond_noise: bool = False) -> str:
    if not enough:
        return ("Not enough resolved positions yet — no claim either way. "
                f"The score stays unproven until {MIN_SAMPLE} have closed.")
    # The verdict used to demand a strictly rising hit rate across every
    # bucket, which noise almost always breaks even when a real gradient
    # exists — five buckets of twenty each must never wobble once. A rank
    # correlation over the positions themselves asks the same question with
    # all the data and an error bar.
    if ic is not None:
        t = ic * math.sqrt(max(n - 1, 1))
        if t > Z_CLAIM:
            return (f"Higher scores have won more often (rank IC {ic:+.2f}, "
                    f"{t:.1f} sigma) — the score is carrying information.")
        if t < -Z_CLAIM:
            return (f"Hit rate *falls* as the score rises (rank IC {ic:+.2f}, "
                    f"{t:.1f} sigma). The score is worse than useless at "
                    "ranking these setups.")
    if overall is not None and advertised is not None:
        delta = overall - advertised
        if abs(delta) < 0.05:
            return ("Results match the advertised odds almost exactly, which is "
                    "what no edge looks like.")
        if not beyond_noise and interval is not None:
            return (f"Realised hit rate is {delta*100:+.1f} points against its own "
                    f"odds, but the 95% range ({interval[0]*100:.0f}–{interval[1]*100:.0f}%) "
                    f"still includes the {advertised*100:.0f}% promised — within noise.")
        return (f'Realised hit rate is {delta*100:+.1f} points against its own '
                "odds, outside the noise, without the score itself showing "
                "ranking power yet.")
    return "Insufficient data."
