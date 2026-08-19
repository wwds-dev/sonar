"""Tests for the close button actually closing the window.

The reported symptom was a close button that did nothing: click it and the
window stayed on screen. It was not the hide failing. Leaving macOS full screen
animates a Space transition, and macOS re-activates the app when that finishes —
*after* the deferred hide has already run. The Dock-click handler in main.py
saw an invisible window and faithfully reopened it.

Qt delivers a Dock click and that echo as the same ApplicationActivate event, so
the only thing separating them is timing. These tests pin the timing rule down,
because the bug is invisible in the source and only appears on a real desktop.
"""

import time

import pytest

pytest.importorskip("PySide6")

from ui.app import REOPEN_GRACE_MS, MainWindow


class FakeWindow:
    """Only the reopen logic, without needing a display server.

    MainWindow's constructor builds the whole UI and starts a poll thread; the
    rule under test is three lines and does not need any of it.
    """

    _hidden_at = 0.0
    reopen_allowed = MainWindow.reopen_allowed
    _hide_now = MainWindow._hide_now
    hidden = False

    def hide(self):
        self.hidden = True


def test_a_fresh_window_may_be_reopened():
    """Nothing has hidden it, so a Dock click must work."""
    assert FakeWindow().reopen_allowed() is True


def test_the_echo_of_our_own_hide_is_refused():
    """The activation that arrives right after the hide must not reopen it."""
    w = FakeWindow()
    w._hide_now()
    assert w.hidden is True
    assert w.reopen_allowed() is False, \
        "the window would reopen itself the moment it closed"


def test_a_later_dock_click_still_works():
    """The guard is a brief window, not a permanent block."""
    w = FakeWindow()
    w._hide_now()
    w._hidden_at -= (REOPEN_GRACE_MS + 200) / 1000.0      # pretend time passed
    assert w.reopen_allowed() is True


def test_the_grace_outlasts_the_fullscreen_exit():
    """The echo cannot arrive before the deferred hide that provokes it.

    FULLSCREEN_EXIT_MS is how long the hide waits for the Space transition; the
    activation lands after that. A grace shorter than it could never help.
    """
    from ui.app import FULLSCREEN_EXIT_MS
    assert REOPEN_GRACE_MS > FULLSCREEN_EXIT_MS


def test_the_guard_uses_a_monotonic_clock():
    """A wall clock going backwards (NTP, DST) must not unblock the guard."""
    w = FakeWindow()
    w._hide_now()
    assert w._hidden_at == pytest.approx(time.monotonic(), abs=1.0)
