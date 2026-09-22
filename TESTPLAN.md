# SONAR v2 — acceptance test plan

The plan for signing off v2. `TESTING.md` is the *automated* coverage roadmap;
this is everything a person has to check, because the suite structurally cannot.

**Run it against `/Applications/SONAR.app`, not the checkout.** Several of the
failures below only exist in a packaged build — a module PyInstaller could not
see, a resource path that moves when frozen, a Qt plugin inherited from a parent
process. A green suite says nothing about any of them.

| | |
|---|---|
| Build under test | `./build_app.sh --install`, then `/Applications/SONAR.app/Contents/MacOS/SONAR --selftest` |
| Automated suite | `./run-tests.sh tests/ -q` — expect **1,339 passed** |
| Time to run this plan | ~30 minutes |
| Prerequisite | A working internet connection. Two cases deliberately need it off. |

**Run it from inside the app.** The **Test plan** button, next to *Learn*, opens
this as a page that remembers which cases you have passed or failed — a hundred
and seventeen of them is more than one sitting. The daemon serves it at `/testplan` too.

That page is *generated* from this file by `scripts/build_testplan.py`, which
`build_app.sh` runs before packaging. Edit the markdown, never the HTML.

**⚠ marks a case that has caught a real regression.** Those are the ones worth
running even when short of time — the list doubles as this project's bug history.

---

## 0. Before starting

| # | Step | Expected |
|---|---|---|
| 0.1 | `./run-tests.sh tests/ -q` | 1,339 passed, in about ten seconds. The suite is deterministic since 2026-09-19 — a wedge or a hang is a regression now, not a known issue. |
| 0.2 | `./build_app.sh --install` | Ends with `All checks passed.` then `Installed:` |
| 0.3 | `/Applications/SONAR.app/Contents/MacOS/SONAR --selftest` | `All checks passed.` Reports 7 sports, 5 rated, cycling with no feed. |
| 0.4 | Note the bankroll before you start | You will compare against it in 5.x |

---

## 1. Launch and window

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 1.1 | ⚠ | Launch from `/Applications`. Time it. | First paint in **under 3s**. *Once took 11s of sequential fetches.* |
| 1.2 | | Count the tabs, and read both lines on each | Eight, each showing a plain name over the name the docs use: Live model/TERMINAL · Screener/ASSETS · News/WIRE · My trades/BOOK · Big picture/MACRO · Practice/LAB · Sports/PLAYMAKER · Learn |
| 1.3 | | Wait 30s, visit each tab | No tab shows "—" in every field |
| 1.4 | ⚠ | Resize the display to 1280×800 (or check on a laptop screen) | Nothing clipped, no horizontal scroll. *Once opened 4,540pt wide on a 1,280pt display.* |
| 1.5 | ⚠ | Click the **red close button** | Window disappears; menu-bar icon stays; app still running. *Reported broken five times, five different causes.* |
| 1.6 | | Click the menu-bar icon | Window returns |
| 1.7 | ⚠ | Enter full screen, leave full screen, then close | Window hides and **does not reopen itself** a second later |
| 1.8 | | ⌘H, then click the Dock icon | Window returns |
| 1.9 | | Menu bar → **Quit SONAR** | Process exits. No crash dialog, no "Python quit unexpectedly". |
| 1.10 | ⚠ | Relaunch, then ⌘Q | Also quits cleanly. *macOS implements a quit by sending a close event to every window, so the hide-on-close guard once cancelled it and ⌘Q did nothing.* |
| 1.11 | ⚠ | Launch, and quit **within 5 seconds** — while the tabs are still filling — by ⌘Q. Repeat three times. | Gone each time, in about a second. *This is the one that produced the blank white window: a quit landing on an in-flight fetch terminated the poll thread, which never gave the GIL back, and the whole process froze with the window unpainted. Watch for a window that turns white and stops responding rather than closing.* |
| 1.12 | ⚠ | Relaunch. Leave it running **20 minutes**, clicking between tabs throughout, and close the window at the end | Stays responsive the whole time, and closes on the first click. *Two freezes hid here. The Wire's news TTL is 8 minutes and a UI-thread fetch froze the window white. The central-bank feed's is 15, and it was fetched while holding the lock the UI thread takes every second — no UI-thread fetch at all, and the same dead event loop: blank window, close button ignored, alive again a few seconds later.* |
| 1.13 | | Read the version beside the wordmark, and the window title | Both show the same `v2.NNN`. It matches `./build_app.sh` output and `python main.py --selftest` |
| 1.14 | ⚠ | Hover the version | Reports commit, date, packaged-vs-checkout, and whether a newer build exists. *It must never say "up to date" when it cannot know — a guessed answer here gets believed.* |

