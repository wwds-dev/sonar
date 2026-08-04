"""Macro regime — the data layer for long-horizon work.

The short-horizon side of SONAR prices a single hour and settles it against a
real candle. Long-horizon analysis has no such anchor, so the honest thing to
give it is not a prediction but a **regime**: what the rates, curve, volatility
and labour picture actually say right now, measured rather than narrated.

Everything here comes from FRED, keyless, as plain CSV.

    DGS10     10-year Treasury yield
    T10Y2Y    10-year minus 2-year spread — the curve. Negative = inverted,
              historically the most-watched recession signal there is.
    DFF       effective fed funds rate — the policy stance
    VIXCLS    VIX — the market's own forward volatility estimate
    CPIAUCSL  CPI index; year-over-year is computed here
    UNRATE    unemployment rate

Why a cache, and why a long one
-------------------------------
These series update daily at most (``UNRATE`` and ``CPIAUCSL`` are monthly), so
refetching them often buys nothing. FRED also rate-limits bursts — hitting it
seven times in a row gets you timeouts. A six-hour disk cache makes both
problems disappear: roughly four fetches per series per day, well inside any
sane limit, with the last good values still on disk if the network is down.

The regime score is a **transparent heuristic**, scored the same way as the rest
of SONAR: named components, published weights, no black box. It is a
description of conditions, not a forecast, and definitely not advice.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
from dataclasses import asdict, dataclass, field

from . import paths

_UA = {"User-Agent": "sonar/0.4"}       # deliberately minimal; FRED dislikes bursts
_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
_TTL = 6 * 3600.0                        # six hours

SERIES = {
    "DGS10": "10-year Treasury yield",
    "T10Y2Y": "10y–2y spread (yield curve)",
    "DFF": "Fed funds effective rate",
    "VIXCLS": "VIX (implied volatility)",
    "CPIAUCSL": "CPI index",
    "UNRATE": "Unemployment rate",
}


def _cache_path(sid: str):
    return paths.cache_dir() / f"fred_{sid}.json"


def _read_cache(sid: str, ttl: float = _TTL):
    p = _cache_path(sid)
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return None, None
    age = time.time() - d.get("fetched", 0)
    return d.get("rows"), age


def _write_cache(sid: str, rows: list) -> None:
    try:
        paths.cache_dir().mkdir(parents=True, exist_ok=True)
        _cache_path(sid).write_text(json.dumps({"fetched": time.time(), "rows": rows}))
    except OSError:
        pass


def series(sid: str, ttl: float = _TTL) -> list[tuple[str, float]]:
    """``[(date, value), ...]`` for a FRED series, newest last.

    Served from cache when fresh. On a network failure a *stale* cache is
    returned rather than nothing — day-old macro is far more useful than a
    blank panel, and the snapshot reports its own age.
    """
    rows, age = _read_cache(sid)
    if rows is not None and age is not None and age < ttl:
        return [(d, v) for d, v in rows]

    try:
        req = urllib.request.Request(_CSV.format(sid=sid), headers=_UA)
        raw = urllib.request.urlopen(req, timeout=25).read().decode()
        parsed = []
        for r in list(csv.reader(io.StringIO(raw)))[1:]:
            if len(r) > 1 and r[1] not in (".", ""):
                try:
                    parsed.append((r[0], float(r[1])))
                except ValueError:
                    continue
        if parsed:
            _write_cache(sid, parsed)
            return parsed
    except Exception:
        pass

    return [(d, v) for d, v in rows] if rows else []


@dataclass
class MacroSnapshot:
    ten_year: float | None = None
    curve_spread: float | None = None      # T10Y2Y; < 0 is inverted
    fed_funds: float | None = None
    vix: float | None = None
    unemployment: float | None = None
    unemployment_chg_12m: float | None = None
    cpi_yoy: float | None = None
    real_10y: float | None = None          # 10y minus CPI YoY
    regime: str = "unknown"
    comp: dict = field(default_factory=dict)
    rationale: str = ""
    as_of: dict = field(default_factory=dict)
    stale: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _latest(rows):
    return (rows[-1][1], rows[-1][0]) if rows else (None, None)


def _yoy(rows) -> float | None:
    """Year-over-year change for a monthly index series."""
    if len(rows) < 13:
        return None
    now, then = rows[-1][1], rows[-13][1]
    return (now / then - 1) if then else None


def _chg_12m(rows) -> float | None:
    if len(rows) < 13:
        return None
    return rows[-1][1] - rows[-13][1]


def snapshot(ttl: float = _TTL) -> MacroSnapshot:
    """Fetch (or serve cached) macro series and classify the regime."""
    data = {sid: series(sid, ttl) for sid in SERIES}
    s = MacroSnapshot()

    s.ten_year, d1 = _latest(data["DGS10"])
    s.curve_spread, d2 = _latest(data["T10Y2Y"])
    s.fed_funds, d3 = _latest(data["DFF"])
    s.vix, d4 = _latest(data["VIXCLS"])
    s.unemployment, d5 = _latest(data["UNRATE"])
    s.unemployment_chg_12m = _chg_12m(data["UNRATE"])
    s.cpi_yoy = _yoy(data["CPIAUCSL"])
    if s.ten_year is not None and s.cpi_yoy is not None:
        s.real_10y = round(s.ten_year - s.cpi_yoy * 100, 2)

    s.as_of = {"DGS10": d1, "T10Y2Y": d2, "DFF": d3,
               "VIXCLS": d4, "UNRATE": d5}
    s.stale = not any(data.values())

    _classify(s)
    return s


# Component weights for the regime score. Published, like every other score
# in SONAR: 1.0 is maximally risk-on, 0.0 maximally risk-off.
_W = {"curve": .30, "volatility": .30, "policy": .20, "labour": .20}


def _classify(s: MacroSnapshot) -> None:
    comp: dict = {}

    # Curve: inverted is the classic late-cycle warning; steep is expansionary.
    if s.curve_spread is not None:
        comp["curve"] = round(max(0.0, min(1.0, (s.curve_spread + 0.5) / 2.0)), 3)

    # Volatility: VIX under ~15 is calm, over ~30 is stress.
    if s.vix is not None:
        comp["volatility"] = round(max(0.0, min(1.0, (30.0 - s.vix) / 18.0)), 3)

    # Policy: a real 10y yield far above zero is restrictive.
    if s.real_10y is not None:
        comp["policy"] = round(max(0.0, min(1.0, (3.0 - s.real_10y) / 4.0)), 3)

    # Labour: rising unemployment over 12m is late-cycle.
    if s.unemployment_chg_12m is not None:
        comp["labour"] = round(max(0.0, min(1.0, (0.5 - s.unemployment_chg_12m) / 1.5)), 3)

    s.comp = comp
    if not comp:
        s.regime, s.rationale = "unknown", "no macro data available"
        return

    # Reweight across whatever components we actually have.
    total_w = sum(_W[k] for k in comp)
    score = sum(_W[k] * v for k, v in comp.items()) / total_w
    s.comp["score"] = round(score, 3)
    s.regime = ("risk-on" if score > 0.60
                else "risk-off" if score < 0.40
                else "transitional")

    bits = []
    if s.curve_spread is not None:
        bits.append(f"curve {s.curve_spread:+.2f}pp"
                    + (" (inverted)" if s.curve_spread < 0 else ""))
    if s.vix is not None:
        bits.append(f"VIX {s.vix:.1f}")
    if s.real_10y is not None:
        bits.append(f"real 10y {s.real_10y:+.2f}%")
    if s.unemployment is not None:
        bits.append(f"unemployment {s.unemployment:.1f}%"
                    + (f" ({s.unemployment_chg_12m:+.1f}pp y/y)"
                       if s.unemployment_chg_12m is not None else ""))
    s.rationale = "; ".join(bits)


class MacroCache:
    """In-process wrapper so the UI can poll cheaply."""

    def __init__(self, ttl: float = _TTL) -> None:
        self.ttl = ttl
        self._at = 0.0
        self._snap: MacroSnapshot | None = None

    def get(self) -> MacroSnapshot:
        now = time.time()
        if self._snap is None or now - self._at > self.ttl:
            self._snap = snapshot(self.ttl)
            self._at = now
        return self._snap
