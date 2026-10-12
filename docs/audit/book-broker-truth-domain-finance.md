# Domain review (Define): book-broker-truth, 2026-10-12

Inputs: `.claude/agents/domain-finance.md`, app-context `## Domain specialist` + `## Invariants`, `docs/playbooks/domain-finance.md` (**status: baseline**, last-reviewed 2026-10-12, so it has not been checked by a radar run yet), the spec, and code and docs in `/Users/as/Documents/lab/active/sonar`. Nothing was edited.

**Problem check:** confirmed. `sonar/core.py:163` and `:959` call `Portfolio(path)` without a broker, so the book always gets `PaperBroker` (`portfolio.py:193`). `default_broker()` has no caller. The harm the spec describes (a user believes their results are "realistic") breaks the app-context rule that every result is shown as simulated, with its cost treatment. Option A is the right scope. Option B would add network and security surface for no user need.

## Findings

**P1: none.**

**P2-1: Spec §Goal/success measure, check 1. The test as written can pass even when the code changes.**
- **Rule:** the success measure must actually bind the docs to the code.
- **Scenario:** `Portfolio(path)` with no broker argument is always `PaperBroker`, so patching `alpaca.available()` does nothing there. Suppose someone later passes `default_broker()` in `core.py`. A test that builds `Portfolio(path)` directly still passes, and the docs are wrong again with no warning.
- **Fix:** make check 1 a static check over `sonar/`, `ui/` and `main.py`:
  - every `Portfolio(` call has no broker argument (positional or keyword);
  - nothing calls `default_broker(`.
- **Optionally also:** build the book through the same code path `core.py` uses, with `available()` patched to True, and assert `isinstance(book.broker, PaperBroker)`.

**P2-2: Spec §Scope (README, docs.html). The "Alpaca does better / more honest" comparison is not addressed.**
- **Where:** `README.md:162` ("Alpaca's **paper** environment does better") and `static/docs.html:516-518` ("is more honest — real market hours…").
- **Rule:** the result must be shown as simulated, with nothing implying a realistic or achievable return.
- **Scenario:** if these lines stay next to the correction, users still read Alpaca as the realistic mode they could switch to. That invites them to go find a way to switch.
- **Fix:** say explicitly in Scope that these sentences are removed, or rewritten in a conditional form such as "once connected, Alpaca paper would add real market hours and order handling". No comparative wording about the current book.

**P2-3: Spec §Success measure, check 3. The test does not protect the disclosure itself.**
- **Scenario:** a later edit keeps "always uses the built-in simulator" but drops "no fees / optimistic bound". The test still passes, and the cost treatment disappears from the Learn tab.
- **Fix:**
  - Assert that the same section of `README.md` and `static/docs.html` also contains "optimistic bound" and "no fees".
  - Assert that `.env.example` contains "not used by the book".

**P3-1: Spec §Design. The proposed sentence is accurate, but slightly less complete than the existing disclosure.**
- **Accurate:** it covers simulated, instant fills, fills exactly at target or stop, no fees, and optimistic bound. It has no advice, edge or certainty wording, and "does not change your results" is true.
- **Gaps against the code's own limits:**
  - spread and slippage are not named (`docs.html:939` names both);
  - prices are polled, so a spike that touches the target and reverses between two polls is missed (`portfolio.py:20-23`).
- **Suggested wording:** "The book always uses the built-in simulator: instant fills at the quoted price, exactly at target or stop, with no spread, slippage or fees. That makes its results an optimistic bound, not a forecast. SONAR includes a guarded Alpaca **paper** adapter, but the book does not use it yet, so adding Alpaca keys does not change the book's results."
  - "not a forecast" mirrors the `PaperBroker` docstring (`portfolio.py:157-160`).
  - "the book's results" avoids reading as a statement about the user's own performance.

**P3-2: Coverage beyond the four files.** I grepped for "Alpaca", "paper key", "more honest", "realistic" and "default_broker":
- **Leave as is** (true statements about the function, not claims that the book uses it): `GOING_LIVE.md:259` and `TODO.md:81` ("`default_broker()` returns Alpaca paper or the internal book"). `GOING_LIVE.md:135-147` ("realistic") is about choosing a live venue, so it is not affected.
- **`GOING_LIVE.md:103`** "it is where Alpaca already sits": the planned edit to lines 103-104 should also cover this phrase.
- **`README.md:339`** calls `alpaca.py` "dormant real-money code". It is paper-only, so this is inaccurate and could undercut the paper-only message. It is outside this spec's scope; fix it if convenient, or log it.
- **`.claude/worktrees/merge-all/`** holds copies of the same false claims (README, docs.html, GOING_LIVE.md). If that worktree is merged after this fix, the claims come back. The phrase checks in the test would catch this, so just note it for whoever merges.
- **No mentions** in `ui/*.py` or `static/index.html`.

**P3-3: Spec §Problem table.** The docs.html location is lines 514-519 (the heading is at 514), not 515-519. Cosmetic.

## Needs a qualified human
Nothing in this spec. It removes an inaccurate claim and keeps the cost disclosure, so it reduces exposure. Users' jurisdiction is still `UNVERIFIED` per app-context. If the Learn tab copy is ever published outside the app (marketing, a store listing), the performance-advertising questions under SEC/FINRA or ESMA/BaFin need a qualified reviewer. I have not given a legal opinion here.

**Verdict:** spec is OK to proceed once P2-1 to P2-3 are folded into Scope and the success measure. They are small edits to the spec, with no change of option.

## Review pass, 2026-10-12

Checked against code: `core.py:163,959` build `Portfolio(path)` with no broker; `portfolio.py:193` falls back to `PaperBroker()`; `default_broker()` has no caller; `PaperBroker` (`portfolio.py:157-160`) is instant, no fees/slippage, "optimistic bound, never a forecast"; `alpaca.py:44-102` paper host and `PK` keys only. Every factual claim in the reviewed copy is true.

- Disclosure: README.md:161-163 and docs.html:515-519 state simulated, instant fills, exactly at target/stop, no spread/slippage/fees, optimistic bound, not a forecast (Define P3-1 wording adopted).
- Define P2-2 resolved: "does better"/"more honest" gone from all four files; replacement is conditional and factual (README.md:164, docs.html:520-521). GOING_LIVE.md:103-105 accurate; README.md:340 relabelled.
- No advice, edge or certainty wording; CHANGELOG.md:13-23 accurate.

P0/P1/P2: none.
- **P3-1** polled-price limit (spikes between polls missed, `portfolio.py:20-23`) not disclosed at README.md:161 / docs.html:515. Optional.
- **P3-2** `sonar/alpaca.py:3-5` docstring still says Alpaca paper "is the cheap way to do better"; developer-facing, but could be copied back into docs. Reword without comparison.
- **P3-3** other "realistic" mentions (GOING_LIVE.md:137,148; docs.html:641) are about venue choice and sample size: out of scope.

Needs a qualified human: nothing new. **Verdict:** pass.