---

## 2. Terminal

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 2.1 | | Read the price | Live BTC price, moves within ~5s |
| 2.2 | | Read the stat row | `price · hour · model · market · edge · tau · bankroll · pnl · trades · win rate · profile` all populated |
| 2.3 | ⚠ | Compare the lattice caption's **P(up)** with the **model** figure above it | They agree. *They disagreed by 10 points at the top of every hour — one counted a bin sitting exactly on the barrier as a win.* |
| 2.4 | | Watch the lattice for a minute | Redraws as price moves; bars at/above the open are coloured differently |
| 2.5 | | Read the equity curve | Renders; a gold **LIVE** marker separates the warm-up from real trades |
| 2.6 | | Press **LLM read on this hour** | Either a read appears, or it says why not. With no API key, "off — no key" is the correct answer, not an error. |
| 2.7 | | Hover every number in the stat row | Each has a tooltip explaining it in plain words |
| 2.8 | | Read the **model vs market** line under the portfolio strip | States how many hours are scored and refuses a verdict below **100** — below the threshold it must not favour either side. |
| 2.9 | | Read the same line's health tail after a few hours of running | `coverage`, `voided` and `last settle` are present; coverage sits near 100% on an uninterrupted run; no ⚠ STALLED while hours are settling. |

---

## 3. Screener (Assets)

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 3.1 | | Count the rows | **129** instruments (50 Equity · 20 Index · 20 Forex · 21 Crypto · 18 Commodity) |
| 3.2 | | Read the columns | Plain wording: `What it is · Trend · Price · Today · Recent move · Swing size · In the news · If you traded it · Worth a look · Updated`. No abbreviations anywhere on the board. |
| 3.3 | | Read **If you traded it** down the column | "win 1.5× the risk / 40% of the time", flat. Anything else means calibration has moved it — check §5.5 agrees. |
| 3.4 | | Check **In the news** | Quiet / Normal / Elevated / Spike. **No bullish/bearish lean anywhere.** |
| 3.5 | | Read the banner above the board | Says the list ranks markets by how *interesting* they look, **not** by whether they will go up, and that nothing spends real money |
| 3.6 | | Click each of the three banner chips | Each opens the **Learn** tab with the matching section selected in the contents |
| 3.7 | | Click the headings drawn in blue | Opens Learn at the section explaining that column. The black headings (What it is, Trend, Price, Today, Updated) are not links — they explain themselves. |
| 3.8 | | Change **horizon** (5 options) | Numbers change; board redraws immediately, not on the next tick |
| 3.9 | | Change **risk profile** (3 options) | Same |
| 3.10 | ⚠ | Press **Buy** on a row | Status shows ✓ and "practice money only"; position appears in **My trades at once**. *A cached board signature once made this look like a dead button.* |
| 3.11 | | Press **Short** on a different row | Same, direction SHORT |
| 3.12 | | Press **Buy** on the same row again | Refused: "already holding" |
| 3.13 | | Hover a row's name | Names where it could actually be traded. 58 of 129 are proxied (indices via UCITS ETFs, futures via ETCs) and one — Monero — is not tradeable at all; it must say so rather than implying you can buy it. |
| 3.14 | ⚠ | Read the **Updated** column down the board | Ages spread from about a minute to about fifteen, and they **count up** while you watch — the board refetches only the 26 stalest of 129 per scan, so a frozen age means it is reporting the scan rather than the fetch. Gold past 20 minutes, red past an hour. *A price that is quietly out of date is the failure this app treats as unacceptable.* |
| 3.15 | | Read the line under each name | One plain phrase — "up hard, heavy news". It must describe the **past** only: nothing saying a market will rise, is a buy, or looks bullish. |

