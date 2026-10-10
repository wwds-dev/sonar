# SONAR QA audit — 2026-10-10

Produced by the `qa-engineer` role. Mutations ran in a scratch copy; the real repo was left
unchanged (`git status` checked).

**Verdict: suite passes; 5 of 8 planted mutations survived, 3 of them in important paths.**

## Runs
| Run | Result |
|---|---|
| Native `./run-tests.sh -q` | 1582 passed, 30 deselected (`-m network`), 26 s |
| `QT_QPA_PLATFORM=offscreen` | 1582 passed, 23 s |
| Offscreen + `coverage run --branch --source=sonar,ui` | 1582 passed, **80%** (9338 stmts, 2328 branches) — matches TESTING.md |

Each mode run once; no failures, so no flakiness observed.
**Teardown noise:** both modes print `RuntimeError: libshiboken: Internal C++ object
(MainWindow) already deleted` at exit. Source: `ui/app.py:3569` — a QTimer lambda calls
`_confirm_hidden` (`ui/app.py:3625`, `self.isVisible()`) after the window is gone. Real
production code firing on a deleted window; the noise can also hide real tracebacks in CI.

## Mutations
| # | Mutation | Result |
|---|---|---|
| M1 | `alpaca.looks_live` → `startswith("AK")` | Caught |
| M2 | flatten slippage direction swapped (`execution.py`) | Caught |
| M6 | settle-idempotency `continue` disabled (`execution.py`) | Caught |
| M3 | `llm.py` `stop_reason == "max_tokens"` check disabled | **Survived** |
| M8 | `llm.py` `stop_reason == "refusal"` check disabled | **Survived** |
| M4 | `engine.py:509` buyability band `(0.02,0.98)` → `(0.0,1.0)` | **Survived** |
| M5 | `scoring.py:~171` `grade()` `ev > 0.05` → `> 0.5` | **Survived** |
| M7 | `engine.py:~299` `_score_hour` `close >= open` → `>` | **Survived** (likely no test with close == open) |

(For survivors, one test that fails in any copy without `.git` —
`test_version.py::…test_a_bundle_finds_the_checkout_its_stamp_points_at` — was removed; the rest was
1579 passed, 2 skipped.)

## Gaps
**P0:** none shown to affect money. Live-key guard, flatten pricing and settle idempotency are pinned.

**P1**
- `sonar/llm.py` **30%** covered (lines 130, 134, 144-174, 193-198, 209-263). `read()` error handling
  (~228-262) — refusal, truncation, unparseable response, RateLimit/APIStatus/APIConnection mapping —
  is untested; M3/M8 survive. Tests only patch `available()` (`tests/test_follow.py:281-300`,
  `tests/test_portfolio_tab.py:125`), never drive the reader with a fake client.
- Hour-outcome boundary (`engine.py:~299`, M7) feeds the model-vs-market Brier log that the
  dry-run readiness gates depend on. Add a close == open test.
- Engine verdict branches uncovered: `engine.py:493, 548, 624, 635, 246->248, 283->285`. M4 survives:
  nothing tests a bid/ask at exactly 0 or 1 or at the 0.02/0.98 edges. TESTING.md claims engine.py
  100%; it is 97%.

**P2**
- `core.py` 67% (150-171, 386-402, 524-584 incl. `read()`/`_read_subject`, 595-614, 806+): poll loop
  and LLM-read plumbing.
- `alpaca.py` 65%: `_request` (66-76, 139, 149-171) and its `AlpacaUnavailable` mapping untested.
- `providers.py` 61% (128-241); `ui/worker.py` 51% (28-137, the thread loop).
- `execution.py` flatten/reconcile error paths: 599-605 (keep flattening after `place` raises),
  688-690, plus 181, 235, 275, 295, 311, 368, 561, 622-623, 676.
- `backtest.py` 54% (108-127, 363-399, 645-707): `fetch_bars`/`run` untested (Yahoo parsing, gap rows).

**P3**
- `scoring.py:93-112, 174-181`: `grade()` only partly pinned (M5); feeds label at `assets.py:486`.
- Research apparatus: `research/study.py` 0%, `panel.py` 27%, `regimes.py` 49%, `macro/__init__.py` 27%.
- `ui/app.py` 78%, `ui/tabs.py` 81% (window handlers).

## Test quality
- No `assert True` / `or True`; 22 bare-truthiness `assert x` (not audited individually).
- ~381 mock/monkeypatch uses over ~1228 tests; network is banned by conftest by design. Risk is where
  the mock replaces the thing under test: the LLM client and the Alpaca transport.
- Time dependence: `tests/test_shutdown.py` uses fixed 0.2-0.3 s sleeps (latent flake); several age
  tests build from `time.time()` with large margins. Only opt-in `test_live_sources.py` hits the network.
- One test needs `.git` and fails in any export without it (harmless).
