# Spec: honest model-vs-market verdict (H1) and stale board prices (H2)

- Status: built (2026-11-18, branch `claude/readiness-h1-h2`; Review and Verify still to run)
- Owner approval: 2026-11-18, Define + Architect ("Fix H1 and H2", then "Approve as written"); recorded in `docs/foundry/approvals.jsonl`
- Source: `docs/audit/code-readiness-2026-11-18.md` H1, H2. Session-owned slug: `readiness-h1-h2`.

## Problem

**H1.** `Engine.model_vs_market` (`sonar/engine.py:632-645`) says "Model beats the market's calibration" once
`n >= 100` and the paired Brier difference is below minus two standard errors, and recomputes that every hour as the
log grows. `model_better` then colours the Terminal's edge figure by side (`ui/app.py:4795-4800`), the one place the
app shows a direction of its own. Re-reading a 2-se test every hour is not a 5% test. Measured under a null (model and
market equally good, 2,000 runs, script in the audit appendix):

| Rule | any look 100..975 h: "beats" / either side | any look 100..3,000 h (the log cap) |
|---|---|---|
| 2 se (today) | 14.2-16.8% / 27.6-30.6% | 18.8% / 36.5% |
| 3 se | 1.5-1.6% / 3.0-3.1% | 2.7% / 5.1% |

The repo already uses 3 se for the same trap: `calibration.Z_CLAIM = 3.0` ("re-checked after every close"), the shadow
ledger (ADR 0002) and buyability.

**H2.** A Yahoo outage leaves `/api/health` green while paper positions open at hours-old prices. Failed fetches are
swallowed (`assets.py:252-257`) and the old cache entry kept; `_rescan_once` still runs Protocol entries
(`core.py:435`) and re-stamps `_scan_at` (`core.py:449`), so the "board not rescanned" check never fires.
`Live.trade` and `Portfolio.enter` take the row's price with no age check.

## User and goal

The owner (and any later reader) running the paper book. Success measures:
1. H1: a rate test on the exact rule `model_vs_market` uses, under a seeded null and re-read at every hour 100..975,
   reads "beats" in at most 5% of runs; the same test at 2 se reads it in at least 10% (the control).
2. H2: a manual trade and a Protocol entry on a row whose price is over an hour old are refused with a sentence, and
   nothing is booked; a fresh row still enters.
3. H2: `Live.health()` reports a `data` problem when more than half of the board's prices are over an hour old, the
   watchdog alarms it after 10 minutes through a fixed phrase, and recovery clears it.

## Scope / Non-goals

In: the verdict threshold and its copy (engine, `static/docs.html`); the entry guard (manual and Protocol); a `data`
health kind with its alarm phrase; README "Data providers" outage list and RUNBOOK §2 kinds.
Not in: a second price source (TODO "Rewire providers"); buyability (already 3 se); the hourly BTC engine's own
trades (Binance/Coinbase, stale candles already rejected); closing or marking held positions on stale prices (a
re-mark at an unchanged price cannot cross a barrier); install or restart of the agent.

## Design

- **H1 copy.** "Model beats the market's calibration by more than three standard errors over these hours." and the
  mirror sentence for the market. A third sentence for "within": unchanged. docs.html "Brier, model vs market" adds:
  "The line is re-read every hour, so it needs three standard errors, not two: at two, a model no better than the
  market would read as better at some point in about one run in six."
- **H2 refusal** (manual trade toast, follower included because the holder applies it): "{SYMBOL}'s price is {N} min
  old (the price source may not be answering), so it was not entered; try again after the next scan." Protocol mode
  says nothing per row: stale rows are left out of the day's ranking, and if fewer than `PROTOCOL_MIN_ROWS` fresh rows
  remain it tries again on the next rescan instead of using up the day.
- **H2 health text:** "{k} of {n} board prices are over an hour old (the price source may not be answering)". Push
  phrase (closed vocabulary): "board prices are stale" with a minutes duration.

## Architecture

- **H1.** `Engine.MVM_Z = 3.0` with a comment naming `calibration.Z_CLAIM` and the measured rates. The rule moves into
  a pure function `mvm_verdict_state(mean_d, se, n, min_sample, z)` returning `"few" | "model" | "market" | "noise"`,
  used by `model_vs_market` and by the rate test, so the test exercises the shipped rule. No state change; the score
  log is untouched.
- **H2.** `assets.BOARD_STALE_S = 3600.0` (the README's red line) and `assets.row_age_s(row, generated, now)` =
  `data_age_s + (now - generated)`: a row's age is fetch age at scan time plus the time since the scan, so a stalled
  rescan cannot make an old row look young. Used by `Live.trade`, `Live._protocol_scan` and `Live.health()`.
  `health()` adds `{"kind": "data"}` in driving mode when `k > n / 2` (n = board rows with a price). `alarm.PHRASES`
  gains `"data"`, `server.ALARM_AFTER_S["data"] = 600.0`; `tests/test_alarm.py`'s `CORE_KINDS` gains `"data"` (it pins
  the kinds in `core.py`; extending it is required, not weakening).
- **Lock order** unchanged: `trade` reads `self.assets` under `self.lock` as today and decides before taking the
  book's lock.
- **Failure modes.** After a night's sleep every row is over an hour old until the rotation refetches it. The board
  refreshes 26 of 129 rows about every 180 s (the scanner's 120 s TTL on the 90 s scan cadence), so more than half
  are fresh after the third refresh, about 6 min after wake: manual entries on not-yet-refreshed rows are refused for
  those minutes, Protocol waits a few rescans, and the `data` problem clears before its 10-minute alarm delay, with
  about 3-4 min of margin (checked from the code, not live: Release check below).
  A throttled source that keeps the rotation behind for an hour refuses entries, which is the intent.
- **Alternatives rejected.** H1: an alpha-spending boundary (more exact, harder to explain, and 3 se already measures
  under 5% to the cap). H2: refusing inside `Portfolio.enter` (it does not know the scan time; replays and tests call
  it with rows that carry no age).

## Risks and open questions

- The owner chooses 3 se (recommended) or another boundary; and 60 min / more than half / 10 min for H2.
- The live agent keeps running v2.406 until the next install; this change reaches it only with the owner's yes at
  Release.

## Verification plan

New tests: the rate test (measure 1) with its control; verdict copy at 3 se; trade refusal on a stale row, entry on a
fresh one, follower path unaffected; Protocol skips stale rows and keeps the day open on a thin fresh screen; health
`data` problem on, off and at exactly half; watchdog alarm after 600 s with the fixed phrase and recovery; existing
kind-sync test extended. Mutation check: 3 back to 2 fails the rate test; dropping the `now - generated` term fails the
stalled-rescan test. Full suite offscreen; native is the owner's run.

Release check (owner, live): after the install, one night's sleep and wake produce no "board prices are stale"
push, and `/api/health` shows `data` for no more than about 6 minutes after wake (agent.err.log).