**Wording — plain and expert.** Same table, continuing the numbering: the
generator only accepts `\d+\.\d+`, so a `3a.1` renders without pass/fail buttons
and is silently dropped from the count.

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 3.16 | | Press **Wording: plain** | Becomes *Wording: expert*. Headings become `TREND · PRICE · 1D · MOM · VOL · NEWS · R:R · P(PROF) · CONF · AGE`, the ticker replaces the sentence under each name, the banner disappears, and the tab bar drops to one line of original names. |
| 3.17 | ⚠ | Compare the two boards side by side | **Same columns, same order, same widths.** Only the words and the row height change. *A mode that rearranged the board would be a second interface to keep true.* |
| 3.18 | | Check a stat strip on **Live model** | `TAU` in expert, `HOUR REMAINING` in plain — the captions follow the switch without a relaunch |
| 3.19 | | Switch to expert, quit, relaunch | Still expert. The choice is remembered in `wording.json` beside the other user data. |
| 3.20 | | Put junk in `wording.json` and relaunch | Opens in plain wording. A preference file a person can edit must not be able to break the app. |
| 3.21 | | Switch back to plain | Everything returns; no relaunch needed |

---

## 4. Wire

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 4.1 | | Read the newswire | Headlines with source and age, from more than one press bloc |
| 4.2 | | Find the bloc spread | Renders |
| 4.3 | | Find the earnings / IPO calendar | Populated with dates |
| 4.4 | | Read the alerts panel | Lists alerts, or says nothing is firing |
| 4.5 | ⚠ | Read every alert carefully | **None contains "buy", "sell", "short" or "immediately".** An alert is a notability flag, never an instruction. |

---

## 5. Book — the paper investment loop

This is the part that answers "would this position have been worth taking",
with no real money anywhere. **5.1–5.8 are the mechanics; 5.9–5.16 are the loop
that makes them mean something**, and that loop is the entire case for the app
existing. Some of it cannot be checked in one sitting — those cases say so.

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 5.1 | | Find the positions opened in 3.8 / 3.9 | Both listed with entry, target, stop, unrealised P&L, progress bar |
| 5.2 | | Check a LONG's barriers | stop < entry < target |
| 5.3 | | Check the SHORT's | target < entry < stop |
| 5.4 | | Press **close** on one | Settles at the current price, moves to closed, bankroll changes by that P&L |
| 5.5 | | Read the calibration table | Either reports, **or says how many more closed positions it needs**. It must not claim an edge below the threshold. |
| 5.6 | | Read the stats | bankroll · total P&L · win rate · profit factor. Profit factor is blank with no losses — not zero, not a crash. |
| 5.7 | | Press **run backtest** | Completes and reports; says it is price-only and excludes costs |
| 5.8 | | Quit and relaunch; return to Book | Open position and bankroll **survive the restart** |

### Evaluating a candidate before committing to it

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 5.9 | | On the Screener, pick a row and read **If you traded it** (expert: **R:R** and **P(PROF)**) | R:R 1.50 and P(PROF) 40% — and `0.40 × 1.50 − 0.60 = 0` exactly. The pair is **expected-value zero by construction**, not a forecast. |
| 5.10 | | Read **CONF** on the same row, then its tooltip | It says plainly that confidence is *notability*, **not** the odds of profit. If a row makes you feel it is a good bet, that is the number doing something it is not entitled to do. |
| 5.11 | | Open the position and read its **target** and **stop** | Both set from volatility, before entry. A position with no barriers never resolves and is never falsifiable. |
| 5.12 | | Change the **risk profile** and open a position on another row | Size changes, barriers do not: at €10,000 the cash at risk is ~€37.50 conservative, ~€100 moderate, ~€187.50 aggressive. Risk appetite moves the stake, never the plan. |

