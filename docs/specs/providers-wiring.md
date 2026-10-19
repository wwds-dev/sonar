# Spec: Providers wiring (the provider fallback the docs promise does not exist)

- Status: Define approved 2026-10-19, option B (with changes from `docs/audit/providers-wiring-domain-finance.md`)
- Owner approval: Define gate approved 2026-10-19
- Priority: **P1** (architecture audit N-1, tier-3 item 4; docs audit item 16 / P3-11 folded in)
- Evidence: `foundry/audits/sonar/architecture.md` N-1 (lines 63-80); `docs/audit/architecture.md:128-140`
- Radar note: not run for this spec. Recommended option B adds no tooling, so none is needed. Option A-later needs `/radar-check feature` at its own Define.

## Problem
The README, the in-app Learn page and a P0 owner task all say SONAR falls back to another vendor when Yahoo fails. It does not.
- **No importer.** Nothing in `sonar/`, `ui/`, `main.py` or `scripts/` imports `sonar/providers.py`. The only
  references are comments (`institutions.py:12`, `paths.py:180`, `diag_priority.py:65`) and two tests
  (`tests/test_providers.py`, `tests/test_state_recovery.py:125-130`).
- **What runs.** Every price comes straight from Yahoo's chart endpoint, through three copies of the same URL:
  - `assets._fetch` (`assets.py:268`, the scan, called at `:399`);
  - `assets.fetch_bars` (`:282`): `(timestamp, close)` pairs, used by the equity seed (`core.py:619`) and by
    shadow-ledger grading (`core.py:1065`);
  - `backtest.fetch_bars` (`backtest.py:250`): OHLC `Bars`, used by the backtest (`:1179`), the Lab (`ui/app.py:3580`)
    and research (`research/panel.py:75`).
- **The docs say otherwise.**
  - README "Data providers" (`README.md:177-179`): "a vendor going down is a skipped provider rather than a broken app".
  - `static/docs.html:409-417`: the same claim, shown to users in the app.
  - **Crypto and FX fallback (domain P1-1).** `static/docs.html:398-399` says "Keyless second sources, so crypto and FX
    survive Yahoo breaking". README `:183-185` and `:190-191` say "crypto still resolves via CoinGecko, FX via
    Frankfurter". CoinGecko and Frankfurter appear only in `providers.py`. `docs.html:397` points to "the provider
    layer below", which would be left dangling.
  - README `:190-192` and `:397-398`: a Finnhub key is "the fix" and "the single highest-value change".
  - `.env.example:10-11`: the same claim.
  - `SUGGESTIONS.md:11`: status PLANNED.
- **The owner's P0 task does nothing.** `TODO.md:98` (`P0` `@me`) says: "No code needed — `providers.py` already registers
  Finnhub at preference 5 … picks the key up from `FINNHUB_API_KEY` in a git-ignored `.env`." Three parts of this
  are false:
  1. Nothing calls the module.
  2. Nothing loads a `.env` for it. The only loader, `alpaca.load_env()`, has no live caller (`starved-engine.md` A3),
     and the launchd agent does not inherit the shell's env.
  3. Even if it were wired, it would not cover bars. Finnhub, Twelve Data and Alpha Vantage declare `BARS`
     (`providers.py:210, 228, 246`), but each registers only a `QUOTES` fetcher (`:211, 229, 247`). `candidates()`
     needs the capability in `fetchers` (`:260`), so `candidates(BARS)` is `[yahoo]` alone.
  4. `_yahoo_bars` returns closes with no timestamps and no OHLC (`:127-138`), so it matches neither `fetch_bars`
     return type (audit P3-4).
- **Who is hurt.** The owner, who would spend his top action on a key that changes nothing. Users, who read a
  resilience claim that is untrue. That is an honesty bug under app-context ("Honesty is the product").

## User and goal
**User:** the owner, who runs the paper agent and keeps the backlog, and the retail users who read the Learn page.
**Goal:** every doc and backlog line describes the data path that actually runs. The 30-day paper run (due
~2026-11-09) and shadow-ledger look 1 (~2026-11-06) keep one price source end to end.

## Options weighed
| | A: wire `providers` now | B: make the docs true now (recommended) |
|---|---|---|
| What it fixes | resilience, but only for spot quotes (no keyed bars fetcher exists) | the honesty bug, all of it |
| Code needed | new bars fetchers per vendor; reconcile two return types; key delivery into the launchd plist; per-bar provenance | none to the data path |
| Effect on the run | mixes vendors into scan scores and shadow grades mid-run. Different vendors give different closes, session cuts and adjustments, so look 1 stops being comparable | none. No restart needed |
| Rate limits | Alpha Vantage ~25/day (`providers.py:249`), Twelve Data tight (`:231`), Finnhub 60/min (unverified). The scan polls 129 instruments (`assets.py:245-249`) | n/a |
| Vendor fit | Finnhub free quotes are US equities only. Users report 403 on free `/stock/candle` (not verified). No coverage of `^` indices, `=X` FX or futures | n/a |

**A staged variant (A-later)** is the honest path to real resilience. It runs after the 30-day run closes:
- Yahoo stays first.
- Each bar records which provider served it.
- Shadow grading refuses mixed-source series.
- It gets its own spec, with a Define gate and a radar check.
It is a feature that needs a user question first: "how often did Yahoo actually fail?" That question has no number yet.
The poll-outage count in the starved-engine measure 4 is the first evidence.

