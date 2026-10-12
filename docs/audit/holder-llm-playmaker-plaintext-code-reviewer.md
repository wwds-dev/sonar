# Code review: holder-llm-playmaker-plaintext, 2026-10-12

Reviewer: code-reviewer agent (read-only; saved by the orchestrator). Base `3a7e572`, uncommitted
diff. Spec `docs/specs/holder-llm-playmaker-plaintext.md`. Playbook `status: baseline`: stale.

**Verdict: no P0-P2. Four P3.** P3-5 and S3 done as specified; P3-2 fixed for the follow thread's
own path, with gaps below (each bounded by one slow mirror round, ~10 s).

## Evidence
- Offscreen: test_follow + test_llm + test_untrusted_text `94 passed`. Native not run.
- Race stress (scratch, `sys.setswitchinterval(1e-6)`): `_follow` cycling vs 300,000
  `llm_available()` calls: 0 exceptions (CPython 3.11, GIL).
- `following` is written only in `_follow` (`sonar/core.py:1072`) and init. `_holder_llm` is also
  written by `_mirror_config`, which runs on the follow thread *and* on `configure()`'s caller
  (`ConfigThread`, `ui/worker.py:92`; HTTP handler, `sonar/server.py:122`).
- Private `_clean` import across modules matches practice (`sonar/replay.py:38`,
  `sonar/institutions.py:108`).

## Findings
- **P3-1** `sonar/core.py:617-629`, `1158-1161`: a `configure()` in flight for holder A can write A's
  answer after `_follow(B)` reset it; B is then shown A's answer until B's next config. Fix: key the
  answer by URL, or write only if `url == self.following`.
- **P3-2** `tests/test_follow.py:620-634` pins `_follow` but not the loop's use of it: reverting
  `core.py:1055` to `self.following = url` survives (36 passed). Fix: a loop-level test with
  `_mirror` stubbed.
- **P3-3** `sonar/core.py:1070`: reset keyed on URL only; a holder restarted at the same address
  (new pid, maybe another SDK) keeps the old answer. `llm_available` reads `following` and
  `_holder_llm` twice (`core.py:671/673`, `674/676`); `_holder_llm` can now go back to None between
  them (TypeError; not reproduced, atomic in practice on 3.11). Fix: key on `(url, pid)`; read once
  into locals.
- **P3-4** Other AutoText sinks of raw exception text (local/localhost sources, not model text):
  `ui/worker.py:94` ConfigThread and `sonar/core.py:638-640` -> `status` / `_toast_label`;
  `core.py:1107-1109` follow-failure detail; `ui/worker.py:78` BacktestThread -> `bt_result`;
  `ui/worker.py:118` SportsMeasureThread -> `sm_result`; the spec's non-goal `ui/app.py:3225`.

## Dispositions (orchestrator)
- P3-1, P3-3: fixed. `_holder_llm` is `(url asked, ok, detail)`; `llm_available` reads
  `following` and the answer once and ignores an answer for another URL; `_follow(url, pid)` resets
  on a change of either. Tests `test_an_answer_from_the_last_holder_is_not_shown_for_the_next`,
  `test_a_new_holder_has_not_answered_for_the_old_one` (restart case added).
- P3-2: fixed. `test_the_follow_loop_resets_the_answer_when_the_holder_changes` (mirroring
  stubbed; holder A -> B -> B with a new pid). Loop bypass, loop without pid, pid ignored and the
  URL key removed each fail it or its siblings.
- P3-4: open, follow-up (same list as security S-C/S-D).
