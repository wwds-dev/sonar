# Code-level readiness audit: promises vs code (2026-11-18)

Role: read-only audit (Foundry phase **Verify / Operate**: no Build, no code or test changes). SONAR `master` at
`283765c` (v2.407 in the tree; the live agent runs the installed **v2.406**, `c2d96dd`), `sonar_macro` at `811bf7b`,
`sonar_playmaker` at `c322aef`. Model: Opus 5.5, high effort. Nothing was restarted, no write endpoint was called and
no data file was touched. Live reads were two GETs (`/api/health`, `/api/state`), `launchctl list`, `ps`, the
installed plist and bundle stamp, the agent log, and `security find-generic-password` without `-w` (existence only).

## Verdict

**Fit to keep running as the owner's paper tool. Not ready to hand to anyone else (testers, the public repo's
readers) until H1-H4 are fixed or their promises reworded.** No Blocker: nothing found can move real money, and an
LLM figure cannot reach a stake. The four High findings are each a place where the app shows a verdict, a stake or a
price with more certainty than the code earns, or ships code whose release left no record.

Most of the doc sweep's leads are **stale**: the alarm work is committed, installed and delivering; the agent runs
the installed bundle at `ProcessType Standard`; the current stamp names the nested commits; the sign-randomisation gate
shipped in v2.340. Detail in "Leads".

## Test suite (run once, as `app-context.md` says)

