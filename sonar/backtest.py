"""Replay the plan over real history and count what actually happened.

The paper book answers "does the score work" eventually — but at one position
per idea it needs months to say anything. This says it today, by running the
same plan over years of real prices that have already happened.

The method
----------
For each instrument, walk historical days. At each one:

1. Compute momentum and volatility from **prior bars only**. Nothing after the
   decision date is visible — the single rule that separates a backtest from a
   flattering illusion.
2. Take the direction from momentum, exactly as the screener's lean does.
3. Build the same volatility-scaled target and stop as :mod:`sonar.scoring`.
4. Walk forward bar by bar and record which barrier is touched first, using the
   real highs and lows.

Then compare the realised hit rate against what the barrier maths predicts for
a market with nothing in it — **given the setup resolved in time**. A setup
that touches neither barrier inside its hold window is a timeout: it is left
out of the hit rate, counted, and shown. Leaving it out changes the baseline,
because the setups that run out of time are mostly ones a far target had not
reached yet; so each resolved setup is compared with P(target first | resolved
within its own window), which is 39.46% at the shipped 1.5:1, not the untimed
``1/(1+R:R)`` = 40% (docs/adr/0001). A setup decided so near the end of the
data that fewer than two horizons of bars follow it is not compared at all,
only counted: over a window that short the driftless baseline's thin tail
calls a far target nearly unreachable, and real prices, which jump, reach it
far more often. Equal means no edge, and that is the
honest null result. Higher is a reason to look closer. It can also come out
lower, which the code reports too — without reading it as worse than a coin
flip, since a direction picked at random can land that far below as well.

Some runs get the numbers and no verdict. Above a 120-day horizon an
instrument's own trend dominates the comparison, so even a coin-flip direction
can read above the prediction; a single asset class tends to move together on
one trend, so only the whole watchlist is judged; under 100 compared setups, or
setups entered on under 20 different days, there is too little to judge;
setups entered within five horizons of each other are mostly one market move;
and setups that fall in under eight separate stretches of four holding periods,
across every class at once, are too few separate readings
(:data:`MAX_VERDICT_HORIZON`, :data:`WHOLE_WATCHLIST`,
:data:`MIN_VERDICT_TRIALS`, :data:`MIN_VERDICT_DATES`,
:data:`MIN_VERDICT_SPAN_HORIZONS`, :data:`MIN_VERDICT_CLUSTERS`). A run without
a verdict claims no finding on attention or on the score's components either.
The error bar a verdict is read against counts the setups entered on one day,
across instruments, as one reading, and lets it run on through the days their
holds share (:func:`_dk_se`): instruments move together, and momentum points a
whole class the same way at once. A verdict also needs the run's directions to
read further from the prediction than directions picked at random for whole
stretches of time (:func:`_randomisation`, docs/adr/0003); outside the bar
without that, the run is "not told apart from chance".

What this does *not* test
-------------------------
**News and catalysts are absent.** Historical headlines matched to a past date
are not available here, so this exercises the price-based half of the score
only. A real edge could live in the news component and this would never see it;
equally, a flat result here does not clear the news weighting. Said plainly
because a backtest that quietly measures less than it claims is worse than none.

Two more caveats, both deliberately pessimistic:

* **Daily bars hide the path.** If a bar's high reaches the target *and* its low
  reaches the stop, the order is unknowable, so it is scored a **loss**. Real
  intraday data would resolve some of those favourably.
* **No costs.** Spread, slippage and financing are all ignored, and all three
  push results down. Anything that fails to beat the baseline here would fail
  harder in reality.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from . import scoring

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh) sonar/0.4"}
_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
          "?range={rng}&interval=1d")

# Bars of history needed before the first decision can be made.
MIN_LOOKBACK = 30
# Give a position this many horizons to resolve before calling it a timeout.
MAX_HOLD_MULTIPLE = 4
# Compare a setup with the baseline only if the data after it covers at least
# this many horizons. Near the end of a series the window is cut short, and
# over a short window the driftless baseline's Gaussian tail makes a far
# target look nearly unreachable — so on fat-tailed real prices those setups
# read well above it: a coin-flip direction at a 250-day horizon on two years
# of bars, where every window is cut short, read +5.7 points, 4 se
# (docs/audit/qa11-qa13-honest-baselines-model-validator.md, P1-1). Shorter
# windows are counted with the data-end exclusions instead. A full window is
# MAX_HOLD_MULTIPLE horizons, so it is never affected.
MIN_WINDOW_HORIZONS = 2.0

# No verdict above this horizon, in days (owner decision P1-A, 2026-10-11).
# Over holds this long an instrument's own trend dominates the comparison: a
# coin-flip direction on five years of bars read +2 to +3 points above the
# prediction at 210–250 days, 3–4.7 se, because drift helps whichever barrier
# lies with it more than it hurts the other one
# (docs/audit/qa11-qa13-honest-baselines-model-validator-r2.md, P1-A). The
# numbers are still returned and shown.
MAX_VERDICT_HORIZON = 120
# No verdict on fewer compared setups than this, or from fewer distinct entry
# dates (owner decision P1-B). Near the floor's edge a run can compare a few
# dozen setups entered within days of each other — one market move read as
# many — and still land outside its error bar (model-validator r2, P1-B).
MIN_VERDICT_TRIALS = 100
MIN_VERDICT_DATES = 20
# No verdict unless the compared entries span at least this many horizons
# (owner decision, loop 3: the P1-B remainder). Twenty dates can arrive within
# weeks across instruments' calendars — one market move read as many: a
# coin-flip direction read "beats" 9.1% of the time under 2 horizons of entry
# span, 6.1% at 2–5 and 0.9% at 5–10 (model-validator r3, P1-B). The span is
# the calendar days from the first entry date to the last; a horizon counts
# trading days, so it is read against 5 × h × 365/252 calendar days (see
# min_verdict_span_days) — the conversion the validator measured with.
MIN_VERDICT_SPAN_HORIZONS = 5
# Trading days in a calendar year, to read a horizon in trading days against
# calendar entry dates. Crypto trades every day, so for it this asks for more
# calendar days than five of its own horizons: the conservative side.
_TRADING_DAYS_PER_YEAR = 252
# The universe a verdict is given for (owner decision P1-C, loop 3). The
# instruments of one class tend to move together on one trend, so a run over
# a single class is a few correlated moves however many setups it holds: a
# coin-flip direction got "beats the prediction" on 2y Equity, Index and
# Commodity at h ≤ 120, the whole watchlist stayed clean (model-validator r3,
# P1-C). The caller says which universe it ran; it is never inferred.
WHOLE_WATCHLIST = "all"

# The direction randomisation (owner decisions at the Build gate, 2026-10-12;
# docs/adr/0003). A verdict needs Δ outside its error bar *and* the run's
# directions to read further from the prediction than directions swapped for
# the opposite ones over whole stretches of time: one stretch is a block of
# MAX_HOLD_MULTIPLE horizons, in calendar days, across every asset class at
# once, its edges anchored at Unix day 0. With the bar alone, a direction
# picked at random for a whole class over a stretch of days got a verdict on
# 11.4% of 2,040 judged real-bar runs (model-validator r6). The gate can only
# take a verdict away. Under MIN_VERDICT_CLUSTERS stretches the run is
# withheld ("few_clusters"): at 8 the smallest one-sided share is 1/256.
MIN_VERDICT_CLUSTERS = 8
# The gate: the randomisation p in the direction of Δ (twice its tail) must be
# under this, so "beats" alone is a one-sided 2.5% test.
RANDOMISATION_ALPHA = 0.05

# The share of meaningless runs that still get a verdict, as user copy quotes
# it (measure 9). PLACEHOLDER: the model-validator's worst held-out figure
# across measures 1–2 replaces "{measured}", with its date, N, interval and
# withheld share where the Learn tab states the rate. Never a pre-filled
# "1 in 20": if the full-scale run misses 5%, this states what it measured.
CHANCE_VERDICT_RATE = "about 1 run in {measured}"

# What attribution says of every measured component on a run with no verdict.
NOT_JUDGED = ("Not judged: this run gets no verdict, so no component of the "
              "score is graded on it either. The readings are shown as they "
              "came out.")

# Daily bars in a two-year range for a market that trades on weekdays. The
# Terminal's backtest reads two years unless the horizon needs more.
_TWO_YEARS_BARS = 500

_PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
              "en.wikipedia/all-access/user/{art}/daily/{a}/{b}")
_WIKI_UA = {"User-Agent": "sonar-research/0.4 (personal backtest)"}

# Symbol -> English Wikipedia article, used as the historical attention proxy.
# Anything missing here simply gets no attention data and is skipped by the
# news test rather than guessed at.
WIKI_ARTICLE = {
    "AAPL": "Apple_Inc.", "MSFT": "Microsoft", "NVDA": "Nvidia",
    "TSLA": "Tesla,_Inc.", "AMZN": "Amazon_(company)", "GOOGL": "Alphabet_Inc.",
    "META": "Meta_Platforms",
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "BNB-USD": "Binance",
    "XRP-USD": "XRP_Ledger", "SOL-USD": "Solana_(blockchain_platform)",
    "TRX-USD": "Tron_(cryptocurrency)", "DOGE-USD": "Dogecoin",
    "ADA-USD": "Cardano_(blockchain_platform)",
    "AVAX-USD": "Avalanche_(blockchain_platform)",
    "LINK-USD": "Chainlink_(blockchain_oracle)", "XMR-USD": "Monero",
    "GC=F": "Gold", "CL=F": "West_Texas_Intermediate",
    "^GSPC": "S&P_500", "^IXIC": "Nasdaq_Composite",
    "^DJI": "Dow_Jones_Industrial_Average",
    "EURUSD=X": "Euro", "GBPUSD=X": "Pound_sterling", "USDJPY=X": "Japanese_yen",
}

# Days of trailing pageviews used as the "normal" baseline for a spike.
ATTENTION_WINDOW = 30


@dataclass
class Bars:
    """Daily OHLC for one instrument."""

    symbol: str
    time: list[int] = field(default_factory=list)
    open: list[float] = field(default_factory=list)
    high: list[float] = field(default_factory=list)
    low: list[float] = field(default_factory=list)
    close: list[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.close)


def fetch_bars(symbol: str, rng: str = "2y") -> Bars | None:
    """Daily OHLC from Yahoo. Rows with gaps are dropped rather than patched."""
    url = _CHART.format(sym=urllib.parse.quote(symbol), rng=rng)
    try:
        req = urllib.request.Request(url, headers=_UA)
        d = json.loads(urllib.request.urlopen(req, timeout=15).read())
        r = d["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        ts = r["timestamp"]
    except Exception:
        return None
    bars = Bars(symbol=symbol)
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        bars.time.append(t)
        bars.open.append(o)
        bars.high.append(h)
        bars.low.append(l)
        bars.close.append(c)
    return bars if len(bars) > MIN_LOOKBACK else None


def fetch_attention(symbol: str, start: str, end: str,
                    articles: dict | None = None) -> dict[str, int] | None:
    """Daily Wikipedia pageviews for ``symbol``, keyed ``YYYYMMDD``.

    A stand-in for "how much is this in the news today". It is a *proxy*, and
    the difference matters: it measures attention, not coverage by the specific
    outlets SONAR reads, and it carries no tone at all. Wikipedia traffic and
    news volume move together — attention spikes are exactly what the live
    ``coverage`` component is built to detect — but this tests the idea, not
    the implementation.
    """
    art = (articles or {}).get(symbol) or WIKI_ARTICLE.get(symbol)
    if not art:
        return None
    url = _PAGEVIEWS.format(art=urllib.parse.quote(art, safe=""), a=start, b=end)
    for attempt in range(3):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=_WIKI_UA)
            d = json.loads(urllib.request.urlopen(req, timeout=25).read())
            return {i["timestamp"][:8]: i["views"] for i in d.get("items", [])}
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                # Backing off matters more than it looks: a swallowed 429 is
                # indistinguishable from "this symbol has no article", which
                # would quietly turn the entire news test into "untested".
                time.sleep(2.0 * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    return None


_last_wiki_call = 0.0
# Wikimedia asks for considerate request rates and enforces it with 429s.
WIKI_MIN_INTERVAL = 0.35


def _throttle() -> None:
    global _last_wiki_call
    wait = WIKI_MIN_INTERVAL - (time.time() - _last_wiki_call)
    if wait > 0:
        time.sleep(wait)
    _last_wiki_call = time.time()


def attention_z(views: dict[str, int], day: str,
                window: int = ATTENTION_WINDOW) -> float | None:
    """How unusual is today's attention, in standard deviations?

    Compared against the *preceding* ``window`` days only — a spike must be
    detectable on the day, not with hindsight.
    """
    days = sorted(views)
    try:
        i = days.index(day)
    except ValueError:
        return None
    if i < window:
        return None
    past = [views[d] for d in days[i - window:i]]
    mean = sum(past) / len(past)
    var = sum((v - mean) ** 2 for v in past) / (len(past) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return None
    return (views[day] - mean) / sd


def _vol(closes: list[float]) -> float:
    # Only returns between two positive closes: a future can settle at or
    # below zero (CL=F closed at −37.63 on 2020-04-20), and a log return
    # through it does not exist.
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
            if closes[i - 1] > 0 and closes[i] > 0]
    if len(rets) < 3:
        return 0.0
    mean = sum(rets) / len(rets)
    return math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))


def _resolve(bars: Bars, start: int, direction: str, target: float,
             stop: float, max_bars: int) -> tuple[str, int]:
    """Walk forward and report which barrier was touched first.

    A bar that spans both barriers is scored ``STOP``: the intraday order is
    unknowable from daily data, so the unfavourable reading is the honest one.
    """
    for i in range(start + 1, min(start + 1 + max_bars, len(bars))):
        hi, lo = bars.high[i], bars.low[i]
        if direction == "LONG":
            hit_stop, hit_target = lo <= stop, hi >= target
        else:
            hit_stop, hit_target = hi >= stop, lo <= target
        if hit_stop:                      # checked first, deliberately
            return "STOP", i - start
        if hit_target:
            return "TARGET", i - start
    return "TIMEOUT", min(max_bars, len(bars) - start - 1)


def _mom_scale(horizon_days: int) -> float:
    """The saturation point assets.py uses for this horizon."""
    from .assets import _MOM_SCALE
    return _MOM_SCALE.get(horizon_days, 0.10)


def longest_comparable_horizon(n_bars: int, step: int = 1) -> int:
    """The longest horizon at which ``n_bars`` of history can yield even one
    compared setup, or 0 if none can.

    A decision needs one horizon of closes before it (and
    :data:`MIN_LOOKBACK`), sits on run_symbol's ``step`` grid, and is compared
    only with :data:`MIN_WINDOW_HORIZONS` horizons of bars after it — so two
    years of weekday bars stop at about 166 days, one year at about 83."""
    best = 0
    for h in range(1, n_bars):
        # the first decision index at or past h on the step grid
        first = MIN_LOOKBACK + max(0, -(-(h - MIN_LOOKBACK) // step)) * step
        if first >= n_bars - 2 or n_bars - first - 1 < MIN_WINDOW_HORIZONS * h:
            break
        best = h
    return best


def min_verdict_span_days(horizon_days: int) -> int:
    """The calendar days the compared entries must span for a verdict at this
    horizon: :data:`MIN_VERDICT_SPAN_HORIZONS` horizons of trading days,
    converted at 365/252 and rounded up — 37 at 5 days, 870 at 120."""
    need = MIN_VERDICT_SPAN_HORIZONS * horizon_days * 365
    return -(-need // _TRADING_DAYS_PER_YEAR)


# The shortest range whose compared setups fall in at least
# MIN_VERDICT_CLUSTERS stretches, by horizon (assumption A15, owner
# 2026-10-12): from the measured map of stretches per range and horizon
# (momentum, step 3, whole watchlist), judged up to 2y h15, 5y h40 and
# 10y h90, with a margin.
_RANGE_FOR_CLUSTERS = ((10, "2y"), (30, "5y"), (80, "10y"))


def range_for_horizon(horizon_days: int) -> str:
    """The Yahoo range the Terminal's backtest reads at this horizon.

    The shortest of two, five and ten years whose setups fall in enough
    separate stretches for a verdict (:data:`MIN_VERDICT_CLUSTERS`): two
    years up to 10 days, five up to 30, ten up to 80 (A15). Without it the
    20- and 60-day profiles would always be withheld for too few stretches.
    Past 80 days no range gives enough, and the range is the one that
    compares anything at all: two years unless one horizon of history before
    the first entry and :data:`MIN_WINDOW_HORIZONS` after the last, plus the
    lookback, run past two years of bars — then five. The 250-day "This
    year" profile on two years compared nothing (code-review r2, P2-1)."""
    for longest, rng in _RANGE_FOR_CLUSTERS:
        if horizon_days <= longest:
            return rng
    need = MIN_LOOKBACK + (1 + MIN_WINDOW_HORIZONS) * horizon_days
    return "2y" if need <= _TWO_YEARS_BARS else "5y"


