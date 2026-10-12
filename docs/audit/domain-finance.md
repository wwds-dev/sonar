# Domain audit: finance (sonar), 2026-10-12

> Orchestrator note: run as `/audit sonar domain` by the `domain-finance` reviewer (read-only).
> P1-1 re-checked by the orchestrator: `default_broker` has no caller in `sonar/`, `ui/` or
> `main.py`, and `core.py:163` and `:959` build `Portfolio(...)` without a broker.

**Playbook status:** `docs/playbooks/domain-finance.md` is `status: baseline` (last reviewed 2026-10-12). It was seeded from the agent prompt and has not been verified by a radar run. None of the regulatory references in it (SEC Marketing Rule, FINRA, ESMA/BaFin, MiFID II, GIPS) were re-checked against primary sources in this audit. Where a finding names one of them, read it as "not verified". The app context sets user jurisdiction to `UNVERIFIED`. I am not a lawyer or regulator. Items marked **[qualified human]** need someone who is.

**Scope:** app-context `## Domain specialist` and `## Invariants`; `sonar/alpaca.py`, `portfolio.py`, `execution.py`, `costs.py`, `scoring.py`, `calibration.py`, `backtest.py` (header and verdict copy), `core.py` (book wiring, marking, trade path), `assets.py` (plan and universe), `horizon.py`, `risk.py`; UI copy in `ui/app.py`, `ui/tray.py`, `ui/words.py`; `static/docs.html`, `README.md`, `CONFIDENCE.md` §13, `GOING_LIVE.md`. I ran `tests/test_alpaca.py` (17 passed). I did not run the full suite.

---

## P0
None found. The paper-only guard holds (see "Checked, nothing found").

## P1

**P1-1. The docs say SONAR uses Alpaca paper when keys are set, but the book never does, so users read optimistic results as realistic.**
- **Where:** `README.md:161-164` ("SONAR picks them up automatically"), `static/docs.html:515-519` ("Add a free paper key … and SONAR uses it"), `GOING_LIVE.md:103-104` ("it is what the Book tab calls, and `default_broker()` picks it up automatically").
- **Code:** `sonar/core.py:163` and `sonar/core.py:959` build `portfolio.Portfolio(...)` with no broker, so it is always `PaperBroker` (`portfolio.py:193`). `portfolio.default_broker()` (`portfolio.py:137`) has no caller in `sonar/`, `ui/` or `main.py`.
- **Rule:** playbook "Simulated or paper results are labelled as such … never presented as returns a user could have achieved". App-context: every result shown as simulated/paper, with its cost treatment.
- **Scenario:** a user adds PK keys because the docs call the Alpaca path "more honest". They then read their book (instant fills at the quoted price, fills exactly at target/stop, no fees) as the realistic version. The docs themselves call the internal book "an optimistic bound".
- **Latent defect if it is ever wired as-is:**
  - `AlpacaPaperBroker` is `synchronous = False` (`alpaca.py:125`).
  - It returns `order_id`, not `client_order_id` (`alpaca.py:188-190`), and has no `settlements()` method.
  - So every Alpaca position would stay PENDING forever (`portfolio.py:372-374`, `398`). Its long cash would stay reserved, and `mark()` skips pending positions (`portfolio.py:438`).
- **Fix:** either correct the three docs to say the book always uses the internal simulator, or wire the broker deliberately. Wiring needs `client_order_id` on submit, a `settlements()` method and a test that runs a full open → fill → close against a stubbed Alpaca.

## P2

