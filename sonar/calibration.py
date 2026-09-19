"""Does a high score actually win more often?

Every other number in SONAR is a claim. This module is the only thing that
checks them, and it is the difference between a screener and a horoscope.

The method is deliberately dull. Every closed paper position carries the
confidence it was opened on and the probability of profit that was advertised
at the time. Bucket them by score, count how many actually won, and compare:

* **hit rate rising across buckets** — the score carries information.
* **flat** — the score is decoration. It ranks things, but not by anything real.
* **inverted** — the score is worse than useless and should be traded against.

From a measured hit rate we can also invert the barrier maths in
:mod:`sonar.scoring` to recover the **drift** that would produce it, expressed
in horizon-sigmas. That number, and only that number, is allowed to move
``P(profit)`` off its driftless baseline. It is earned, never assumed.

The gate that matters
---------------------
Below :data:`MIN_SAMPLE` closed trades a bucket reports *nothing*. Twelve
resolved positions cannot distinguish skill from a coin, and the temptation to
read a trend into them is exactly how a paper portfolio starts lying. An empty
calibration table is the honest state for a young install, and it says so.
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
    for lo, hi in BUCKETS:
        rows = [p for p in closed
                if p.pnl is not None and lo <= (p.confidence or 0) < hi]
        wins = sum(1 for p in rows if (p.pnl or 0) > 0)
        expected = (sum(p.p_profit for p in rows) / len(rows)) if rows else 0.0
        out.append(Bucket(lo=lo, hi=hi, n=len(rows), wins=wins,
                          expected=expected,
                          pnl=sum(p.pnl or 0.0 for p in rows)))
    return out


def report(closed: list) -> dict:
    """The whole picture: buckets, whether the score ranks, and the edge earned."""
    bs = buckets(closed)
    settled = [p for p in closed if p.pnl is not None]

    overall_hits = sum(1 for p in settled if (p.pnl or 0) > 0)
    overall_rate = overall_hits / len(settled) if settled else None
    advertised = (sum(p.p_profit for p in settled) / len(settled)) if settled else None

    edge = 0.0
    calibrated = False
    if overall_rate is not None and len(settled) >= MIN_SAMPLE:
        edge = implied_edge(overall_rate)
        calibrated = True

    # The ranking question, asked of every position rather than of bucket
    # averages: the rank correlation between the confidence a position was
    # opened on and whether it won. None when every position carried the same
    # score — a real state on a book traded off one setup, not an error.
    ic = None
    if calibrated:
        from .research import stats as _stats
        ic = _stats.spearman(
            [float(p.confidence or 0.0) for p in settled],
            [1.0 if (p.pnl or 0) > 0 else 0.0 for p in settled])

    return {
        "n_settled": len(settled),
        "min_sample": MIN_SAMPLE,
        "buckets": [b.as_dict() for b in bs],
        "overall_hit_rate": overall_rate,
        "advertised_rate": advertised,
        "implied_edge_sigma": round(edge, 4),
        "calibrated": calibrated,
        "score_ic": None if ic is None else round(ic, 4),
        "verdict": _verdict(calibrated, overall_rate, advertised, ic,
                            len(settled)),
    }


def _verdict(calibrated: bool, overall: float | None,
             advertised: float | None, ic: float | None, n: int) -> str:
    if not calibrated:
        return ("Not enough resolved positions yet — no claim either way. "
                f"The score stays unproven until {MIN_SAMPLE} have closed.")
    # The verdict used to demand a strictly rising hit rate across every
    # bucket, which noise almost always breaks even when a real gradient
    # exists — five buckets of twenty each must never wobble once. A rank
    # correlation over the positions themselves asks the same question with
    # all the data and an error bar.
    if ic is not None:
        t = ic * math.sqrt(max(n - 1, 1))
        if t > 2.0:
            return (f"Higher scores have won more often (rank IC {ic:+.2f}, "
                    f"{t:.1f} sigma) — the score is carrying information.")
        if t < -2.0:
            return (f"Hit rate *falls* as the score rises (rank IC {ic:+.2f}, "
                    f"{t:.1f} sigma). The score is worse than useless at "
                    "ranking these setups.")
    if overall is not None and advertised is not None:
        delta = overall - advertised
        if abs(delta) < 0.05:
            return ("Results match the advertised odds almost exactly, which is "
                    "what no edge looks like.")
        return (f'Realised hit rate is {delta*100:+.1f} points against its own '
                "odds, without the score itself showing ranking power yet.")
    return "Insufficient data."
