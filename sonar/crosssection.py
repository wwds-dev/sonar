"""Standardising a component within its own asset class.

The defect, measured on a live screen of 129 instruments:

    class       volatility component (median)   median CONF
    Crypto      1.00  — saturated                     23
    Commodity   0.82                                  19
    Equity      0.58                                  13
    Index       0.26                                   8
    Forex       0.14  — never exceeds 0.23             5

The volatility component was not measuring "is this unusually volatile". It was
measuring "is this crypto". Every coin sat pinned at the ceiling and no currency
pair could reach a quarter of it, because the scale — `min(1, vol / 0.03)` — is
an absolute one applied to instruments whose normal volatility differs by an
order of magnitude.

The consequence is a ranking defect, not a cosmetic one: a move that is genuinely
extraordinary *for EUR/USD* scored below a dull day in Dogecoin, so a whole asset
class could not compete for attention however it behaved.

This is the standard institutional construction — the Barra/MSCI pipeline
winsorises, z-scores cross-sectionally, then neutralises — and `CONFIDENCE.md`
§3 has wanted it since the first review. It was blocked until Sep 2026 on class
sizes: a median absolute deviation over the two Commodity members the watchlist
then had is not a standardisation.

**What this does not claim.** It does not create a directional edge, and it is
not expected to. Five studies found none, and rescaling a component cannot
manufacture one. The claim is narrower and checkable: after this, a score means
the same thing in every class.
"""

from __future__ import annotations

import math

#: Scale factor making the median absolute deviation a consistent estimator of
#: the standard deviation for normally distributed data.
MAD_TO_SIGMA = 1.4826

#: Below this many members a class cannot support a cross-sectional statistic,
#: and the absolute score is used unchanged. Two instruments have a median and
#: a deviation; neither means anything.
MIN_CLASS = 8

#: How much of the final component comes from the relative reading. Not 1.0 on
#: purpose: at 1.0 every class is forced to the same distribution, so "nothing
#: is happening anywhere" becomes indistinguishable from "a normal day", and
#: the board would always look equally busy. This keeps the absolute level
#: audible while letting the relative reading do the ranking.
RELATIVE_MIX = 0.6

#: z is clipped before squashing so one extreme member cannot flatten the rest.
Z_CLIP = 3.0


def median(xs: list[float]) -> float:
    ordered = sorted(xs)
    n = len(ordered)
    if not n:
        return 0.0
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def mad(xs: list[float], centre: float | None = None) -> float:
    """Median absolute deviation — robust where a standard deviation is not.

    One instrument having an extraordinary day is the normal case on this
    screen, and it would drag a mean and inflate a standard deviation enough to
    hide everything else.
    """
    if not xs:
        return 0.0
    c = median(xs) if centre is None else centre
    return median([abs(x - c) for x in xs])


def zscore(value: float, sample: list[float]) -> float | None:
    """How unusual `value` is against its own class, in robust sigmas.

    Returns None when the class cannot support the statistic — too few members,
    or every member identical, which is a real state on a quiet day and not an
    error.
    """
    if len(sample) < MIN_CLASS:
        return None
    centre = median(sample)
    spread = mad(sample, centre) * MAD_TO_SIGMA
    if spread <= 0:
        return None
    return max(-Z_CLIP, min(Z_CLIP, (value - centre) / spread))


def squash(z: float) -> float:
    """Map a robust z to [0, 1], with a typical member landing at 0.5."""
    return 1.0 / (1.0 + math.exp(-z))


def standardise(values: dict[str, float], classes: dict[str, str],
                mix: float = RELATIVE_MIX) -> dict[str, float]:
    """Blend each absolute component with its within-class standardised version.

    `values` maps a symbol to its raw component; `classes` maps a symbol to its
    asset class. Symbols in a class too small to standardise keep their absolute
    value, so a thin class degrades to today's behaviour rather than to noise.
    """
    by_class: dict[str, list[float]] = {}
    for symbol, value in values.items():
        by_class.setdefault(classes.get(symbol, ""), []).append(value)

    out: dict[str, float] = {}
    for symbol, value in values.items():
        sample = by_class.get(classes.get(symbol, ""), [])
        z = zscore(value, sample)
        if z is None:
            out[symbol] = value
            continue
        out[symbol] = (1.0 - mix) * value + mix * squash(z)
    return out


def spread_across(groups: dict[str, list[float]]) -> float:
    """How far apart the class medians are — the number this exists to shrink.

    Zero would mean every class sits at the same typical level, which is the
    property being aimed at: a score that means the same thing everywhere.
    """
    medians = [median(v) for v in groups.values() if v]
    return max(medians) - min(medians) if len(medians) > 1 else 0.0


def standardise_raw(raw: dict[str, float], classes: dict[str, str],
                    absolute: dict[str, float],
                    mix: float = RELATIVE_MIX) -> dict[str, float]:
    """Standardise the *unclipped* quantity, then blend with the clipped score.

    The distinction matters more than it looks. `assets` derives each component
    as `min(1, x / scale)`, which pins most of Crypto to exactly 1.0 — so
    standardising the component gives a within-class deviation of zero and
    changes nothing for the very class that needed it most. Feeding the raw
    `x` in instead is what makes the class's own spread visible.

    `absolute` is still blended in, so a quiet day everywhere still scores lower
    than a busy one rather than every class being forced to look equally active.
    """
    by_class: dict[str, list[float]] = {}
    for symbol, value in raw.items():
        by_class.setdefault(classes.get(symbol, ""), []).append(value)

    out: dict[str, float] = {}
    for symbol, value in raw.items():
        z = zscore(value, by_class.get(classes.get(symbol, ""), []))
        base = absolute.get(symbol, 0.0)
        out[symbol] = base if z is None else (1.0 - mix) * base + mix * squash(z)
    return out
