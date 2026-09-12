"""Tell me when something changed — never what to do about it.

An alert is a delivery mechanism for the confidence score, and the score is a
**notability** heuristic: "something is happening here, worth a look." So that is
what an alert says. It does not say buy, it does not say short, and there is a
test asserting no alert can ever contain those words.

That restraint is not squeamishness, it is the current evidence. Five
pre-registered studies found no directional edge, and the component attribution
in :mod:`sonar.backtest` found the blended score's IC is *negative* — so an alert
firing on a high score and shouting BUY would, on the numbers this project has,
be pointing at the wrong instruments with an air of authority. The honest path to
a directional alert runs through :mod:`sonar.calibration`: once the paper book
has a measured edge, an alert gated on that is earned. Until then it would be
invented.

Firing on change, not on level
------------------------------
The rule that makes alerts usable rather than noise: an alert is an **event**, so
it fires on a transition. "News went Normal → Spike" happens once. "News is
Spike" is a state, and alerting on it re-fires every ninety seconds until the
story ages out, which trains you to ignore the whole feature.

Everything carries the age of the data it fired on. An alert is a claim about
right now, and for an equity outside market hours "right now" can be six hours
old — see :func:`sonar.alerts.Alert.stale`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# How long before the same (symbol, kind) may fire again. Long enough that a
# value oscillating around a threshold cannot machine-gun the panel.
COOLDOWN_S = 3600.0

# News levels, ordered, so a *rise* can be distinguished from any change.
_LEVELS = ["Quiet", "Normal", "Elevated", "Spike"]

# A score move worth mentioning. Below this it is noise in the inputs.
SCORE_JUMP = 15.0

# Volatility regime break: today's vol against the instrument's own recent vol.
VOL_BREAK = 1.6

# Data older than this is called out in the alert itself.
STALE_S = 1800.0


@dataclass(frozen=True)
class Alert:
    """One thing that changed. Deliberately carries no direction."""

    symbol: str
    name: str
    kind: str              # news | volatility | catalyst | score | policy
    message: str
    severity: str          # info | notable
    ts: float = field(default_factory=time.time)
    data_age_s: float = 0.0

    @property
    def stale(self) -> bool:
        """Was the data behind this already old when it fired?

        Equities outside market hours are hours stale, and an alert that does not
        say so is implying an immediacy it does not have.
        """
        return self.data_age_s > STALE_S

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "name": self.name, "kind": self.kind,
                "message": self.message, "severity": self.severity,
                "ts": self.ts, "data_age_s": round(self.data_age_s),
                "stale": self.stale}

    def line(self) -> str:
        age = ""
        if self.stale:
            age = f"  (on data {self.data_age_s / 60:.0f} min old)"
        return f"{self.symbol} — {self.message}{age}"


class AlertEngine:
    """Compares each scan against the last and reports what moved.

    Stateful by necessity: an event is a difference, and a difference needs
    something to difference against. The state is deliberately small — the last
    level, score and volatility per symbol — so a restart loses nothing that
    matters beyond one scan's worth of transitions.
    """

    def __init__(self, cooldown: float = COOLDOWN_S) -> None:
        self.cooldown = cooldown
        self._prev: dict[str, dict] = {}
        self._fired: dict[tuple[str, str], float] = {}
        self.log: list[Alert] = []

    # -- gating ------------------------------------------------------------ #
    def _allowed(self, symbol: str, kind: str, now: float) -> bool:
        last = self._fired.get((symbol, kind))
        return last is None or (now - last) >= self.cooldown

    def _fire(self, alert: Alert) -> Alert:
        self._fired[(alert.symbol, alert.kind)] = alert.ts
        self.log.append(alert)
        self.log = self.log[-200:]
        return alert

    # -- detection --------------------------------------------------------- #
    def scan(self, payload: dict, policy: dict | None = None,
             now: float | None = None) -> list[Alert]:
        """Diff this asset payload against the previous one.

        The first scan after a restart establishes the baseline and reports
        nothing. Alerting on it would mean every launch fired a screenful of
        transitions that never happened.
        """
        now = time.time() if now is None else now
        generated = payload.get("generated") or now
        age = max(0.0, now - generated)
        out: list[Alert] = []
        first = not self._prev

        for a in payload.get("assets", []):
            sym = a.get("symbol", "")
            if not sym:
                continue
            prev = self._prev.get(sym)
            cur = {"level": a.get("lean", "Normal"),
                   "confidence": float(a.get("confidence") or 0.0),
                   "volatility": float(a.get("volatility") or 0.0)}
            self._prev[sym] = cur
            if first or prev is None:
                continue
            out.extend(self._for_asset(a, prev, cur, now, age))

        if policy:
            alert = self._for_policy(policy, now, age)
            if alert:
                out.append(alert)
        return out

    def _for_asset(self, a: dict, prev: dict, cur: dict,
                   now: float, age: float) -> list[Alert]:
        sym, name = a["symbol"], a.get("name", a["symbol"])
        out = []

        # News, on a *rise* only. A story fading is not an event worth waking for.
        try:
            before, after = _LEVELS.index(prev["level"]), _LEVELS.index(cur["level"])
        except ValueError:
            before = after = 0
        if after > before and after >= _LEVELS.index("Elevated"):
            if self._allowed(sym, "news", now):
                out.append(self._fire(Alert(
                    symbol=sym, name=name, kind="news",
                    message=f"news coverage went {prev['level']} → {cur['level']}",
                    severity="notable" if cur["level"] == "Spike" else "info",
                    ts=now, data_age_s=age)))

        # Volatility regime break, measured against this instrument's own recent
        # level rather than an absolute — which is the level-vs-surprise point
        # CONFIDENCE.md §5 makes, applied where it is cheapest.
        if prev["volatility"] > 0 and cur["volatility"] / prev["volatility"] >= VOL_BREAK:
            if self._allowed(sym, "volatility", now):
                out.append(self._fire(Alert(
                    symbol=sym, name=name, kind="volatility",
                    message=(f"daily volatility {cur['volatility'] * 100:.2f}% is "
                             f"{cur['volatility'] / prev['volatility']:.1f}× its "
                             "own recent level"),
                    severity="notable", ts=now, data_age_s=age)))

        # A large move in the score itself.
        jump = cur["confidence"] - prev["confidence"]
        if abs(jump) >= SCORE_JUMP and self._allowed(sym, "score", now):
            out.append(self._fire(Alert(
                symbol=sym, name=name, kind="score",
                message=(f"score {prev['confidence']:.0f} → {cur['confidence']:.0f} "
                         f"({jump:+.0f})"),
                severity="info", ts=now, data_age_s=age)))

        # A scheduled catalyst arriving. Known in advance, which is the whole
        # point of it — this is a reminder, not a discovery.
        cat = a.get("catalyst") or {}
        days = cat.get("days_away")
        if days is not None and 0 <= days <= 2 and self._allowed(sym, "catalyst", now):
            out.append(self._fire(Alert(
                symbol=sym, name=name, kind="catalyst",
                message=(f"{cat.get('kind', 'event')} in {days} day"
                         f"{'' if days == 1 else 's'} — {cat.get('label', '')}".strip(" —")),
                severity="info", ts=now, data_age_s=age)))
        return out

    def _for_policy(self, policy: dict, now: float, age: float) -> Alert | None:
        if policy.get("level") != "Heavy":
            return None
        if not self._allowed("*", "policy", now):
            return None
        return self._fire(Alert(
            symbol="*", name="Central banks", kind="policy",
            message=(f"{policy.get('n_policy', 0)} policy communications in "
                     f"{policy.get('window_h', 72):.0f}h — the rate path is being "
                     "repriced"),
            severity="notable", ts=now, data_age_s=age))

    # -- reporting --------------------------------------------------------- #
    def recent(self, limit: int = 20) -> list[dict]:
        return [a.as_dict() for a in reversed(self.log[-limit:])]
