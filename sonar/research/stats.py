"""The statistics, done the way that makes a negative result trustworthy.

Four things separate a real study from a backtest that flatters itself, and all
four are implemented here rather than assumed.

**1. Use the whole return, not a coin flip.** The earlier work asked "did price
touch the target before the stop" — a binary outcome that throws away most of
what a return contains. The standard cross-sectional measure is the
**information coefficient**: the rank correlation, computed *within each date*,
between a feature and the return that followed. Ranks make it robust to
outliers and comparable across instruments, and dating it removes any common
market move, so a feature is judged only on whether it sorted winners from
losers among the names available that day.

**2. Correct the standard errors for overlap.** Sampling daily but predicting
20 days ahead means consecutive observations share 19 days of future. The IC
series is badly autocorrelated and a naive t-statistic is far too confident.
:func:`newey_west_t` applies the Heteroskedasticity and Autocorrelation
Consistent correction with the Bartlett kernel — the reason a result here can be
believed at all.

**3. Correct for how many things were tried.** Twenty features at p<0.05 yields
one false positive per run, near enough. :func:`benjamini_hochberg` controls the
false discovery *rate* rather than the family-wise error rate, which is the
right trade for exploratory work: it tolerates a known fraction of false leads
instead of demanding near-certainty and finding nothing.

**4. Report an effect size with an interval.** A p-value says "probably not
zero"; the bootstrap interval says *how big*, which is the number that decides
whether anything is worth trading after costs.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation, with ties averaged."""
    n = len(xs)
    if n < 5 or len(ys) != n:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx > 0 and dy > 0 else None


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def newey_west_t(xs: list[float], lags: int | None = None) -> tuple[float, float]:
    """``(t_statistic, hac_standard_error)`` for the mean of ``xs``.

    Overlapping forward windows make the IC series autocorrelated, and ignoring
    that inflates the t-statistic by roughly the square root of the overlap —
    which is exactly how a null result gets published as a discovery.
    """
    n = len(xs)
    if n < 10:
        return 0.0, 0.0
    mean = sum(xs) / n
    dev = [x - mean for x in xs]
    if lags is None:
        lags = max(1, int(round(4 * (n / 100) ** (2 / 9))))   # Newey-West rule
    gamma0 = sum(d * d for d in dev) / n
    var = gamma0
    for L in range(1, min(lags, n - 1) + 1):
        cov = sum(dev[i] * dev[i - L] for i in range(L, n)) / n
        var += 2.0 * (1.0 - L / (lags + 1)) * cov           # Bartlett kernel
    if var <= 0:
        return 0.0, 0.0
    se = math.sqrt(var / n)
    return (mean / se if se > 0 else 0.0), se


def normal_p(t: float) -> float:
    """Two-sided p-value from a normal approximation."""
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2.0))))


def benjamini_hochberg(pvals: list[float], q: float = 0.10) -> list[bool]:
    """Which hypotheses survive at false-discovery rate ``q``.

    Chosen over Bonferroni deliberately: with twenty-odd exploratory features,
    controlling the family-wise error rate would demand p < 0.0025 and reject
    everything including anything real. FDR accepts that one in ten survivors
    may be spurious, which is the honest trade for a screen whose output is
    "worth a second look", not "deploy this".
    """
    n = len(pvals)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvals[i])
    keep = [False] * n
    cutoff = 0
    for rank, idx in enumerate(order, start=1):
        if pvals[idx] <= q * rank / n:
            cutoff = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= cutoff:
            keep[idx] = True
    return keep


def bootstrap_ci(xs: list[float], reps: int = 2000, alpha: float = 0.05,
                 block: int = 10, seed: int = 11) -> tuple[float, float]:
    """Percentile interval from a **moving-block** bootstrap.

    Blocks rather than individual draws, for the same reason the t-statistic
    needs a HAC correction: resampling autocorrelated observations one at a time
    destroys the dependence and returns an interval that is far too narrow.
    """
    n = len(xs)
    if n < 20:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    nblocks = max(1, n // block)
    means = []
    for _ in range(reps):
        sample = []
        for _ in range(nblocks):
            start = rng.randrange(0, n - block + 1)
            sample.extend(xs[start:start + block])
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int(alpha / 2 * reps)]
    hi = means[min(reps - 1, int((1 - alpha / 2) * reps))]
    return lo, hi


@dataclass
class ICResult:
    name: str
    family: str
    expected: int
    n_dates: int
    n_obs: int
    mean_ic: float
    t_stat: float
    p_value: float
    ci_low: float
    ci_high: float
    hit_rate: float          # share of dates with the expected sign
    significant: bool = False        # set after FDR correction

    @property
    def sign_agrees(self) -> bool:
        """Did it come out the way it was pre-registered to?"""
        return self.expected == 0 or (self.mean_ic * self.expected) > 0

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["sign_agrees"] = self.sign_agrees
        return d


def evaluate(name: str, family: str, expected: int,
             ics: list[float], counts: list[int],
             overlap: int) -> ICResult | None:
    """Summarise one feature's IC series into a testable result."""
    ics = [x for x in ics if x is not None and not math.isnan(x)]
    if len(ics) < 30:
        return None
    t, _se = newey_west_t(ics, lags=max(overlap, 5))
    lo, hi = bootstrap_ci(ics)
    ref = expected if expected != 0 else 1
    hits = sum(1 for x in ics if x * ref > 0) / len(ics)
    return ICResult(name=name, family=family, expected=expected,
                    n_dates=len(ics), n_obs=sum(counts),
                    mean_ic=sum(ics) / len(ics), t_stat=t,
                    p_value=normal_p(t), ci_low=lo, ci_high=hi,
                    hit_rate=hits)


def apply_fdr(results: list[ICResult], q: float = 0.10) -> list[ICResult]:
    keep = benjamini_hochberg([r.p_value for r in results], q=q)
    for r, k in zip(results, keep):
        r.significant = k
    return results


def ic_to_sharpe(mean_ic: float, breadth: int) -> float:
    """Grinold's fundamental law: ``IR ≈ IC · sqrt(breadth)``.

    A rough translation from "does it sort" to "would it have been worth
    trading", and a useful reality check — an IC of 0.02 across 100 names is an
    information ratio of about 0.2, which is a real but thin signal, and one
    that transaction costs eat readily.
    """
    return mean_ic * math.sqrt(max(1, breadth))
