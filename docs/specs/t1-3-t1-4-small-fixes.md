# Spec: T1-3 + T1-4 — an unstamped build starts; the LLM table grades only real calls

- Status: built (branch `fix/t1-3-t1-4`). Owner approval: delegated in chat 2026-10-10 ("go on").
- Source: `docs/audit/code-review.md` P2-11, P2-9. Small and behaviour-pinned; independent review
  skipped (two one-line-class fixes, each with a test that fails on the old code, 2 planted
  mutations caught); Security phase skipped (no network, auth or untrusted input).

## T1-3
`version.info()` returned no `dirty` key when neither a checkout nor a stamp existed, so
`tooltip()` (called while building the tray and a window widget) and `--selftest` raised
`KeyError('dirty')`. A bundle without its stamp could fail to start. Now `"dirty": False`.

## T1-4
`Engine.llm_calibration` scored an UNCLEAR read as a miss. The model says UNCLEAR mostly at low
conviction, so an LLM with no information showed 0% low and ~50% high — the "conviction tracks
reality" shape the table exists to test. UNCLEAR reads are now excluded from the hit rate and
counted (`unclear` per bucket, `n_unclear`).

## Verification
Full suite 1,666 passed natively and under `QT_QPA_PLATFORM=offscreen`.

## CHANGELOG draft
**An unstamped build starts, and the LLM table no longer invents skill from "unclear".**
