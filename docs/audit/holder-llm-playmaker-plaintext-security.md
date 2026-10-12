# Security review: holder-llm-playmaker-plaintext (P3-2, P3-5, S3), 2026-10-12

Reviewer: security-engineer agent (read-only; saved by the orchestrator). Playbook
`status: baseline`: stale.

**Verdict: no P0-P2.** The diff opens no injection path. Model replies and feed headlines now reach
only plain-text or escaped sinks (ReadPanel `ui/app.py:1079-1082`; playmaker narrative
`html.escape`d `3355-3375`; headlines `795-796`, `852-853`, `3881`). Remaining rich-text paths carry
the owner's own paste, local exception text, or the localhost holder's text: all P3.

## Evidence
- Offscreen: test_untrusted_text + test_llm + the new follow test `59 passed`. Native not run.
- `_clean` probe: full-width `＜img＞` is NFKC-folded then stripped; entities survive harmlessly.
- No dependency change; pip-audit not run.

## Closed by the diff
`sonar/llm.py:361` `complete()`, `ui/worker.py:45` ReadThread, `ui/worker.py:140` PropThread:
`_clean(…, 160)`. `ui/app.py:3095` `playmaker_status` PlainText (covers `3224`, `3350`).
The `_holder_llm` reset fails closed ("has not said yet"); nothing new is allowed.

## Findings
| # | Pri | Where | Finding | Fix |
|---|---|---|---|---|
| S-A | P3 (new) | `sonar/core.py:671-677` | Check-then-use: `_follow` can set `_holder_llm` to None between the test and the unpack (TypeError in the UI slot `ui/app.py:3660` or `/api/config`). Not reproduced. | Read each attribute once into a local. |
| S-B | P3 | `ui/app.py:3225`, `3279`, `3299` -> `3321` `playmaker_out.setHtml` | Parse errors quote the pasted book name (`sonar/playmaker/devig.py:331-333`, `200`); book names also go raw into `_devig_html`/`_screen_html`. Self-injection only (owner's paste). `setOpenLinks` not set (default True): a pasted `file://` link could load a local file into the pane (not verified). | `html.escape` at the three sites; `setOpenLinks(False)`; a test with book `<b>x</b>`. |
| S-C | P3 | `ui/worker.py:78` -> `lab_out.setHtml(_lab_html(r))` (`ui/app.py:2766/3501`, `2783`, `2857`) | BacktestThread's raw exception text goes into HTML unescaped; no route from a server body found. `lab_out` lacks `setOpenLinks(False)`. | `_clean` in the worker; `html.escape` in `_lab_html`; `setOpenLinks(False)`. |
| S-D | P3 | AutoText `status` (`ui/app.py:1360`), `_bar_status`/`_toast_label` (`4198-4199`), `bt_result` (1950), `sm_result` (2582) | Raw exception text and the followed holder's mirrored `detail` (`sonar/core.py:897`, `1079-1083`, `640`, `1110`, `1193`; `ui/worker.py:94`, `118`). Holder URL comes from a lock file only the user can write: defence in depth. | PlainText on those labels and `lab_status`; `_clean` on the listed catch-alls. |

Not verified: native run; QTextBrowser link behaviour (from Qt defaults); the source of the
screener card's `s["name"]` (`ui/app.py:780`).

## Dispositions (orchestrator)
- S-A: fixed (locals in `llm_available`, with the code review's P3-1/P3-3 change).
- S-B, S-C, S-D: open, outside this task; proposed as one follow-up "untrusted-text sweep".
