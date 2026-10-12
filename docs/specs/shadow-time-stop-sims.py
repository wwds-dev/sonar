"""Evidence for docs/specs/shadow-time-stop.md and docs/adr/0002 (2026-10-12). Pure stdlib.

    python docs/specs/shadow-time-stop-sims.py null 45 2000     # no-edge null, three vol gradients
    python docs/specs/shadow-time-stop-sims.py null 400 400 1   # steep gradient only, large n
    python docs/specs/shadow-time-stop-sims.py null 400 400 1 5 # the same with seed 5
    python docs/specs/shadow-time-stop-sims.py looks            # sequential boundaries and power

Model: driftless walks in sigma-hat units, target +1.5, stop -1.0, marked 20 times per horizon,
fills exactly at the barrier, time stop at T = 4 horizons marked at the path value. Realised vol /
sigma-hat = s(score). No edge anywhere, so any statistic that is "about the score" should centre
on zero and reject at its nominal rate.
"""

import math
import random
import sys

K_T, K_S, T_H, STEPS = 1.5, 1.0, 4.0, 20


def ranks(v):
    order = sorted(range(len(v)), key=v.__getitem__)
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return None if sxx == 0 or syy == 0 else sxy / math.sqrt(sxx * syy)


def hc3_z(x, y):
    """z of the OLS slope of y on x with an HC3 (heteroscedasticity-robust) standard error."""
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
    a0 = my - b * mx
    v = 0.0
    for xi, yi in zip(x, y):
        e = yi - a0 - b * xi
        h = 1 / n + (xi - mx) ** 2 / sxx
        v += (xi - mx) ** 2 * e * e / (1 - h) ** 2
    return b / math.sqrt(v / sxx ** 2) if v > 0 else 0.0


def walk(s, rng):
    dt = 1.0 / STEPS
    sd = s * math.sqrt(dt)
    x = 0.0
    for i in range(int(round(T_H * STEPS))):
        x += rng.gauss(0.0, sd)
        if x >= K_T:
            return "TARGET", K_T / K_S, (i + 1) * dt
        if x <= -K_S:
            return "STOP", -1.0, (i + 1) * dt
    return "TIME", x / K_S, T_H


def null(n, books, scale, seed):
    rng = random.Random(seed)
    out = {"sp": [], "hc": [], "cl": [], "time": 0}
    for _ in range(books):
        conf = [rng.uniform(0, 80) for _ in range(n)]
        res = [walk(scale(c), rng) for c in conf]
        r = [x[1] for x in res]
        out["sp"].append(pearson(ranks(conf), ranks(r)) or 0.0)
        out["hc"].append(hc3_z(conf, r))
        out["time"] += sum(x[0] == "TIME" for x in res)
        # What report() sees today: a snapshot where each entry has a random age in [0, T)
        # and only barrier closes are graded, 0/1.
        ages = [rng.uniform(0, T_H) for _ in range(n)]
        idx = [i for i in range(n) if res[i][0] != "TIME" and res[i][2] <= ages[i]]
        if len(idx) >= 10:
            c = pearson(ranks([conf[i] for i in idx]),
                        ranks([1.0 if res[i][0] == "TARGET" else 0.0 for i in idx]))
            if c is not None:
                out["cl"].append((c, len(idx)))
    mean = lambda v: sum(v) / len(v)  # noqa: E731
    sp_z = [v * math.sqrt(n - 1) for v in out["sp"]]
    cl_z = [c * math.sqrt(m - 1) for c, m in out["cl"]]
    return (f"TIME share {out['time'] / (n * books):.3f} | "
            f"rank IC mean {mean(out['sp']):+.3f}, |z|>2 {mean([abs(z) > 2 for z in sp_z]):.3f} | "
            f"HC3 slope |z|>2 {mean([abs(z) > 2 for z in out['hc']]):.3f}, "
            f"|z|>3 {mean([abs(z) > 3 for z in out['hc']]):.3f} | "
            f"closed-only hit rank IC mean {mean([c for c, _ in out['cl']]):+.3f}, "
            f"|z|>2 {mean([abs(z) > 2 for z in cl_z]):.3f} "
            f"(n~{mean([m for _, m in out['cl']]):.0f})")


GRADIENTS = [("s = 1 everywhere          ", lambda c: 1.0),
             ("s falls 1.3 -> 0.5 with score", lambda c: 1.3 - 0.8 * c / 80),
             ("s falls 1.0 -> 0.6 with score", lambda c: 1.0 - 0.4 * c / 80)]


def looks():
    """Two-sided 5% boundaries for looks at 45, 101 and 201 entries, by Monte Carlo."""
    ns = (45, 101, 201)
    t = [n / ns[-1] for n in ns]
    rng = random.Random(7)
    paths = []
    for _ in range(400_000):
        s = prev = 0.0
        zs = []
        for tk in t:
            s += rng.gauss(0, math.sqrt(tk - prev))
            prev = tk
            zs.append(abs(s) / math.sqrt(tk))
        paths.append(zs)

    def alpha(bounds):
        return sum(any(z > b for z, b in zip(zs, bounds)) for zs in paths) / len(paths)

    def solve(make):
        lo, hi = 1.5, 5.0
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if alpha(make(mid)) > 0.05 else (lo, mid)
        return make(hi)

    def power(ic, bounds, reps=40_000):
        hit = 0
        for _ in range(reps):
            s = prev = 0.0
            for tk, b, n in zip(t, bounds, ns):
                s += rng.gauss(0, math.sqrt(tk - prev))
                prev = tk
                if abs(s / math.sqrt(tk) + ic * math.sqrt(n - 1)) > b:
                    hit += 1
                    break
        return hit / reps

    designs = [("Pocock", solve(lambda c: [c] * 3)),
               ("O'Brien-Fleming", solve(lambda c: [c / math.sqrt(tk) for tk in t])),
               ("3 sigma at each look", [3.0] * 3)]
    for name, b in designs:
        need = [round(z / math.sqrt(n - 1), 3) for z, n in zip(b, ns)]
        pw = ", ".join(f"IC {ic}: {power(ic, b):.2f}" for ic in (0.1, 0.2, 0.3))
        print(f"{name}: z {[round(z, 3) for z in b]} alpha {alpha(b):.4f} "
              f"IC needed {need} | power {pw}")
    for z in (2.0, 3.0):
        pw = ", ".join(f"IC {ic}: {0.5 * math.erfc((z - ic * math.sqrt(44)) / math.sqrt(2)):.2f}"
                       for ic in (0.1, 0.2, 0.3))
        print(f"one look at 45, z {z}: IC needed {z / math.sqrt(44):.3f} | power {pw}")


if __name__ == "__main__":
    if sys.argv[1] == "null":
        n, books = int(sys.argv[2]), int(sys.argv[3])
        picks = GRADIENTS if len(sys.argv) < 5 else [GRADIENTS[int(sys.argv[4])]]
        for seed, (name, scale) in enumerate(picks, start=1):
            seed = int(sys.argv[5]) if len(sys.argv) > 5 else seed
            print(f"n={n} seed={seed} {name}: {null(n, books, scale, seed)}")
    else:
        looks()
