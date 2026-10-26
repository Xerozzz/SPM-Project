"""The minute timer that sends arrangement reminders (SCRUM-85).

The same shape as `core.hold_expiry`: a plain background thread started and stopped with
the app, each tick opening its own session, a failed tick logged and left for the next
one. Deliberately a second timer rather than a second job inside that one — the two have
nothing to say to each other, and a reminder sweep that threw would otherwise stop holds
expiring.

The duplication is about thirty lines of thread mechanics. Factoring it into a shared
helper is the obvious next step, but it would mean reworking SCRUM-108's timer, which
this story has no reason to touch.

A tick that never runs loses nothing: an occurrence stays unprocessed and is picked up by
a later tick while the event is still upcoming (AC7), which is why the rule asks whether
an occurrence is *due*, not whether it falls in this minute.
"""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from core.database import SessionLocal
from services.event_reminders import process_due

logger = logging.getLogger(__name__)

#: How often to look for occurrences that have fallen due. A reminder therefore arrives
#: at most this long after the moment the Coordinator asked for.
INTERVAL_SECONDS = 60.0


def _now() -> datetime:
    return datetime.now(UTC)


class ReminderSweepTimer:
    """Runs `process_due` every `interval` seconds until stopped."""

    def __init__(
        self,
        interval: float = INTERVAL_SECONDS,
        session_factory: Callable[[], Session] = SessionLocal,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._interval = interval
        self._session_factory = session_factory
        self._clock = clock
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> None:
        """One tick. Never raises: a failure is logged and left for the next tick.

        AC8: a failure here leaves the occurrence unprocessed, because the row is marked
        in the same transaction as the notification it raised. Nothing is recorded as
        sent that was not sent.
        """
        try:
            with self._session_factory() as db:
                process_due(db, self._clock())
        except Exception:
            logger.exception("sending arrangement reminders failed")

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="reminder-sweep", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        # Wait first, then work: the app is fully up before the first tick.
        while not self._stopped.wait(self._interval):
            self.run_once()
