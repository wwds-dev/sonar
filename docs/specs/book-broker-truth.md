# Spec: the docs say what broker the book actually uses

- Status: defined (Define phase), domain review folded in. Priority: **P1**. Owner approval:
  option A approved (relayed by the coordinator, 2026-10-12).
- Source: `docs/audit/domain-finance.md` P1-1 (also `docs/audit/SUMMARY.md:91`,
  `docs/audit/code-review.md:125-126`, `docs/audit/architecture.md:221-222`).
- Playbook note: `docs/playbooks/product-manager.md` is `status: baseline` (seeded 2026-10-10,
  not yet verified by a radar run), so this spec follows `AGENTS.md` and the role prompt only.

## Problem
User-facing docs say that adding Alpaca paper keys makes the book use Alpaca, and that Alpaca is
the more honest mode. No code path does that. Verified 2026-10-12:

| Claim | Where |
|---|---|
| "SONAR picks them up automatically and falls back to the internal book" | `README.md:161-164` |
| "Alpaca's **paper** environment does better" | `README.md:162` |
| "Add a free paper key … and SONAR uses it"; "is more honest — real market hours…" | `static/docs.html:514-519` (in-app Learn tab via `ui/learn.py`) |
| "it is where Alpaca already sits, it is what the Book tab calls, and `default_broker()` picks it up automatically" | `GOING_LIVE.md:103-104` |
| "Alpaca PAPER trading (sonar/alpaca.py)" above the key slots, with no "not used yet" | `.env.example:5-7` |
| `alpaca.py` … "dormant real-money code" (it is paper-only) | `README.md:339` |

Code: `sonar/core.py:163` and `:959` build `portfolio.Portfolio(path)` with no broker, so it is
always `PaperBroker` (`portfolio.py:193`). `portfolio.default_broker()` (`portfolio.py:137`) has no
caller in `sonar/`, `ui/` or `main.py`. `alpaca.available()` is not called from the UI.

**Who is hurt and how:** a retail user without finance training adds PK keys because the docs call
Alpaca "more honest". They then read the book as the realistic version. In fact the book still
fills instantly at the quoted price, exactly at target or stop, with no spread, slippage or fees,
and the same docs call that "an optimistic bound". This breaks the domain rule that every result
is shown as simulated, with its cost treatment. **Evidence:** code reading only; no user report or
telemetry. The harm is plausible, not observed.

## Target user
A SONAR user who reads the README or the Learn tab and has, or is about to add, Alpaca paper keys.

## Goal and success measure
**Goal:** every statement about which broker the book uses matches the code, and the cost
disclosure stays.

**Success measure (testable):** a new test, e.g. `tests/test_broker_docs_truth.py`, that:
1. **statically** scans `sonar/`, `ui/` and `main.py`. Every `Portfolio(` call passes no broker
   (neither positional nor `broker=`), and nothing calls `default_broker(`. Optional extra: build
   the book through the path `core.py` uses, with `alpaca.available()` patched to `True`, and
   assert `isinstance(book.broker, PaperBroker)`.
2. asserts `README.md`, `static/docs.html`, `GOING_LIVE.md` and `.env.example` do not contain the
   automatic-use or comparative claims: "picks them up automatically", "and SONAR uses it",
   "picks it up automatically", "where Alpaca already sits", "does better", "more honest".
3. asserts that the Alpaca section in `README.md` and in `static/docs.html` each:
   - say the book always uses the built-in simulator, and
   - contain "optimistic bound" and the fee disclosure ("slippage or fees") in that same section.
4. asserts `.env.example` contains "not used by the book".

If someone wires Alpaca later, check 1 fails, so the docs have to be rewritten along with the
code. If a later edit drops the cost disclosure, check 3 fails. The existing suite stays green
natively and offscreen.

