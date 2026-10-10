# App context: SONAR

## Product
SONAR is a notability scanner and paper-trading terminal (PySide6 desktop app plus a headless
agent). It asserts **no edge** (see `CONFIDENCE.md`). Users are retail investors without
finance training. Honesty is the product: any copy implying edge, profit or certainty is a bug.

## Stack
Python 3, PySide6 >= 6.6 (optional `anthropic` for the LLM read panel), pytest, PyInstaller
(`SONAR.spec`, `build_app.sh`), launchd for the headless agent, GitHub Actions
(`.github/workflows/tests.yml`). Data sources: Alpaca (paper), ESPN, news feeds.

## Commands
- Install deps: `pip install -r requirements.txt` (venv at `.venv`)
- Tests: `./run-tests.sh` (external watchdog; native), and
  `QT_QPA_PLATFORM=offscreen ./run-tests.sh` (offscreen). Both must pass. Run twice if flaky.
- Coverage: `coverage run --branch --source=sonar,ui -m pytest tests/`
- Build: `./build_app.sh`
- Release smoke test: launch the bundle, run one scan, place one paper trade, quit, relaunch
  with state intact; confirm the headless agent (`python main.py --headless`) is running and
  healthy.

## Docs and process files
`README.md`, `static/docs.html` (rendered by `ui/learn.py`), `CHANGELOG.md`, `VERSIONING.md`
(version and changelog format), `TODO.md` (backlog: priority, category, owner `@me`/`@ai`),
`SUGGESTIONS.md`, `TESTING.md`, `TESTPLAN.md`, `docs/ROADMAP.md`, `CONFIDENCE.md`,
`GOING_LIVE.md` (a plan only). UI: `ui/tabs.py`, `ui/theme.py`, `ui/words.py` (wording
conventions). Lab-wide rules: `../../AGENTS.md`.

## Architecture hot spots
Engine single-writer lock and follow mode; QThread use; state-file recovery; provider
fallbacks; nested repos `sonar/macro`, `sonar/playmaker`; `SONAR_DATA` points the agent at the
app's Application Support directory.

## Security surface
`sonar/server.py` (localhost HTTP); keys and tokens (`.env`, Application Support);
`sonar/llm.py` and `sonar/news.py` (untrusted text into prompts, prompt injection);
`sonar/alpaca.py` and `execution.py` (paper-only guard); file writes under `SONAR_DATA`;
`requirements.txt`; `SONAR.spec` / `build_app.sh` (signing, bundled secrets); launchd plist.

## Test bar
80% branch coverage; the two-run rule for flakiness (see `TESTING.md`); the suite builds real
`MainWindow`s, so the external watchdog in `run-tests.sh` is required.

## Invariants
- **Real money is out of scope** until the owner says otherwise in writing. `alpaca.py` must
  keep refusing any non-paper host; `GOING_LIVE.md` stays a plan.
- No copy that implies edge, profit or certainty.
- Concurrent sessions share this worktree: stage files by name, never `git add -A`.
- Do not commit, push or release unless the owner asks.
- Model-risk checks (for `model-validator`): look-ahead and survivorship bias, costs and
  slippage, multiple testing, calibration sample size with intervals, `1/(1+R:R)` identities,
  Brier logs; model files `sonar/model.py`, `scoring.py`, `backtest.py`, `calibration.py`,
  `volatility.py`, `replay.py` and the research studies.

## Optional roles installed
model-validator
