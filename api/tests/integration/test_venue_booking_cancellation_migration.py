"""SCRUM-109: migration 0038 and what the database itself enforces about cancellation.

The record must be complete once a row is cancelled (AC2), and a cancelled row must not
occupy its slot (AC3). The second is the exclusion constraint from 0021, which this
story deliberately leaves alone, so these tests pin it rather than trust it.
"""

from datetime import UTC, datetime, timedelta

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from core.database import engine
from domain.venue_booking import BookingStatus
from tests.integration.test_submit_event_request import MakeUser
from tests.integration.test_venue_buffer_conflicts import booking_for
from tests.integration.test_venue_search import make_venue

_START = datetime(2031, 5, 6, 2, 0, tzinfo=UTC)
_END = _START + timedelta(hours=2)
_COLUMNS = {"cancelled_by_id", "cancelled_at", "cancellation_reason"}


def _booking_columns() -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("venue_bookings")}


def _check_names() -> set[str]:
    checks = inspect(engine).get_check_constraints("venue_bookings")
    return {name for check in checks if (name := check["name"]) is not None}


@pytest.mark.story("SCRUM-109")
def test_migration_adds_and_removes_only_the_cancellation_record() -> None:
    command.downgrade(Config("alembic.ini"), "0037")
    try:
        assert not _COLUMNS & _booking_columns()
        assert "venue_bookings_cancelled_has_record" not in _check_names()
        command.upgrade(Config("alembic.ini"), "0038")
        assert _booking_columns() >= _COLUMNS
        assert "venue_bookings_cancelled_has_record" in _check_names()
    finally:
        command.upgrade(Config("alembic.ini"), "head")
    # Downgrading took nothing else with it.
    assert {"status", "decided_by_id", "expires_at", "held_by_id"} <= _booking_columns()
    assert "venue_bookings_tentative_has_hold" in _check_names()


@pytest.mark.story("SCRUM-109")
def test_the_overlap_constraint_still_covers_only_confirmed_and_tentative(db: Session) -> None:
    definition = db.scalar(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'venue_bookings_no_confirmed_overlap'"
        )
    )
    assert definition is not None
    assert "effective_start_at" in definition and "effective_end_at" in definition
    assert "'confirmed'" in definition and "'tentative'" in definition
    assert "'cancelled'" not in definition


@pytest.mark.story("SCRUM-109")
@pytest.mark.parametrize("missing", sorted(_COLUMNS), ids=lambda name: f"without {name}")
def test_a_cancelled_row_must_say_who_when_and_why(
    missing: str, db: Session, make_user: MakeUser
) -> None:
    """AC2: the database refuses a cancellation record with any part missing."""
    coordinator = make_user("coordinator")
    row = booking_for(db, coordinator, make_venue(db), _START, _END, status=BookingStatus.PENDING)
    record = {
        "cancelled_by_id": coordinator.id,
        "cancelled_at": datetime.now(UTC),
        "cancellation_reason": "No longer needed",
    }
    record[missing] = None
    refused = pytest.raises(IntegrityError, match="venue_bookings_cancelled_has_record")
    with refused, db.begin_nested():
        db.execute(
            text(
                "UPDATE venue_bookings SET status = 'cancelled', "
                "cancelled_by_id = :cancelled_by_id, cancelled_at = :cancelled_at, "
                "cancellation_reason = :cancellation_reason WHERE id = :id"
            ),
            {**record, "id": row.id},
        )


@pytest.mark.story("SCRUM-109")
def test_the_database_lets_a_booking_overlap_a_cancelled_one(
    db: Session, make_user: MakeUser
) -> None:
    """AC3 at the lowest level: the slot of a cancelled booking is free, while the same
    overlap with a live booking is still refused."""
    coordinator = make_user("coordinator")
    venue = make_venue(db)
    booking_for(db, coordinator, venue, _START, _END, status=BookingStatus.CANCELLED)
    booking_for(db, coordinator, venue, _START, _END, status=BookingStatus.CONFIRMED)

    refused = pytest.raises(IntegrityError, match="venue_bookings_no_confirmed_overlap")
    with refused, db.begin_nested():
        booking_for(db, coordinator, venue, _START, _END, status=BookingStatus.CONFIRMED)
