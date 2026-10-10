"""The hourly volatility study's apparatus, proven on data with known answers.

The daily volatility study's lesson (`volatility.py`) was that the *control*
is what makes a result trustworthy: its first, much larger GARCH win was an
artefact of effective sample size, caught only by scoring the same models on
a synthetic series with constant volatility, where there is no clustering to
find. The same controls run here on every build:

* on constant volatility, the seasonal variants must not beat their bases —
  there is no pattern to find, and a win there would mean the profile is
  manufacturing one;
* on planted hour-of-day seasonality, the seasonal variant must win — a
  detector that cannot find a pattern put there on purpose measures nothing;
* on planted regime shifts, EWMA must beat the trailing window — same logic.

Everything is seeded, offline and fast.
"""

import math
import random

import pytest

from sonar.research import hourlyvol as hv

HOUR = 3600


def series(sigmas, seed=7, start=20_000.0):
    """Closes and times for hourly log-returns r_i ~ N(0, sigmas[i])."""
    rng = random.Random(seed)
    closes, times = [start], [0]
    for i, s in enumerate(sigmas):
        closes.append(closes[-1] * math.exp(rng.gauss(0.0, s)))
        times.append((i + 1) * HOUR)
    return closes, times


def scored(result, model):
    return next(v for v in result["verdicts"] if v["model"] == model)


N = hv.DIURNAL_WINDOW + 6000


def test_the_constant_volatility_control():
    """No clustering and no seasonality to find. The seasonal variants must
    not beat their bases (a win would be a manufactured pattern), and EWMA —
    a noisier estimate of the same constant — must lose to the wider window."""
    closes, times = series([0.004] * N)
    r = hv.study(closes, times)
    assert scored(r, "ewma")["vs_trailing_pct"] < 0
    assert scored(r, "ewma")["verdict"] == "DROP"
    base = r["pooled_qlike"]["trailing72"]
    seasonal = r["pooled_qlike"]["trailing72_diurnal"]
    assert seasonal >= base * 0.995, "the profile found a pattern that is not there"
    assert scored(r, "trailing72_diurnal")["verdict"] != "KEEP"


def test_planted_seasonality_is_found():
    """Twice the volatility during 'US hours', and the seasonal variant must
    convert that into a QLIKE win that holds across blocks."""
    sigmas = [0.006 if 13 <= (i + 1) % 24 <= 20 else 0.003 for i in range(N)]
    closes, times = series(sigmas)
    r = hv.study(closes, times)
    v = scored(r, "trailing72_diurnal")
    assert v["vs_trailing_pct"] > 5.0
    assert v["verdict"] == "KEEP"