## Options
| | Option | Cost | Verdict |
|---|---|---|---|
| A | **Correct the docs** and add the test | XS, docs + 1 test | **Approved** |
| B | Wire `default_broker()` into `core.py` | M–L: needs `client_order_id` on submit, `AlpacaPaperBroker.settlements()`, an open → fill → close test against a stubbed Alpaca, and a guard on `execute` (`docs/audit/security.md:85`) | Non-goal. Today every Alpaca position would stay PENDING forever |
| C | Delete the Alpaca section entirely | XS | Rejected. It hides a real, guarded module and the reason the book is an optimistic bound |

## Scope (option A)
- **`README.md:159-164`:** replace the paragraph with the Design wording below. Remove "Alpaca's
  paper environment does better". Anything that stays about Alpaca must be conditional (e.g. "once
  connected, Alpaca paper would add real market hours and order handling"). Nothing may compare
  Alpaca with the current book.
- **`static/docs.html:514-519`:** the same correction. Remove "is more honest…" or rewrite it
  conditionally. Rename the heading, e.g. "Alpaca paper (not connected yet)". Keep the guards
  warning.
- **`GOING_LIVE.md:103-104`:** drop "where Alpaca already sits". Say `default_broker()` exists but
  has no caller, and that the Book tab builds the internal `PaperBroker`. Leave `GOING_LIVE.md:259`
  and `TODO.md:81` as they are; they describe the function correctly.
- **`.env.example:5`:** add "not used by the book yet".
- **`README.md:339`:** change "dormant real-money code" to "paper-broker adapter and dormant
  execution guard". The line also lists `costs.py`, `universe.py` and `venues.py`, so Build must
  keep the label true for every file on it.
- The test above.
- **Merge note:** `.claude/worktrees/merge-all/` holds copies of the same false claims in README,
  docs.html and GOING_LIVE.md. Do not touch that worktree in this change. Whoever merges it later
  must resolve conflicts in favour of this fix. The phrase checks will flag any claim that slips
  back in.

## Design (user-visible copy)
Only a short copy pass is needed, not a full Designer phase. Use the domain reviewer's wording in
both README and docs.html:

> The book always uses the built-in simulator: instant fills at the quoted price, exactly at target
> or stop, with no spread, slippage or fees. That makes its results an optimistic bound, not a
> forecast. SONAR includes a guarded Alpaca **paper** adapter, but the book does not use it yet, so
> adding Alpaca keys does not change the book's results.

No "should", profit or edge wording.

## Architect
Not needed. There is no production code change, only docs and one test.

## Non-goals
- Wiring Alpaca into the book (option B), recorded in `SUGGESTIONS.md` #18.
- Docstrings in `portfolio.py` and `execution.py`. They are not shown to users and describe
  `default_broker()` correctly.
- The `SUGGESTIONS.md` Done row "Providers, Alpaca paper trading…", which is a history log.
- Any live or real-money path (invariant).

## Open questions
1. Does the owner want B planned at all? If not, `SUGGESTIONS.md` #18 moves to Rejected.

## Risks
- The copy could over-correct into "Alpaca is broken". Mitigation: say "not connected yet".
- The phrase checks are brittle. Mitigation: check 1 (static, the code fact) carries the weight.
  The phrase checks only guard the known false claims and the disclosure.
- Build owes a `CHANGELOG.md` entry per `VERSIONING.md`.
- The jurisdiction of users is `UNVERIFIED`. If this copy is ever published outside the app, the
  performance-advertising questions go to a qualified human (per the domain review).

## Domain review
`docs/audit/book-broker-truth-domain-finance.md` (2026-10-12) had no P1s and said the spec could
proceed once P2s were folded in. All findings are folded in:
- **P2-1:** check 1 is now static, with the `isinstance` check optional.
- **P2-2:** the comparative wording is removed or made conditional.
- **P2-3:** the test now asserts the disclosure and the `.env.example` text.
- **P3-1:** the Design section uses the reviewer's wording.
- **P3-2:** `GOING_LIVE.md:103` and `README.md:339` are in scope, and the merge-all note is added.
- **P3-3:** the docs.html range is corrected to 514-519.
