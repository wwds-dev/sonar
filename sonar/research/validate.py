"""Three ways to kill a lead, and the noise floor measured beside each one.

A single holdout produced ``dist_52w_high`` at t = +3.39 and looked like a
discovery — until the seeded random control in the same window reached −1.87.
One window cannot tell a signal from a regime, because daily cross-sections are
correlated and everything in a period drifts together.

So a candidate now has to pass three independent tests, each of which a real
effect should pass and a lucky one should not:

**Consistency across blocks.** Split the history into non-overlapping periods
and compute the IC in each. A genuine cross-sectional effect shows up in most
of them; a lucky one lives in one or two. Scored with a sign test, which asks
only "how many blocks went the right way" and is therefore immune to a single
enormous block.

**Decay across horizons.** A real signal fades smoothly as the forward window
lengthens, because information is used up. Noise has no reason to be orderly:
it jumps around, changes sign, or peaks at whatever horizon it was found at.

**Where it should and should not appear.** The 52-week-high effect is an
*equity* anomaly with a behavioural story — anchoring on a salient reference
price. If it shows up just as strongly in currency pairs, the story is wrong and
what is being measured is something else.

Every test is also run on the controls. A number is only interesting relative to
what a feature that cannot possibly work scored under identical conditions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import panel as panel_mod
from . import stats


def _ic_series(rows, name: str, horizon: int | None = None) -> list[float]:
    """IC per date, optionally against a different forward horizon."""
    out = []
    for date, group in sorted(panel_mod.by_date(rows).items()):
        xs, ys = [], []
        for r in group:
            v = r.values.get(name)
            if v is None:
                continue
            y = r.fwd if horizon is None else r.fwd_h.get(horizon)
            if y is None:
                continue
            xs.append(v)
            ys.append(y)
        if len(xs) >= 8:
            ic = stats.spearman(xs, ys)
            if ic is not None:
                out.append(ic)
    return out


def binomial_p(k: int, n: int, p: float = 0.5) -> float:
    """Two-sided sign-test p-value: ``k`` successes in ``n``."""
    if n == 0:
        return 1.0
    def pmf(i):
        return math.comb(n, i) * p ** i * (1 - p) ** (n - i)
    obs = abs(k - n * p)
    tail = sum(pmf(i) for i in range(n + 1) if abs(i - n * p) >= obs - 1e-12)
    return min(1.0, tail)


@dataclass
class BlockResult:
    name: str
    blocks: list[dict] = field(default_factory=list)
    n_blocks: int = 0
    n_agree: int = 0
    sign_p: float = 1.0
    mean_ic: float = 0.0

    @property
    def consistent(self) -> bool:
        return self.n_blocks >= 4 and self.sign_p < 0.05


def blocked(rows, name: str, n_blocks: int = 6, horizon: int | None = None
            ) -> BlockResult:
    """IC computed independently in ``n_blocks`` consecutive periods."""
    dates = sorted({r.date for r in rows})
    if len(dates) < n_blocks * 30:
        return BlockResult(name=name)
    size = len(dates) // n_blocks
    res = BlockResult(name=name)
    ics_all = []
    for b in range(n_blocks):
        lo = dates[b * size]
        hi = dates[min(len(dates) - 1, (b + 1) * size - 1)]
        chunk = [r for r in rows if lo <= r.date <= hi]
        ics = _ic_series(chunk, name, horizon)
        if len(ics) < 20:
            continue
        m = sum(ics) / len(ics)
        t, _ = stats.newey_west_t(ics, lags=20)
        res.blocks.append({"from": lo.isoformat(), "to": hi.isoformat(),
                           "n_dates": len(ics), "mean_ic": round(m, 5),
                           "t": round(t, 2)})
        ics_all.extend(ics)
    if not res.blocks:
        return res
    res.n_blocks = len(res.blocks)
    res.mean_ic = sum(ics_all) / len(ics_all)
    ref = 1 if res.mean_ic >= 0 else -1
    res.n_agree = sum(1 for b in res.blocks if b["mean_ic"] * ref > 0)
    res.sign_p = binomial_p(res.n_agree, res.n_blocks)
    return res


def decay(rows, name: str, horizons: list[int]) -> list[dict]:
    """IC at each forward horizon — the shape matters more than any one value."""
    out = []
    for h in horizons:
        ics = _ic_series(rows, name, h)
        if len(ics) < 30:
            continue
        m = sum(ics) / len(ics)
        t, _ = stats.newey_west_t(ics, lags=max(h, 5))
        out.append({"horizon": h, "n_dates": len(ics),
                    "mean_ic": round(m, 5), "t": round(t, 2)})
    return out


def monotone_decay(points: list[dict]) -> bool:
    """Does |IC| fall as the horizon lengthens, without changing sign?

    The pattern a used-up information signal makes. Demanding it is strict —
    a real effect can be noisy — but this is being used to *filter* a lead, and
    a lead that fails should stay dead until better evidence arrives.
    """
    if len(points) < 3:
        return False
    signs = {1 if p["mean_ic"] >= 0 else -1 for p in points}
    if len(signs) > 1:
        return False
    mags = [abs(p["mean_ic"]) for p in points]
    return all(a >= b - 1e-9 for a, b in zip(mags, mags[1:]))


def by_class(rows, name: str, horizon: int | None = None) -> list[dict]:
    """IC computed separately within each asset class."""
    classes: dict[str, list] = {}
    for r in rows:
        classes.setdefault(r.cls or "Unknown", []).append(r)
    out = []
    for cls, chunk in sorted(classes.items()):
        ics = _ic_series(chunk, name, horizon)
        if len(ics) < 30:
            continue
        m = sum(ics) / len(ics)
        t, _ = stats.newey_west_t(ics, lags=20)
        out.append({"cls": cls, "n_dates": len(ics), "n_rows": len(chunk),
                    "mean_ic": round(m, 5), "t": round(t, 2)})
    return out


def investigate(rows, name: str, controls: list[str],
                horizons: list[int]) -> dict:
    """Run all three tests on ``name`` and on each control for comparison."""
    blk = blocked(rows, name)
    dec = decay(rows, name, horizons)
    cls = by_class(rows, name)

    ctrl_blocks, ctrl_t = [], []
    for c in controls:
        cb = blocked(rows, c)
        if cb.n_blocks:
            ctrl_blocks.append({"name": c, "n_agree": cb.n_agree,
                                "n_blocks": cb.n_blocks,
                                "sign_p": round(cb.sign_p, 4),
                                "mean_ic": round(cb.mean_ic, 5)})
        ctrl_t += [abs(b["t"]) for b in cb.blocks]

    floor = max(ctrl_t) if ctrl_t else 0.0
    beats_floor = sum(1 for b in blk.blocks if abs(b["t"]) > floor)
    return {
        "feature": name,
        "blocks": blk.blocks,
        "n_blocks": blk.n_blocks,
        "n_agree": blk.n_agree,
        "sign_p": round(blk.sign_p, 4),
        "consistent": blk.consistent,
        "mean_ic": round(blk.mean_ic, 5),
        "decay": dec,
        "decays_monotonically": monotone_decay(dec),
        "by_class": cls,
        "controls": ctrl_blocks,
        "control_block_t_floor": round(floor, 2),
        "blocks_beating_floor": beats_floor,
        "verdict": _verdict(blk, dec, cls, floor, beats_floor),
    }


def _verdict(blk: BlockResult, dec, cls, floor: float, beats: int) -> str:
    if not blk.n_blocks:
        return "Not enough data to split into blocks."
    parts = []
    if blk.consistent:
        parts.append(f"consistent across periods ({blk.n_agree}/{blk.n_blocks} "
                     f"blocks agree, sign-test p={blk.sign_p:.3f})")
    else:
        parts.append(f"NOT consistent ({blk.n_agree}/{blk.n_blocks} blocks, "
                     f"p={blk.sign_p:.3f})")
    parts.append("decays monotonically with horizon"
                 if monotone_decay(dec) else "no orderly decay across horizons")
    parts.append(f"{beats}/{blk.n_blocks} blocks beat the control noise floor "
                 f"(|t|>{floor:.2f})")

    passed = blk.consistent and monotone_decay(dec) and beats >= max(2, blk.n_blocks // 2)
    head = ("SURVIVES all three checks — " if passed
            else "FAILS — ")
    tail = ("worth a purged walk-forward with costs next."
            if passed else
            "the single-window result was period-specific, not a signal.")
    return head + "; ".join(parts) + ". " + tail
