"""Conditional effects: does anything work *sometimes*?

Every test so far asked whether a feature predicts returns on average, and the
answer was consistently no. But the asset-pricing literature rarely finds
unconditional effects either — what it finds are effects that switch on in
particular states of the world. Momentum is documented to work in calm markets
and crash violently at turning points; the low-volatility anomaly is strongest
when rates are falling. So the honest last question for this feature space is
whether anything hides inside a regime.

Regimes are built from FRED — VIX, the 10y–2y curve, and the direction of
policy rates — and classified **point-in-time**: a date's label uses only data
published on or before it. A trailing median is fine; the full-sample median is
not, and using one would let "this was a high-volatility year" leak backwards
into every date in it.

The statistical cost is real and stated up front. Splitting each feature across
two regimes doubles the number of hypotheses, so the chance of finding a
spurious "it only works when X" rises accordingly. That is exactly how
conditional results get published and then fail to replicate. The defence here
is the same as everywhere else in this package: the controls go through the
identical conditioning, and any interaction that a seeded random number can
match is not a result.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from .. import macro
from . import panel as panel_mod
from . import stats

TRAILING = 252          # one year of trailing context for a point-in-time median


def _as_map(rows: list[tuple[str, float]]) -> list[tuple[dt.date, float]]:
    out = []
    for d, v in rows:
        try:
            out.append((dt.date.fromisoformat(d), float(v)))
        except (ValueError, TypeError):
            continue
    return sorted(out)


def _forward_fill(series: list[tuple[dt.date, float]], dates: list[dt.date]
                  ) -> dict[dt.date, float]:
    """Value most recently *published* on or before each date.

    Forward-filling rather than interpolating matters: interpolation between a
    past and a future observation would smear tomorrow's number into today.
    """
    out, i, last = {}, 0, None
    for d in dates:
        while i < len(series) and series[i][0] <= d:
            last = series[i][1]
            i += 1
        if last is not None:
            out[d] = last
    return out


def _rolling_median_split(values: dict[dt.date, float], dates: list[dt.date],
                          hi: str, lo: str) -> dict[dt.date, str]:
    """Label each date against the median of the *preceding* year only."""
    out, hist = {}, []
    for d in dates:
        v = values.get(d)
        if v is None:
            continue
        if len(hist) >= 60:
            med = sorted(hist[-TRAILING:])[len(hist[-TRAILING:]) // 2]
            out[d] = hi if v > med else lo
        hist.append(v)
    return out


def build(dates: list[dt.date]) -> dict[str, dict[dt.date, str]]:
    """``{regime_name: {date: label}}`` for the dates in the panel."""
    dates = sorted(set(dates))
    out: dict[str, dict[dt.date, str]] = {}

    try:
        vix = _forward_fill(_as_map(macro.series("VIXCLS")), dates)
        out["vix"] = _rolling_median_split(vix, dates, "high_vol", "low_vol")
    except Exception:
        pass

    try:
        curve = _forward_fill(_as_map(macro.series("T10Y2Y")), dates)
        # Zero is a real economic threshold, not a fitted one — an inverted
        # curve is a named state, so no trailing median is needed.
        out["curve"] = {d: ("inverted" if v < 0 else "normal")
                        for d, v in curve.items()}
    except Exception:
        pass

    try:
        dff = _forward_fill(_as_map(macro.series("DFF")), dates)
        labels, hist = {}, []
        for d in dates:
            v = dff.get(d)
            if v is None:
                continue
            if len(hist) >= 63:
                labels[d] = "rates_rising" if v > hist[-63] else "rates_falling"
            hist.append(v)
        out["rates"] = labels
    except Exception:
        pass

    return out


@dataclass
class Interaction:
    feature: str
    regime: str
    a_label: str
    b_label: str
    a_ic: float
    b_ic: float
    a_n: int
    b_n: int
    diff: float
    diff_se: float
    diff_t: float

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        for k in ("a_ic", "b_ic", "diff", "diff_se"):
            d[k] = round(d[k], 5)
        d["diff_t"] = round(d["diff_t"], 2)
        return d


def _ic_by_label(rows, name: str, labels: dict[dt.date, str]
                 ) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for date, group in panel_mod.by_date(rows).items():
        lab = labels.get(date)
        if lab is None:
            continue
        xs, ys = [], []
        for r in group:
            v = r.values.get(name)
            if v is not None:
                xs.append(v)
                ys.append(r.fwd)
        if len(xs) >= 8:
            ic = stats.spearman(xs, ys)
            if ic is not None:
                out.setdefault(lab, []).append(ic)
    return out


def interaction(rows, name: str, regime: str, labels: dict[dt.date, str]
                ) -> Interaction | None:
    """Difference in IC between the two states of one regime.

    The standard error combines both sides' HAC errors, so the overlap in each
    is carried through rather than dropped at the last step.
    """
    by = _ic_by_label(rows, name, labels)
    if len(by) != 2:
        return None
    (la, ia), (lb, ib) = sorted(by.items())
    if len(ia) < 40 or len(ib) < 40:
        return None
    ma, mb = sum(ia) / len(ia), sum(ib) / len(ib)
    _, sea = stats.newey_west_t(ia, lags=20)
    _, seb = stats.newey_west_t(ib, lags=20)
    se = math.sqrt(sea ** 2 + seb ** 2)
    diff = ma - mb
    return Interaction(feature=name, regime=regime, a_label=la, b_label=lb,
                       a_ic=ma, b_ic=mb, a_n=len(ia), b_n=len(ib),
                       diff=diff, diff_se=se,
                       diff_t=(diff / se if se > 0 else 0.0))


def study(rows, features: list[str], controls: list[str]) -> dict:
    """Every feature against every regime, with the controls alongside."""
    labels = build([r.date for r in rows])
    results, control_rows = [], []
    for regime, lab in labels.items():
        for name in features:
            it = interaction(rows, name, regime, lab)
            if it:
                results.append(it)
        for c in controls:
            it = interaction(rows, c, regime, lab)
            if it:
                control_rows.append(it)

    floor = max((abs(c.diff_t) for c in control_rows), default=0.0)
    pvals = [stats.normal_p(r.diff_t) for r in results]
    keep = stats.benjamini_hochberg(pvals, q=0.10)

    survivors = [r.as_dict() | {"p": round(p, 4)}
                 for r, p, k in zip(results, pvals, keep)
                 if k and abs(r.diff_t) > 1.5 * floor]

    return {
        "n_tests": len(results),
        "regimes": {k: sorted({v for v in lab.values()})
                    for k, lab in labels.items()},
        "control_diff_t_floor": round(floor, 2),
        "results": [r.as_dict() | {"p": round(p, 4)}
                    for r, p in zip(results, pvals)],
        "controls": [c.as_dict() for c in control_rows],
        "survivors": survivors,
        "verdict": _verdict(survivors, results, floor, len(control_rows)),
    }


def _verdict(survivors, results, floor: float, n_controls: int) -> str:
    if not results:
        return "No regime had enough data on both sides to compare."
    if not survivors:
        return (f"No conditional effect. {len(results)} feature-by-regime tests, "
                f"FDR-controlled, none beating the {floor:.2f} noise floor that "
                f"{n_controls} control interactions reached under identical "
                "conditioning. Nothing in this feature space works even "
                "sometimes.")
    names = ", ".join(f'{s["feature"]}×{s["regime"]}' for s in survivors)
    return (f"{len(survivors)} conditional effect(s) survived FDR and beat the "
            f"control floor: {names}. Conditioning doubles the hypothesis count, "
            "so this needs replication in separate periods before it is believed.")
