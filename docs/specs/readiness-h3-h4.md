# Spec: Playmaker stake on an unmeasured interval (H3) and the v2.406 release record (H4)

- Status: built (2026-11-18: playmaker `d20e54b`; H4 records written). Review and Verify still to run
- Owner approval: 2026-11-18, Define + Architect ("Fix H3 and H4", then "Approve as written");
  recorded in `docs/foundry/approvals.jsonl`. H4: the owner says the v2.406 install was deliberate ("Yes,
  deliberate") and will run the smoke test themselves ("Skip, I'll run it").
- Source: `docs/audit/code-readiness-2026-11-18.md` H3, H4. Session-owned slug: `readiness-h3-h4`.

## Problem

**H3.** Playmaker's cross-book stake (`ui/app.py:4274-4286`) is sized by `staking.from_consensus`, which returns a
zero-width interval when the peer books show no spread (`sonar/playmaker/staking.py:101-102`), and full Kelly is then
taken at that "low end". Books A and B at -110/-110 and C at +105/-125 stake **2.38% of bankroll**, with the note
"sized at the low end of the interval (50.0%)". When there is spread, the interval uses z = 1.96 whatever the number
of peers; with two peers (one degree of freedom) Student's t is 12.7, so the interval is about 6.5 times too narrow.
`devig.Opportunity.is_outlier` treats an undefined z (no spread) as an outlier and uses a fixed 2.0 for any peer count.
This is the one figure in the repository a reader could act on with real money at a bookmaker.

**H4.** The agent was restarted onto v2.406 on 2026-11-17 21:02 (`/Applications/SONAR.app` installed 21:01:56). No
release report, no CHANGELOG entry (the newest is v2.366; the legal fixes still read "Unreleased — 2026-11-10"), and
four `TODO.md` items still say "Next: Review/Verify" for code that is live. Lab Hub's "Update now" rebuilds and
installs apps in place (`active/lab_hub/README.md` "Update now"), which fits the timing; the owner confirms.

## User and goal

H3 success measures (tests on `sonar_playmaker`):
1. The three-book case above stakes 0.00% and says why ("the other books show no spread, so the estimate's
   uncertainty is not measured; no stake").
2. With spread, the interval half-width is `t(0.975, books - 1) x se`: a two-peer interval is 12.71 se wide each side,
   and the old 1.96-se control (peers -110/-110 and -112/-108, previously 1.96%) stakes 0.
3. A row with no measured spread is not flagged "outlier"; an outlier needs |z| at or above the same t value.
4. Existing behaviour with real spread and many books is unchanged within the t vs 1.96 difference (the
   tight-books fixtures still flag their outlier and still stake the 5% cap).

H4 success measure: `docs/audit/release-v2.406.md` says what v2.406 contains, how and when it was installed, the
stamp and live health, and the smoke-test result (or why it was not run); CHANGELOG has a v2.406 entry; the four stale
TODO items say what is live and which phases are still owed.

## Scope / Non-goals

In (H3): `staking.from_consensus` (t-quantile; `measured` flag), `staking.kelly`/`assess` (no stake and its note when
unmeasured), `devig.Opportunity` (`peers`, `is_outlier` on t), `devig.screen` (sets `peers`), playmaker README and
MODELS §9 wording, tests. Not in: `from_market` (not used to size in the UI), the "best edge" cell (audit L5), odds
validation and duplicate books (M7, M8), the LLM prompt (M6).
In (H4): records only. No build, install or agent restart.

## Design

Stake block text when unmeasured: "no stake: the other books show no spread, so how sure the consensus is cannot be
measured". The estimate line keeps "(no spread)". With spread, the basis reads "N books, +/-X pts (t, N-1 df)".

## Architecture

- `Estimate` gains `measured: bool = True` (frozen dataclass; default keeps every other caller as it is).
  `from_consensus(cons, index, confidence=None)`: no spread (se 0 or NaN) returns width 0 with `measured=False`;
  otherwise `confidence` defaults to `t_975(cons.books - 1)` from a fixed table (df 1-30, then 40, 60, 120, inf =
  1.96; a df between rows takes the lower row, which is the wider interval). A caller passing `confidence` keeps it.
- `kelly()` returns 0 when `not estimate.measured`; `assess()` gives the note above. `can_size` stays a property of
  the source, so a consensus is still a sizeable kind of estimate.
- `Opportunity` gains `peers: int = 0`; `is_outlier` is `edge > 0 and z is a number and |z| >= t_975(peers - 1)`
  (2.0 when `peers` is unknown). `screen()` passes `peers.books`.
- Two existing tests build consensus from identical books and assert `can_size`
  (`tests/test_staking.py:55-58`, `tests/test_sports.py:164-167`); they stay true (the source may size) and keep
  passing. New tests carry measures 1-4. Mutation: z back to 1.96 fails measure 2; dropping `measured` fails measure 1.
- The CI pin for `sonar/playmaker` moves to the new commit.

## Risks and open questions

- Fewer stakes: many real markets have books that copy each other exactly; those now show no stake. That is the
  honest answer, and the screen still lists the price gap.
- H4 needs the owner: was the 2026-11-17 install deliberate, and may the release smoke test (it places one paper
  trade in the live book) run now?

## Verification plan

New and existing playmaker tests; full SONAR suite offscreen; mutation checks above. The smoke test only with the
owner's yes.
