"""Background threads.

Two jobs must never block the UI:

* the **poll loop**, which drives the paper engine forever, and
* the **LLM read**, which is one request that can take tens of seconds.

Both run on ``QThread``s. ``core.Live`` stays completely Qt-unaware — the poll
thread just calls into it and the window pulls the resulting snapshot on a
timer. That keeps the same driver usable headlessly by ``sonar.server``.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from sonar.core import Live


class PollThread(QThread):
    """Runs the engine's polling loop for the life of the app."""

    def __init__(self, live: Live, parent=None) -> None:
        super().__init__(parent)
        self.live = live

    def run(self) -> None:                 # noqa: D102
        self.live.run()                    # blocks forever; daemon-style


class ReadThread(QThread):
    """One LLM read, off the UI thread."""

    done = Signal(dict)

    def __init__(self, live: Live, kind: str, ident: str, parent=None) -> None:
        super().__init__(parent)
        self.live, self.kind, self.ident = live, kind, ident

    def run(self) -> None:                 # noqa: D102
        try:
            self.done.emit(self.live.read(self.kind, self.ident))
        except Exception as exc:           # never take the window down
            self.done.emit({"error": f"{type(exc).__name__}: {exc}"})


class BacktestThread(QThread):
    """Replaying years of bars over the whole watchlist takes seconds and hits
    the network, so it never runs on the refresh timer — only when asked.

    The Lab tab drives the same replay with the parameters exposed, which is why
    everything below the symbol list is settable rather than fixed.
    """

    done = Signal(dict)
    progress = Signal(str, int)

    def __init__(self, symbols, horizon_days: int, parent=None, *,
                 rng: str = "2y", step: int = 3, with_news: bool = False) -> None:
        super().__init__(parent)
        self.symbols, self.horizon_days = symbols, horizon_days
        self.rng, self.step, self.with_news = rng, step, with_news

    def run(self) -> None:                 # noqa: D102
        from sonar import backtest
        try:
            self.done.emit(backtest.run(
                self.symbols, horizon_days=self.horizon_days, rng=self.rng,
                step=self.step, with_news=self.with_news,
                progress=lambda sym, n: self.progress.emit(sym, n)))
        except Exception as exc:
            self.done.emit({"n": 0, "verdict": f"{type(exc).__name__}: {exc}"})


class ConfigThread(QThread):
    """Applying a risk/horizon change triggers a rescan, which hits the network."""

    done = Signal(dict)

    def __init__(self, live: Live, risk_name, horizon_name, parent=None) -> None:
        super().__init__(parent)
        self.live, self.risk_name, self.horizon_name = live, risk_name, horizon_name

    def run(self) -> None:                 # noqa: D102
        try:
            self.done.emit(self.live.configure(self.risk_name, self.horizon_name))
        except Exception as exc:
            self.done.emit({"error": str(exc)})


class SportsMeasureThread(QThread):
    """One sports-model measurement: seasons of results fetched, the rating
    walked forward, the verdict returned. Network plus arithmetic that takes
    tens of seconds, so never on the refresh timer — only when asked."""

    done = Signal(dict)
    progress = Signal(str)

    def __init__(self, sport_key: str, seasons: int, parent=None) -> None:
        super().__init__(parent)
        self.sport_key, self.seasons = sport_key, seasons

    def run(self) -> None:                 # noqa: D102
        from sonar.playmaker import scoring
        try:
            self.done.emit(scoring.measure(
                self.sport_key, seasons=self.seasons,
                progress=self.progress.emit))
        except Exception as exc:           # never take the window down
            self.done.emit({"sport": self.sport_key, "n_games": 0,
                            "verdict": "ERROR",
                            "summary": f"{type(exc).__name__}: {exc}"})


class PropThread(QThread):
    """One sports prop analysis, off the UI thread.

    Separate from ``ReadThread`` because that one goes through ``Live`` and the
    opportunity JSON schema; a prop read is a plain completion.
    """

    done = Signal(str, str)

    def __init__(self, system: str, prompt: str, parent=None) -> None:
        super().__init__(parent)
        self.system, self.prompt = system, prompt

    def run(self) -> None:                 # noqa: D102
        from sonar import llm
        try:
            text, error = llm.complete(self.system, self.prompt)
            self.done.emit(text, error or "")
        except Exception as exc:           # never take the window down
            self.done.emit("", f"{type(exc).__name__}: {exc}")