`QT_QPA_PLATFORM=offscreen ./run-tests.sh -q -p no:cacheprovider -rfEs`: **3256 passed, 66 deselected
(`network`, `slow` via `addopts`), 0 failed, 0 skipped, 0 errors, 252.75 s**, exit 0, under the external watchdog,
with the Sentinel and Imprint audits loading the machine. The native-mode run was **not** done (it opens real
windows on the owner's screen); the coverage two-pass was **not** re-run. stderr carried three
`watchdog step failed (AttributeError: 'StubLive' object has no attribute '_stop')` lines (L3).

## Findings, ranked

### High

**H1. Model-vs-market verdict is a 2-se test re-read every hour: under no edge it says "model beats market" at some
point in about 1 run in 6.**
- Promise: `static/docs.html:868-873` ("The verdict compares the two paired, hour by hour, with an error bar … the
  line says so itself"); `engine.py:597-606` docstring ("it refuses to call noise a win"). The verdict also decides
  whether the Terminal colours the model's edge figure by side (`ui/app.py:4795-4800`), the one place the app shows a
  direction of its own.
- Code: `sonar/engine.py:632-645` declares `model_better` once `n >= 100` and `mean_d < -2*se`, recomputed every
  snapshot over a growing sample with no allowance for repeated looks. The repo already guards this trap elsewhere
  (`Z_CLAIM = 3`, `docs/adr/0002-shadow-time-stop-grade.md:84`; buyability at three se).
- Measured (null: model and market equally good, each the true p plus N(0, 0.05) noise; 2,000 runs to n = 975,
  today's live n): at one fixed look n = 975, "beats" 3.0%, either side 5.1% (the control, as designed); **at any
  hourly look 100..975, "beats" 16.8%, either side 30.6%**. At 3 se: 1.5% and 3.0%. Script in the appendix.
- Live today: n = 975, Brier diff +0.0058, se 0.0023 (2.5 se): "the market is better calibrated". Not wrong on its
  face, but the rule that produced it is not the calibrated test the copy implies.
- Fix: use the shadow ledger's `Z_CLAIM = 3` (or an alpha-spending boundary) for both verdicts and for
  `model_better`; add a rate test with this null. Or reword to "two standard errors at this look; checked every hour,
  so a chance crossing is likely over a long run".

**H2. A Yahoo outage leaves health green while paper entries book at hours-old prices.**
- Promise: README "What a Yahoo outage does" (board keeps scoring from cache, Updated turns red) and "The agent raises
  alarms off the Mac. A stall … goes to your phone"; `app-context.md` Domain specialist ("data provenance and
  staleness").
- Code: `_get` swallows every error and returns None (`sonar/assets.py:252-257`); a failed fetch keeps the old
  cache entry (`assets.py:397-401`), so rows keep their old price and age. `_rescan_once` still marks the book
  (`core.py:428`), runs **Protocol mode's automatic entries** (`core.py:435`) and re-stamps `_scan_at`
  (`core.py:449`), so the health check "board not rescanned" (`core.py:1560`) never fires and no alarm goes out.
  `Live.trade` and `Portfolio.enter` take `asset["price"]` with no age check (`core.py:1129-1152`,
  `portfolio.py:256-292`). Only the Updated colour (a UI hint) shows it.
- Effect: during a long outage, manual and protocol positions open at a price up to hours old, and the agent reports
  `ok`. Not reproduced live (would need an outage); the code path is unambiguous.
- Fix: refuse an entry when `data_age_s` exceeds a bound (say 1 h, the README's red line) with that sentence; add a
  `data` health problem when more than half the board is older than that, so the watchdog alarms; add the entry rule
  to the README outage list.

**H3. Playmaker: a zero-width interval gets full Kelly, labelled "sized at the low end of the interval".**
- Promise: `sonar/playmaker/README.md` ("Kelly sized at the interval's low end"), `MODELS.md` §9; Playmaker Stage 1
  item "Probabilities carry an interval and Kelly uses it" is ticked done.
- Code: `staking.from_consensus` returns `low = p = high` when the peer standard error is 0 or NaN
  (`staking.py:101-102`); `devig.Opportunity.is_outlier` treats a NaN z as an outlier (`devig.py:259`). With two
  peers the interval uses z = 1.96 although one degree of freedom needs about 12.7.
- Measured (reproduced from the subagent's script): books A and B at -110/-110, C at +105/-125 → estimate 0.50,
  low = high = 0.50, **stake 2.38% of bankroll**, note "sized at the low end of the interval (50.0%)". Control: peers
  at -110/-110 and -112/-108 → z 6.4, stake 1.96%.
- Why High: this is the one figure in the repo a reader could act on with real money at a bookmaker.
- Fix: no stake (or a "cannot size" source) with fewer than three peers or zero spread; use a t-quantile for small
  peer counts; do not mark NaN z an outlier.

**H4. v2.406 went live with no release record, and the backlog still describes it as unreviewed.**
- Promise: Foundry pipeline (Review, Verify, Secure, Release reports per spec; Release is a GATE);
  `CHANGELOG.md` header ("records the builds that were installed"); `app-context.md` release smoke test.
- Facts: the agent was restarted on 2026-11-17 21:02 onto `/Applications/SONAR.app` v2.406 (`ps`, bundle stamp,
  `agent.out.log`). That build carries alarm-delivery, starved-engine, build-traceability, providers-wiring, the legal
  copy fixes and several Lab Hub merges "conflicts resolved by Claude Code". The newest CHANGELOG version is v2.366;
  the legal fixes still sit under "Unreleased — 2026-11-10". `docs/audit/` has no release report after
  `alarm-delivery-sre-release.md` ("built and smoke-tested. NOT installed", v2.362) and no
  `build-traceability-verify.md`. `docs/foundry/approvals.jsonl` does not exist, although specs and TODO cite
  approved gates; `docs/foundry/activity.jsonl` ends 2026-10-19 (providers-wiring review "start"). TODO still says
  "Next: Review" or "Verify" for the alarm (P0), starved-engine, build-traceability and providers-wiring items, and
  "Decide whether to restart the launchd agent on v2.178" / "Open the installed v2.178".
- Correction (same day): `docs/foundry/activity.jsonl` logs build-traceability Verify done 2026-10-19
  (`build-traceability-qa.md`); only a file under the planned name is missing. The owner confirmed the install was
  deliberate (Lab Hub "Update now"); record in `docs/audit/release-v2.406.md`.
- Fix: a release note for v2.406 (what it contains, who installed it, smoke-test result) and a CHANGELOG entry; update
  the four TODO items to say what is live and which phase is still owed; record future gate approvals with
  `record_approval.py`. The owner says whether v2.406 was a deliberate release.

### Medium

**M1. A forwarded trade that did book can read "did not take it" (lead narrowed: no duplicate position).**
- Code: `Live._forward` (`core.py:1819-1837`) wraps both the POST and the follow-up `_mirror_book` fetch
  (`core.py:1831`, `1766`) in one `except`, so a timeout on either reports `ok: False, "did not take it"`, and the
  Undo toast never appears. `FOLLOW_TIMEOUT = 2.0` (`core.py:111`). `/api/trade` has no idempotency key
  (`server.py:137-143`).
- Narrower than the TODO lead: a second click cannot open a duplicate, because the book allows one position per
  symbol (`portfolio.py:263-264`, "already holding"). The harm is a false "not taken" and a lost Undo.
- Fix: report a mirror failure separately from the POST ("taken; the book view will catch up"); on a POST timeout say
  "no answer in time; it may have gone through, check the book". Existing TODO item reworded.

**M2. A hung agent is caught only by a missing 09:00 heartbeat (confirmed).**
- Code: the watchdog runs inside the agent (`server.py:440-442`); launchd restarts only a non-zero exit
  (`KeepAlive/SuccessfulExit false` in the installed plist). A wedged process (the Qt/GIL wedge `run-tests.sh`
  describes, a stuck HTTP thread pool) stops the watchdog too. No external probe exists in `scripts/`, `packaging/`
  or LaunchAgents. RUNBOOK §2 names the blind spot; the TODO P1 "External probe outside the agent" stands and still
  has no spec.
- Smallest fix: that probe (a 5-minute launchd `curl -m 10 /api/health`, push on non-200 or no answer twice).

**M3. A book restored from backup is announced only on stderr.**
- Code: `paths.read_state` (`paths.py:188-229`) moves an unreadable `portfolio.json` aside and loads the newest daily
  backup, printing one stderr line. No UI or `/api/health` field says so (grep of `ui/` and `core.py`). Up to a day of
  positions can vanish with the app showing a normal book. `write_atomically` (`paths.py:131-148`) has no `fsync`
  before `replace`, which makes a power loss one route there (unconfirmed on APFS).
- Fix: keep a `restored_from` note in memory, show it on My trades and as a health problem until acknowledged; fsync
  the temp file before the rename.

**M4. "DROP" is a verdict with no error bar.**
- Code: `backtest._verdict_for` returns DROP, "removing it does not lower the blend's IC — the weight is buying
  nothing", whenever the leave-one-out cost `loo <= 0` (`backtest.py:1670-1673`; `loo_cost` at `1482-1483` is a
  plain difference with no standard error). Every other verdict in that function is gated on FDR, a 2-se spread and
  the randomisation check. False-DROP rate not measured.
- Fix: call it DROP only when `loo_cost` is below zero by more than its own bootstrap se; otherwise WEAK/UNCLEAR. Or
  reword to "removing it did not lower the IC on this replay".

**M5. Macro presents stale or partial data as fresh** (sonar_macro; partly in its TODO). `series()` serves the old
disk cache on any error (`macro/__init__.py:102-105`); `stale` is True only when all six series are empty (`:163`);
no fetch time is stored; the UI never reads `stale`; the LLM read gets the regime without `as_of`/`stale`
(`core.py:1391-1403`); a missing series silently reweights the regime (`:199`); a failed snapshot is held 6 h with no
retry (`:229-234`). FRED is the only source (lead confirmed).

**M6. Playmaker's LLM prompt contradicts "commentary only"** (sonar_playmaker). `SYSTEM_PROMPT`
(`playmaker/__init__.py:355`) says the stated percentage "is the number the app converts into expected value" (false:
`staking.kelly` returns 0 for a narrative source, `staking.py:148`) and asks for "Lean: OVER, UNDER or NO EDGE"; the
prompt gets only the first book's price (`ui/app.py:4354`), not the computed fair price.

**M7. Playmaker accepts impossible American odds** (`devig.py:300`, `playmaker/__init__.py:274`): `"X -50 +50"`
parses, -50 becomes decimal 3.0; a typo "-11" for "-110" makes a phantom edge. Reproduced.

**M8. Playmaker: duplicate book names break leave-one-out** (`devig.py:225` drops every row with that name).
Reproduced: "Same, Same, Other" prices each row against a one-book consensus with z = NaN, flagged as outliers.

### Low

- **L1. Coverage label** (existing TODO): branch-only 79.5% against app-context's "80% branch"
  (`docs/foundry/tooling-baseline.md:44`). Not re-measured here.
- **L2. Stale backlog entries** beside H4: the sign-randomisation item (TODO "not merged") shipped in v2.340 and its
  measured rates are disclosed in `CONFIDENCE.md` and in-app.
- **L3. Three `test_server.py` tests leave a live Watchdog thread** (`tests/test_server.py:340-427` call
  `server.main` without patching `Watchdog.run`, unlike `tests/test_alarm.py:851`). It fails every 15 s on the stub
  for the rest of the session (the stderr lines above). Harmless today because conftest blocks `osascript` and
  `security`; patch `Watchdog.run` there.
- **L4. Agent log**: `~/Library/Logs/SONAR/agent.err.log` is 739 KB since 2026-10-12 with no rotation; lines mix
  local and ISO-UTC timestamps (`core.py:1521` vs `alarm.ts()`). `/api/health` returns `ok: true` with a
  `last_error` from an earlier failed poll, which reads as a current error.
- **L5. Playmaker smaller items** (subagent, spot-checked): `calibrated_estimate` is called only from tests, so
  README's "only route from a model to a stake" and "WEAK shrinks the stake" are true but inert (Stub); the "best
  edge" cell shows `opportunities[0]` even when it is not an outlier (`ui/app.py:4279`); `results._fetch_token`
  returns `[]` after retries, so a `measure` can run on partial history silently (`results.py:289-290`); no test
  covers H3, M7 or M8.
- **L6. Macro smaller items**: `as_of` omits CPIAUCSL (`macro/__init__.py:161`); README calls `MacroCache` a disk
  cache (it is in-process); `/api/macro` runs `get()` on a request thread and can block up to 6 x 25 s
  (`server.py:173`).

## Leads from the doc sweep

| Lead | Result | Evidence |
|---|---|---|
| Alarm: osascript banner failed 45/47; ntfy fix built but uncommitted, unreviewed | **Stale.** Committed (`d548361`), reviewed (`docs/audit/alarm-delivery-*`), installed in v2.406. Live: ntfy configured (Keychain item present), banner 3/3 and ntfy 3/3 sends OK since the restart, heartbeat queued 2026-11-18 09:14 | `/api/health` `notify` block; agent.err.log; H4 for the missing release record |
| Nothing outside the agent notices a dead or hung agent | **Confirmed** | M2 |
| Engine starved (Background, Nice 5); health 3-24 s | **Refuted for the live agent.** Installed plist: `ProcessType Standard`, no `Nice`; `/api/health` answered in 15 ms while the suite ran | plist; `curl` timing |
| Forwarded trade timeout reads "not taken"; no idempotency key | **Confirmed, narrower**: no duplicate (one position per symbol), but a successful trade can read "not taken" for two reasons | M1 |
| Yahoo only price source, no fallback | **Confirmed and disclosed** in README; the undisclosed part is H2 | `assets.py:42,252-257` |
| v2.340 stamped `"nested": {}` and clean | **Historical, fixed going forward.** v2.406's stamp names macro `811bf7b` and playmaker `c322aef`, `traceable: true`, matching both repos' HEAD and `origin`. Pre-v2.365 ledger entries stay untraceable (existing TODO "Look-1 note") | `_build_info.json` in the bundle |
| Backtest error bar: verdict on 11.4% of coin-flip runs; DROP no error bar; `model_vs_market` at 2 se | **11.4%: superseded** (the randomisation gate shipped; worst held-out 9.11%, disclosed in `CONFIDENCE.md:650-664` and in-app). **DROP: confirmed** (M4). **model_vs_market: confirmed and measured** (H1) | |
| "80% branch" but branch-only 79.5% | **Confirmed from the record**, not re-measured | L1 |
| Agent runs the main working tree | **Refuted.** Default install runs `/Applications/SONAR.app`; `--checkout` is opt-in and documented (`scripts/install_agent.sh:5-14`, README "Uptime") | plist |
| Macro has one source (FRED), no stale flag | **Confirmed, narrower**: a `stale` flag exists but means "all six empty" | M5 |

## Promise classification

| Promise (where) | Status |
|---|---|
| Paper only; `alpaca.py` refuses non-paper hosts; no live venue (README, app-context) | Delivered (Alpaca not connected; `PaperBroker` default) |
| P(profit) pinned at `1/(1+R:R)`, EV zero until an edge is measured (README, `scoring.py`) | Delivered: every live `build_plan` call passes `edge_sigma = 0` (`assets.py:466`, `portfolio.py:272`) |
| "Worth a look" is notability, never direction (README, `ui/words.py`) | Delivered (a heuristic ranking, no predictive claim) |
| An LLM read never blends into confidence or sizes a bet (README, `llm.py`) | Delivered: logged on the hourly trade record only (`engine.py:479-491`); playmaker stake cells set only from the cross-book screen |
| Model vs market "refuses to call noise a win" (docs.html, `engine.py`) | Narrower (H1) |
| Backtest verdict needs the bar and the randomisation check; chance rates disclosed (CONFIDENCE) | Delivered, with the disclosed 9.11% worst case; DROP is the exception (M4) |
| Agent alarms a stall or dead loop to the phone; daily heartbeat (README "Uptime") | Delivered for an engine stall or exit; narrower for a hung process (M2) and for a data outage (H2). Phone receipt: owner check 1 |
| `/api/health` turns red on a failing push channel (README) | Delivered (`server.py:294-316`) |
| One engine per state file; follower forwards writes (README) | Delivered; messages narrower (M1) |
| State files keep a daily backup; unreadable file recovered (README, `paths.py`) | Delivered; silent to the user (M3) |
| Protocol mode: coin-flip direction, fixed small stakes (README) | Delivered; entries can use stale prices (H2) |
| Yahoo outage behaviour as listed (README "Data providers") | Narrower: the list omits stale-price entries and the silent health (H2) |
| Build stamp names the nested commits (build-traceability spec) | Delivered for v2.406 |
| Changelog records every installed build (CHANGELOG header) | Not delivered for v2.406 (H4) |
| 80% branch coverage (app-context test bar) | Narrower (79.5%, L1) |
| Macro: six FRED series, 6 h disk cache, last good values offline | Delivered |
| Macro: `stale` flag, self-reported age, per-series `as_of` | Narrower (M5, L6) |
| Macro: regime meaningful at 2008/2020 conditions | Unverifiable (no test; existing macro TODO) |
| Playmaker: three devig methods, Shin default (MODELS §7c table) | Delivered (reproduced 91.95/93.45/94.47) |
| Playmaker: Kelly at the interval's low end, 5% cap | Narrower (H3) |
| Playmaker: leave-one-out Kaunitz screen | Delivered with H3/M8 caveats |
| Playmaker: LLM read sits on numbers it did not invent | Narrower (M6) |
| Playmaker: `calibrated_estimate` is the only model-to-stake route | Stub, not wired (L5) |
| Playmaker: Brier/skill table, Dixon-Coles RPS 0.2149 | Unverifiable without a live run (owner check 6) |

## What the docs do not mention (summary)

Silent paths found: Yahoo fetch errors (`assets.py:252-257`) and a green health during an outage (H2); book restored
from backup (M3); macro serving any-age cache (M5); playmaker results windows dropped (L5). Stale shown as fresh:
macro regime (M5); board prices into new positions (H2). Fixture-only tests where the docs imply more: every
playmaker and macro behaviour except one network-marked macro test; the alarm path is unit-tested on fakes, and its
live proof is the health counters above.

## Checks only the owner can run live

1. **Phone receipt.** Confirm today's 09:14 heartbeat reached the phone (ntfy counters show HTTP success, not
   receipt). If unsure: `python main.py --test-alarm` from the checkout, or the bundle with `--test-alarm`.
2. **Release record for v2.406** (H4): who installed it on 2026-11-17 21:01 and whether it was meant as a release;
   then the app-context release smoke test (one scan, one paper trade, quit, relaunch with state intact,
   `./scripts/install_agent.sh --status`).
3. **Native-mode suite**: `./run-tests.sh` (opens windows; only offscreen ran here).
4. **Coverage two-pass** from `app-context.md` "Commands", to replace the 79.5% record.
5. **Yahoo outage drill** on a scratch engine (`SONAR_DATA` pointed at a temp folder, `SONAR_ALARM=off`, a different
   port), with `query1.finance.yahoo.com` blocked: expect health to stay `ok` and a Protocol entry to book at the
   cached price (H2). Never against the live book.
6. **Playmaker live check**: one real market from three books, compared by hand against the screen and the stake.

## Appendix: H1 simulation

`scratchpad/mvm_sim.py` (pure Python, `random.Random(7)`), run with `.venv/bin/python -I mvm_sim.py <Z>`:

```python
import random, math, sys
Z = float(sys.argv[1]); R, N = 2000, 975; rng = random.Random(7)
fb = fe = ab = ae = 0
for _ in range(R):
    s = s2 = 0.0; hit_b = hit_e = False
    for i in range(1, N + 1):
        p = rng.uniform(0.2, 0.8); y = 1.0 if rng.random() < p else 0.0
        m = min(.99, max(.01, p + rng.gauss(0, .05))); k = min(.99, max(.01, p + rng.gauss(0, .05)))
        d = (m - y) ** 2 - (k - y) ** 2; s += d; s2 += d * d
        if i >= 100:   # engine.py SCORE_MIN_SAMPLE, rule at engine.py:633-640
            mean = s / i; se = math.sqrt(max((s2 - i * mean * mean) / (i - 1), 0) / i)
            b = mean < -Z * se; e = abs(mean) > Z * se
            hit_b |= b; hit_e |= e
            if i == N: fb += b; fe += e
    ab += hit_b; ae += hit_e
print(fb / R, fe / R, ab / R, ae / R)
```

Z = 2: fixed look 0.030 / 0.051, any look 0.168 / 0.306. Z = 3: 0.002 / 0.002, 0.015 / 0.030.