**P2-1. Non-USD instruments are booked and shown in "$" with no currency conversion.**
- **Where:** `sonar/portfolio.py:245-263` (enter sizes and charges in the instrument's quote currency), `portfolio.py:450-460` (equity sums them), `ui/app.py:964`, `ui/app.py:2231-2239` ("$" on equity, invested, cash).
- **Affected rows:** the watchlist includes `^N225`, `^KS11`, `^BSESN`, `^GDAXI`, `USDJPY=X`, `EURJPY=X`, `USDSEK=X` and others (`sonar/assets.py:~104-139`). Nothing in `portfolio.py` or `assets.py` handles currency.
- **Rule:** playbook "currency on every amount".
- **Scenario:** take a long USD/JPY at 150 with a 1% horizon move.
  - Sizing gives about 66.7 USD of exposure.
  - The book charges "$10,000 invested" and reports "$100 at risk".
  - The real-currency equivalent is about 100 JPY (≈ $0.67).
  - On Nikkei or DAX rows, P&L leaves out the FX move entirely.
  - A user without finance training reads these dollar figures literally.
- **Fix:** either convert each position to the book currency at entry and at mark (Frankfurter is already a provider), or keep non-USD rows out of the book and say why. At minimum, label the amounts in the quote currency.

**P2-2. Long horizons can produce impossible plans: a short target or a long stop at or below zero, still shown with P(profit) 40%.**
- **Where:** `sonar/scoring.py:244-252` (arithmetic barriers with no floor); `horizon.py` YEAR `momentum_days=250`; `core.py:356` and `core.py:533` pass `momentum_days` as `horizon_days`.
- **Verified:** `build_plan(100, 0.045, 250, "SHORT")` gives target −6.73 with p_profit 0.40. `build_plan(100, 0.07, 250, "LONG")` gives stop −10.68.
- **Thresholds:** at the year horizon the short target is ≤ 0 once daily vol ≥ 4.2%, and the long stop once it is ≥ 6.3%. Only the conservative profile caps vol (4%, `risk.py:81`); moderate (the default) and aggressive do not.
- **Rule:** domain arithmetic at the edges; app-context "money arithmetic … in `scoring.py`".
- **Scenario:**
  - A short with a negative target can only close at its stop or by hand, yet the screen and the calibration record say 40%.
  - Protocol mode picks the direction by coin flip (`core.py:355`), so these plans also enter the calibration table.
  - The driftless arithmetic-walk approximation is also poor once σ_h is above ~50%.
- **Not verified:** whether any listed instrument's forecast vol currently passes 4.2%.
- **Fix:** refuse (or cap σ_h for) plans whose barrier would be ≤ 0 or beyond some fraction of price, or switch to log-space barriers. Add edge tests.

**P2-3. Paper entries can be booked at a price that is up to an hour old, with no warning.**
- **Where:** `core.py:515-535` (`trade`) and `core.py:340-358` (protocol) feed `asset["price"]` into `portfolio.enter` (`portfolio.py:245`). Nothing checks `data_age_s`.
- **Context:** README:196-201 says rows are refreshed 26 at a time and can be more than an hour old (red in the Updated column).
- **Rule:** playbook "stale data is marked stale". Paper results must not be presented as achievable.
- **Scenario:** the user presses Buy on a row whose price is stale after a move they have just seen in the news. The entry is booked at the old price, which flatters the result in a way no real order could. The next refresh can then hit a barrier at once, adding noise to calibration.
- **Fix:** refuse, or warn and refetch, when `data_age_s` is above a threshold at entry. Store the price's age on the `Position`.

## P3

**P3-1. Calibration copy says "promised".**
- **Where:** `ui/app.py:2037`, `ui/app.py:2132` ("the plan promised N%"), `ui/app.py:2136` ("% promised"), `sonar/calibration.py:221`, `static/docs.html:817`.
- **Rule:** app-context "No copy that implies … certainty".
- **Scenario:** "promised" frames P(profit) as an undertaking. Elsewhere it is correctly called "advertised" (`calibration.py:86`).
- **Fix:** use "the plan's odds" or "the baseline".

**P3-2. The tray tooltip shows the model–market gap as "edge", signed, with no proven check.**
- **Where:** `ui/tray.py:170-173` ("edge +3.2¢").
- **Contrast:** the main window mutes this figure until the model is proven (`ui/app.py:3608-3618`), and plain wording calls it "we disagree by" (`ui/app.py:385`).
- **Rule:** never claim edge.
- **Fix:** reuse the plain label and drop the signed "edge" until `model_better` is true.

**P3-3. "Live trades" wording on a paper terminal.**
- **Where:** `ui/app.py:1578-1580` ("Settled live trades", "Share of live trades won").
- **Problem:** here "live" means "not warm-up", but a reader can take it to mean real money.
- **Fix:** use "paper trades since start" or "forward trades".

**P3-4. The cost ledger's bps figure is labelled per side but is per round trip, so the documented number is 2× too high.**
- **Where:** `sonar/costs.py:97-99`. It divides the round-trip cost by half the summed buy and sell notional. That gives cost per one-leg notional, which is round-trip bps.
- **Docs:** `CONFIDENCE.md:550` reports "50.0 bps per side" for inputs of 0.2% fee + 5 bp slippage. That is 25 bp per side; the €1.05 total is consistent with this.
- **Impact:** it is conservative and not shown in the UI, but it is wrong money arithmetic in a go-live input.
- **Fix:** divide by the full summed notional (or relabel as round trip), and correct CONFIDENCE.md.

**P3-5. The book's calibration baseline ignores a bias the code itself documents.**
- **Where:** `calibration.py:18-21` states that a driftless walk watched at discrete marks lands at 40.6–41.3%. `report()` still tests against the untimed `p_profit` (40%) (`calibration.py:157-163`), and fills are booked exactly at the barrier (`portfolio.py:442`).
- **Scenario:** with a large n, "outside the noise" (`calibration.py:222-224`) could appear with no edge at all. That is unlikely within a year at ≤ 10 positions a day.
- **Fix:** compare against a marked-walk baseline, or state the bias next to the verdict. This belongs to model-validator.

**P3-6. The calibration verdict has no period and no cost treatment next to it.**
- **Where:** `ui/app.py:2119-2163` shows n and the hit rate, but not the date range of the graded positions or "before costs, instant fills".
- **Rule:** app-context: figures carry period, sample size and cost/slippage treatment.
- **Fix:** add "N positions, first–last date, paper fills at target/stop, no fees".

**P3-7. README calls `alpaca.py` "real-money code".**
- **Where:** `README.md:339` ("alpaca.py execution.py … dormant real-money code").
- **Problem:** this contradicts the invariant and `alpaca.py:28` ("Nothing here can be pointed at real money").
- **Fix:** "paper-broker adapter and dormant execution guard".

**P3-8. A README glossary line is wrong.**
- **Where:** `README.md:25`: a bigger R:R "lowers the hit rate by the same proportion".
- **Problem:** going from 1:1 to 1.5:1 moves P from 50% to 40% (−20%) while R:R rises 50%.
- **Fix:** "lowers the hit rate so that expected value stays zero".

**P3-9. Product/venue naming and a Buy prompt next to "worth a look" [qualified human].**
- **Where:** `ui/app.py:2178-2181` (Start card: "pick a row marked 'worth a look' … Press Buy or Short") and `ui/app.py:576-579` (per-row tooltip naming the products and brokers to buy).
- **What is in place:** both carry disclaimers ("never which way", "Reference only — not advice").
- **Open question:** whether instrument-specific product and venue naming next to a Buy action counts as an investment recommendation under ESMA/BaFin or MAR rules is **not verified**.
- **Suggestion:** a qualified reviewer decides. Meanwhile, add "not advice" to the Start card.

**P3-10. `AlpacaPaperBroker._verify` checks for an account number starting "LIVE".**
- **Where:** `alpaca.py:167-168`.
- **Problem:** that convention is not verified, so the check is probably a no-op. The host constant and the PK key check carry the real protection.
- **Fix:** drop the claim "the account is checked on connect" (`docs.html:524`), or check a documented field.

---

## Checked, nothing found
- **Paper-only guard** (`alpaca.py`):
  - The host is a module constant, compared by exact equality, so lookalikes are refused.
  - Keys must start with `PK`; anything else is refused before any request.
  - Checks are re-run on every `_request`.
  - `live = False` on both brokers.
  - No other `alpaca.markets` reference anywhere in `sonar/`, `ui/`, `scripts/` or `main.py`.
  - `tests/test_alpaca.py` passes (17).
- **`GOING_LIVE.md`** stays a plan: "Nothing in this document has been applied" (line 7) and "Out of scope until the owner says otherwise in writing" (line 476). The tax section is flagged "not advising".
- **`execution.py`** ships only `SimBroker` ("no network, no money"). Caps, the fail-closed allowlist and the confirmation default all refuse. Slippage sign conventions are correct.
- **Scoring maths:** `1/(1+R:R)`, EV = 0 and `grade()` always return "unproven" in production (`edge_sigma` is never non-zero; `assets.py:482-493`). `position_size` is correct.
- **Book arithmetic:** long/short cash flows, cancel/reopen symmetry, −0.00 handling, equity-log refusal on missing prices, and the warm-up kept out of the bankroll (`engine.py:230-257`).
- **Paper labelling** is everywhere: the "Practice money only" chip (`app.py:1264`), toasts, the tray, the Book start card and the docs.
- **Backtest copy:** costs excluded and said so, "before costs … not a finding", survivorship disclosed, sample size and period stated (CONFIDENCE.md: 25,504 setups, 5 years, 113 instruments), the withdrawn +4.9 pt result recorded.
- **Copy scan:** no instance of "guaranteed", "risk-free", "beat the market" or "should buy/sell". README and docs carry a "Not advice" section.
- **Staleness** is shown on the screener (Updated column, alert ages), and the venue list shows its CHECKED date (2026-09-12).

## Not verified
- All regulatory standards in the playbook watch list (SEC/FINRA, ESMA/BaFin, MiFID II, MAR, GIPS). The playbook is still baseline.
- Alpaca key-prefix (`PK`/`AK`) and account-number conventions.
- Live vol levels per instrument, so I could not confirm that P2-2 currently triggers.
- Accuracy of the venue/product table (`sonar/venues.py`) and the German tax figures in `GOING_LIVE.md` §9.
- The full test suite and coverage (not run).
- `static/index.html` (BTC terminal) copy, Playmaker and macro sub-repos, and the `research/` study code (model-validator scope).
