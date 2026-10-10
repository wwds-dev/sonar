# SONAR v2 — acceptance test plan

The plan for signing off v2. `TESTING.md` is the *automated* coverage roadmap;
this is everything a person has to check, because the suite structurally cannot.

**Run it against `/Applications/SONAR.app`, not the checkout.** Several of the
failures below only exist in a packaged build — a module PyInstaller could not
see, a resource path that moves when frozen, a Qt plugin inherited from a parent
process. A green suite says nothing about any of them.

**Run it in the state it is used in: the app open on top of the launchd agent**
(`./scripts/install_agent.sh --status` says *installed and loaded*). Since v2.128
the window *follows* the agent — every figure is the agent's, every action that
writes the book is handed to it — so a case passed with the agent stopped has
tested a different program. §10.4–10.5 and the handovers in §12 say when to stop it.

| | |
|---|---|
| Build under test | `./build_app.sh --install`, then `/Applications/SONAR.app/Contents/MacOS/SONAR --selftest` |
| Automated suite | `./run-tests.sh tests/ -q` — expect **1,723 tests** and no failures (a few skip off macOS). The suite checks this figure against its own collection, so it cannot go stale silently |
| Time to run this plan | ~30 minutes |
| Prerequisite | A working internet connection. Two cases deliberately need it off. |

**Run it from inside the app.** The **Test plan** button, next to *Learn*, opens
this as a page that remembers which cases you have passed or failed — a hundred
and forty-five of them is more than one sitting. The daemon serves it at `/testplan` too.

That page is *generated* from this file by `scripts/build_testplan.py`, which
`build_app.sh` runs before packaging. Edit the markdown, never the HTML.

**⚠ marks a case that has caught a real regression.** Those are the ones worth
running even when short of time — the list doubles as this project's bug history.

---

## 0. Before starting

| # | Step | Expected |
|---|---|---|
| 0.1 | `./run-tests.sh tests/ -q` | No failures — the count is in the header table — in well under a minute. The suite is deterministic since 2026-09-19 — a wedge or a hang is a regression now, not a known issue. |
| 0.2 | `./build_app.sh --install` | Ends with `All checks passed.` then `Installed:` |
| 0.3 | `/Applications/SONAR.app/Contents/MacOS/SONAR --selftest` | `All checks passed.` Reports 7 sports, 5 rated, cycling with no feed. |
| 0.4 | Note the bankroll before you start | You will compare against it in 5.x |
| 0.5 | `QT_QPA_PLATFORM=offscreen ./run-tests.sh -q` | Also no failures. This is how CI runs the suite, and the two disagree on font metrics: CI was red for two days in Oct 2026 while the native run above was green. |
| 0.6 | `gh run list --limit 1` | `completed success` on the commit being signed off |
| 0.7 | Hover the version in the installed app; then `git cat-file -e <commit>` with the commit it names | The commit exists in the repository and the tooltip does not say *uncommitted changes*. *The v2.132 bundle of 2026-10-08 named a commit that had been amended away — and the badge called it up to date.* |
| 0.8 | `./run-tests.sh -m network -q` | Every live source answers in the shape SONAR parses: Binance, Coinbase's fallback, Polymarket's hourly market and book, Yahoo, FRED, Nasdaq, the newswires, the central banks, and each ESPN league. Opt-in because it needs the internet — and therefore the one run nobody makes unless it is on this list: the ESPN checks had been broken for a month when it was first run. |

---

## 1. Launch and window

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 1.1 | ⚠ | Launch from `/Applications`. Time it. | First paint in **under 3s**. *Once took 11s of sequential fetches.* |
| 1.2 | | Count the tabs, and read both lines on each | Eight, each showing a plain name over the name the docs use: My investments/PORTFOLIO · Screener/ASSETS · News/WIRE · My trades/BOOK · Big picture/MACRO · Practice/LAB · Sports/PLAYMAKER · Learn |
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
| 1.14 | ⚠ | Hover the version | Reports commit, date, packaged-vs-checkout, and whether a newer build exists. *It must never say "up to date" when it cannot know — a guessed answer here gets believed.* The same build number with a different commit says so and names both. |

---

## 2. The hourly model (foot of Practice)

