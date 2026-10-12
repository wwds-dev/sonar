"""Randomisation p-values for the backtest's verdict and attribution grades.

The backtest's error bar (Driscoll–Kraay, clustered by entry date) lets a
meaningless direction land outside it more often than its nominal rate: a
direction picked at random for a whole asset class over a stretch of days got a
verdict on about 11% of judged real-bar runs. This module asks a second
question of the same run, and a verdict needs both (docs/adr/0003): does the
run's choice of direction read further from the prediction than directions
picked at random for whole stretches of time?

Two tests, both on clusters the caller builds (``sonar.backtest`` owns the
blocks, this module owns the arithmetic):

* :func:`direction_p` — a direction swap. Each cluster carries the sums of its
  setups as the run took them and as the opposite direction would have gone.
  Every pattern of swapping whole clusters is scored with the cluster-robust t
  of the gap (win − predicted), recomputed under the pattern: the count of
  resolved setups changes when a swap turns a timeout into a resolved setup,
  and nothing assumes a long and a short outcome mirror each other.
* :func:`sign_flip_p` — a sign change of per-cluster scores (a component's
  centred IC products), studentised as Canay, Romano and Shaikh (2017).

Both enumerate every pattern when there are at most :data:`ENUMERATE_MAX`
clusters (the usual case: 8–22 at most judged settings), which gives an exact
p in steps of 1/2^q. Above that they draw :data:`B_DRAWS` patterns from a local
:class:`random.Random` seeded from the run's own content (:func:`content_seed`),
never from the clock, so the same run always gives the same p.

The test is exact in finite samples only for a meaningless direction whose
random draws are nested inside its clusters. For directions that persist across
clusters there is no guarantee; their rate is measured, not promised.

Pure standard library; no ``sonar`` imports and no state. Sums go through
:func:`math.fsum`, so the result does not depend on the order of the rows.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Iterable, Sequence
from itertools import chain, compress, product

# Monte Carlo draws above ENUMERATE_MAX clusters: the Monte Carlo standard
# error of a p near 0.05 is sqrt(0.05 × 0.95 / 12,000) ≈ 0.0020.
B_DRAWS = 11_999
# Enumerate all 2^q patterns up to this many clusters (4,096 patterns).
ENUMERATE_MAX = 12

# One random byte per cluster: the high half of the byte range swaps it.
_SWAP = bytes([0] * 128 + [1] * 128)
_KEEP = bytes([1] * 128 + [0] * 128)

# A variance this small next to its own terms is cancellation, not a reading:
# the t is 0 there (fail closed), as it is for a variance at or below zero.
_V_FLOOR = 1e-12

_SEED_VERSION = "sonar-rand-v1"


def content_seed(label: str, horizon_days: int | None,
                 lines: Iterable[str]) -> int:
    """The seed of a run's Monte Carlo draws, from the run's own content.

    The first 8 bytes of sha256 over ``"sonar-rand-v1|<label>|<h>|"`` and the
    sorted ``lines`` (one per setup, each followed by a newline), read
    big-endian. Sorted, so the row order does not matter; hashlib, so
    ``PYTHONHASHSEED`` does not either.

    The lines include the observed directions, so a run whose directions are
    all swapped gets a different stream. That is harmless in practice: the
    stream is fixed before the reference distribution is drawn, the observed
    pattern is counted once whatever the stream, and the p is exact on the
    enumerated path (q ≤ 12), which uses no stream at all. Above that, a
    stream that depends on the observed directions makes the Monte Carlo p
    approximately, not exactly, valid (code review P3-7)."""
    m = hashlib.sha256(f"{_SEED_VERSION}|{label}|{horizon_days}|".encode())
    for line in sorted(lines):
        m.update(line.encode())
        m.update(b"\n")
    return int.from_bytes(m.digest()[:8], "big")


def _five(s: float, n: float) -> tuple[float, float, float, float, float]:
    """A cluster's gap sum ``s`` and count ``n`` as the five terms the t is
    built from: s, n, s², s·n, n²."""
    return (s, n, s * s, s * n, n * n)


def cluster_t(S: float, N: float, A: float, Bsn: float, C: float) -> float:
    """The cluster-robust t of the mean gap Δ = S/N.

    ``S`` and ``N`` are the sums over clusters of the gap sums and counts;
    ``A``, ``Bsn`` and ``C`` the sums of s², s·n and n², so that
    V = Σ (s_g − n_g·Δ)² = A − 2·Δ·Bsn + Δ²·C and T = Δ·N/√V. T is 0 when
    nothing resolved (N = 0) or V is not positive (fail closed)."""
    if N <= 0:
        return 0.0
    d = S / N
    v = A - 2.0 * d * Bsn + d * d * C
    if v <= _V_FLOOR * (A + d * d * C):
        return 0.0
    return d * N / math.sqrt(v)


def _tails(ge: int, le: int, draws: int, monte_carlo: bool
           ) -> tuple[float, float]:
    """The upper and lower tail shares. Under Monte Carlo the observed
    pattern counts once more, (1 + #)/(1 + B); enumerated, it is already one
    of the 2^q patterns."""
    if monte_carlo:
        return (1 + ge) / (1 + draws), (1 + le) / (1 + draws)
    return ge / draws, le / draws


def direction_p(clusters: Sequence[tuple[tuple[float, float],
                                         tuple[float, float]]],
                seed: int, draws: int = B_DRAWS,
                enumerate_max: int = ENUMERATE_MAX) -> dict:
    """The direction-swap p of a run's gap.

    ``clusters`` holds one ``((s_kept, n_kept), (s_swapped, n_swapped))`` per
    cluster: the sum of win − predicted over its resolved setups and their
    count, as the run took them and with every setup's direction swapped for
    the opposite one (a timeout adds nothing to either sum). The observed t
    is the no-swap pattern's.

    Returns ``p`` (equal-tailed: twice the smaller tail, at most 1), ``p_tail``
    (twice the tail in the direction of the observed gap: the upper one when
    Δ > 0, otherwise the lower one), the tails ``p_hi`` and ``p_lo``, ``q``
    (clusters), ``draws`` (patterns scored: 2^q enumerated, else ``draws``),
    ``method`` (``"enumerate"`` or ``"monte_carlo"``), the observed ``t`` and
    ``delta``. A tie with the observed t counts against the run. With no
    clusters every p is ``None``."""
    q = len(clusters)
    if q == 0:
        return {"p": None, "p_tail": None, "p_hi": None, "p_lo": None,
                "q": 0, "draws": 0, "method": None, "t": None, "delta": None}
    kept = [_five(*k) for k, _s in clusters]
    swapped = [_five(*s) for _k, s in clusters]
    observed = [math.fsum(col) for col in zip(*kept)]
    t0 = cluster_t(*observed)
    delta = observed[0] / observed[1] if observed[1] > 0 else 0.0
    ge = le = 0
    if q <= enumerate_max:
        monte_carlo, n_draws = False, 2 ** q
        for combo in product(*zip(kept, swapped)):
            t = cluster_t(*(math.fsum(col) for col in zip(*combo)))
            ge += t >= t0
            le += t <= t0
    else:
        monte_carlo, n_draws = True, draws
        kept_cols = list(zip(*kept))
        swapped_cols = list(zip(*swapped))
        rng = random.Random(seed)
        for _ in range(draws):
            pick = rng.randbytes(q)
            swap, keep = pick.translate(_SWAP), pick.translate(_KEEP)
            t = cluster_t(*(math.fsum(chain(compress(kc, keep),
                                            compress(sc, swap)))
                            for kc, sc in zip(kept_cols, swapped_cols)))
            ge += t >= t0
            le += t <= t0
    p_hi, p_lo = _tails(ge, le, n_draws, monte_carlo)
    return {"p": min(1.0, 2 * min(p_hi, p_lo)),
            "p_tail": min(1.0, 2 * (p_hi if delta > 0 else p_lo)),
            "p_hi": p_hi, "p_lo": p_lo, "q": q, "draws": n_draws,
            "method": "monte_carlo" if monte_carlo else "enumerate",
            "t": t0, "delta": delta}


def _crs_t(total: float, sq: float, q: int) -> float:
    """The t of the mean of q cluster scores whose sum is ``total`` and sum of
    squares ``sq`` (Canay–Romano–Shaikh's studentised statistic)."""
    m = total / q
    v = (sq - q * m * m) / (q - 1)
    if v <= _V_FLOOR * (sq / (q - 1)):
        return 0.0
    return m / math.sqrt(v / q)


def sign_flip_p(scores: Sequence[float], seed: int, draws: int = B_DRAWS,
                enumerate_max: int = ENUMERATE_MAX) -> dict:
    """The sign-change p of per-cluster ``scores`` summing to a statistic.

    Every pattern of sign changes over whole clusters is scored with the
    studentised t of the scores' mean; the sum of squares does not change
    under a sign change, the mean does. Returns ``p`` (equal-tailed), ``p_hi``,
    ``p_lo``, ``q``, ``draws``, ``method`` and the observed ``t``, as
    :func:`direction_p`. With under two clusters every p is ``None``."""
    q = len(scores)
    if q < 2:
        return {"p": None, "p_hi": None, "p_lo": None, "q": q, "draws": 0,
                "method": None, "t": None}
    pos = tuple(float(x) for x in scores)
    neg = tuple(-x for x in pos)
    sq = math.fsum(x * x for x in pos)
    t0 = _crs_t(math.fsum(pos), sq, q)
    ge = le = 0
    if q <= enumerate_max:
        monte_carlo, n_draws = False, 2 ** q
        for combo in product(*zip(pos, neg)):
            t = _crs_t(math.fsum(combo), sq, q)
            ge += t >= t0
            le += t <= t0
    else:
        monte_carlo, n_draws = True, draws
        rng = random.Random(seed)
        for _ in range(draws):
            pick = rng.randbytes(q)
            t = _crs_t(math.fsum(chain(compress(pos, pick.translate(_KEEP)),
                                       compress(neg, pick.translate(_SWAP)))),
                       sq, q)
            ge += t >= t0
            le += t <= t0
    p_hi, p_lo = _tails(ge, le, n_draws, monte_carlo)
    return {"p": min(1.0, 2 * min(p_hi, p_lo)), "p_hi": p_hi, "p_lo": p_lo,
            "q": q, "draws": n_draws,
            "method": "monte_carlo" if monte_carlo else "enumerate", "t": t0}
