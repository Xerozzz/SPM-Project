"""SCRUM-85 API evidence: configurable reminders about incomplete arrangements.

Against real PostgreSQL, because the things that matter most here are not pure: the
schedule's uniqueness, the once-only processing of an occurrence under a lock, and the
fact that what counts as outstanding is read from SCRUM-80's merged readiness rather
than worked out again.

`arranged_event` gives a plan that is still missing its safety approval, and
`ready_event` gives one with nothing outstanding; between them they are the two answers
a reminder can get.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.event_reminder import ReminderOutcome
from domain.event_status import EventStatus
from domain.notifications import NotificationSource
from domain.venue_booking import BookingStatus
from models.event_reminder import EventReminder
from models.event_request import EventRequest
from models.notification import Notification
from models.user import User
from models.venue_booking import VenueBooking
from services import event_reminders as service
from tests.integration.test_event_confirmation import approve_safety, ready_event
from tests.integration.test_safety_review import _NOW, _START, arranged_event
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_search import effective_for, make_venue

#: `arranged_event` holds its venue only until a day before the event starts, so after
#: that the plan is genuinely incomplete and a reminder is right to fire. A test about a
#: *complete* plan therefore has to process its occurrence while the hold is still live:
#: two days of lead time, processed a day and a half before the event.
_COMPLETE_LEAD = 2880
_WHILE_HELD = _START - timedelta(days=1, hours=12)


def _inbox(db: Session, user: User) -> list[Notification]:
    """The reminders addressed to this user, oldest first.

    Filtered to this story's source rather than reading the whole inbox: arranging an
    event legitimately notifies its Coordinator about other things — a safety decision,
    for one — and a test about reminders should not fail because another story did its
    job.
    """
    return list(
        db.scalars(
            select(Notification)
            .where(
                Notification.recipient_id == user.id,
                Notification.source_type == NotificationSource.EVENT_REMINDER,
            )
            .order_by(Notification.occurred_at)
        )
    )


def schedule(db: Session, event: EventRequest, coordinator: User, *minutes: int) -> None:
    """Put a schedule on the event the way the Coordinator would."""
    service.configure(db, event, list(minutes), coordinator.id, _NOW)


def reminders_of(db: Session, event: EventRequest) -> list[EventReminder]:
    return service.list_for_event(db, event)


@pytest.mark.story("SCRUM-85")
async def test_the_assigned_coordinator_sets_and_reads_a_schedule(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 and AC2: one or more distinct lead times, theirs to see and change."""
    event, _, coordinator = arranged_event(db, make_user)

    async with make_client(coordinator) as client:
        saved = await client.put(
            f"/api/event-requests/{event.id}/reminders", json={"lead_minutes": [60, 1440]}
        )
        read = await client.get(f"/api/event-requests/{event.id}/reminders")

    assert saved.status_code == 200
    # Longest lead time first, so the schedule reads as a timeline towards the event.
    assert [row["lead_minutes"] for row in read.json()] == [1440, 60]
    assert all(row["processed_at"] is None for row in read.json())


@pytest.mark.story("SCRUM-85")
@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ([0], "must be more than zero minutes"),
        ([-30], "must be more than zero minutes"),
        ([90.5], "must be whole minutes"),
        ([60, 60], "must not repeat a lead time"),
    ],
)
async def test_an_invalid_schedule_is_refused_whole(
    db: Session, make_user: MakeUser, make_client: MakeClient, values: list[object], reason: str
) -> None:
    """AC1: refused "without partial changes" — the stored schedule is untouched."""
    event, _, coordinator = arranged_event(db, make_user)
    schedule(db, event, coordinator, 120)

    async with make_client(coordinator) as client:
        response = await client.put(
            f"/api/event-requests/{event.id}/reminders", json={"lead_minutes": values}
        )

    assert response.status_code == 422
    assert reason in str(response.json())
    db.expire_all()
    assert [row.lead_minutes for row in reminders_of(db, event)] == [120]


@pytest.mark.story("SCRUM-85")
async def test_a_part_valid_schedule_saves_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC1 again, with the case that actually tempts a partial save: one good, one bad."""
    event, _, coordinator = arranged_event(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.put(
            f"/api/event-requests/{event.id}/reminders", json={"lead_minutes": [60, 0]}
        )

    assert response.status_code == 422
    assert reminders_of(db, event) == []


@pytest.mark.story("SCRUM-85")
async def test_only_the_assigned_coordinator_sees_or_sets_the_schedule(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: a Lead, the Organiser and another Coordinator get nothing from those roles."""
    event, _, _ = arranged_event(db, make_user)

    for other in ("coordinator", "organiser", "coordinator_lead", "safety_officer"):
        async with make_client(make_user(other)) as client:
            read = await client.get(f"/api/event-requests/{event.id}/reminders")
            written = await client.put(
                f"/api/event-requests/{event.id}/reminders", json={"lead_minutes": [60]}
            )
        assert (read.status_code, written.status_code) == (403, 403), other


