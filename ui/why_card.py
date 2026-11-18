"""The "why is this notable" card: pure text from one Screener row.

No Qt, no I/O, no clock, no model call. `build_card` turns one row of the
`/api/assets` payload (plus the board, for ranks) into plain data; the Qt widget
in `ui/app.py` only draws it. Every clause is a number on the row, a rank
computed from the board, or a fixed sentence below (spec
`docs/specs/why-notable-card.md`, W1-W9).

Weights, the news thresholds and the rank keys are read from `sonar.assets`,
never retyped, so the card cannot drift from the score it explains.
"""
from __future__ import annotations

import logging
import math
import time
import types
from dataclasses import dataclass

from sonar import assets as A

log = logging.getLogger(__name__)

# A row this old (seconds) shows the "fetched at" line; the AGE column colours
# use the same two numbers.
AGE_WARN_S = 20 * 60
AGE_BAD_S = 60 * 60

#: Same on every card, and #16's first-run card reuses it verbatim.
FOOTER = (
    "This score counts what was found in news and price data. It does not say "
    "which way the price goes next, or that a trade would make money. In "
    "SONAR's own simulated replay of 25,504 past setups, before costs, big "
    "moves and news spikes showed no clear link to which way prices went; "
    "that test can only rule out large effects.")

ROUNDING_NOTE = "Points are rounded to whole numbers so they add up to the score."

#: Components whose weight has an open research row (W8). One neutral sentence,
#: no measured result. Remove or reword the entry in the change that decides #10.
UNDER_DISPUTE = {
    "volatility": "Whether big swings belong in this score is an open question "
                  "in SONAR's own research (Learn, section 5).",
}

UNAVAILABLE_PART = "Not available for this row."
UNAVAILABLE_ALL = "The parts of this score are not available for this row."

SINGULAR = {"Equity": "share", "Index": "index", "Forex": "currency pair",
            "Crypto": "cryptocurrency", "Commodity": "commodity"}
PLURAL = {"Equity": "shares", "Index": "indices", "Forex": "currency pairs",
          "Crypto": "cryptocurrencies", "Commodity": "commodities"}

#: key -> (plain label, expert label)
LABELS = {"news": ("News", "NEWS"), "momentum": ("Recent move", "MOM"),
          "volatility": ("Swing size", "VOL"), "catalyst": ("Earnings date", "EARN")}

#: Lines sort by points, ties in weight order, largest weight first.
ORDER = tuple(sorted(A._W, key=lambda k: -A._W[k]))


def swing_words(daily_vol: float) -> str:
    """The same number in words. 4.3% a day means nothing to most people; "big
    swings" does, and the number is right there for anyone it does mean
    something to."""
    if daily_vol >= 0.030:
        return "big swings"
    if daily_vol >= 0.015:
        return "medium"
    return "small swings"


@dataclass(frozen=True)
class CardLine:
    key: str
    label: str
    points: "int | float | None"   # None: the part is missing from `comp`
    max: int
    text: str
    expert_detail: "str | None"
    muted: bool


@dataclass(frozen=True)
class Card:
    title: str
    as_of: str
    stale: "str | None"
    stale_level: "str | None"      # "warn" | "bad" | None
    unavailable: "str | None"
    lines: "tuple[CardLine, ...]"
    rounding_note: str
    footer: str


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def displayed_score(confidence: float) -> int:
    """The integer the "Worth a look" cell shows: the one definition of it."""
    return int(f"{confidence:.0f}")


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def max_points(key: str) -> int:
    return round(100 * A._W[key])


def _hhmm(epoch: float) -> str:
    return time.strftime("%H:%M", time.localtime(epoch))


def _rank(value: float, values: list) -> int:
    """Competition rank, descending: 1 + the rows with a strictly larger value."""
    return 1 + sum(1 for v in values if v > value)


def _raw(key: str, row: dict) -> float:
    return A.CROSS_SECTIONAL[key](types.SimpleNamespace(**row))


def _class_rank(key: str, row: dict, board: dict) -> "tuple[int, int]":
    peers = [r for r in board.get("assets", []) if r.get("cls") == row.get("cls")]
    if not peers:
        peers = [row]
    return _rank(_raw(key, row), [_raw(key, r) for r in peers]), len(peers)