The BTC up/down model was the landing page, "Terminal", until v2.127. It lives,
unchanged, at the foot of **Practice** now — open that page and scroll down.

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 2.1 | | Read the price | Live BTC price, moves within ~5s |
| 2.2 | | Read the stat row | `price · hour · model · market · edge · tau · bankroll · pnl · trades · win rate · profile` all populated |
| 2.3 | ⚠ | Compare the lattice caption's **P(up)** with the **model** figure above it | They agree. *They disagreed by 10 points at the top of every hour — one counted a bin sitting exactly on the barrier as a win.* |
| 2.4 | | Watch the lattice for a minute | Redraws as price moves; bars at/above the open are coloured differently |
| 2.5 | | Read the equity curve | Renders; a gold **LIVE** marker separates the warm-up from real trades |
| 2.6 | | Press **LLM read on this hour** | Either a read appears, or it says why not. With no API key, "off — no key" is the correct answer, not an error. |
| 2.7 | | Hover every number in the stat row | Each has a tooltip explaining it in plain words |
| 2.8 | | Read the **model vs market** line in the ledger panel under the equity curve | States how many hours are scored and refuses a verdict below **100** — below the threshold it must not favour either side. |
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
| 3.18 | | Check the stat strip of the hourly model at the foot of **Practice** | `TAU` in expert, `HOUR REMAINING` in plain — the captions follow the switch without a relaunch |
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
| 7.5 | | Read the run's **predicted** hit rate against the realised one | Predicted reads 40% — `1/(1+R:R)` at the shipped 1.5:1, the identity the app rests on — and realised sits within its error bar of it unless the verdict names a cause. *There is no R:R control in the Lab, whatever its description once said; the identity is pinned by `tests/test_backtest.py` at 1:1 and 1.5:1. At 2:1 and wider the backtest's own baseline is biased by the trials it drops as timeouts (14% realised against 25% at 3:1 on a walk with no drift), so a control must not be added without fixing that first.* |
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
| 9.9 | | Check §2's table | Eight rows, the first *My investments*, each naming the plain tab name and the original underneath |

---

## 10. Degraded conditions

The cases most likely to be skipped, and the ones that produced the worst bugs.

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 10.1 | | Turn Wi-Fi **off**. Relaunch. | Starts. Shows stale/empty values with a visible reason. **Does not hang, does not crash.** |
| 10.2 | ⚠ | With Wi-Fi off, click every tab | All render. *A stale feed must read as missing, never as a price — Binance served a delisted pair's last candle for years without erroring.* |
| 10.3 | | Turn Wi-Fi back on | Recovers within one poll cycle without a restart |
| 10.4 | | With the agent stopped, launch a **second** SONAR while the first runs | Second says **READ-ONLY** and names the conflict. Two engines settling the same hour would double-count the book. |
| 10.5 | | Quit both. Relaunch. | Starts normally — the stale lock is reclaimed |
| 10.6 | | Leave Wi-Fi **off for over two hours** with the app running | The menu-bar tooltip gains **⚠ STALLED** and a notification is posted once — a dead run must not look identical to a healthy one. |
| 10.7 | | Turn Wi-Fi back on and let an hour settle | The STALLED flag clears on its own; coverage resumes counting. |
| 10.8 | | After a day of running, look in `~/Library/Application Support/SONAR/` | `state.json.bak.<date>` exists (and `portfolio.json.bak.<date>` once the book has saved that day); at most **seven** days of each are kept. |

---

## 11. My investments — the first screen