@pytest.mark.story("SCRUM-85")
async def test_reassignment_moves_the_schedule_to_the_new_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC2: "reassignment transfers access", because the check is the current assignee."""
    event, _, first = arranged_event(db, make_user)
    schedule(db, event, first, 60)
    second = make_user("coordinator")
    event.coordinator_id = second.id
    db.flush()

    async with make_client(second) as client:
        theirs = await client.get(f"/api/event-requests/{event.id}/reminders")
    async with make_client(first) as client:
        former = await client.get(f"/api/event-requests/{event.id}/reminders")

    assert theirs.status_code == 200
    assert [row["lead_minutes"] for row in theirs.json()] == [60]
    assert former.status_code == 403


@pytest.mark.story("SCRUM-85")
def test_a_due_occurrence_on_an_incomplete_plan_notifies_the_coordinator(
    db: Session, make_user: MakeUser
) -> None:
    """AC3 and AC5: the arrangements are evaluated, and the Coordinator is told."""
    event, _, coordinator = arranged_event(db, make_user)  # no safety approval yet
    schedule(db, event, coordinator, 60)

    done = service.process_due(db, _START - timedelta(minutes=30))

    assert [row.outcome for row in done] == [ReminderOutcome.NOTIFIED]
    inbox = _inbox(db, coordinator)
    assert [row.type.value for row in inbox] == ["arrangements_incomplete"]
    assert inbox[0].event_request_id == event.id


@pytest.mark.story("SCRUM-85")
def test_a_due_occurrence_on_a_complete_plan_notifies_nobody(
    db: Session, make_user: MakeUser
) -> None:
    """AC5: "if no work remains, create none" — but the occurrence is still processed."""
    event, _, coordinator = ready_event(db, make_user)
    schedule(db, event, coordinator, _COMPLETE_LEAD)

    done = service.process_due(db, _WHILE_HELD)

    assert [row.outcome for row in done] == [ReminderOutcome.NOTHING_OUTSTANDING]
    assert _inbox(db, coordinator) == []
    assert reminders_of(db, event)[0].processed_at is not None


@pytest.mark.story("SCRUM-85")
def test_an_occurrence_is_processed_only_once(db: Session, make_user: MakeUser) -> None:
    """AC6: at most one per occurrence, whatever a retry or a second run does."""
    event, _, coordinator = arranged_event(db, make_user)
    schedule(db, event, coordinator, 60)
    at = _START - timedelta(minutes=30)

    first = service.process_due(db, at)
    second = service.process_due(db, at + timedelta(minutes=1))

    assert len(first) == 1 and second == []
    assert len(_inbox(db, coordinator)) == 1


@pytest.mark.story("SCRUM-85")
def test_an_occurrence_that_has_not_fallen_due_waits(db: Session, make_user: MakeUser) -> None:
    event, _, coordinator = arranged_event(db, make_user)
    schedule(db, event, coordinator, 60)

    assert service.process_due(db, _START - timedelta(hours=2)) == []
    assert reminders_of(db, event)[0].processed_at is None


@pytest.mark.story("SCRUM-85")
def test_nothing_is_sent_once_the_event_has_started(db: Session, make_user: MakeUser) -> None:
    """AC7: a missed occurrence is caught up only while the event is still upcoming."""
    event, _, coordinator = arranged_event(db, make_user)
    schedule(db, event, coordinator, 60)

    assert service.process_due(db, _START + timedelta(minutes=1)) == []
    assert _inbox(db, coordinator) == []


@pytest.mark.story("SCRUM-85")
def test_a_missed_occurrence_is_caught_up_once(db: Session, make_user: MakeUser) -> None:
    """AC7: a tick that never ran is not lost, and does not become a burst either."""
    event, _, coordinator = arranged_event(db, make_user)
    schedule(db, event, coordinator, 1440)  # a day before
    just_before_start = _START - timedelta(minutes=5)

    caught_up = service.process_due(db, just_before_start)
    again = service.process_due(db, just_before_start + timedelta(minutes=1))

    assert [row.lead_minutes for row in caught_up] == [1440]
    assert again == []
    assert len(_inbox(db, coordinator)) == 1


@pytest.mark.story("SCRUM-85")
@pytest.mark.parametrize("status", [EventStatus.CANCELLED, EventStatus.COMPLETED])
def test_no_reminder_for_a_cancelled_or_completed_event(
    db: Session, make_user: MakeUser, status: EventStatus
) -> None:
    """AC7 names both: there is nothing left to arrange for either."""
    event, _, coordinator = arranged_event(db, make_user)
    schedule(db, event, coordinator, 60)
    event.status = status
    db.flush()

    assert service.process_due(db, _START - timedelta(minutes=30)) == []
    assert _inbox(db, coordinator) == []


@pytest.mark.story("SCRUM-85")
def test_changing_the_schedule_does_not_resend_a_delivered_occurrence(
    db: Session, make_user: MakeUser
) -> None:
    """AC6: the kept lead time keeps its row, and with it what it has already done."""
    event, _, coordinator = arranged_event(db, make_user)
    schedule(db, event, coordinator, 60)
    service.process_due(db, _START - timedelta(minutes=30))
    kept = next(row for row in reminders_of(db, event) if row.lead_minutes == 60)
    sent_at = kept.processed_at
    assert sent_at is not None

    schedule(db, event, coordinator, 60, 1440)  # add another, keep the first

    kept = next(row for row in reminders_of(db, event) if row.lead_minutes == 60)
    assert kept.processed_at == sent_at, "the kept row lost its history"
    service.process_due(db, _START - timedelta(minutes=20))

    # The added day-before occurrence is due as well and rightly fires; what must not
    # happen is a second notification for the occurrence already delivered, so this
    # counts by source rather than by inbox size.
    for_kept = [row for row in _inbox(db, coordinator) if row.source_id == str(kept.id)]
    assert len(for_kept) == 1


@pytest.mark.story("SCRUM-85")
def test_moving_the_event_moves_future_occurrences_and_keeps_history(
    db: Session, make_user: MakeUser
) -> None:
    """AC8: the due time is derived from the event, so it follows a change of plan.

    The hour-before occurrence has already been sent. Pushing the event a week out does
    not resend it, and the day-before occurrence — which had not fallen due — now falls
    due against the new start rather than the old one.
    """
    event, _, coordinator = arranged_event(db, make_user)
    schedule(db, event, coordinator, 60, 1440)
    # Half a day out: the day-before occurrence has fallen due, the hour-before has not.
    # Lead times nest, so this is the only way to have one fire and not the other.
    service.process_due(db, _START - timedelta(hours=12))
    assert len(_inbox(db, coordinator)) == 1

    moved = _START + timedelta(days=7)
    event.start_at = moved
    event.end_at = moved + timedelta(hours=2)
    db.flush()

    # The hour-before occurrence was an hour away under the old start and is a week and
    # an hour away under the new one, so nothing fires at the old moment.
    assert service.process_due(db, _START) == []
    later = service.process_due(db, moved - timedelta(minutes=30))

    assert [row.lead_minutes for row in later] == [60]
    assert len(_inbox(db, coordinator)) == 2


@pytest.mark.story("SCRUM-85")
def test_a_superseded_arrangement_does_not_create_a_false_reminder(
    db: Session, make_user: MakeUser
) -> None:
    """AC4: "retained historical superseded arrangements do not create false reminders".

    The event keeps a refused venue request forever — nobody can clear one — beside the
    hold that actually stands. Judging the dead row would report an incomplete venue
    arrangement every time, for an event that is in fact fully arranged.

    True because this reads SCRUM-80's readiness, which already excludes rows that are
    history rather than plan, not because it is checked again here. The test exists to
    prove the reuse really happens.
    """
    event, _, coordinator = arranged_event(db, make_user)
    approve_safety(db, event, make_user)
    refused_venue = make_venue(db, name=f"Hall {uuid.uuid4()}")
    effective_start, effective_end = effective_for(
        refused_venue, _START, _START + timedelta(hours=2)
    )
    db.add(
        VenueBooking(
            venue_id=refused_venue.id,
            event_request_id=event.id,
            requested_by_id=coordinator.id,
            session_label="Tried and refused",
            start_at=_START,
            end_at=_START + timedelta(hours=2),
            effective_start_at=effective_start,
            effective_end_at=effective_end,
            status=BookingStatus.REJECTED,
        )
    )
    db.flush()
    schedule(db, event, coordinator, _COMPLETE_LEAD)

    done = service.process_due(db, _WHILE_HELD)

    assert [row.outcome for row in done] == [ReminderOutcome.NOTHING_OUTSTANDING]
    assert _inbox(db, coordinator) == []


@pytest.mark.story("SCRUM-85")
async def test_an_empty_schedule_clears_every_reminder(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Removing the last reminder has to be possible, and the screen does it this way.

    AC1 asks for "one or more distinct lead times", which is about what a schedule may
    contain rather than a floor on it: a Coordinator who no longer wants reminding sends
    an empty list, and the panel's Remove button on the last row does exactly that.
    """
    event, _, coordinator = arranged_event(db, make_user)
    schedule(db, event, coordinator, 60, 1440)

    async with make_client(coordinator) as client:
        response = await client.put(
            f"/api/event-requests/{event.id}/reminders", json={"lead_minutes": []}
        )

    assert response.status_code == 200
    assert response.json() == []
    db.expire_all()
    assert reminders_of(db, event) == []
