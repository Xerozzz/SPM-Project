"""The minute timer that expires tentative venue holds (SCRUM-108, ADR-0030).

A plain background thread started and stopped with the app, so no scheduler library is
needed. Each tick opens its own session, runs services.venue_hold_expiry and closes it.
A failed tick is logged and the next one tries again, so one bad run never stops expiry.
"""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from core.database import SessionLocal
from services.venue_hold_expiry import expire_due_holds

logger = logging.getLogger(__name__)

# How often to look for holds that have run out. A hold therefore stops blocking at most
# this long after its expiry, unless a hold or approval at that venue expires it first.
INTERVAL_SECONDS = 60.0


def _now() -> datetime:
    return datetime.now(UTC)


class HoldExpiryTimer:
    """Runs `expire_due_holds` every `interval` seconds until stopped."""

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
        """One tick. Never raises: a failure is logged and left for the next tick."""
        try:
            with self._session_factory() as db:
                expire_due_holds(db, self._clock())
        except Exception:
            logger.exception("expiring tentative venue holds failed")

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="hold-expiry", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        # Wait first, then work: the app is fully up before the first tick.
        while not self._stopped.wait(self._interval):
            self.run_once()