### The loop that makes it falsifiable

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 5.13 | | Leave a position open and watch it over a session | Unrealised P&L and the progress bar move with price. Progress is measured from the stop toward the target. |
| 5.14 | ⚠ | Leave positions open **over days**, until one touches a barrier | It closes **itself** — outcome TARGET or STOP, not MANUAL. Nothing about the app is falsifiable unless positions resolve without you. |
| 5.15 | | After a position resolves by itself, re-read the calibration table | The count of closed positions has gone up. It needs **20** before it will report anything at all. |
| 5.16 | | Once 20 have closed, read what calibration says | Either it measures drift and `P(PROF)` moves off 40%, or it does not and 40% stands. **Both are real answers.** This is the only thing in the app that can settle whether the score is worth anything. |

### What the paper P&L does not include

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 5.17 | | Read the Book's P&L, then `README.md` §"The cost floor" | The book's P&L **excludes costs**. The measured floor is **€1.05 per round trip** (50 bps per side), so a real version of the same trade is €1.05 worse. |
| 5.18 | ⚠ | Ask whether the app told you that anywhere you would have seen it | Today it does not — the caveat is in the Lab and backtest captions and in the README, not on the Book tab. **A paper P&L that reads better than reality is the single most misleading thing this app could show.** Log it if it still is not surfaced. |

### Protocol mode — filling the table without discretion

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 5.19 | | Tick **protocol mode** in the Book header, quit, relaunch | Still ticked — the switch survives a restart. |
| 5.20 | | Within a scan or two of ticking it, read the open positions | Up to **10** new small positions: the five highest- and five lowest-confidence rows. Directions are **mixed** — several days of all-LONG or all-SHORT means the coin is broken. |
| 5.21 | | Check one protocol position's size | Cash at risk ≈ **0.25%** of the book (~€25 on €10,000) regardless of risk profile — measurement stakes, not appetite stakes. |
| 5.22 | | Leave it on over days | At most ten new entries per day, never a second position in a symbol already held, and the protocol open count never exceeds **40**. |
| 5.23 | | Untick protocol mode | Existing protocol positions stay open and resolve on their own. Closing them early would censor exactly the outcomes being measured. |

---

## 6. Macro

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 6.1 | | Read all seven | `10y · curve · fed funds · VIX · real 10y · CPI y/y · unemployment` populated |
| 6.2 | | Read the regime label | Named, with a rationale sentence |
| 6.3 | | Read central-bank communication | Lists releases/speeches. **No direction claimed anywhere.** |
| 6.4 | | Hover each of the seven | The tooltip says what it is *and how to read it* — not a restatement of the label. "Effective policy rate" would be a fail. |

---

## 7. Lab

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 7.1 | | **Run simulation**, whole watchlist, 2y | Completes; reports trials, hit rate, and an error bar |
| 7.2 | | Narrow the universe to one class, re-run | Fewer trials, still completes |
| 7.3 | | Read component attribution | Each component gets **KEEP / WEAK / DROP / INVERTED** |
| 7.4 | | Find the catalyst component | Says it is **not measured** — the replay has no historical earnings calendar — rather than implying it passed |
| 7.5 | | Change R:R and re-run | Realised hit rate moves toward `1/(1+R:R)`. *This identity is the claim the whole app rests on.* |
| 7.6 | | Press **Start replay** | A setup appears |
| 7.7 | ⚠ | Read the setup line | It does **not** reveal the model's call before you commit |
| 7.8 | | Press Buy, then Short, then **Skip** on successive setups | All three advance |
| 7.9 | | Read the scorecard | Shows **your P&L against the model's**, including on setups you skipped |

---

## 8. Playmaker

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 8.1 | | Open the sport picker | Seven: NFL · College Football · NBA · MMA (UFC) · International Football · Golf · Cycling |
| 8.2 | | Switch between them | Prop list, context hint and price example all change |
| 8.3 | | Select International Football | Price example shows **three** prices per book |
| 8.4 | | Paste 4 books, 2-way, one clearly generous. Press **Price it** | `books · margin · fair · book spread · best edge · EV / unit · stake` populate |
| 8.5 | | Read the fair-price panel | All three devig methods shown, with the default (shin) marked |
| 8.6 | | Read the screen | The generous book flagged as an outlier with a z-score |
| 8.7 | | Delete two books, re-price | Explains there is no consensus below three books, rather than showing an empty table |
| 8.8 | | Enter a line with only one price | Names the line that failed and why both sides are needed |
| 8.9 | | Select **Golf** | Says plainly that no head-to-head model rates a field event |
| 8.10 | | Select **Cycling** | Says it has **no results feed at all** |
| 8.11 | ⚠ | Read the model's narrative section | Labelled commentary, and states the stake is **not** derived from it |

