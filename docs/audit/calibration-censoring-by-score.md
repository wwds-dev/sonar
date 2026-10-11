# Live calibration is right-censored by score (2026-10-11)

Found while reading the first calibration verdict (21 closed, hit 48% vs 40% promised, rank IC −0.32).
Read-only analysis of `~/Library/Application Support/SONAR/portfolio.json`; nothing was changed.
**Status: open, owner decision.** Not reproduced by a test yet; the numbers below are from the live book on
2026-10-11 22:58 and will move.

## Finding
`calibration.report()` grades **closed** positions only, and the paper book has **no time stop** ("exits are
prices, not dates"). How long a position takes to close depends on its score, so the closed set is not a
random sample of what was entered. High-score positions are systematically the ones still open.

| score band | entered | closed | still open | closed % | median hold (closed) | median age (open) |
|---|---|---|---|---|---|---|
| 0–20 | 28 | 15 | 13 | 54% | 5.6 d | 4.9 d |
| 40–60 | 15 | 6 | 9 | 40% | 2.5 d | 9.0 d |
| 60–80 | 7 | 1 | 6 | 14% | 15.9 d | 19.9 d |

Protocol mode enters top-5 and bottom-5 by score each day, so entries are balanced by design; the closed set is
not (15 of 21 in the lowest band). In the 40–60 and 60–80 bands the open positions are already older than the
closed ones ever got — the survivors are the slow ones.

## Consequence
- The per-band hit rates and the rank IC (−0.32, ≈1.4σ) are computed on the fast resolvers. The sign and size are
  **not interpretable** yet; this includes the "higher scores won less" reading. Neither confirms nor clears the
  score.
- The 2σ gate and the 95% interval are valid for a random sample, which this is not. They are too confident.
- Closure rate is itself censored: 1.43/day over 14 d, 1.05/day over 21 d. Time-to-verdict figures assume it
  holds: n≈45 for IC 0.3 (≈16 d), ≈101 for IC 0.2 (≈55 d), ≈401 for IC 0.1 (≈265 d), ≈150 for a ±8-pt hit-rate
  interval (≈90 d).
- Same family as QA-13 (backtest drops timeouts at R:R ≥ 2): unresolved trials removed from the denominator.

## Options (owner's call — each changes the experiment or the readout)
1. **Make the censoring visible** (readout only): show entered / closed / still open per band on the landing
   panel and My trades, and say the verdict is provisional while any band has a large open share.
2. **Grade by entry cohort**: a cohort counts only when fully resolved or older than a cap (say 15 trading days).
3. **Add a time stop**: close at the horizon, marked to market, so every entry resolves by a fixed date. Removes
   the bias; changes what the barrier maths promise (P(profit) is the *untimed* 1/(1+R:R)) and resets the
   experiment's comparability with positions already open. Needs an ADR.

Recommendation: 1 now (no behaviour change), decide 2 vs 3 with `model-validator` — the QA-11/QA-13 session
already has `calibration.py` and `docs/adr/0001` open, so route it there rather than editing in parallel.

**2026-10-11: option 1 built for the landing panel** (v2.187, branch `claude/happy-visvesvaraya-84b4ef`, not merged;
My trades does not show it yet). Each band's line gives entered / still open (median age) / closed, and the panel
calls the verdict provisional while any band has 40% or more of its entries open. `calibration.report()` and its
verdict text are untouched. Options 2 and 3 are still open.

## Reproduce
```
.venv/bin/python - <<'EOF'
import json, time, statistics as S; from pathlib import Path
d = json.load(open(Path.home()/'Library/Application Support/SONAR/portfolio.json'))
op, cl = d['open'], [p for p in d['closed'] if p.get('pnl') is not None]
band = lambda c: '0-20' if c < 20 else '20-40' if c < 40 else '40-60' if c < 60 else '60-80' if c < 80 else '80+'
for b in ('0-20','20-40','40-60','60-80','80+'):
    c = [p for p in cl if band(p['confidence']) == b]; o = [p for p in op if band(p['confidence']) == b]
    if c or o: print(b, len(c)+len(o), len(c), len(o))
EOF
```
