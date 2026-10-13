"""The direction randomisation behind the backtest's verdict (docs/adr/0003).

A verdict needs Δ outside its error bar and the run's directions to read
further from the prediction than directions swapped for the opposite ones over
whole stretches of time. These tests pin the arithmetic of
:mod:`sonar.randomisation` against hand-rolled references, its determinism
(the same run always gives the same p, in any row order and under any
``PYTHONHASHSEED``), and its exactness on a placebo nested in its clusters.
"""

import itertools
import math
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from sonar import randomisation as rnd

ROOT = Path(__file__).resolve().parent.parent


def _ref_t(pattern, clusters):
    """The cluster-robust t of the gap under one swap pattern, written out the
    long way: Δ = S/N, V = Σ (s_g − n_g·Δ)², T = Δ·N/√V."""
    chosen = [c[1] if swap else c[0] for swap, c in zip(pattern, clusters,
                                                        strict=True)]
    S = sum(s for s, _n in chosen)
    N = sum(n for _s, n in chosen)
    if N <= 0:
        return 0.0
    d = S / N
    V = sum((s - n * d) ** 2 for s, n in chosen)
    return 0.0 if V <= 1e-12 else d * N / math.sqrt(V)


# Three clusters: (kept, swapped) gap sums and resolved counts. The swapped
# side of the first has one more resolved setup (a timeout that resolved the
# other way), so N changes under a swap.
_Q3 = [((1.2, 3), (-0.8, 4)), ((0.6, 2), (-0.4, 2)), ((-0.4, 1), (0.6, 1))]


def test_an_enumerated_p_is_the_share_of_patterns_by_hand():
    """q = 3: all eight swap patterns, each scored with the cluster t of the
    gap recomputed under the pattern (N changes), and the p is the share at
    or beyond the observed one. Ties count against the run.
    Mutation it catches: N held fixed under a swap, the observed pattern left
    out of the count, or a tie counted for the run."""
    r = rnd.direction_p(_Q3, seed=1)
    ts = [_ref_t(p, _Q3) for p in itertools.product((0, 1), repeat=3)]
    t0 = ts[0]
    assert r["t"] == pytest.approx(t0)
    assert r["method"] == "enumerate" and r["draws"] == 8 and r["q"] == 3
    ge = sum(t >= t0 - 1e-12 for t in ts)
    le = sum(t <= t0 + 1e-12 for t in ts)
    assert r["p_hi"] == ge / 8 and r["p_lo"] == le / 8
    assert r["p"] == min(1.0, 2 * min(ge, le) / 8)
    # Δ > 0 here, so the gate reads the upper tail.
    assert r["delta"] == pytest.approx(1.4 / 6) and r["delta"] > 0
    assert r["p_tail"] == min(1.0, 2 * ge / 8)
    # one other pattern reads further up (the third cluster swapped alone,
    # t 8.49 against 1.71): two of eight, so p_tail = 2 × 2/8
    assert ge == 2 and r["p_tail"] == 0.5


def test_a_swap_that_turns_resolved_setups_into_timeouts_changes_n():
    """Three of four clusters time out entirely the other way (n = 0 when
    swapped): the t under each pattern is over the setups that resolved in
    that pattern. Only the observed pattern reads as far up: p_tail = 2/16.
    Mutation it catches: N held at the kept count under a swap (p_tail 0.25)."""
    clusters = [((0.6, 1), (0.0, 0)), ((0.6, 1), (0.0, 0)),
                ((1.2, 2), (-0.8, 2)), ((-0.2, 3), (0.0, 0))]
    r = rnd.direction_p(clusters, seed=1)
    ts = [_ref_t(p, clusters) for p in itertools.product((0, 1), repeat=4)]
    assert r["p_hi"] == sum(t >= ts[0] - 1e-12 for t in ts) / 16 == 1 / 16
    assert r["p_tail"] == 0.125


def test_the_tail_follows_the_sign_of_the_gap():
    """p_tail is twice the tail in Δ's direction: the lower one when the run
    reads below the prediction. Mirror every gap and the tails swap.
    Mutation it catches: p_tail always the upper tail, or the smaller one."""
    up = rnd.direction_p(_Q3, seed=1)
    down = rnd.direction_p([((-k[0], k[1]), (-s[0], s[1])) for k, s in _Q3],
                           seed=1)
    assert down["delta"] == pytest.approx(-up["delta"])
    assert down["p_lo"] == up["p_hi"] and down["p_hi"] == up["p_lo"]
    assert down["p_tail"] == min(1.0, 2 * down["p_lo"]) == up["p_tail"]
    assert up["p"] == down["p"]


def test_ties_count_against_the_run():
    """A cluster that reads the same either way changes nothing when it is
    swapped: every pattern ties the observed t, and the p is 1, not 0.
    And a run where nothing resolved reads t = 0 (fail closed).
    Mutation it catches: ties counted for the run (strict inequalities)."""
    same = [((0.6, 2), (0.6, 2))] * 5
    r = rnd.direction_p(same, seed=3)
    assert r["p_hi"] == r["p_lo"] == 1.0 and r["p"] == r["p_tail"] == 1.0
    assert rnd.cluster_t(0.0, 0, 0.0, 0.0, 0.0) == 0.0
    # V = 0: every cluster on the run's own gap
    assert rnd.cluster_t(2.0, 4, 1.0, 2.0, 4.0) == 0.0
    assert rnd.direction_p([], seed=3)["p"] is None