---

## 9. Learn — the manual, in the app

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 9.1 | | Press **Learn** | The **Learn tab** opens inside the window. No web browser launches. |
| 9.2 | | Read the first contents entry | §1 "Start here — plain English" |
| 9.3 | | Click every entry in the contents | All 14 scroll to their section. *Qt does not follow the `id` a browser follows, so this breaks silently if the injected anchors go.* |
| 9.4 | | Read the glossary | 24 terms across markets, probability, betting, macro — rendered, not raw HTML |
| 9.5 | | Type `devigging` in **Find** and press return | Jumps to it and highlights. Press return twice more: it keeps finding rather than stopping dead at the end of the document. |
| 9.6 | | Type a word that is not there | Says so, rather than doing nothing |
| 9.7 | | Check §14 | Documents Playmaker, including Kaunitz's account-limiting caveat next to the profit figure |
| 9.8 | | Press **Open in browser** | The same page in a real browser, with the styling Qt cannot draw |
| 9.9 | | Check §2's table | Eight rows, each naming the plain tab name and the original underneath |

---

## 10. Degraded conditions

The cases most likely to be skipped, and the ones that produced the worst bugs.

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 10.1 | | Turn Wi-Fi **off**. Relaunch. | Starts. Shows stale/empty values with a visible reason. **Does not hang, does not crash.** |
| 10.2 | ⚠ | With Wi-Fi off, click every tab | All render. *A stale feed must read as missing, never as a price — Binance served a delisted pair's last candle for years without erroring.* |
| 10.3 | | Turn Wi-Fi back on | Recovers within one poll cycle without a restart |
| 10.4 | | Launch a **second** SONAR while the first runs | Second says **READ-ONLY** and names the conflict. Two engines settling the same hour would double-count the book. |
| 10.5 | | Quit both. Relaunch. | Starts normally — the stale lock is reclaimed |
| 10.6 | | Leave Wi-Fi **off for over two hours** with the app running | The menu-bar tooltip gains **⚠ STALLED** and a notification is posted once — a dead run must not look identical to a healthy one. |
| 10.7 | | Turn Wi-Fi back on and let an hour settle | The STALLED flag clears on its own; coverage resumes counting. |
| 10.8 | | After a day of running, look in `~/Library/Application Support/SONAR/` | `state.json.bak.<date>` exists (and `portfolio.json.bak.<date>` once the book has saved that day); at most **seven** days of each are kept. |

---

## 11. Exit criteria

v2 signs off when:

- [ ] Every ⚠ case passes. These are regressions; a failure is a re-opened bug.
- [ ] §0 passes — build, self-test, and 1,339 automated tests.
- [ ] No case in §1 (launch, window, quit) fails. The app being hard to close or
      quit has been reported twice and is the most visible class of defect here.
- [ ] §10 passes. An app that misbehaves offline is worse than one that says it
      is offline.
- [ ] Any failure is either fixed, or written into `TODO.md` with its evidence.

## 12. Known, and not blocking

- ~~The Qt window tests wedge about one run in three.~~ **Fixed 2026-09-19**:
  the conftest guards were function-scoped below a module-scoped window fixture,
  so the three window tests ran unguarded. Session-scoped now; three consecutive
  full runs deterministic. `./run-tests.sh` still bounds the suite externally as
  a backstop, and a wedge today is a regression to report.
- **The calibration table will be empty** until ~20 paper positions have closed.
  That is the honest state, not a defect.
- **No Finnhub key** means equities ride on one undocumented Yahoo endpoint, with
  a ~15-minute delay during market hours.
- **Golf and cycling have no rating model**, and cycling has no results feed.
  Both are stated in the UI.
