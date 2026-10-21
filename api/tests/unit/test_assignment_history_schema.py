"""SCRUM-105: AssignmentHistoryRead carries each person's email beside their id.

The history columns are foreign keys to users, so a missing user row cannot be arranged
in the database (ADR-0047). The fallback is proved here, on the schema, and in the UI.
"""

import uuid
from datetime import UTC, datetime

import pytest

from models.event_coordinator_assignment import EventCoordinatorAssignment
from schemas.event_requests import AssignmentHistoryRead

ASSIGNED_AT = datetime(2026, 10, 20, 1, 30, tzinfo=UTC)


def entry(previous: uuid.UUID | None) -> EventCoordinatorAssignment:
    return EventCoordinatorAssignment(
        id=uuid.uuid4(),
        event_request_id=uuid.uuid4(),
        previous_coordinator_id=previous,
        new_coordinator_id=uuid.uuid4(),
        acted_by_id=uuid.uuid4(),
        assigned_at=ASSIGNED_AT,
    )


@pytest.mark.story("SCRUM-105")
def test_from_row_pairs_each_id_with_its_email() -> None:
    row = entry(previous=uuid.uuid4())

    read = AssignmentHistoryRead.from_row(row, "a@example.com", "b@example.com", "l@example.com")

    assert (read.id, read.assigned_at) == (row.id, ASSIGNED_AT)
    assert (read.previous_coordinator_id, read.previous_coordinator_email) == (
        row.previous_coordinator_id,
        "a@example.com",
    )
    assert (read.new_coordinator_id, read.new_coordinator_email) == (
        row.new_coordinator_id,
        "b@example.com",
    )
    assert (read.acted_by_id, read.acted_by_email) == (row.acted_by_id, "l@example.com")


@pytest.mark.story("SCRUM-105")
def test_missing_users_give_null_emails_but_keep_their_ids() -> None:
    """The UI's "Unknown user": an id is present but its email is not."""
    row = entry(previous=uuid.uuid4())

    read = AssignmentHistoryRead.from_row(row, None, None, None)

    assert read.previous_coordinator_id == row.previous_coordinator_id
    assert read.new_coordinator_id == row.new_coordinator_id
    assert read.acted_by_id == row.acted_by_id
    assert (read.previous_coordinator_email, read.new_coordinator_email, read.acted_by_email) == (
        None,
        None,
        None,
    )


@pytest.mark.story("SCRUM-105")
def test_first_assignment_has_neither_previous_id_nor_email() -> None:
    """Distinct from a missing user: "First assignment", not "Unknown user"."""
    read = AssignmentHistoryRead.from_row(
        entry(previous=None), None, "b@example.com", "l@example.com"
    )

    assert read.previous_coordinator_id is None
    assert read.previous_coordinator_email is None
