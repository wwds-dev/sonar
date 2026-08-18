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
    the network, so it never runs on the refresh timer — only when asked."""

    done = Signal(dict)

    def __init__(self, symbols, horizon_days: int, parent=None) -> None:
        super().__init__(parent)
        self.symbols, self.horizon_days = symbols, horizon_days

    def run(self) -> None:                 # noqa: D102
        from sonar import backtest
        try:
            self.done.emit(backtest.run(self.symbols,
                                        horizon_days=self.horizon_days))
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