def randomisation_block_days(horizon_days: int) -> int:
    """The calendar days of one stretch the direction randomisation swaps as
    a whole: :data:`MAX_HOLD_MULTIPLE` horizons of trading days at 365/252,
    rounded up per horizon — 32 at 5 days, 116 at 20, 348 at 60. A hold
    lasts at most that long, so it reaches at most into the next stretch."""
    return MAX_HOLD_MULTIPLE * math.ceil(horizon_days * 365
                                         / _TRADING_DAYS_PER_YEAR)


def _block_of(t: float, block_days: int) -> int:
    """The stretch a setup entered at ``t`` (seconds, UTC) belongs to: by its
    UTC entry date, edges anchored at Unix day 0, never at the sample."""
    return int(t // 86400) // block_days


def run_symbol(bars: Bars, horizon_days: int, step: int = 3,
               k_target: float = scoring.K_TARGET,
               k_stop: float = scoring.K_STOP,
               attention: dict[str, int] | None = None,
               earnings: list[str] | None = None,
               keep_timeouts: bool = False) -> list[dict]:
    """Every decision point for one instrument.

    ``earnings`` is the symbol's historical earnings dates (ISO strings,
    sorted) from :mod:`sonar.research.earnings`; with it the catalyst
    component is computed exactly as the live screen computes it, so the one
    weight that had never been measured can face attribution.

    Each row's ``predicted`` is P(target first | resolved within this row's
    own window) for a driftless walk — ``window`` is the bars actually watched,
    which the end of the data can cut short (``truncated``). A row whose
    window is under :data:`MIN_WINDOW_HORIZONS` horizons is ``short_window``
    and is not compared, whatever its outcome. By default only the resolved
    rows that are compared are returned. ``keep_timeouts`` also returns the
    rows that are not: those that touched neither barrier in time
    (``outcome: "TIMEOUT"``) and the short-window ones. Both carry
    ``predicted: None`` — so a consumer that forgets to filter them fails
    loudly instead of quietly counting them.

    Every row also says how the opposite direction would have gone from the
    same bar, volatility and window (``opp_outcome``, ``opp_bars_held``, and
    ``opp_predicted``, ``None`` if it timed out): the direction randomisation
    swaps them in (:func:`_randomisation`). The opposite is never a row of
    its own. A short-window row carries ``None`` in all three and is not
    resolved the other way. A caller that forces ``build_plan`` to one side
    forces the opposite plan too, so it must pair the rows itself."""
    from . import events as events_mod
    from .research import earnings as earnings_mod

    out = []
    max_bars = horizon_days * MAX_HOLD_MULTIPLE
    for i in range(MIN_LOOKBACK, len(bars) - 2, step):
        past = bars.close[:i + 1]                   # inclusive of today only
        vol = _vol(past[-30:])
        if vol <= 0:
            continue
        if len(past) <= horizon_days:
            continue
        # No plan at a price at or below zero, and no momentum read off one:
        # the ratio would flip its sign and pick the direction.
        if past[-1] <= 0 or past[-(horizon_days + 1)] <= 0:
            continue
        mom = past[-1] / past[-(horizon_days + 1)] - 1
        if mom == 0:
            continue
        direction = "LONG" if mom > 0 else "SHORT"
        price = past[-1]
        plan = scoring.build_plan(price, vol, horizon_days, direction,
                                  k_target=k_target, k_stop=k_stop)
        outcome, held = _resolve(bars, i, plan.direction, plan.target,
                                 plan.stop, max_bars)
        # The bars this decision could actually be watched for — the same
        # bound _resolve walks. Near the end of the data it is cut short.
        window = min(max_bars, len(bars) - i - 1)
        horizons = window / horizon_days
        # Too little data left to compare with the baseline (see
        # MIN_WINDOW_HORIZONS): counted, never judged, whatever happened.
        short = horizons < MIN_WINDOW_HORIZONS
        if (outcome == "TIMEOUT" or short) and not keep_timeouts:
            continue                                 # not a comparable result
        # The same driftless chance for either direction: the barriers sit
        # at the same distances and the window is the same.
        q_hit = (None if short else
                 scoring.resolved_hit_probability(k_target, k_stop, horizons))
        opp_outcome = opp_held = opp_predicted = None
        if not short:
            opp = scoring.build_plan(
                price, vol, horizon_days,
                "SHORT" if plan.direction == "LONG" else "LONG",
                k_target=k_target, k_stop=k_stop)
            opp_outcome, opp_held = _resolve(bars, i, opp.direction,
                                             opp.target, opp.stop, max_bars)
            opp_predicted = None if opp_outcome == "TIMEOUT" else q_hit
        row = {"symbol": bars.symbol, "t": bars.time[i],
               "direction": plan.direction, "momentum": mom,
               "vol": vol, "outcome": outcome, "bars_held": held,
               "predicted": None if outcome == "TIMEOUT" else q_hit,
               "opp_outcome": opp_outcome, "opp_bars_held": opp_held,
               "opp_predicted": opp_predicted,
               "rr": plan.rr, "k_target": k_target, "k_stop": k_stop,
               "window": window, "horizons": horizons,
               "truncated": window < max_bars, "short_window": short,
               "attention": None,
               # The component scores exactly as assets.py computes them live,
               # so attribution measures the shipped score and not a
               # reconstruction of it that could quietly differ.
               "c_momentum": min(1.0, abs(mom) / _mom_scale(horizon_days)),
               "c_volatility": min(1.0, vol / 0.03),
               "c_news": None, "c_catalyst": None}
        if earnings:
            day = dt.datetime.utcfromtimestamp(bars.time[i]).date()
            away = earnings_mod.days_to_next(earnings, day)
            row["c_catalyst"] = events_mod.catalyst_score(away, horizon_days)
        if attention:
            day = dt.datetime.utcfromtimestamp(bars.time[i]).strftime("%Y%m%d")
            row["attention"] = attention_z(attention, day)
            # Attention z mapped onto the 0-1 shape the live news component has.
            if row["attention"] is not None:
                row["c_news"] = max(0.0, min(1.0, (row["attention"] + 1.0) / 4.0))
        out.append(row)
    return out


def _trial_ks(t: dict, rr: float | None) -> tuple[float, float]:
    """The barrier distances a trial was built with, in horizon-sigmas.

    A hand-built trial without them is read off its ``rr`` (or the fallback)
    with the shipped stop distance, which is what ``build_plan`` would have
    used for that ratio."""
    k_stop = t.get("k_stop") or scoring.K_STOP
    k_target = t.get("k_target")
    if not k_target:
        ratio = t.get("rr") or (rr if rr is not None
                                else scoring.K_TARGET / scoring.K_STOP)
        k_target = ratio * k_stop
    return k_target, k_stop


def _dk_lag_days(avg_bars_held: float) -> int:
    """The Bartlett lag of the date-clustered error bar, in calendar days:
    one average hold, which counts trading days, read at 365/252 and rounded
    up — the conversion the span rule uses. 5 at a 3-bar hold."""
    return math.ceil(avg_bars_held * 365 / _TRADING_DAYS_PER_YEAR)


def _dk_se(trials: list[dict], lag_days: int) -> float:
    """Driscoll–Kraay standard error of the mean hit-rate gap (win −
    predicted), clustered by entry calendar date across every instrument.

    Momentum points a whole class the same way on the same days, so the
    setups entered on one day are one market move read many times, and the
    holds that follow overlap for days after. Each trial's residual — win −
    predicted − the run's gap — is summed per UTC entry date (as the entry
    dates are counted in :func:`summarise`); the daily sums get a Bartlett
    kernel over ``lag_days`` calendar days, days without an entry counting
    as zero. A trial without an entry time is its own cluster. Cost is about
    (days spanned) × ``lag_days``.
    (docs/audit/qa11-qa13-honest-baselines-model-validator-r4.md, P1-D.)"""
    won = [1.0 if t["outcome"] == "TARGET" else 0.0 for t in trials]
    return _dk_mean_se([w - t["predicted"] for w, t in zip(won, trials, strict=True)],
                       [t.get("t") for t in trials], lag_days)


def _dk_mean_se(values: list[float], times: list[float | None],
                lag_days: int) -> float:
    """Driscoll–Kraay standard error of the mean of ``values``, one per
    trial entered at ``times`` (seconds, UTC; ``None`` for no entry time):
    :func:`_dk_se`'s bar for any per-trial reading, centred on its mean."""
    n = len(values)
    mean = sum(values) / n
    return math.sqrt(max(_dk_var([v - mean for v in values], times,
                                 lag_days), 0.0)) / n


def _dk_var(residuals: list[float], times: list[float | None],
            lag_days: int) -> float:
    """The Driscoll–Kraay variance of the sum of per-trial ``residuals``
    (already centred): summed per UTC entry date, Bartlett kernel over
    ``lag_days`` calendar days on a dense day grid, days without an entry
    counting as zero; a trial without an entry time is its own cluster."""
    by_day: dict[int, float] = {}
    var = 0.0
    for r, t in zip(residuals, times, strict=True):
        if t is None:
            var += r * r
        else:
            day = int(t // 86400)
            by_day[day] = by_day.get(day, 0.0) + r
    if by_day:
        first = min(by_day)
        x = [0.0] * (max(by_day) - first + 1)
        for day, s in by_day.items():
            x[day - first] = s
        var += sum(s * s for s in x)
        for lag in range(1, min(lag_days, len(x) - 1) + 1):
            var += (2 * (1 - lag / (lag_days + 1))
                    * sum(a * b for a, b in zip(x, x[lag:], strict=False)))
    return var


def _dk_lag_of(trials: list[dict]) -> int:
    """:func:`_dk_lag_days` at these trials' own average hold."""
    return _dk_lag_days(sum(t.get("bars_held") or 0 for t in trials)
                        / max(len(trials), 1))


def _implied_drift(trials: list[dict], hit: float, predicted: float,
                   rr: float | None) -> float:
    """The drift m (horizon-sigmas per horizon) that makes the time-aware
    prediction equal the realised hit rate.

    Solves (1/n) Σ q(T_i, m) = hit by bisection on [−5, 5]; q rises with m,
    and m = 0 exactly when hit equals the driftless prediction. A trial with
    no ``horizons`` is untimed (T = ∞), which is ``calibration.implied_edge``.
    """
    if abs(hit - predicted) < 1e-12:
        return 0.0
    groups: dict[tuple[float, float, float], int] = {}
    for t in trials:
        k_t, k_s = _trial_ks(t, rr)
        key = (k_t, k_s, t.get("horizons") or math.inf)
        groups[key] = groups.get(key, 0) + 1
    n = len(trials)

    def mean_q(m: float) -> float:
        return sum(c * scoring.resolved_hit_probability(k_t, k_s, T, m)
                   for (k_t, k_s, T), c in groups.items()) / n

    lo, hi = -5.0, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if mean_q(mid) < hit:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def summarise(trials: list[dict], rr: float | None = None, step: int = 1,
              timeouts: list[dict] | tuple = (),
              short_windows: list[dict] | tuple = (),
              horizon_days: int | None = None,
              universe: str | None = None) -> dict:
    """Realised hit rate against what the barrier maths predicted for a
    market with nothing in it, given each setup resolved in its own window.

    ``trials`` are the resolved setups; ``timeouts`` the ones that touched
    neither barrier in time, and ``short_windows`` the ones with under
    :data:`MIN_WINDOW_HORIZONS` horizons of data after them. Both are counted
    and shown but never enter the hit rate. Each trial's own ``rr`` drives the
    expectancy figures; ``rr`` is only a fallback for a hand-built trial
    without one.

    Every number is returned whatever the sample, but there is a verdict only
    at a ``horizon_days`` up to :data:`MAX_VERDICT_HORIZON`, on the
    ``universe`` :data:`WHOLE_WATCHLIST`, on at least
    :data:`MIN_VERDICT_TRIALS` setups entered on at least
    :data:`MIN_VERDICT_DATES` distinct days, counted from each trial's entry
    time ``t`` (UTC; a trial without one counts no date), and when those
    entry dates span at least :func:`min_verdict_span_days`, and when the
    compared setups fall in at least :data:`MIN_VERDICT_CLUSTERS` stretches
    (:func:`randomisation_block_days`). Otherwise ``significant`` is False
    and ``withheld`` says why — ``"horizon"``, ``"single_class"``,
    ``"too_few"``, ``"span"`` or ``"few_clusters"``, the first that applies
    in that order: the two a reader changes by picking another setting come
    before those that depend on the sample. A hand-built sample without a
    ``horizon_days`` or ``universe`` (``None``) is not held to the horizon,
    span or universe rules, and one without a ``universe`` is not held to
    the stretch count or the randomisation either.

    A judged run reads ``verdict_state``: ``"within"`` its error bar;
    ``"beats"`` or ``"below"`` when Δ is outside it (``outside_bar``) and
    the direction randomisation agrees (``randomisation["p_tail"]`` under
    :data:`RANDOMISATION_ALPHA`); ``"unconfirmed"`` when Δ is outside the bar
    and the randomisation does not agree — an internal value, which users
    read as "not told apart from chance". A withheld run reads
    ``"withheld"``. ``significant`` is ``verdict_state`` in beats or below.
    The randomisation needs each compared row's opposite outcome
    (:func:`run_symbol`); a run without them has no stretches and is
    withheld (fail closed)."""
    n_timeout = len(timeouts)
    n_data_end = sum(1 for t in timeouts if t.get("truncated"))
    if not trials:
        # Nothing to compare, but how much ran out of time or data is still
        # the answer to "why nothing": say it rather than drop it. With some
        # setups too near the end of the data, some may well have resolved —
        # they just could not be compared.
        return {"n": 0,
                "verdict": ("nothing to compare" if short_windows else
                            "no resolved trials"),
                "n_timeout": n_timeout, "n_timeout_data_end": n_data_end,
                "n_short_window": len(short_windows),
                "symbols_compared": 0, "compared_by_class": {},
                "n_entry_dates": 0}
    wins = sum(1 for t in trials if t["outcome"] == "TARGET")
    n = len(trials)
    hit = wins / n
    predicted = sum(t["predicted"] for t in trials) / n
    # Standard error on a proportion — the honest error bar on the claim. It
    # is never below the Agresti–Coull standard error at z = 2, the "add two
    # wins and two losses" estimate behind the ~95% interval the two-se
    # verdict uses: the rate it is taken at is never 0 or 1, so a run where
    # every setup was a stop does not read ±0.00. On an ordinary sample the
    # plain binomial bar is the wider one and is what shows.
    p_ac = (wins + 2) / (n + 4)
    se = max(math.sqrt(hit * (1 - hit) / n),
             math.sqrt(p_ac * (1 - p_ac) / (n + 4)))
    # At a step smaller than the holding time, consecutive trials share future
    # bars: a position opened Monday and one opened Thursday can be decided by
    # the same Friday move, so n trials are fewer than n independent readings
    # and the binomial bar above is too tight. The trials list is time-ordered
    # within each symbol, which is what a Newey-West correction needs; the lag
    # covers how many neighbouring trials one holding period spans. Overlap
    # only ever *widens* the bar, so the wider of the two estimates is used.
    avg_held = sum(t["bars_held"] for t in trials) / n
    if n >= 10 and step >= 1:
        from .research import stats as _stats
        lags = max(1, round(avg_held / step))
        _t, se_hac = _stats.newey_west_t(
            [1.0 if t["outcome"] == "TARGET" else 0.0 for t in trials],
            lags=lags)
        se = max(se, se_hac)
    # Neither bar above sees that instruments move together: momentum points
    # a whole class the same way on the same days, so setups entered on one
    # day are one move read many times. A direction that does that and means
    # nothing — one coin per class and horizon-long block — got a verdict on
    # 59% of real-bar runs with the bars above (model-validator r4, P1-D).
    # So the bar is never below the Driscoll–Kraay one, clustered by entry
    # date across instruments with a Bartlett lag of one average hold. On
    # correlated synthetic walks that brings the clustered coin's verdicts
    # from 18.9% to 7.5% of runs: closer to the 4.6% a right 2-se bar gives,
    # not on it — which is why a verdict also needs the direction
    # randomisation below (docs/adr/0003; the rate tests in
    # tests/test_backtest.py).
    lag_days = _dk_lag_days(avg_held)
    se_dk = _dk_se(trials, lag_days)
    se = max(se, se_dk)
    delta = hit - predicted
    edge = _implied_drift(trials, hit, predicted, rr)
    days = sorted({dt.datetime.utcfromtimestamp(t["t"]).date()
                   for t in trials if t.get("t") is not None})
    span_days = (days[-1] - days[0]).days if days else 0
    if horizon_days is not None and horizon_days > MAX_VERDICT_HORIZON:
        withheld = "horizon"
    elif universe is not None and universe != WHOLE_WATCHLIST:
        withheld = "single_class"
    elif n < MIN_VERDICT_TRIALS or len(days) < MIN_VERDICT_DATES:
        withheld = "too_few"
    elif (horizon_days is not None
          and span_days < min_verdict_span_days(horizon_days)):
        withheld = "span"
    else:
        withheld = None
    # The direction randomisation, for a run over a stated universe; a
    # hand-built sample without one is not held to it [A11].
    randomisation = None
    if universe is not None:
        block_days = (randomisation_block_days(horizon_days)
                      if horizon_days else None)
        clusters, lines = _direction_clusters(list(trials) + list(timeouts),
                                              block_days)
        if withheld is None and len(clusters) < MIN_VERDICT_CLUSTERS:
            withheld = "few_clusters"
        randomisation = _randomisation(clusters, lines, horizon_days,
                                       block_days, judged=withheld is None)
    outside_bar = withheld is None and abs(delta) > 2 * se
    if withheld:
        verdict_state = "withheld"
    elif not outside_bar:
        verdict_state = "within"
    elif (randomisation is None
          or randomisation["p_tail"] < RANDOMISATION_ALPHA):
        verdict_state = "beats" if delta > 0 else "below"
    else:
        verdict_state = "unconfirmed"
    significant = verdict_state in ("beats", "below")
    symbols = {t["symbol"] for t in trials if t.get("symbol")}

    # Each trial at its own ratio, not the shipped constant: a run at 3:1
    # pays 3R a win, whatever scoring.K_TARGET says.
    ks = [_trial_ks(t, rr) for t in trials]
    rrs = [k_t / k_s for k_t, k_s in ks]
    won = [1.0 if t["outcome"] == "TARGET" else 0.0 for t in trials]
    expectancy = sum(r if w else -1.0 for r, w in zip(rrs, won)) / n
    # Over resolved setups only, a market with nothing in it scores
    # q·rr − (1−q) per setup, which is negative; this is the part beyond it.
    vs_null = sum((1 + r) * (w - t["predicted"])
                  for r, w, t in zip(rrs, won, trials)) / n
    untimed = sum(k_s / (k_t + k_s) for k_t, k_s in ks) / n

    # The share a driftless walk would leave unresolved. An output field, not
    # a monitor and not diagnostic (owner, 2026-10-11): real prices time out
    # more often than a driftless walk with the baseline still fine. The
    # check on the baseline is the coin-flip placebo (docs/adr/0001).
    expected_timeouts = 0.0
    every = list(trials) + list(timeouts)
    for t in every:
        k_t, k_s = _trial_ks(t, rr)
        p_t, p_s = scoring.barrier_probabilities_within(
            k_t, k_s, t.get("horizons") or math.inf)
        expected_timeouts += 1.0 - p_t - p_s
    return {
        "n": n,
        "wins": wins,
        "hit_rate": round(hit, 4),
        "predicted": round(predicted, 4),
        "baseline_untimed": round(untimed, 4),
        "delta": round(delta, 4),
        "std_error": round(se, 4),
        # The date-clustered bar on its own, and its lag, for the record:
        # std_error is the widest of it, the binomial and the Newey-West.
        "se_dk": round(se_dk, 4),
        "dk_lag_days": lag_days,
        "significant": significant,
        "outside_bar": outside_bar,
        "verdict_state": verdict_state,
        "randomisation": randomisation,
        "implied_edge_sigma": round(edge, 4),
        "expectancy_r": round(expectancy, 4),
        "expectancy_vs_null_r": round(vs_null, 4),
        "n_timeout": n_timeout,
        "n_timeout_data_end": n_data_end,
        "n_short_window": len(short_windows),
        "timeout_share": round(n_timeout / (n + n_timeout), 4),
        "timeout_share_expected": round(expected_timeouts / len(every), 4),
        "avg_bars_held": round(sum(t["bars_held"] for t in trials) / n, 1),
        # What was actually compared: a long horizon can leave one class, and
        # the window floor moves the entries earlier (model-validator r2,
        # P2-A and P2-C).
        "symbols_compared": len(symbols),
        "compared_by_class": _classes(symbols),
        "n_entry_dates": len(days),
        "first_entry": days[0].isoformat() if days else None,
        "last_entry": days[-1].isoformat() if days else None,
        "entry_span_days": span_days,
        "entry_span_horizons": (round(_span_horizons(span_days, horizon_days), 2)
                                if horizon_days else None),
        "withheld": withheld,
        "verdict": (_withheld_verdict(
                        withheld, horizon_days, n, len(days),
                        universe=universe, span_days=span_days,
                        clusters=(randomisation or {}).get("q", 0))
                    if withheld else _verdict(delta, se, verdict_state)),
    }


def _direction_clusters(rows: list[dict], block_days: int | None
                        ) -> tuple[list[tuple[tuple[float, int],
                                              tuple[float, int]]], list[str]]:
    """The compared setups in stretches, as the direction randomisation reads
    them, and one content line per setup for its seed.

    Each stretch (:func:`_block_of`, across every class) carries the sum of
    win − predicted over its resolved setups and their count, as the run took
    them and with each setup's direction swapped for the opposite one
    (``opp_outcome``, ``opp_predicted``); a timeout adds nothing to either.
    The sums go through :func:`math.fsum`, so the row order does not matter.
    A stretch where nothing resolved either way is not counted. A compared
    row without its opposite outcome or an entry time, or a run without a
    stretch length, gives no stretches at all (fail closed): a run that
    cannot be swapped whole is not judged."""
    if not block_days:
        return [], []
    by_block: dict[int, tuple[list[float], list[float]]] = {}
    lines = []
    for t in rows:
        if t.get("short_window"):
            continue
        opp = t.get("opp_outcome")
        if opp is None or t.get("t") is None:
            return [], []
        kept, swapped = by_block.setdefault(_block_of(t["t"], block_days),
                                            ([], []))
        if t["outcome"] != "TIMEOUT":
            kept.append((1.0 if t["outcome"] == "TARGET" else 0.0)
                        - t["predicted"])
        if opp != "TIMEOUT":
            swapped.append((1.0 if opp == "TARGET" else 0.0)
                           - t["opp_predicted"])
        lines.append(f'{t.get("symbol")}|{t["t"]}|{t.get("direction")}|'
                     f'{t["outcome"]}|{opp}')
    clusters = [((math.fsum(k), len(k)), (math.fsum(sw), len(sw)))
                for _b, (k, sw) in sorted(by_block.items()) if k or sw]
    return clusters, lines


def _randomisation(clusters: list, lines: list[str],
                   horizon_days: int | None, block_days: int | None,
                   judged: bool) -> dict:
    """The direction randomisation's reading of a run (docs/adr/0003).

    Every pattern of swapping whole stretches for the opposite directions —
    all 2^q of them up to 12 stretches, else
    :data:`sonar.randomisation.B_DRAWS` drawn from a seed of the run's own
    content — is scored with the stretch-clustered t of the gap, and
    ``p_tail`` is twice the share that reads at least as far as the run in
    the direction of Δ (ties count against the run). ``p`` is the
    equal-tailed p, kept as a field and not shown. Computed only for a
    judged run; a withheld one carries its stretch count ``q`` alone."""
    from . import randomisation as rnd
    out = {"p": None, "p_tail": None, "q": len(clusters), "draws": 0,
           "method": None, "block_days": block_days, "seed": None}
    if judged:
        seed = rnd.content_seed("headline", horizon_days, lines)
        r = rnd.direction_p(clusters, seed)
        out.update(p=r["p"], p_tail=r["p_tail"], draws=r["draws"],
                   method=r["method"], seed=seed)
    return out


def _span_horizons(span_days: int, horizon_days: int) -> float:
    """Calendar days of entry span in horizons of trading days."""
    return span_days * _TRADING_DAYS_PER_YEAR / 365 / horizon_days


def _classes(symbols: set[str]) -> dict[str, int]:
    """How many of ``symbols`` fall in each watchlist class, largest first;
    a symbol off the watchlist counts as ``"other"``."""
    from .assets import WATCHLIST
    cls = {sym: c for sym, _name, c, _kw in WATCHLIST}
    counts: dict[str, int] = {}
    for sym in symbols:
        key = cls.get(sym, "other")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _withheld_verdict(why: str, horizon_days: int | None, n: int,
                      dates: int, *, universe: str | None = None,
                      span_days: int = 0, clusters: int = 0) -> str:
    """Why a run is shown without a verdict. The numbers stay on screen."""
    if why == "few_clusters":
        # Names the fix, as the span sentence does: the stretches are a
        # property of the range and the horizon, which the reader picks.
        stretch = (f" of {randomisation_block_days(horizon_days):,} days"
                   if horizon_days else "")
        return ("Too few separate stretches of time, across asset classes, "
                f"to judge: these setups fall in {clusters} stretch"
                f"{'' if clusters == 1 else 'es'}{stretch} (four holding "
                "periods each, every asset class together), and a verdict "
                f"needs at least {MIN_VERDICT_CLUSTERS}. A longer range or a "
                "shorter horizon gives more.")
    if why == "single_class":
        return (f"No verdict on {universe} alone. The instruments in one class "
                "tend to move together on one trend, so a run over a single "
                "class is shown without a verdict; the whole watchlist gets "
                "one.")
    if why == "span":
        # Rounded down, so a span just short of the bar never reads as on it.
        times = math.floor(_span_horizons(span_days, horizon_days) * 10) / 10
        return (f"Too close together to judge: these setups were entered over "
                f"{span_days:,} days, {times:.1f} times the {horizon_days}-day "
                "horizon. Setups entered close together mostly share one "
                "market move, so a verdict needs them spread over at least "
                f"{MIN_VERDICT_SPAN_HORIZONS} times the horizon "
                f"({min_verdict_span_days(horizon_days):,} days; a horizon "
                "counts trading days). A longer range or a shorter horizon "
                "spreads them out.")
    if why == "horizon":
        return (f"No verdict at a {horizon_days}-day horizon. At horizons this "
                "long an instrument's own trend dominates the comparison — "
                "even a coin-flip direction can read above the prediction — so "
                "the run is shown without a verdict. Horizons up to "
                f"{MAX_VERDICT_HORIZON} days get one.")
    return (f"Too few to judge: {n:,} compared setups from {dates:,} entry "
            f"dates. A verdict needs at least {MIN_VERDICT_TRIALS} from at "
            f"least {MIN_VERDICT_DATES} different dates, so the numbers are "
            "shown without one.")


def _verdict(delta: float, se: float, state: str) -> str:
    """The sentence for a judged run's ``verdict_state``: within, beats,
    below, or unconfirmed — the last worded "not told apart from chance",
    never with its internal name, and never "within"."""
    if state == "within":
        # Not "no edge": a gap inside its bar is not shown, which is not the
        # same as shown to be absent (measure 9).
        return (f"Before costs, the realised hit rate is within "
                f"{2*se*100:.1f} points of the barrier model's prediction: "
                "not shown to differ from the prediction, which is not the "
                "same as no difference. From one replay of past prices.")
    # The bar is the widest of three, and still not a calibrated 2-se test:
    # alone, a direction picked at random for a whole asset class landed
    # outside it on 11.4% of 2,040 judged real-bar runs (model-validator r5
    # and r6). So the copy names the bar, not a number of standard errors,
    # and a verdict also needs the direction randomisation (docs/adr/0003).
    bar = f"outside its error bar (±{2*se*100:.1f})"
    if state == "unconfirmed":
        side = "above" if delta > 0 else "under"
        return (f"Before costs, {abs(delta)*100:.1f} points {side} the "
                f"prediction, {bar}, but directions picked at random over "
                "stretches of time across the watchlist land this far out "
                "often enough that this is not told apart from chance. From "
                "one replay of past prices.")
    if delta > 0:
        # "beats" carries the sign, as "below" does.
        return (f"Hit rate beats the prediction by {delta*100:.1f} points, "
                f"{bar}, and further above it than directions picked at "
                "random over stretches of time across the watchlist usually "
                "land. That is not a guarantee: in our tests, directions "
                "picked at random over stretches of up to four holding "
                f"periods still got this verdict {CHANCE_VERDICT_RATE}, and "
                "that rate is per run, so trying many settings makes a "
                "chance verdict likely. Before costs, from one replay of past "
                "prices: a reason to look closer, not a finding.")
    return (f"Hit rate is {abs(delta)*100:.1f} points below the prediction, "
            f"{bar}, and further below it than directions picked at random "
            "over stretches of time across the watchlist usually land. A "
            "direction picked at random can land this far below too, so this "
            "does not show the lean is worse than a coin flip. Before costs, "
            "from one replay of past prices.")


def run(symbols: list[str], horizon_days: int = 5, rng: str = "2y",
        step: int = 3, progress=None, with_news: bool = False,
        articles: dict | None = None, with_catalyst: bool = False,
        universe: str = WHOLE_WATCHLIST) -> dict:
    """Backtest a whole watchlist. Returns the summary plus per-bucket views.

    ``universe`` is what ``symbols`` are: :data:`WHOLE_WATCHLIST`, or the
    name of the one asset class they were picked from — said by the caller,
    which knows, and never guessed from the symbols. Only the whole
    watchlist gets a verdict; a run without one claims no attention finding
    and grades no component either (``withheld`` in :func:`summarise`).

    ``with_news`` additionally pulls a historical attention series per symbol,
    so the news component is tested rather than assumed. One extra request per
    instrument. ``with_catalyst`` does the same for the catalyst weight, from
    EDGAR's record of Item-2.02 8-K filings — US filers only; ADRs yield no
    dates and their rows simply carry no catalyst series.

    ``predicted`` throughout is the driftless chance of the target first,
    given the setup resolved in time. Setups that ran out of time
    (``n_timeout``) and those with too little data left after them to compare
    (``n_short_window``) are counted but never reach the hit rate, the
    buckets, the timing table or attribution — every one of those sees the
    compared, resolved setups only.
    """
    earnings_by_symbol: dict[str, list[str]] = {}
    if with_catalyst:
        from .research import earnings as earnings_mod
        earnings_by_symbol = earnings_mod.history(symbols)

    trials: list[dict] = []
    timeouts: list[dict] = []
    short: list[dict] = []
    fetched = 0
    longest = 0
    with_attention = 0
    for sym in symbols:
        bars = fetch_bars(sym, rng)
        if bars is None:
            continue
        fetched += 1
        longest = max(longest, len(bars))
        att = None
        if with_news and bars.time:
            a = dt.datetime.utcfromtimestamp(bars.time[0]).strftime("%Y%m%d")
            b = dt.datetime.utcfromtimestamp(bars.time[-1]).strftime("%Y%m%d")
            att = fetch_attention(sym, a, b, articles)
            if att:
                with_attention += 1
        for row in run_symbol(bars, horizon_days, step=step, attention=att,
                              earnings=earnings_by_symbol.get(sym) or None,
                              keep_timeouts=True):
            if row["short_window"]:
                short.append(row)
            elif row["outcome"] == "TIMEOUT":
                timeouts.append(row)
            else:
                trials.append(row)
        if progress:
            progress(sym, len(trials))

    summary = summarise(trials, step=step, timeouts=timeouts,
                        short_windows=short, horizon_days=horizon_days,
                        universe=universe)
    summary["symbols"] = fetched
    # What the longest series fetched could compare at all: the screen's
    # answer to "nothing to compare — so what would work?"
    summary["longest_comparable_horizon"] = (
        longest_comparable_horizon(longest, step) if fetched else None)
    summary["horizon_days"] = horizon_days
    summary["range"] = rng
    summary["generated"] = int(time.time())
    summary["buckets"] = _momentum_buckets(trials)
    summary["attention_symbols"] = with_attention
    withheld = summary.get("withheld")
    summary["attention_buckets"] = _attention_buckets(trials, withheld)
    summary["news_verdict"] = _news_verdict(summary["attention_buckets"],
                                            withheld)
    summary["timing"] = timing(trials)
    summary["attribution"] = attribute(trials, withheld=withheld,
                                       horizon_days=horizon_days)
    return summary


def _attention_buckets(trials: list[dict],
                       withheld: str | None = None) -> list[dict]:
    """Does an attention spike change the odds?

    This is the news component on trial. If a spike carried information the
    high-attention bucket would stand apart from the rest of the run; if it
    is noise, every bucket sits on the run's own number. So each bucket is
    read against the run's gap (hit − predicted, ``vs_run``), not against
    the prediction: a run that beats the prediction everywhere has buckets
    that each beat it too, and that says nothing about attention. "The run"
    here is the setups that carry an attention reading: only some
    instruments have a pageview series, and they are not a fair sample of
    the watchlist (25 of 129, crypto-heavy), so a gap of their own, read
    against the whole run's, would move every bucket at once (code review
    r5 P2-1). ``delta`` stays the gap to the prediction, for the record.
    Each bucket's error bar counts setups entered on the same day together
    (:func:`_dk_se`, on that bucket's setups), and the four levels
    are four chances to be fooled, so they go through Benjamini–Hochberg at
    :data:`ATTENTION_FDR_Q` together (model-validator r4, P1-E: random
    attention 'shifted the odds' on 9 of 21 judged runs).

    On a run that gets no verdict (``withheld``) no bucket is significant: its
    buckets share the run's sample, and with it whatever kept the run from a
    verdict.
    """
    rows = [t for t in trials if t.get("attention") is not None]
    if not rows:
        return []
    from .research import stats
    run_gap = sum((1.0 if t["outcome"] == "TARGET" else 0.0) - t["predicted"]
                  for t in rows) / len(rows)
    edges = [(-99.0, 0.0, "below normal"), (0.0, 1.0, "normal"),
             (1.0, 2.0, "elevated"), (2.0, 99.0, "spike")]
    out, pvals = [], []
    for lo, hi, name in edges:
        sel = [t for t in rows if lo <= t["attention"] < hi]
        if len(sel) < 30:
            continue
        wins = sum(1 for t in sel if t["outcome"] == "TARGET")
        hit = wins / len(sel)
        pred = sum(t["predicted"] for t in sel) / len(sel)
        held = sum(t["bars_held"] for t in sel) / len(sel)
        se_dk = _dk_se(sel, _dk_lag_days(held))
        se = max(math.sqrt(max(hit * (1 - hit), 1e-9) / len(sel)), se_dk)
        vs_run = hit - pred - run_gap
        p = stats.normal_p(vs_run / se)
        pvals.append(p)
        out.append({"name": name, "lo": lo, "hi": hi, "n": len(sel),
                    "hit_rate": round(hit, 4), "predicted": round(pred, 4),
                    "delta": round(hit - pred, 4),
                    "vs_run": round(vs_run, 4), "std_error": round(se, 4),
                    "se_dk": round(se_dk, 4), "p": round(p, 4)})
    keep = stats.benjamini_hochberg(pvals, q=ATTENTION_FDR_Q)
    for b, survives in zip(out, keep, strict=True):
        b["significant"] = not withheld and survives
    return out


# The false-discovery rate the attention buckets are tested at, together.
ATTENTION_FDR_Q = 0.05


def _news_verdict(buckets: list[dict], withheld: str | None = None) -> str:
    if not buckets:
        return "No attention data — the news component is untested, not cleared."
    if withheld:
        return ("No reading on attention either: this run gets no verdict, so "
                "its attention buckets are shown as numbers only.")
    live = [b for b in buckets if b["significant"]]
    spike = next((b for b in buckets if b["name"] == "spike"), None)
    # "The run" is the setups with an attention reading (_attention_buckets).
    if not live:
        return ("No attention level stood apart from the run as a whole (the "
                "setups with an attention reading), with setups entered on the "
                "same day counted together and the levels judged together: no "
                "effect of a news spike was detected, which is not the same as "
                "none.")
    parts = [f'{b["name"]} {b["vs_run"]*100:+.1f} pts against the run as a '
             f'whole (n={b["n"]})' for b in live]
    lead = ("A news spike shifts the odds: "
            if spike and spike["significant"] else
            "Some attention levels shift the odds: ")
    return (lead + "; ".join(parts) + " — beyond its error bar with the "
            "levels judged together, the run being the setups with an "
            "attention reading. From one replay of past prices, before "
            "costs: a reason to look closer, not a finding.")


# Thresholds for the verdicts in attribute(). Deliberately conservative: a
# component has to earn its place, and "no evidence either way" is a different
# answer from "this is dead weight".
IC_KEEP = 0.02          # below this an IC is not worth a weight, whatever its p
SPREAD_KEEP = 0.02      # 2 points of hit rate between best and worst quintile


def _quintile_spread(trials: list[dict], key: str) -> dict:
    """Hit rate in the top fifth by this component, minus the bottom fifth.

    The question a weight is making a claim about: does ranking on this
    component actually sort winners from losers? Quintiles rather than a
    correlation because the score is used to *rank*, and a spread is the thing
    a human can check against the board in front of them.
    """
    rows = [t for t in trials if t.get(key) is not None]
    if len(rows) < 50:
        return {"n": len(rows), "spread": None, "se": None}
    rows.sort(key=lambda t: t[key])
    cut = max(1, len(rows) // 5)
    bottom, top = rows[:cut], rows[-cut:]

    def hit(rs):
        return sum(1 for t in rs if t["outcome"] == "TARGET") / len(rs)

    h_top, h_bot = hit(top), hit(bottom)
    # Standard error on a difference of two proportions.
    se = math.sqrt(max(h_top * (1 - h_top), 1e-9) / len(top)
                   + max(h_bot * (1 - h_bot), 1e-9) / len(bottom))
    # Never below the date-clustered bar, as the headline's (validator r5
    # P1-A): a component that is one number per class and stretch of days
    # puts a whole day's setups, which win or lose together, in one fifth.
    # Each setup's share of the difference, summed per entry date.
    sides = [(t, 1.0 / len(top), h_top) for t in top] + [
        (t, -1.0 / len(bottom), h_bot) for t in bottom]
    se_dk = math.sqrt(max(_dk_var(
        [w * ((1.0 if t["outcome"] == "TARGET" else 0.0) - h)
         for t, w, h in sides],
        [t.get("t") for t, _w, _h in sides], _dk_lag_of(rows)), 0.0))
    se = max(se, se_dk)
    return {"n": len(rows), "n_per_side": cut, "top": round(h_top, 4),
            "bottom": round(h_bot, 4), "spread": round(h_top - h_bot, 4),
            "se": round(se, 4), "se_dk": round(se_dk, 4)}


def attribute(trials: list[dict], q: float = 0.10,
              withheld: str | None = None,
              horizon_days: int | None = None) -> dict:
    """Which components of the confidence score actually earn their weight.

    The score blends four components with fixed weights. This asks, of each one,
    the only question a weight is a claim about: **does ranking on it sort
    winners from losers?** Three readings per component, because one is easy to
    fool:

    * **IC** — rank correlation between the component and the outcome, across
      every resolved setup.
    * **Quintile spread** — hit rate in the top fifth minus the bottom fifth,
      with the standard error on that difference. This is what a human can check
      by eye against the live board.
    * **Leave-one-out** — the IC of the blended score with this component
      removed. If dropping it does not lower the blend's IC, the weight is
      buying nothing.

    p-values go through Benjamini-Hochberg together, because testing four
    components and reporting the best one is how noise gets published.

    The IC's p-value and the spread's error bar each count the setups
    entered on the same day together, as the headline's bar does
    (:func:`_ic_t`, :func:`_quintile_spread`): a reading shared by a whole
    class over a stretch of days is one reading, not one per instrument.

    The catalyst component is absent by construction and said so rather than
    faked: the replay has no historical earnings calendar, so there is nothing
    to attribute it against. An untested component is not a passing one.

    On a run that gets no verdict (``withheld``, the reason from
    :func:`summarise`) every reading is still computed, but no measured
    component is graded: each is ``"not judged"`` and the result carries
    :data:`NOT_JUDGED` as its ``note``.

    A run at a ``horizon_days`` also puts each component's IC through a
    sign change of its per-stretch scores — the centred products summed over
    the same stretches as the headline's randomisation, four holding periods
    across every class (:func:`randomisation_block_days`) — and those
    ``p_rand`` through Benjamini-Hochberg at ``q`` together. A grade needs
    both (``confirmed``): a component today's rule would grade KEEP or
    INVERTED that the randomisation does not confirm is ``"UNCONFIRMED"``, an
    internal name users read as "not told apart from chance". "Ranks
    backwards" also needs the blend's ``blend_p_rand`` at the claim bar. The
    quintile spread keeps its date-clustered bar. A hand-built sample
    without a horizon is not held to the randomisation [A11]. It does not
    cover a component that is a fixed trait of each instrument, such as
    volatility: no time-block randomisation can (docs/adr/0003).
    """
    from . import randomisation as rnd
    from .research import stats

    resolved = [t for t in trials if t.get("outcome") in ("TARGET", "STOP")]
    if len(resolved) < 50:
        return {"n": len(resolved), "components": [],
                "note": "too few resolved setups to attribute anything"}

    wins = [1.0 if t["outcome"] == "TARGET" else 0.0 for t in resolved]
    names = {"c_momentum": "momentum", "c_volatility": "volatility",
             "c_news": "news", "c_catalyst": "catalyst"}

    # The randomisation runs on a judged run with a known stretch length.
    gated = horizon_days is not None and not withheld
    block_days = randomisation_block_days(horizon_days) if gated else None

    rows, pvals, p_rand = [], [], {}
    for key, label in names.items():
        have = [t for t in resolved if t.get(key) is not None]
        if len(have) < 50:
            rows.append({"component": label, "n": len(have), "ic": None,
                         "verdict": "not measured",
                         "why": "no historical series for this component"})
            pvals.append(1.0)
            continue
        xs = [t[key] for t in have]
        ys = [1.0 if t["outcome"] == "TARGET" else 0.0 for t in have]
        ic = stats.spearman(xs, ys)
        pv = stats.normal_p(_ic_t(xs, ys, [t.get("t") for t in have],
                                  _dk_lag_of(have)))
        spread = _quintile_spread(have, key)
        if gated:
            p_rand[len(rows)] = _ic_rand_p(have, xs, ys, block_days,
                                           label, horizon_days)
        rows.append({"component": label, "n": len(have),
                     "ic": None if ic is None else round(ic, 4),
                     "p": round(pv, 4), "spread": spread,
                     "weight": _live_weight(label)})
        pvals.append(pv)

    keep = stats.benjamini_hochberg(pvals, q=q)
    # The randomisation's p go through BH together across the measured
    # components; a component it cannot test (under two stretches, or a
    # setup without an entry time) counts as p = 1, so it is not confirmed.
    measured = [i for i, row in enumerate(rows) if row.get("ic") is not None]
    rand_keep = dict(zip(measured, stats.benjamini_hochberg(
        [1.0 if p_rand.get(i) is None else p_rand[i] for i in measured],
        q=q), strict=True)) if gated else {}
    blend = _blend_series(resolved, list(names))
    blend_ic = None if blend is None else stats.spearman(*blend[:2])
    blend_t = None if blend is None else _ic_t(
        *blend[:2], [t.get("t") for t in blend[2]], _dk_lag_of(blend[2]))
    blend_p_rand = (None if not gated or blend is None else
                    _ic_rand_p(blend[2], blend[0], blend[1], block_days,
                               "blend", horizon_days))
    for i, (row, survives) in enumerate(zip(rows, keep)):
        if row.get("ic") is None:
            continue
        without = _blend_ic(resolved, [k for k in names if names[k] != row["component"]])
        row["blend_ic"] = None if blend_ic is None else round(blend_ic, 4)
        row["blend_ic_without"] = None if without is None else round(without, 4)
        row["loo_cost"] = (None if (blend_ic is None or without is None)
                           else round(blend_ic - without, 4))
        row["survives_fdr"] = bool(survives)
        row["p_rand"] = (None if p_rand.get(i) is None
                         else round(p_rand[i], 4))
        row["confirmed"] = bool(survives) and (not gated or rand_keep[i])
        row.update(_verdict_for(row))
        if withheld:
            row.update(survives_fdr=False, confirmed=False,
                       verdict="not judged", why=NOT_JUDGED)
    catalyst_measured = any(
        r["component"] == "catalyst" and r.get("ic") is not None for r in rows)
    # "The score as a whole ranks the wrong way round" is a finding, so it
    # takes the components' own test on the blend, at the claim bar, and a
    # run that gets a verdict; otherwise the blend IC is only a number
    # (code-review r4 P2-1). The randomisation's p must clear the same bar,
    # which it can only do at 10 stretches or more (2/2^9 is 0.0039).
    from .calibration import Z_CLAIM
    backwards = (not withheld and blend_ic is not None and blend_ic < 0
                 and blend_t is not None and blend_t <= -Z_CLAIM
                 and (not gated or (blend_p_rand is not None and
                                    blend_p_rand <= stats.normal_p(Z_CLAIM))))
    q_all = (len({_block_of(t["t"], block_days) for t in resolved
                  if t.get("t") is not None}) if gated else 0)
    out = {"n": len(resolved), "components": rows,
           "blend_ic": None if blend_ic is None else round(blend_ic, 4),
           "blend_ic_t": None if blend_t is None else round(blend_t, 2),
           "blend_ranks_backwards": backwards,
           "blend_p_rand": (None if blend_p_rand is None
                            else round(blend_p_rand, 4)),
           "randomisation": ({"q": q_all,
                              "draws": (2 ** q_all
                                        if q_all <= rnd.ENUMERATE_MAX
                                        else rnd.B_DRAWS),
                              "block_days": block_days} if gated else None),
           "fdr_q": q, "withheld": withheld,
           # Kept as an explicit line either way: an untested component must
           # not read as a passing one, and once tested the note says so.
           "catalyst": ("measured — see its component row; historical "
                        "earnings dates from EDGAR Item-2.02 8-K filings"
                        if catalyst_measured else
                        "not measured — no historical earnings series was "
                        "supplied for this run, so the catalyst weight is "
                        "untested rather than validated")}
    if withheld:
        out["note"] = NOT_JUDGED
    return out


def _ic_rand_p(rows: list[dict], xs: list[float], ys: list[float],
               block_days: int, label: str,
               horizon_days: int | None) -> float | None:
    """The sign-change p of a component's IC: its centred products
    (x − x̄)(y − ȳ), the numerator :func:`_ic_t` tests, summed per stretch
    (:func:`_block_of`, every class together) and put through
    :func:`sonar.randomisation.sign_flip_p`, seeded from the setups and the
    component's own readings under ``ic|<label>``. ``None`` when a setup has
    no entry time or there are under two stretches."""
    from . import randomisation as rnd
    if any(t.get("t") is None for t in rows):
        return None
    mx, my = math.fsum(xs) / len(xs), math.fsum(ys) / len(ys)
    by_block: dict[int, list[float]] = {}
    for t, x, y in zip(rows, xs, ys, strict=True):
        by_block.setdefault(_block_of(t["t"], block_days), []).append(
            (x - mx) * (y - my))
    scores = [math.fsum(v) for _b, v in sorted(by_block.items())]
    seed = rnd.content_seed(
        f"ic|{label}", horizon_days,
        (f'{t.get("symbol")}|{t["t"]}|{t.get("direction")}|{t["outcome"]}|'
         f'{x!r}' for t, x in zip(rows, xs, strict=True)))
    return rnd.sign_flip_p(scores, seed)["p"]


def _live_weight(label: str) -> float:
    from .assets import _W
    return _W.get(label, 0.0)


def _ic_t(xs: list[float], ys: list[float], times: list[float | None],
          lag_days: int) -> float:
    """The t of a component's ranking skill: the mean of the centred
    products, the test every component's p-value comes from. Its error bar
    is the wider of Newey-West in trial order and the date-clustered one
    (:func:`_dk_mean_se`, setups entered at ``times`` summed per day, over
    ``lag_days``), as the headline's is: the trials are ordered by symbol,
    so Newey-West never sees setups entered on the same day across
    instruments (model-validator r5 P1-A: a meaningless component, one value
    per class and stretch of days, was graded KEEP or INVERTED on 24% of
    judged real-bar runs)."""
    from .research import stats
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    prods = [(x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)]
    _t, se = stats.newey_west_t(prods)
    se = max(se, _dk_mean_se(prods, times, lag_days))
    return sum(prods) / len(prods) / se if se > 0 else 0.0


def _blend_ic(trials: list[dict], keys: list[str]) -> float | None:
    """IC of the weighted blend built from exactly these components."""
    from .research import stats
    series = _blend_series(trials, keys)
    return None if series is None else stats.spearman(*series[:2])


def _blend_series(trials: list[dict], keys: list[str]
                  ) -> tuple[list[float], list[float], list[dict]] | None:
    """The weighted blend of exactly these components and the outcomes, per
    setup that has them all, and those setups; ``None`` with under 50."""
    from .assets import _W
    names = {"c_momentum": "momentum", "c_volatility": "volatility",
             "c_news": "news", "c_catalyst": "catalyst"}
    # Only components actually present in this replay. Demanding all of them
    # meant the blend could never be scored whenever attention was off, which
    # is the default — so leave-one-out silently returned nothing.
    keys = [k for k in keys
            if sum(1 for t in trials if t.get(k) is not None) >= 50]
    usable = [t for t in trials if all(t.get(k) is not None for k in keys)]
    if len(usable) < 50 or not keys:
        return None
    xs = []
    for t in usable:
        w_sum = sum(_W[names[k]] for k in keys) or 1.0
        xs.append(sum(_W[names[k]] * t[k] for k in keys) / w_sum)
    ys = [1.0 if t["outcome"] == "TARGET" else 0.0 for t in usable]
    return xs, ys, usable


def _verdict_for(row: dict) -> dict:
    """Turn the three readings into one recommendation a person can act on.

    The verdict that matters most is INVERTED. A component with a *significant
    negative* IC is not merely useless — it is being added with a positive
    weight, so it actively pushes losers up the ranking. That is worse than
    dead weight and the opposite of what a passing p-value usually means.
    """
    ic = row.get("ic")
    sp = row.get("spread") or {}
    spread, se = sp.get("spread"), sp.get("se")
    strong_spread = (spread is not None and se
                     and abs(spread) > 2 * se and abs(spread) >= SPREAD_KEEP)
    loo = row.get("loo_cost")
    significant = bool(row.get("survives_fdr")) and abs(ic or 0.0) >= IC_KEEP
    # A row from a run held to the randomisation says whether it agreed; a
    # hand-built one without the field is graded on today's rule alone.
    confirmed = row.get("confirmed", True)

    def phrase() -> str:
        if spread is None:
            return ""
        verb = "beats" if spread > 0 else "trails"
        return (f"the top quintile {verb} the bottom by "
                f"{abs(spread) * 100:.1f} points")

    if significant and strong_spread and not confirmed:
        # Never "survives FDR", "confirmed" or "verified", and never the
        # internal name (domain P3-B): the reading, then why it is not one.
        backwards = " backwards" if (ic or 0) < 0 else ""
        return {"verdict": "UNCONFIRMED",
                "why": f"IC {ic:+.3f}: it looks like it ranks setups"
                       f"{backwards} on this replay, but a meaningless "
                       "reading held for stretches of time ranked them this "
                       "well often enough that this is not told apart from "
                       "chance. Before costs, from one replay of past prices."}
    if significant and strong_spread and (ic or 0) < 0:
        return {"verdict": "INVERTED",
                "why": f"IC {ic:+.3f} is significant and *negative* — {phrase()}. "
                       "Added with a positive weight, this component would push "
                       "the wrong instruments up the board. Worth testing with "
                       "its sign flipped, or dropped. From one replay of past "
                       "prices: a reason to look closer, not a finding."}
    if significant and strong_spread:
        return {"verdict": "KEEP",
                "why": f"IC {ic:+.3f} survives FDR and {phrase()} — from one "
                       "replay of past prices"}
    if loo is not None and loo <= 0:
        return {"verdict": "DROP",
                "why": "removing it does not lower the blend's IC — the weight "
                       "is buying nothing"}
    if abs(ic or 0.0) < IC_KEEP and not strong_spread:
        return {"verdict": "WEAK",
                "why": f"IC {ic:+.3f} and no quintile spread beyond its own error "
                       "bar; carrying weight it has not earned"}
    return {"verdict": "UNCLEAR",
            "why": "readings disagree — more setups needed before cutting it"}


def timing(trials: list[dict]) -> dict:
    """What history says about *when* — entry weekday and holding time.

    Both questions people most want answered ("which day should I buy",
    "when do I sell") get measured here rather than asserted. The weekday test
    is the one likely to disappoint: if entry day mattered, a hit rate would
    stand out, and a flat table is the honest answer that it does not.

    Holding time is the useful half. The plan's exit is already exact — the
    target and the stop are prices, not dates — so the practical question is
    how long that usually takes, which is a distribution, not a promise.
    """
    if not trials:
        return {}
    dows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    by_dow = []
    for i, name in enumerate(dows):
        sel = [t for t in trials
               if dt.datetime.utcfromtimestamp(t["t"]).weekday() == i]
        if len(sel) < 30:
            continue
        wins = sum(1 for t in sel if t["outcome"] == "TARGET")
        hit = wins / len(sel)
        se = math.sqrt(max(hit * (1 - hit), 1e-9) / len(sel))
        by_dow.append({"day": name, "n": len(sel), "hit_rate": round(hit, 4),
                       "std_error": round(se, 4)})

    held = sorted(t["bars_held"] for t in trials)
    winners = sorted(t["bars_held"] for t in trials if t["outcome"] == "TARGET")
    losers = sorted(t["bars_held"] for t in trials if t["outcome"] == "STOP")

    def pct(xs, q):
        return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None

    spread = ((max(b["hit_rate"] for b in by_dow) -
               min(b["hit_rate"] for b in by_dow)) if by_dow else 0.0)
    worst_se = max((b["std_error"] for b in by_dow), default=0.0)
    # Seven days tested means seven chances to be fooled: at a 2-sigma bar,
    # roughly one run in three throws up a "significant" day from noise alone.
    # The first version of this test duly announced Thursday at 49% — which
    # then reversed in commodities and ranged from 64% to 29% across symbols.
    # So the bar is Bonferroni-style and deliberately hard to clear.
    bonferroni = 4.0
    return {
        "by_weekday": by_dow,
        "weekday_spread": round(spread, 4),
        "weekday_matters": spread > bonferroni * 2 * worst_se,
        "weekday_note": (
            "Entry weekday shows no reliable effect. An apparent Thursday\n"
            "edge did not survive: commodities reversed it and per-symbol\n"
            "hit rates ranged from 64% to 29%. Seven days tested means\n"
            "seven chances at a false positive, and no mechanism explains\n"
            "why a weekday would matter. Treat entry day as irrelevant."),
        "hold_median": pct(held, 0.5),
        "hold_p25": pct(held, 0.25),
        "hold_p75": pct(held, 0.75),
        "hold_median_win": pct(winners, 0.5),
        "hold_median_loss": pct(losers, 0.5),
    }


def _momentum_buckets(trials: list[dict]) -> list[dict]:
    """Does a *bigger* momentum reading win more often? The screener ranks by
    score, so this is the part of that ranking history can actually test."""
    edges = [(0.0, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 1.0)]
    out = []
    for lo, hi in edges:
        rows = [t for t in trials if lo <= abs(t["momentum"]) < hi]
        if not rows:
            continue
        wins = sum(1 for t in rows if t["outcome"] == "TARGET")
        hit = wins / len(rows)
        predicted = sum(t["predicted"] for t in rows) / len(rows)
        # `label` and `delta` are what the Lab's bucket table reads; without
        # them every row read "?" and "+0.0 vs baseline" (code-review r3 P2-2).
        out.append({"label": f"{lo * 100:.0f}–{hi * 100:.0f}%",
                    "lo": lo, "hi": hi, "n": len(rows),
                    "hit_rate": round(hit, 4),
                    "predicted": round(predicted, 4),
                    "delta": round(hit - predicted, 4)})
    return out