def test_planted_clustering_is_found():
    """Calm and stormy regimes in blocks of 200 hours. EWMA forgets in ~11
    hours and adapts; the 72-hour window drags a regime and a half behind."""
    sigmas = [0.010 if (i // 200) % 2 else 0.002 for i in range(N)]
    closes, times = series(sigmas)
    r = hv.study(closes, times)
    assert scored(r, "ewma")["vs_trailing_pct"] > 0


def test_too_little_history_is_an_error_not_a_verdict():
    closes, times = series([0.004] * 500)
    assert "error" in hv.study(closes, times)


def test_hour_of_day_is_read_in_utc():
    assert hv.hods_from_times([0, 3600, 86_400 + 7200]) == [0, 1, 2]


def test_the_profile_is_causal_and_clamped():
    d = hv._Diurnal(window=48)
    for i in range(48):
        d.push(i % 24, 1e-4 if i % 24 else 1.0)   # hour 0 is absurdly loud
    lo, hi = hv.PROFILE_CLAMP
    assert d.factor(0) == hi, "one loud hour is clamped, not believed"
    assert d.factor(1) >= lo


def test_qlike_punishes_underforecasting_harder():
    assert hv.qlike(0.5 * 0.004, 0.004) > hv.qlike(2.0 * 0.004, 0.004)


# --------------------------------------------------------------------------- #
# The live forecaster the app ships
# --------------------------------------------------------------------------- #
def test_forecast_prices_a_loud_hour_above_a_quiet_one():
    """The point of the seasonal term: the same history must answer with a
    higher σ when the hour being priced is one that is routinely loud."""
    sigmas = [0.006 if 13 <= (i + 1) % 24 <= 20 else 0.003 for i in range(N)]
    closes, times = series(sigmas)
    nxt = times[-1] + HOUR
    loud = next(t for t in range(nxt, nxt + 24 * HOUR, HOUR)
                if 13 <= (t % 86400) // 3600 <= 20)
    quiet = next(t for t in range(nxt, nxt + 24 * HOUR, HOUR)
                 if not 12 <= (t % 86400) // 3600 <= 21)
    assert hv.forecast(closes, times, loud) > 1.3 * hv.forecast(closes, times, quiet)


def test_forecast_without_a_full_profile_window_is_plain_ewma():
    """A three-day profile is a different, unmeasured estimator — below the
    window the seasonal factor must drop out entirely, not thin out."""
    sigmas = [0.006 if 13 <= (i + 1) % 24 <= 20 else 0.003 for i in range(500)]
    closes, times = series(sigmas)
    nxt = times[-1] + HOUR
    readings = {hv.forecast(closes, times, nxt + k * HOUR) for k in range(24)}
    assert len(readings) == 1, "no profile yet, so the hour must not matter"


def test_forecast_is_the_estimator_the_study_measured():
    """The study's +7.5% belongs to EWMA over deseasonalised r². The shipped
    forecast ran EWMA over raw r² instead — a different, unmeasured and on
    real data worse estimator. Held equal here, at origins across the run."""
    rng = random.Random(3)
    sigmas = []
    level = 0.004
    for i in range(hv.DIURNAL_WINDOW + 400):
        level = max(0.001, level * math.exp(rng.gauss(0, 0.05)))   # clustering
        season = 2.0 if 13 <= (i + 1) % 24 <= 20 else 1.0           # US hours
        sigmas.append(level * season)
    closes, times = series(sigmas, seed=11)
    trace: list = []
    hv.study(closes, times, warmup=hv.DIURNAL_WINDOW, trace=trace)
    assert trace
    for i, studied in trace[::37]:
        shipped = hv.forecast(closes[:i + 1], times[:i + 1], target_time=times[i + 1])
        assert shipped == pytest.approx(max(studied, hv.MIN_VOL), rel=1e-12), i


def test_forecast_needs_a_minimum_of_history():
    closes, times = series([0.004] * 20)
    assert hv.forecast(closes, times) is None


def test_forecast_refuses_a_gappy_series():
    """A zero close is what a halted feed sends; the returns then no longer
    line up with the hours, and a misaligned profile is worse than none."""
    closes, times = series([0.004] * 200)
    closes[50] = 0.0
    assert hv.forecast(closes, times) is None


def test_forecast_refuses_a_missing_hour():
    closes, times = series([0.004] * 200)
    del closes[120], times[120]
    assert hv.forecast(closes, times) is None


def test_forecast_refuses_history_that_ended_hours_ago():
    """A partial pull once ended twenty days back and was priced as now."""
    closes, times = series([0.004] * 200)
    assert hv.forecast(closes, times, now=times[-1] + 1800) is not None
    assert hv.forecast(closes, times, now=times[-1] + 20 * 86400) is None


def test_a_failed_page_is_an_error_not_a_shorter_history(monkeypatch):
    """The second page of a 62-day pull failing used to return the first page
    alone, ending about twenty days ago."""
    import io, json as _json
    calls = []

    def fake_urlopen(req, timeout=15):
        calls.append(req.full_url)
        if len(calls) == 1:
            rows = [[(1_700_000_000 + h * 3600) * 1000, "0", "0", "0", "100"]
                    for h in range(1000)]
            return io.BytesIO(_json.dumps(rows).encode())
        raise OSError("page two failed")

    monkeypatch.setattr(hv.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="incomplete"):
        hv.fetch_hourly(days=62)


def test_only_the_hour_in_progress_is_dropped(monkeypatch):
    import io, json as _json
    import time as _time
    now_hour = int(_time.time()) // 3600 * 3600
    rows = [[(now_hour - (5 - h) * 3600) * 1000, "0", "0", "0", str(100 + h)]
            for h in range(5)]                    # ends with the last *closed* hour
    monkeypatch.setattr(hv.urllib.request, "urlopen",
                        lambda req, timeout=15: io.BytesIO(_json.dumps(rows).encode()))
    times, closes = hv.fetch_hourly(days=1)
    assert len(times) == 5, "a closed hour was dropped as if in progress"


def test_forecast_tracks_a_volatility_regime():
    calm, stormy = series([0.002] * 300)[0], series([0.010] * 300, seed=8)[0]
    times = [i * HOUR for i in range(301)]
    assert hv.forecast(stormy, times) > 3 * hv.forecast(calm, times)