def _many(q: int, seed: int = 5):
    rng = random.Random(seed)
    out = []
    for _ in range(q):
        nk, ns = rng.randint(0, 6), rng.randint(0, 6)
        out.append(((sum(rng.choice((0.6, -0.4)) for _ in range(nk)), nk),
                    (sum(rng.choice((0.6, -0.4)) for _ in range(ns)), ns)))
    return out


def test_monte_carlo_counts_the_observed_pattern_once():
    """Above 12 clusters the p is (1 + #{T* ≥ T}) / (1 + B), B = 11,999 draws
    of one random byte per cluster from a local Random seeded with the run's
    seed, the high half of the byte swapping the cluster. Recomputed here
    from the same stream.
    Mutation it catches: the +1s dropped, B changed, or the stream drawn
    differently."""
    assert rnd.B_DRAWS == 11_999 and rnd.ENUMERATE_MAX == 12
    clusters = _many(14)
    r = rnd.direction_p(clusters, seed=99)
    assert r["method"] == "monte_carlo" and r["draws"] == 11_999
    t0 = _ref_t([0] * 14, clusters)
    rng = random.Random(99)
    ge = le = 0
    for _ in range(11_999):
        pattern = [b >= 128 for b in rng.randbytes(14)]
        t = _ref_t(pattern, clusters)
        ge += t >= t0 - 1e-12
        le += t <= t0 + 1e-12
    assert r["p_hi"] == (1 + ge) / 12_000 and r["p_lo"] == (1 + le) / 12_000


def test_enumeration_and_monte_carlo_agree():
    """The same 12 clusters, enumerated (exact) and drawn: the drawn p lies
    within four Monte Carlo errors of the exact one.
    Mutation it catches: the draw biased (a byte read the wrong way round
    swaps the same clusters every time, or never)."""
    for seed in (1, 2, 3):
        clusters = _many(12, seed)
        exact = rnd.direction_p(clusters, seed=seed)
        drawn = rnd.direction_p(clusters, seed=seed, enumerate_max=0)
        assert exact["method"] == "enumerate" and exact["draws"] == 4096
        assert drawn["method"] == "monte_carlo"
        for key in ("p_hi", "p_lo"):
            p = exact[key]
            assert abs(drawn[key] - p) < 4 * math.sqrt(p * (1 - p) / 12_000) + 2e-4, (
                seed, key, exact[key], drawn[key])


def test_the_same_run_always_gives_the_same_p():
    """Measure 7: determinism. Two calls, and a reordering of the clusters,
    give the same p — enumerated always, and drawn for the same seed
    (the clusters come sorted by stretch from the backtest)."""
    clusters = _many(10)
    a, b = rnd.direction_p(clusters, 7), rnd.direction_p(clusters, 7)
    assert a == b
    shuffled = list(clusters)
    random.Random(1).shuffle(shuffled)
    c = rnd.direction_p(shuffled, 7)
    assert (c["p"], c["p_tail"], c["t"]) == (a["p"], a["p_tail"], a["t"])
    drawn = _many(20)
    assert rnd.direction_p(drawn, 11) == rnd.direction_p(drawn, 11)


def test_the_sums_do_not_depend_on_the_order():
    """math.fsum, so the t of a pattern is the correctly rounded value
    whatever order its clusters come in. With 1e16 in the sums a plain left
    fold gives different answers for different orders.
    Mutation it catches: a plain sum in place of fsum."""
    clusters = [((1e16, 1), (0.0, 1)), ((1.0, 1), (0.0, 1)),
                ((-1e16, 1), (0.0, 1)), ((1.0, 1), (0.0, 1))]
    assert sum(k[0] for k, _s in clusters) != sum(
        k[0] for k, _s in reversed(clusters))          # the trap is real
    ts = set()
    for perm in itertools.permutations(clusters):
        ts.add(rnd.direction_p(list(perm), 1)["delta"])
    assert ts == {0.5}


def test_the_seed_is_the_runs_content():
    """The seed is sha256 over a version tag, the label, the horizon and the
    sorted content lines: the same in any order, different for any change.
    Golden value, so a change to the stream fails loudly.
    Mutation it catches: unsorted lines, the label or horizon left out, or
    the hash changed."""
    lines = ["AAPL|86400|LONG|TARGET|STOP", "BTC-USD|172800|SHORT|TIMEOUT|TARGET",
             "GC=F|259200|LONG|STOP|TIMEOUT"]
    seed = rnd.content_seed("headline", 5, lines)
    assert seed == 7758299461763895366
    assert rnd.content_seed("headline", 5, reversed(lines)) == seed
    assert rnd.content_seed("ic|news", 5, lines) != seed
    assert rnd.content_seed("headline", 20, lines) != seed
    assert rnd.content_seed("headline", 5, lines[:2]) != seed


