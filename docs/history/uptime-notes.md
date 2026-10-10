# Uptime: the full notes

The long form of the README's Uptime section: full-screen and hide interplay, the no-fetch-under-a-lock rule, quitting, one directory, follow mode, run health, protocol mode.

Moved verbatim from `README.md` on 2026-10-10 when the README was cut to what / how / where. Statements here are as of the commit they were written in; the README no longer repeats them.

SONAR is a daemon wearing an app: the equity curve only means something if positions settle on
the hours they were priced for. So two things protect that.

**The close button hides.** The window disappears, the engine keeps running, and the menu-bar
item shows bankroll and open position. Quitting is a separate, deliberate menu action — and
clicking the Dock icon brings the window back if the menu-bar item is hard to find. Clicking
the menu-bar icon itself only opens its menu, the same as every other Mac menu-bar item; it
used to also reveal the window, which dragged the whole app to the front over whatever was in
it.

Leaving full-screen and hiding are also untangled from each other, in both directions. Exiting
a full-screen Space and clicking the close button both trigger the macOS activation event a
real Dock click uses, so for just over a second after either one the window ignores that event
rather than reopening itself the moment it just hid (`reopen_allowed`). And a close pressed
while still in full screen waits for the Space to actually finish collapsing — not for
`showNormal()` to be called, which Qt reports as done a full transition-length before it is —
then confirms against the platform window's own exposure state that the hide landed, retrying
if it did not: AppKit can drop a hide aimed at a window still mid-animation while Qt marks it
hidden anyway, which is what once left the window on screen, blank, with a second press of the
close button doing nothing because Qt believed there was nothing left to hide. A close arriving
at a window Qt already thinks is hidden shows it before hiding it again, for the same reason.
Everything that reopens the window goes through one method, because a reveal has to call off a
hide a full-screen close leaves pending.

**Nothing the window waits on may fetch**, which is a wider rule than it sounds. The UI
thread reads the shared snapshot under a lock every second, so a background thread holding
that lock across a network call freezes the window just as thoroughly as fetching on the UI
thread would: the window goes blank, ignores the close button, and comes back a few seconds
later when the fetch finishes. That is what the central-bank feed did every fifteen minutes.
Build the payload first, then take the lock for the assignment — `tests/test_ui_thread.py`
checks both the behaviour and, by AST, that no known fetch sits inside a lock.

**Quitting never waits for the network.** A quit that lands while the app is fetching gives
the background threads about a second and then ends the process, printing what it gave up on.
That is deliberate: the alternative is a window that stops repainting while it waits, which is
indistinguishable from a hang — and the earlier attempt to stop a stuck thread outright froze
the app completely. Nothing is lost by leaving this way, because the engine writes each change
as it happens rather than saving on exit.

**A launchd agent** keeps it running when you are not logged into the app at all:

```bash
./scripts/install_agent.sh             # install and start
./scripts/install_agent.sh --status
./scripts/install_agent.sh --uninstall
```

**One directory, or they never meet.** A frozen app keeps its state in
`~/Library/Application Support/SONAR`; a checkout keeps it in its own `data/`. The agent runs
`main.py` from the checkout, so without help it runs a *second* experiment beside the
installed app's — which is exactly what happened for weeks until the build's self-test line
"state file: …/Application Support/SONAR/state.json" gave it away. `SONAR_DATA` overrides the
directory (`paths.user_data_base`, `~` expanded, frozen or not), and `install_agent.sh` writes
it into the agent's plist pointing at the app's directory. A checkout run from source without
the variable still uses `data/` — a development book, separate on purpose.

Running both is safe, and since Oct 2026 it is also useful. `sonar/enginelock.py` enforces
**one engine per state file**: whoever starts first drives, because two engines settling the
same hour would double-count the portfolio silently. The other one **follows** rather than
sitting there blank: the agent records its HTTP address in the lock, and a window that loses
the race mirrors the agent's snapshot, board, book, alerts and knobs over localhost
(`Live._wait_for_lock`, `/api/book`, `/api/wire`) — every figure on every page is the
agent's, and every action that writes the book (buy, short, close, the knobs, protocol mode,
an LLM read) is handed to the agent over `/api/trade`, `/api/close`, `/api/config`,
`/api/read`, so there is still exactly one writer. The status line says *following the
engine at 127.0.0.1:8787* while this is so. Whoever waits re-tries the lock every fifteen
seconds and **takes over the moment it is free**: quit the agent and the window drives
without a restart; quit the window and the agent — which was waiting, not idling — drives
the night. A second window has no address to follow, so it waits with a plain message. A
lock left behind by a killed process is reclaimed rather than blocking forever.

**The run watches itself.** Over a weeks-long collection run, hours can go missing silently —
feed down, machine asleep, agent dead — and the damage would only show at review time as a
mysteriously small n. So the hourly model's panel carries the run's vital signs (hours scored vs
elapsed, settlements voided, time since anything last settled), and because the BTC market
resolves around the clock, **two silent hours always means a stall**: the menu-bar item posts
a notification and flags STALLED rather than sitting there looking healthy. The state files
also keep a **daily rotating backup** (`.bak.<date>`, last seven days) beside themselves —
they are the experiment's output and live nowhere else.

**Protocol mode** (a checkbox on the Book tab, off by default) is how the calibration table
fills without discretion: once a day it opens fixed-small paper positions on the five highest-
and five lowest-confidence rows, direction chosen by **coin flip**. Random on purpose — the
score claims notability, never direction, and a coin flip isolates exactly the claim the
calibration table exists to test. Turning it off leaves open positions to resolve; closing
them early would censor the outcomes being measured. Paper money, as everything here.

**Headless is still dependency-free.** `python main.py --headless` runs the same
`sonar.core.Live` behind the stdlib HTTP server with the original browser dashboards.
