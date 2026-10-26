"""SCRUM-85: the minute timer that sends arrangement reminders (core/reminder_sweep.py).

The same shape as SCRUM-108's timer test, because the timer is the same shape. What
matters here is that a tick gets its own session and the current time, that a failure is
logged rather than killing the thread (AC8: nothing is recorded as sent that was not
sent), and that the app runs it alongside the hold sweep rather than instead of it.
"""

import logging
import threading
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

import main
from core import hold_expiry, reminder_sweep
from core.reminder_sweep import ReminderSweepTimer

_NOW = datetime(2030, 3, 1, 9, 0, tzinfo=UTC)


@pytest.mark.story("SCRUM-85")
def test_a_tick_processes_due_reminders_with_its_own_session_and_the_current_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, datetime]] = []
    monkeypatch.setattr(reminder_sweep, "process_due", lambda db, now: calls.append((db, now)))
    session = MagicMock()
    timer = ReminderSweepTimer(session_factory=lambda: session, clock=lambda: _NOW)

    timer.run_once()

    assert calls == [(session.__enter__.return_value, _NOW)]
    session.__exit__.assert_called_once()  # the session is closed after the tick


@pytest.mark.story("SCRUM-85")
def test_a_failed_tick_is_logged_and_does_not_stop_the_timer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC8: a failure leaves the occurrence unprocessed for the next tick to find."""

    def boom(db: object, now: datetime) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(reminder_sweep, "process_due", boom)
    # Alembic's logging setup, run in-process by the migration tests, disables loggers
    # that already exist. The API runs Alembic as a separate command, so only tests see it.
    monkeypatch.setattr(reminder_sweep.logger, "disabled", False)
    caplog.set_level(logging.ERROR, logger=reminder_sweep.logger.name)
    timer = ReminderSweepTimer(session_factory=MagicMock, clock=lambda: _NOW)

    timer.run_once()  # does not raise

    assert "sending arrangement reminders failed" in caplog.text


@pytest.mark.story("SCRUM-85")
def test_the_timer_ticks_until_it_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    ticked = threading.Event()
    monkeypatch.setattr(reminder_sweep, "process_due", lambda db, now: ticked.set())
    timer = ReminderSweepTimer(interval=0.01, session_factory=MagicMock, clock=lambda: _NOW)

    timer.start()
    assert ticked.wait(timeout=2)
    timer.stop()

    assert timer._thread is not None and not timer._thread.is_alive()


@pytest.mark.story("SCRUM-85")
async def test_the_app_runs_both_sweeps_and_stops_both(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kept apart on purpose: a reminder sweep that threw must not stop holds expiring."""
    events: list[str] = []
    monkeypatch.setattr(
        reminder_sweep.ReminderSweepTimer, "start", lambda self: events.append("reminders:start")
    )
    monkeypatch.setattr(
        reminder_sweep.ReminderSweepTimer, "stop", lambda self: events.append("reminders:stop")
    )
    monkeypatch.setattr(
        hold_expiry.HoldExpiryTimer, "start", lambda self: events.append("holds:start")
    )
    monkeypatch.setattr(
        hold_expiry.HoldExpiryTimer, "stop", lambda self: events.append("holds:stop")
    )
    app = main.create_app()

    async with app.router.lifespan_context(app):
        assert events == ["holds:start", "reminders:start"]

    assert events == ["holds:start", "reminders:start", "reminders:stop", "holds:stop"]