def test_the_random_stream_is_pinned():
    """Golden values for both tests' Monte Carlo paths: 13 clusters, one
    seed. A change in how the patterns are drawn moves these counts.
    Mutation it catches: the byte table, the draw or the stream changed."""
    cl = [((0.6 * ((i * 7) % 5) - 0.4 * (i % 3), 1 + (i % 4)),
           (-0.4 * ((i * 3) % 4) + 0.6 * (i % 2), 1 + ((i + 1) % 3)))
          for i in range(13)]
    r = rnd.direction_p(cl, 20261012)
    assert r["method"] == "monte_carlo"
    assert round(r["p_hi"] * 12_000) == 53 and round(r["p_lo"] * 12_000) == 11_948
    s = rnd.sign_flip_p([0.3, -0.1, 0.25, 0.4, -0.05, 0.2, 0.15, 0.1, -0.2,
                         0.35, 0.05, 0.12, 0.22], 20261012)
    assert round(s["p_hi"] * 12_000) == 134 and round(s["p_lo"] * 12_000) == 11_899


_SUBPROCESS = """
import json, sys
sys.path.insert(0, {root!r})
from sonar import randomisation as rnd
from tests.test_randomisation import _many
lines = ["S{{}}|{{}}|LONG|TARGET|STOP".format(i % 7, i * 86400) for i in range(40)]
seed = rnd.content_seed("headline", 5, lines)
r = rnd.direction_p(_many(20), seed)
print(json.dumps([seed, r["p"], r["p_tail"]]))
"""


def test_the_p_is_the_same_under_any_hash_seed():
    """Measure 7: across processes with different PYTHONHASHSEED the seed and
    the drawn p are the same — hashlib, not hash(), and no set order."""
    code = _SUBPROCESS.format(root=str(ROOT))
    outs = set()
    for hs in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=hs)
        res = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, env=env, cwd=ROOT, timeout=60)
        assert res.returncode == 0, res.stderr
        outs.add(res.stdout.strip())
    assert len(outs) == 1, outs


def test_the_sign_change_test_by_hand():
    """attribution's test: every pattern of sign changes on per-cluster
    scores, scored with the studentised t of their mean (Canay–Romano–
    Shaikh); the sum of squares does not move, the mean does.
    Mutation it catches: an unstudentised sum, or the observed pattern left
    out."""
    scores = [0.5, 0.2, -0.1, 0.4]
    r = rnd.sign_flip_p(scores, seed=1)

    def t(xs):
        m = sum(xs) / len(xs)
        v = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
        return m / math.sqrt(v / len(xs))
    t0 = t(scores)
    ts = [t([x if s else -x for x, s in zip(scores, signs, strict=True)])
          for signs in itertools.product((1, 0), repeat=4)]
    assert r["t"] == pytest.approx(t0)
    assert r["p_hi"] == sum(x >= t0 - 1e-12 for x in ts) / 16
    assert r["p_lo"] == sum(x <= t0 + 1e-12 for x in ts) / 16
    assert r["p"] == min(1.0, 2 * min(r["p_hi"], r["p_lo"]))
    assert rnd.sign_flip_p([0.3], seed=1)["p"] is None


def _nested_placebo(k: int, q: int = 9, per: int = 12):
    """One dataset: q clusters of setups, each with a long and a short outcome
    that do not mirror each other (a 1.5:1 asymmetry: the long side wins 45%,
    the short 33%, either can time out), and one random direction per cluster
    — nested in the test's clusters, and meaning nothing."""
    rng = random.Random(f"nested|{k}")
    clusters = []
    for _ in range(q):
        sides = []
        for p_win, p_out in ((0.45, 0.10), (0.33, 0.15)):
            s = n = 0
            for _ in range(per):
                u = rng.random()
                if u < p_out:
                    continue                          # a timeout
                s += (1.0 if u < p_out + p_win * (1 - p_out) else 0.0) - 0.3946
                n += 1
            sides.append((s, n))
        clusters.append(tuple(sides) if rng.random() < 0.5
                        else (sides[1], sides[0]))
    return clusters


def test_it_is_exact_for_a_direction_nested_in_its_clusters():
    """Exactness: a direction picked at random per cluster, on outcomes where
    neither side mirrors the other and N changes under a swap, is rejected
    (p_tail < 0.05) at no more than the test's own size. At q = 9 the
    enumerated tail steps in 1/512, so the size is at most 2 × 12/512 =
    4.69%; ties, which count against the run, bring it lower: 117 of 3,000
    datasets (3.9%; these 300 read 14). Bounds: at most 24, the 99.5th
    percentile of Binomial(300, 4.69%), and at least 4, the 0.5th of
    Binomial(300, 3.9%).
    Mutation it catches: a dead statistic (never rejects) or an inverted one
    (the wrong tail rejects far too often)."""
    rejected = sum(rnd.direction_p(_nested_placebo(k), seed=k)["p_tail"] < 0.05
                   for k in range(300))
    assert 4 <= rejected <= 24, rejected
