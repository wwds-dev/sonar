# Spec: T1-8 — the order guard fails closed; untrusted text stays text

- Status: built (branch `fix/t1-8-security`). Owner approval: delegated in chat ("go on").
- Source: `docs/audit/security.md` P1-2, P2-1, P2-3, P2-4, P3-4 (MarketWatch over http).
- Review: `docs/audit/t1-8-security-security-engineer.md` — no P0/P1; both P2 and four P3 fixed.

## Changes
- **Guard** (`sonar/execution.py`): non-finite or non-numeric quantity, price or venue equity is
  rejected (NaN passed every cap, since every comparison with NaN is False; a string or Decimal now
  rejects instead of raising `TypeError`; `notional` tolerates them so `check()` can ask first).
- **Audit log:** `write()` returns whether it wrote; opened 0600 (an older log is chmod'd), fsync'd.
  `submit()` refuses to send if the "submitted" record cannot be written; the daily cap uses
  max(log count, this process's own per-day count). `flatten`/`panic` ignore the return value, so
  the kill switch fires with an unwritable log (reviewer checked).
- **Prompt** (`sonar/llm.py`): `_clean` (NFKC, no `<`/`>`, no control characters, capped) applied to
  headline source/title/age and to subject, kind, risk, horizon, measurement keys and non-numeric
  values — a title containing `</HEADLINES>` could close the untrusted block.
- **Window:** the Playmaker reply (sections, lean, confidence) is HTML-escaped before `setHtml`;
  the feed-fed labels (top headline on a card, the headline rows, the central-bank list) are
  plain-text.
- **MarketWatch** is fetched over https (`feeds.content.dowjones.io`, the 301 target).

## Residual risk
- A refused write leaves the intent in the process's `_sent` set: after the log recovers the same
  intent cannot be retried (fails closed; make a new intent).
- `os.fsync` on macOS does not flush the drive cache; durability is best-effort.
- Rich-text sinks not traced: `quote.book` in the devig HTML builders (user-typed odds input).
- `sonar/macro` and `sonar/playmaker` are gitignored nested repos: a clean clone cannot import
  `sonar.core` (T1-9, nested repos).

## Verification
Full suite 1,687 passed natively and under `QT_QPA_PLATFORM=offscreen`; 11 planted mutations caught
(one equivalent: `Guard.equity()` already maps a non-positive/NaN reading to None).

## CHANGELOG draft
**The order guard can no longer be talked past by NaN, and text from feeds and the model stays text.**
