# Spec: untrusted-text sweep (security S-B, S-C, S-D; code review P3-4)

- Status: built (branch `untrusted-text-sweep`, from `c4847c5`)
- Owner approval: asked for in chat 2026-10-12 ("do the untrusted-text sweep next").
- Source: `docs/audit/holder-llm-playmaker-plaintext-security.md` S-B, S-C, S-D;
  `docs/audit/holder-llm-playmaker-plaintext-code-reviewer.md` P3-4.
- Phases: defence-in-depth fixes, no visible change for ordinary text. Define/Design/Architect
  skipped (no state, concurrency or module change). Secure required (untrusted input).

## Problem
Text that is not the app's own reached Qt widgets that draw markup:
- S-B: the Playmaker pane (`QTextBrowser`, rich text) got pasted book names raw in the fair-price
  block and the cross-book screen, and the parser's error (which quotes the name) raw. Links in the
  pane were followable (`openLinks` defaulted to True), so a pasted `file://` link could load a
  local file into it.
- S-C: the Lab pane got a backtest's `verdict` (a raw exception on failure), and the attribution
  block's `note`, `why` and `catalyst`, unescaped; same `openLinks` default.
- S-D: the status line, its collapsed-bar copy, the toast, `bt_result`, `lab_status` and `sm_result`
  were AutoText labels fed raw exception text and the followed engine's mirrored `detail`.
  `ConfigThread`, `BacktestThread`, `SportsMeasureThread` and seven `sonar/core.py` sites put
  `f"{type}: {exc}"` (or `str(exc)`) into those strings uncapped.

## Change
- `ui/app.py`: `html.escape(…, quote=False)` on the book names (`_devig_html`, `_screen_html`), the
  price parse error, the Lab verdict (both paths) and the attribution `note` (both paths), `why`,
  `catalyst`. `setOpenLinks(False)` on `playmaker_out` and `lab_out`. `Qt.PlainText` on `status`,
  `_bar_status`, `_toast_label`, `bt_result`, `lab_status`, `sm_result`.
  `quote=False`: text content needs no quote escaping, and `&#x27;` broke an exact-text test.
- `ui/worker.py`: the three remaining catch-alls use `_clean(…, 160)`.
- `sonar/core.py`: `_exc_line(exc)` (= `llm._clean(f"{type}: {exc}", 160)`) at the six UI-bound
  `{type}: {exc}` sites (assets error, configure/forward "did not confirm/take it", book read
  retry, poll error, follow failure); `llm._clean(exc, 160)` for the poll snapshot `detail`. The
  stderr-only print at `core.py:871` is unchanged.
- Component names are app constants: not escaped in the attribution table; escaped in the
  per-component "why" line alongside the reason (harmless, consistent within the line).
- `ConfigThread`'s error now carries the exception type ("Setting not applied: OSError: …"), as
  the other workers' do.

### Added after review
- `label()` sets `Qt.PlainText` by default (security S-E, S-F): Nasdaq calendar text in `EventRow`
  and the followed holder's JSON in rows, cards and verdicts are drawn as characters. The one rich
  banner opts in with `setTextFormat(Qt.RichText)`, as it already did.
- The AssetRow tooltip `_clean`s name, symbol, class and rationale (S-F).
- `rep_card.setOpenLinks(False)` (S-G).
- `pm_devig.consensus` moved inside the parse `try`: books disagreeing on the outcome count show
  "Could not read the prices." instead of raising in the slot (code review note).

## Success measure
`tests/test_untrusted_text.py`, 9 new tests; each planted mutation (one per site, engineer run,
file restored after each) fails one: the 3 book/parse-error escapes, both `setOpenLinks`, the Lab
verdict, the 4 attribution escapes, the 5 label formats (status, bt_result, lab_status, sm_result,
bar+toast), the 3 worker catch-alls, `_exc_line` itself and the poll-error call site. 20 of 20
killed. The other `core.py` `_exc_line` call sites are pinned only through the helper; the poll
snapshot `detail` has its own test. After review, 5 more tests: each of the poll `detail`, the
`label()` default, the banner's opt-in, the tooltip's name and rationale, `rep_card` links and the
consensus move fails one when reverted.

## Review
- Code review `docs/audit/untrusted-text-sweep-code-reviewer.md`: no P0-P2; four P3 handled.
- Security `docs/audit/untrusted-text-sweep-security.md`: S-B/S-C/S-D closed; S-E, S-F, S-G
  fixed; restricting the follow URL to localhost left open.

## Non-goals
- QA P2-7 (`libshiboken` teardown traceback).
- Restricting the follow URL to `http://localhost` (security S-F side note; same-user only).