def _kind_phrase(rank: int, n: int, noun: str, cls: str, *, of: bool) -> str:
    """"the 5th-largest move of 50 shares", "the largest ...", "the smallest ...",
    "the only share on the board"."""
    if n == 1:
        return f"the only {SINGULAR.get(cls, 'one')} on the board"
    plural = PLURAL.get(cls, "rows")
    if rank == 1:
        rk = f"the largest {noun}"
    elif rank == n:
        rk = f"the smallest {noun}"
    else:
        rk = f"the {ordinal(rank)}-largest {noun}"
    rk = rk.strip()
    return f"{rk} of {n} {plural}" + (" on the board" if of else "")


def _plural_noun(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _age_phrase(hours: float) -> str:
    if hours < 1:
        m = max(1, round(hours * 60))
        return f"{m} minute{'s' if m != 1 else ''}"
    if hours < 48:
        h = round(hours)
        return f"{h} hour{'s' if h != 1 else ''}"
    d = round(hours / 24)
    return f"{d} days"


def _span_phrase(hours: float) -> str:
    if hours < 1:
        return "hour"
    if hours < 48:
        h = math.ceil(hours)
        return "hour" if h == 1 else f"{h} hours"
    return f"{math.ceil(hours / 24)} days"


def _hours_phrase(h: int) -> str:
    return "day" if h == 24 else f"{h} hours"


def _sources(headlines: list) -> str:
    counts: dict = {}
    for h in headlines:
        s = str(h.get("source") or "unknown source")
        counts[s] = counts.get(s, 0) + 1
    return ", ".join(f"{s} ×{c}" if c > 1 else s for s, c in counts.items())


def _level_sentence(lean: str) -> str:
    if lean == "Spike":
        return (f"{A.NEWS_SPIKE_N} or more stories in the last "
                f"{A.NEWS_FRESH_H} hours.")
    if lean == "Elevated":
        return (f"At least one story in the last {A.NEWS_FRESH_H} hours, or "
                f"{A.NEWS_DAY_N} in the last {_hours_phrase(A.NEWS_DAY_H)}.")
    if lean == "Normal":
        return (f"No story in the last {A.NEWS_FRESH_H} hours and fewer than "
                f"{A.NEWS_DAY_N} in the last {_hours_phrase(A.NEWS_DAY_H)}.")
    return ""


# --------------------------------------------------------------------------- #
# points: largest remainder
# --------------------------------------------------------------------------- #
def allocate_points(comp: dict, target: int) -> "dict | None":
    """Whole points per component that sum exactly to `target`.

    Over K = components present in `comp`, plus catalyst (0 when absent).
    Returns None if the formula and the target disagree by more than rounding
    can explain; the caller then shows unrounded points.
    """
    keys = [k for k in ORDER if k in comp or k == "catalyst"]
    exact = {k: 100 * A._W[k] * comp.get(k, 0.0) for k in keys}
    pts = {k: math.floor(exact[k] + 1e-9) for k in keys}
    rem = target - sum(pts.values())
    cands = [k for k in keys if exact[k] - pts[k] > 1e-9]
    if rem < 0 or rem > len(cands):
        return None
    cands.sort(key=lambda k: (-(exact[k] - pts[k]), ORDER.index(k)))
    for k in cands[:rem]:
        pts[k] += 1
    if any(pts[k] > max_points(k) or pts[k] < 0 for k in keys):
        return None
    return pts


# --------------------------------------------------------------------------- #
# the card
# --------------------------------------------------------------------------- #
def _news_text(row: dict) -> str:
    hl = row.get("headlines") or []
    k = len(hl)
    if k == 0:
        return "No matched news."
    noun = _plural_noun(k, "story", "stories")
    srcs = _sources(hl)
    ages = [h["age_h"] for h in hl if h.get("age_h") is not None]
    if not ages:
        return f"{k} matched news {noun}, with no publication time given ({srcs})."
    span = _span_phrase(max(ages))
    sp = "the last hour" if span == "hour" else f"the last {span}"
    base = (f"{k} matched news {noun} in {sp} (newest {_age_phrase(min(ages))} "
            f"before the scan; {srcs}).")
    lvl = _level_sentence(row.get("lean", ""))
    return f"{base} {lvl}".strip()


def _move_text(row: dict, board: dict) -> str:
    cls = row.get("cls", "")
    rank, n = _class_rank("momentum", row, board)
    days = row.get("momentum_days") or board.get("horizon", {}).get("momentum_days", 0)
    mom = row.get("momentum", 0.0)
    verb = "Rose" if mom > 0 else "Fell" if mom < 0 else "Moved"
    where = _kind_phrase(rank, n, "move", cls, of=True)
    out = f"{verb} {abs(mom) * 100:.1f}% over the last {days} days, {where}."
    if n > 1:
        out += " The score partly compares moves within the kind and partly with a fixed size."
    return out + " The size counts, not the direction: a fall scores the same as a rise."


def _swing_text(row: dict, board: dict) -> str:
    cls = row.get("cls", "")
    rank, n = _class_rank("volatility", row, board)
    vol = row.get("volatility", 0.0)
    where = _kind_phrase(rank, n, "", cls, of=False)
    out = (f"SONAR's estimate of its daily swing is about {vol * 100:.1f}% "
           f"({swing_words(vol)}), {where}.")
    if n > 1:
        out += (f" The score partly compares it with other "
                f"{PLURAL.get(cls, 'rows')} and partly with a fixed size.")
    return out


def _earn_text(row: dict, board: dict) -> str:
    cls = row.get("cls", "")
    if cls != "Equity":
        return (f"SONAR only tracks company earnings dates, so "
                f"{PLURAL.get(cls, 'these rows')} never score here.")
    cat = row.get("catalyst") or {}
    if cat.get("label") and cat.get("date"):
        label = str(cat["label"])
        return (f"{label[:1].upper()}{label[1:]} ({cat['date']}): a date on the "
                "calendar, not a forecast.")
    days = row.get("momentum_days") or board.get("horizon", {}).get("momentum_days", 0)
    return f"No earnings date within the next {2 * days} days."


def build_card(row: dict, board: dict, *, plain: bool, age_s: float) -> Card:
    score = displayed_score(row["confidence"])
    allrows = board.get("assets", []) or [row]
    brank = _rank(row["confidence"], [r["confidence"] for r in allrows])
    n = len(allrows)
    profile = (board.get("risk") or {}).get("name", "")
    if plain:
        title = (f"{row.get('name') or row['symbol']} — notability score {score} / 100, "
                 f"ranked {ordinal(brank)} of {n} by this score today "
                 f"(risk filter: {profile})")
    else:
        title = (f"{row['symbol']} — NOTABILITY {score}, ranked {ordinal(brank)} "
                 f"of {n} (risk filter: {profile})")
    gen = board.get("generated", 0)
    as_of = f"As of the {_hhmm(gen)} scan."
    stale = level = None
    if age_s >= AGE_WARN_S:
        fetched = gen - row.get("data_age_s", 0.0)
        stale = (f"The price and news for this row were fetched at {_hhmm(fetched)}; "
                 "every figure here is as of then.")
        level = "bad" if age_s >= AGE_BAD_S else "warn"

    comp = row.get("comp") or {}
    if not comp:
        return Card(title, as_of, stale, level, UNAVAILABLE_ALL, (),
                    "", FOOTER)

    pts = allocate_points(comp, score)
    exact_ok = pts is not None
    if not exact_ok:
        log.warning("why card: points for %s do not add up to %s; showing "
                    "unrounded points", row.get("symbol"), score)
        pts = {k: round(100 * A._W[k] * comp.get(k, 0.0), 1)
               for k in ORDER if k in comp or k == "catalyst"}
    texts = {"momentum": _move_text, "volatility": _swing_text,
             "catalyst": _earn_text}
    lines = []
    for k in ORDER:
        label = LABELS[k][0 if plain else 1]
        mx = max_points(k)
        if k not in pts:                       # defensive: part missing
            lines.append(CardLine(k, label, None, mx, UNAVAILABLE_PART, None, True))
            continue
        text = _news_text(row) if k == "news" else texts[k](row, board)
        if k in UNDER_DISPUTE:
            text += " " + UNDER_DISPUTE[k]
        detail = None
        if not plain:
            c = comp.get(k, 0.0)
            detail = f"{c:.2f} × {A._W[k]:.2f} = {100 * A._W[k] * c:.1f}"
        lines.append(CardLine(k, label, pts[k], mx, text, detail, pts[k] == 0))

    def order_key(ln: CardLine):
        if ln.points is None:
            return (2, 0, 0)
        return (1 if ln.points == 0 else 0, -ln.points, ORDER.index(ln.key))
    lines.sort(key=order_key)
    return Card(title, as_of, stale, level, None, tuple(lines),
                ROUNDING_NOTE if exact_ok else "", FOOTER)
