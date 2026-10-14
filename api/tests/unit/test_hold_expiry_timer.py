"""SCRUM-108: the minute timer that expires tentative holds (core/hold_expiry.py)."""

import logging
import threading
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

import main
from core import hold_expiry
from core.hold_expiry import HoldExpiryTimer

_NOW = datetime(2030, 3, 1, 9, 0, tzinfo=UTC)


@pytest.mark.story("SCRUM-108")
def test_a_tick_expires_holds_with_its_own_session_and_the_current_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, datetime]] = []
    monkeypatch.setattr(hold_expiry, "expire_due_holds", lambda db, now: calls.append((db, now)))
    session = MagicMock()
    timer = HoldExpiryTimer(session_factory=lambda: session, clock=lambda: _NOW)

    timer.run_once()

    assert calls == [(session.__enter__.return_value, _NOW)]
    session.__exit__.assert_called_once()  # the session is closed after the tick


@pytest.mark.story("SCRUM-108")
def test_a_failed_tick_is_logged_and_does_not_stop_the_timer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(db: object, now: datetime) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(hold_expiry, "expire_due_holds", boom)
    # Alembic's logging setup, run in-process by the migration tests, disables loggers
    # that already exist. The API runs Alembic as a separate command, so only tests see it.
    monkeypatch.setattr(hold_expiry.logger, "disabled", False)
    caplog.set_level(logging.ERROR, logger=hold_expiry.logger.name)
    timer = HoldExpiryTimer(session_factory=MagicMock, clock=lambda: _NOW)

    timer.run_once()  # does not raise

    assert "expiring tentative venue holds failed" in caplog.text


@pytest.mark.story("SCRUM-108")
def test_the_timer_ticks_until_it_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    ticked = threading.Event()
    monkeypatch.setattr(hold_expiry, "expire_due_holds", lambda db, now: ticked.set())
    timer = HoldExpiryTimer(interval=0.01, session_factory=MagicMock, clock=lambda: _NOW)

    timer.start()
    assert ticked.wait(timeout=2)
    timer.stop()

    assert timer._thread is not None and not timer._thread.is_alive()


@pytest.mark.story("SCRUM-108")
async def test_the_app_starts_the_timer_on_startup_and_stops_it_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(hold_expiry.HoldExpiryTimer, "start", lambda self: events.append("start"))
    monkeypatch.setattr(hold_expiry.HoldExpiryTimer, "stop", lambda self: events.append("stop"))
    app = main.create_app()

    async with app.router.lifespan_context(app):
        assert events == ["start"]

    assert events == ["start", "stop"]