The landing page since v2.127. Every figure on it is the book's, and several are
the same quantity reached two ways, so most of these cases compare one number
with another rather than with a value written here. `curl -s
127.0.0.1:8787/api/book` is the agent's own account of the book.

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 11.1 | | Launch the app | It opens on **My investments**: P&L now (the largest figure), account value, invested, at risk, closed. |
| 11.2 | | Compare the strip with `curl -s 127.0.0.1:8787/api/book` (`positions.stats`) | Equity, P&L, invested and at-risk match to the dollar. |
| 11.3 | | Read the line under **invested** | Two figures — *your cash in N longs* and *borrowed for M shorts* — that add up to the big one. N + M is the number of open positions. Never one figure called cash. |
| 11.4 | | Read the line under **at risk** | A percentage of the account and *N stops set*, N equal to the open count. |
| 11.5 | | Check: account value − starting cash = P&L now, and P&L now = open + closed on its own line | Both hold to the dollar. |
| 11.6 | | Read the account-value curve | Starts on or before the day of the first entry; its last point is within the hour of the account value in the strip; no step without an entry or exit near it. |
| 11.7 | | Count the tiles, then the cards | One of each per open position. The biggest tile is the position with the most to lose; a tile's colour follows the sign of its P&L. |
| 11.8 | | Close a position from its card | Asks first; then it leaves the cards, appears under recently closed, and **My trades** agrees. |
| 11.9 | | Read **Is the score right?** and compare its first sentence with the calibration verdict on **My trades** | Word for word the same. |
| 11.10 | | Read the band lines | Bands print as 0–20 … 80–100 — never *101*. Each band under 20 closed says it needs 20 to count. |
| 11.11 | | Read the whole grade panel for forecast words | None of *will, should, buy, sell, expect, likely, going to, bullish, bearish*. It describes what happened. |
| 11.12 | | Toggle protocol mode on **My trades**, come back | The panel's last line follows: *protocol mode is on* / *is off*, and how many of the closed positions protocol opened. |
| 11.13 | | Narrow the window to 1280×775 | The figures and the curve are on screen first; the page scrolls; nothing clips. |

---

## 12. Follow mode — the app on top of the agent

Two processes, one book (v2.128, v2.130): the agent holds the engine lock, the
window mirrors it and hands it every action that writes the book. **12.6–12.10
stop and restart the live run** — do them just after an hour has settled, and
finish with `./scripts/install_agent.sh --status` showing it loaded again. Note
the model-vs-market *n* and the closed count before 12.6; 12.10 compares.

| # | ⚠ | Steps | Expected |
|---|---|---|---|
| 12.1 | | With the agent running, launch the app | The status line at the foot of the rail says *following the engine at 127.0.0.1:8787*. |
| 12.2 | | `cat ~/Library/Application\ Support/SONAR/engine.lock` | Names the agent's pid, role `agent`, and its URL. The app is not the holder. |
| 12.3 | | Buy a row on **Screener** | The position appears in `curl -s 127.0.0.1:8787/api/book` and on the window within a few seconds — the agent booked it. |
| 12.4 | | Close it from **My trades** | Gone from the agent's book too. |
| 12.5 | | Change the risk knob | `curl -s 127.0.0.1:8787/api/config` reports the new profile, and the window's knob stays on it. |
| 12.6 | | Press **LLM read on this hour** | It runs on the agent. If the agent's environment has no `anthropic`, the reply says so **and says it is the agent's**, not just "off". |
| 12.7 | | Stop the agent: `launchctl bootout gui/$(id -u)/com.netrunner3000.sonar` | Within about 15 seconds the status line stops saying *following*, the lock names the app, and the price keeps moving — no restart. |
| 12.8 | | Reinstall the agent with the window still open: `./scripts/install_agent.sh` | The agent starts and **waits** (the window holds the lock and publishes no address); the window keeps driving. |
| 12.9 | | Quit the window from the menu bar | Within about 15 seconds the lock names the agent and `curl -s 127.0.0.1:8787/api/state` reports `"status": "live"`. |
| 12.10 | | Compare the model-vs-market *n* and the closed count with the note from before 12.7 | *n* has grown by at most one per hour elapsed; no closed position appears twice. Two engines settling the same hour would show here. |
| 12.11 | | `kill -9` the agent's pid while the window follows it | launchd restarts it; the window either keeps following or takes over — either way, within a minute one of them drives and the lock is not left stale. |

---

## 13. Exit criteria

v2 signs off when:

- [ ] Every ⚠ case passes. These are regressions; a failure is a re-opened bug.
- [ ] §0 passes — build, self-test, and the full automated suite.
- [ ] No case in §1 (launch, window, quit) fails. The app being hard to close or
      quit has been reported twice and is the most visible class of defect here.
- [ ] §10 passes. An app that misbehaves offline is worse than one that says it
      is offline.
- [ ] §11 and §12 pass — the first screen and the two-process book are the two
      newest parts of the app, and §12 is the only check that the run's sample
      survives a handover.
- [ ] Any failure is either fixed, or written into `TODO.md` with its evidence.

## 14. Known, and not blocking

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
