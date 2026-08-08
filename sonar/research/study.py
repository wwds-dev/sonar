"""Run the study, and split the sample before looking at any of it.

The design is fixed before the data is touched:

* **Hypotheses are pre-registered.** Every feature in the registry carries the
  sign it is expected to have. Recording that in advance is what prevents a
  negative result being reinterpreted as a positive one with the sign reversed.
* **Discovery and holdout are split by time, not at random.** A random split
  would put a Tuesday in training and the Wednesday beside it in test, and the
  overlapping forward windows would leak one into the other. Time splits with a
  gap do not.
* **An embargo sits between them.** The last ``horizon`` days of discovery are
  dropped, so no training row's forward window can reach into the holdout.
* **Two features exist only to fail.** A seeded random number and the raw price
  level. If either survives correction, the pipeline is broken and every other
  number on the page is void — that check runs before the results are read.

The honest expectation is that almost nothing survives. Markets are close to
efficient and two prior studies here found nothing. The value of the apparatus
is that it can tell a real result from a hopeful one, and will say so either
way.
"""

from __future__ import annotations

import datetime as dt
import json

from . import features as feat
from . import panel as panel_mod
from . import stats


def _run_ics(rows, horizon: int) -> list[stats.ICResult]:
    out = []
    for f in feat.REGISTRY:
        ics, counts = [], []
        for _date, xs, ys in panel_mod.cross_sections(rows, f.name):
            ic = stats.spearman(xs, ys)
            if ic is not None:
                ics.append(ic)
                counts.append(len(xs))
        res = stats.evaluate(f.name, f.family, f.expected, ics, counts, horizon)
        if res is not None:
            out.append(res)
    return stats.apply_fdr(out)


def split(rows, embargo: int):
    """Two-thirds discovery, one-third holdout, with a gap between them."""
    dates = sorted({r.date for r in rows})
    if len(dates) < 200:
        return rows, []
    cut = dates[int(len(dates) * 0.67)]
    gap = cut + dt.timedelta(days=int(embargo * 1.5))   # calendar ≈ trading×1.5
    disc = [r for r in rows if r.date <= cut]
    hold = [r for r in rows if r.date > gap]
    return disc, hold


def run(symbols: list[str], horizon: int = 20, rng: str = "5y",
        articles: dict | None = None, progress=None) -> dict:
    rows = panel_mod.build(symbols, horizon=horizon, rng=rng,
                           articles=articles, progress=progress)
    if not rows:
        return {"error": "no data"}

    disc, hold = split(rows, embargo=horizon)
    disc_res = _run_ics(disc, horizon)
    hold_res = {r.name: r for r in _run_ics(hold, horizon)} if hold else {}

    # The canaries decide whether anything else may be read.
    controls = [r for r in disc_res if r.family == "control"]
    broken = [r.name for r in controls if r.significant]

    noise_floor = control_reference(hold_res)
    survivors = []
    for r in disc_res:
        if r.family == "control" or not r.significant or not r.sign_agrees:
            continue
        h = hold_res.get(r.name)
        survivors.append({
            "name": r.name, "family": r.family,
            "discovery_ic": round(r.mean_ic, 5), "discovery_t": round(r.t_stat, 2),
            "holdout_ic": round(h.mean_ic, 5) if h else None,
            "holdout_t": round(h.t_stat, 2) if h else None,
            # Must beat the noise floor measured in the same window, not a
            # textbook threshold — see control_reference().
            "replicated": bool(h and h.mean_ic * r.mean_ic > 0
                               and abs(h.t_stat) > max(1.65, 1.5 * noise_floor)),
            "implied_ir": round(stats.ic_to_sharpe(
                r.mean_ic, int(r.n_obs / max(1, r.n_dates))), 3),
        })

    return {
        "generated": int(dt.datetime.now().timestamp()),
        "horizon_days": horizon,
        "range": rng,
        "n_rows": len(rows),
        "n_features": len(feat.REGISTRY),
        "n_dates": len({r.date for r in rows}),
        "n_symbols": len({r.symbol for r in rows}),
        "discovery_rows": len(disc),
        "holdout_rows": len(hold),
        "pipeline_broken": broken,
        "holdout_noise_floor": round(noise_floor, 2),
        "results": [r.as_dict() for r in disc_res],
        "holdout": {k: v.as_dict() for k, v in hold_res.items()},
        "survivors": survivors,
        "verdict": _verdict(broken, survivors, disc_res),
    }


def control_reference(hold_res: dict) -> float:
    """The largest |t| any *control* reached in the holdout window.

    This turned out to matter more than any correction. In the first run the
    seeded random number — a feature that cannot predict anything, by
    construction — reached t = −1.87 out of sample, while several real features
    sat at +2.4 to +3.4 and looked like discoveries.

    The explanation is that daily cross-sections are correlated with each other,
    so a single holdout window contains far fewer independent observations than
    its date count suggests, and everything drifts together. A candidate that
    cannot clearly beat the noise floor *measured in its own window* has shown
    nothing, whatever its t-statistic says.
    """
    ts = [abs(v.t_stat) for k, v in hold_res.items()
          if v.family == "control"]
    return max(ts) if ts else 0.0


def _verdict(broken, survivors, results) -> str:
    if broken:
        return (f"PIPELINE BROKEN — the control feature(s) {broken} came out "
                "significant. A seeded random number cannot predict returns, so "
                "something is leaking or the correction is wrong. No other "
                "result on this page means anything until that is fixed.")
    tested = len([r for r in results if r.family != "control"])
    if not survivors:
        return (f"No feature survived. {tested} tested, false-discovery rate "
                "controlled at 10%, and nothing cleared it with the sign it was "
                "pre-registered to have. That is the expected result for a "
                "near-efficient market, and it is a real finding rather than a "
                "failed run.")
    rep = [s for s in survivors if s["replicated"]]
    if not rep:
        return (f"{len(survivors)} feature(s) survived discovery but none "
                "replicated out of sample. Almost certainly in-sample luck — "
                "the holdout is the whole reason it was held back.")
    names = ", ".join(s["name"] for s in rep)
    return (f"{len(rep)} feature(s) survived correction AND replicated out of "
            f"sample: {names}. Small, but it is the first thing in this project "
            "to clear that bar — worth pursuing, not yet worth trading.")


def save(result: dict, path) -> None:
    with open(path, "w") as fh:
        json.dump(result, fh, indent=1)
