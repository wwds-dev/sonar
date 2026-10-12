# Security review: untrusted-text-sweep (S-B, S-C, S-D), 2026-10-12

Reviewer: security-engineer agent (read-only; saved by the orchestrator). Playbook
`status: baseline`: stale.

**Verdict: S-B, S-C, S-D closed as described; no P0-P2; three new P3 found by a full sweep.**
`html.escape(quote=False)` is sufficient at all nine sites: every value lands in element text;
the only interpolated attribute is `style='color:{colour}'` from a constant lookup. (If one ever
moves into an attribute, `quote=False` becomes wrong.)

Evidence: offscreen `test_untrusted_text.py` 28 passed; Qt probe confirms `QLabel` defaults to
AutoText and `QTextBrowser.openLinks()` to True; `_clean` output can never hold a tag. No
dependency change; pip-audit unavailable.

Sweep: `learn_view` static and links-off; `lab_out`, `playmaker_out` fixed; no
`insertHtml`/`appendHtml`; only `Qt.RichText` is the constant banner (`ui/app.py:1391`); no
`QMessageBox` or `linkActivated`. Screener card `s["name"]` (`ui/app.py:781`): WATCHLIST constants
locally (`sonar/assets.py:404`, `468`; `universe.fetch_universe` has no caller); the holder's
`/api/assets` in follow mode (S-F).

## Findings
| # | Pri | Where | Finding | Fix |
|---|---|---|---|---|
| S-E | P3 | `sonar/events.py:132-140` -> `EventRow` labels `ui/app.py:868-875` | Nasdaq IPO `companyName`, ticker, price and earnings `symbol` drawn in AutoText labels; local mode, third-party data. Spoofed styling or wording (honesty invariant), local `<img>`. | PlainText on the labels or `_clean` the fields; test with markup. |
| S-F | P3 | Follow mode: AssetRow (606, 615, tooltip 622), SuggestionCard (781-783, 830), `assets['error']` (3878), alert_list, cal_verdict, grade_verdict, regime_sub, mvm, PositionRow | Holder JSON stored as-is (`sonar/core.py:1063`, `1088`, `1101-1106`, `1148-1151`) and drawn AutoText / in a tooltip. Lock file is user-owned: defence in depth. `_fetch` accepts any scheme (same user). | `label()` PlainText by default (banner already opts in); clean the tooltip; optionally restrict the follow URL to localhost http. |
| S-G | P3 | `ui/app.py:2544-2547` `rep_card` | QTextBrowser with `openLinks` True; content app-generated. | `setOpenLinks(False)` + assertion. |

Not verified: native run, full suite, live Nasdaq payloads with markup.

## Dispositions (orchestrator)
- S-E, S-F: fixed at the choke point: `label()` sets `Qt.PlainText` (the banner's explicit
  `RichText` stays; a test asserts it is the only rich label in the window), and the AssetRow
  tooltip `_clean`s name, symbol, class and rationale. Tests: `test_every_themed_label_is_plain_
  text_unless_it_opts_in` (incl. EventRow), `test_an_asset_tooltip_never_carries_markup`.
- S-G: fixed, `test_the_replay_card_follows_no_link`.
- Restricting the follow URL to localhost: open (same-user only; not in this task).