## Success measures (all must be shown)
1. **No false claims.**
   - **Grep.** A grep over `README.md`, `static/docs.html`, `.env.example`, `TODO.md`, `SUGGESTIONS.md` and
     `CONFIDENCE.md` finds 0 hits for these phrases: "skipped provider", "No code needed", "is the fix", "closes that
     gap", "highest-value", "survive Yahoo breaking", "still resolves" and "provider layer". It also finds no
     "CoinGecko" or "Frankfurter" outside a sentence that says they are not used. `docs.html:398-399` (the table row)
     is removed.
   - **Source sentence (domain P1-2).** README's data section and `docs.html` §3 each contain this sentence: "Yahoo is
     the only source for the Screener's equities, FX, commodities and crypto rows, with no fallback; the BTC hourly
     model uses Binance, with Coinbase if Binance is unreachable." (`feeds.py:5-8, 148-153`).
   - **What an outage looks like (domain P2-1).** The same places say what a Yahoo outage does. Each point is checked
     against the code:
     - **The board.** The board keeps scoring from cached prices, and the Updated column turns gold past 20 min and
       red past an hour (README `:197-202`). README `:201-202` then gains: "red can also mean Yahoo is not answering".
     - **Shadow grading.** A failed fetch keeps the closes already held (`core.py:1071-1072`). The symbol is marked as
       tried for that UTC day and is not refetched until the next one (`core.py:1059`). An entry past its time-stop
       with no closing bar stays "waiting for a price" and holds its look. It becomes "no price" and is left out only
       after 28 days and 3 failed fetch days (`calibration.py:274-282, 581-587`). So an outage delays grading by at
       least a day, and only a long outage removes entries.
     - **The account-value seed.** The seed retries later (`SEED_RETRY_EVERY`). A partial answer uses up one of
       `SEED_MAX_TRIES`; an empty answer uses none (`core.py:605-623`). So the equity curve waits.
   - **Delay disclosure (domain P2-2).** The same places also say: "Quotes may be delayed by the exchange; Updated
     shows when SONAR fetched the price, not the exchange's time." The size of the delay is not verified, so no number
     is given.
2. **One home for Finnhub status** (docs P3-11). Only README "Data providers" states it. `TODO.md`, `SUGGESTIONS.md`
   and `docs.html` link to it or say nothing.
3. **Backlog is true.** The Finnhub P0 is replaced, done at Define, by a `P2` item: "rewire providers after
   2026-11-09 (A-later spec)". `SUGGESTIONS.md:11` moves from PLANNED to DEFERRED and links to that item.
4. **The module is gone (owner decision).** The following are all deleted:
   - `sonar/providers.py`;
   - `tests/test_providers.py`;
   - `tests/test_state_recovery.py:125-130`.

   The stale references are corrected:
   - the comments at `paths.py:180`, `institutions.py:12` and `diag_priority.py:65`. The diag script still blanks the
     key env vars; only the comment changes;
   - the README module map (`README.md:370`, domain P3-2).

   `grep -rn providers sonar ui main.py scripts` returns only `providers.json` mentions, or nothing. The full suite is
   green native and offscreen.
5. **Run untouched.** `git diff` shows no change to `assets.py`, `backtest.py`, `core.py` or the plist. The live agent
   is not restarted for this item.
6. **Result records carry the source (domain P3-1).** `docs/specs/v1-product.md` and `CONFIDENCE.md` each state, next
   to the look-1 and v1 results: "prices: Yahoo chart endpoint only, no fallback, run window X–Y". X and Y are the
   run's real dates, filled in when the result is recorded.

## Scope
Docs and backlog text as listed above (measures 1-3 and 6). Delete `providers.py` and its tests (measure 4). Move the Stooq
"verified not working" note (`providers.py:21-26`) into the README, so the knowledge survives a deletion. The
`docs.html` change reaches users at the next build that is already planned, not a build of its own.

## Non-goals
- Any change to the price source, `_fetch` or either `fetch_bars`, or to scoring, the book or shadow grading.
- Merging the three Yahoo URL copies (audit P3-1/P3-4). That belongs to A-later.
- Key handling for the launchd agent (Keychain or plist env).
- Real money. Out of scope as always.

## Challenge to the request
The handoff offers wiring as an equal option. It is not, for two reasons. As written, wiring gives no bars fallback at
all (the third and fourth problem bullets). Done properly, it is a new feature that changes data provenance in the
middle of the run that v1.0 depends on (`docs/specs/v1-product.md`). The smaller and fully sufficient fix for N-1 is to
make the claim match the code.

## Risks
- **Losing a starting point.** Deleting the module throws away the switch and registry design. Mitigation: git history,
  plus a pointer in the A-later backlog item.
- **The fragility stays.** Equities still depend on one undocumented endpoint. The docs now say so plainly instead of
  promising a fix. That is the honest state, not a regression.
- **The edit misses a copy of the claim.** Measure 1's grep is the guard. A phrase it does not list can survive, so the
  reviewer reads the data section in full.

## Owner decisions (2026-10-19)
1. **Delete `providers.py` and its tests.** Recommended at Define because wiring it later needs a redesign anyway:
   bars fetchers, return types and provenance.
2. **Replace the Finnhub P0 with a P2:** "rewire providers after 2026-11-09 (A-later spec)". Done in `TODO.md`.
3. **A single price source for the 30-day run and look 1 is accepted** (option B).

## Architecture
No Architect gate. The change does not touch state, concurrency or module boundaries beyond deleting a module that
nothing imports.
- No persisted file changes. Any `providers.json` already in a user's data dir is left in place. Nothing reads it, and
  deleting user files is out of scope.
- No change to the data path, no new dependency and no ADR.
- The bundle loses one module that no code imports, so nothing at runtime changes.
- `/radar-check` and Secure are not needed: there is no network, secret or packaging change.
- Phases skipped: Design (no UI change beyond copy) and Architect (reasons above).
