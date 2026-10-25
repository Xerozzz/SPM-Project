"""SCRUM-115: cancel a whole event and release everything it holds.

Against real PostgreSQL, so the locks, the partial unique index on pending requests and
the one-commit release are exercised rather than only the pure rules. Attendee
notifications are SCRUM-135's and are not tested here.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.change_decision import Decision
from domain.equipment_requirement import RequirementFields, RequirementReview
from domain.event_cancellation import RequestStatus
from domain.event_status import EventStatus
from domain.notifications import NotificationType
from domain.registration import RegistrationStatus
from domain.roles import Role
from domain.venue_booking import BookingStatus
from models.equipment_reservation import EquipmentReservation
from models.event_cancellation_request import EventCancellationRequest
from models.event_registration import EventRegistration, EventRegistrationHistory
from models.event_request import EventRequest
from models.notification import Notification
from models.user import User
from models.venue_booking import VenueBooking
from repositories import equipment as catalogue_repo
from repositories import equipment_reservations as reservation_repo
from repositories import event_registrations as registration_repo
from repositories import safety_reviews as safety_repo
from repositories import venue_availability as booking_repo
from services import equipment_requirements as requirement_service
from services import equipment_reservations as reservation_service
from services import event_cancellations as service
from services import event_change_requests, event_confirmations, event_registrations
from services import lifecycle_notifications as lifecycle
from services.event_requests import NotAuthorisedError
from tests.integration.test_event_confirmation import ready_event
from tests.integration.test_safety_review import _NOW, _START
from tests.integration.test_submit_event_request import MakeClient, MakeUser, make_draft
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_search import effective_for, make_venue

_END = _START + timedelta(hours=2)


def _url(event: EventRequest, path: str) -> str:
    return f"/api/event-requests/{event.id}/{path}"


def _stored(db: Session, event: EventRequest) -> EventRequest:
    db.expire_all()
    row = db.get(EventRequest, event.id)
    assert row is not None
    return row


def _status(db: Session, booking: VenueBooking) -> BookingStatus:
    row = db.get(VenueBooking, booking.id)
    assert row is not None
    return row.status


def _got(db: Session, user_id: uuid.UUID | None, kind: NotificationType) -> int:
    db.expire_all()
    statement = select(Notification).where(
        Notification.recipient_id == user_id, Notification.type == kind.value
    )
    return len(list(db.scalars(statement)))


def _confirmed(db: Session, make_user: MakeUser) -> tuple[EventRequest, VenueBooking, User]:
    """A Confirmed event with a Confirmed booking, reserved equipment and a safety
    approval, each recorded against the staff member who did it."""
    event, booking, coordinator = ready_event(db, make_user)
    event_confirmations.confirm(db, event, coordinator.id, _NOW)
    return event, booking, coordinator


def _booking(db: Session, event: EventRequest, status: BookingStatus) -> VenueBooking:
    """One more venue request for `event`, at a venue of its own, in `status`."""
    venue = make_venue(db, name=f"Room {uuid.uuid4()}")
    start, end = effective_for(venue, _START, _END)
    assert event.coordinator_id is not None
    booking = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=event.coordinator_id,
        session_label=f"Session {uuid.uuid4()}",
        start_at=_START,
        end_at=_END,
        effective_start_at=start,
        effective_end_at=end,
        status=status,
    )
    db.add(booking)
    db.flush()
    return booking


def _other_event(db: Session, make_user: MakeUser) -> tuple[EventRequest, VenueBooking]:
    """An unrelated planning event with its own booking and a reserved Projector."""
    coordinator = make_user("coordinator")
    event = approved_event(db, make_user("organiser"), coordinator, start_at=_START, end_at=_END)
    booking = _booking(db, event, BookingStatus.PENDING)
    requirement = requirement_service.add(
        db, event, RequirementFields(equipment_type="Projector", quantity=2), coordinator.id, _NOW
    )
    requirement_service.review(db, requirement.id, RequirementReview.AVAILABLE, _NOW)
    reservation_service.reserve(
        db, event.id, requirement.id, None, make_user("tech_support").id, _NOW
    )
    return event, booking


def _register(db: Session, event: EventRequest, make_user: MakeUser) -> EventRegistration:
    attendee = make_user("attendee")
    return event_registrations.submit(
        db, event.id, attendee.id, "Ada Lovelace", 24, "+65 8123 4567", None, _NOW
    )


def _reservations(db: Session, event: EventRequest) -> list[EquipmentReservation]:
    db.expire_all()
    statement = select(EquipmentReservation).where(
        EquipmentReservation.event_request_id == event.id
    )
    return list(db.scalars(statement))


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-115")
async def test_the_organiser_asks_and_the_coordinator_is_told(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    organiser = db.get(User, event.organiser_id)

    async with make_client(organiser) as client:
        response = await client.post(
            _url(event, "cancellation-requests"), json={"reason": "  Speaker is ill  "}
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["reason"] == "Speaker is ill"
    assert body["requested_by_id"] == str(event.organiser_id)
    assert _got(db, coordinator.id, NotificationType.CANCELLATION_REQUESTED) == 1
    # Asking changes nothing about the event yet.
    assert _stored(db, event).status is EventStatus.CONFIRMED
    assert _status(db, booking) is BookingStatus.CONFIRMED


@pytest.mark.story("SCRUM-115")
async def test_only_the_owning_organiser_can_ask(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    for user in [coordinator, make_user("organiser"), make_user("coordinator_lead")]:
        async with make_client(user) as client:
            response = await client.post(
                _url(event, "cancellation-requests"), json={"reason": "No"}
            )
        assert response.status_code == 403
    assert service.requests_of(db, event) == []


@pytest.mark.story("SCRUM-115")
async def test_a_request_needs_a_reason_and_only_one_waits_at_a_time(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, _ = _confirmed(db, make_user)
    organiser = db.get(User, event.organiser_id)

    async with make_client(organiser) as client:
        blank = await client.post(_url(event, "cancellation-requests"), json={"reason": " "})
        first = await client.post(_url(event, "cancellation-requests"), json={"reason": "A"})
        second = await client.post(_url(event, "cancellation-requests"), json={"reason": "B"})

    assert blank.status_code == 422
    assert blank.json()["detail"] == [{"field": "reason", "reason": "is required"}]
    assert first.status_code == 201
    assert second.status_code == 409
    assert [row.reason for row in service.requests_of(db, event)] == ["A"]


@pytest.mark.story("SCRUM-115")
async def test_the_coordinator_applies_a_request_with_its_reason(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    request = service.request_cancellation(db, event.id, event.organiser_id, "Funding cut", _NOW)

    async with make_client(coordinator) as client:
        response = await client.post(_url(event, "cancel"), json={"request_id": str(request.id)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["cancellation_reason"] == "Funding cut"
    assert [row["status"] for row in body["requests"]] == ["applied"]
    assert body["requests"][0]["decided_by_id"] == str(coordinator.id)


@pytest.mark.story("SCRUM-115")
async def test_the_coordinator_declines_a_request_with_a_note(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    request = service.request_cancellation(db, event.id, event.organiser_id, "Low sign-ups", _NOW)
    decline = _url(event, f"cancellation-requests/{request.id}/decline")

    async with make_client(coordinator) as client:
        blank = await client.post(decline, json={"note": ""})
        unknown = await client.post(
            _url(event, f"cancellation-requests/{uuid.uuid4()}/decline"), json={"note": "x"}
        )
        response = await client.post(decline, json={"note": "Numbers are fine for this room"})
        again = await client.post(decline, json={"note": "Twice"})

    assert blank.status_code == 422
    assert unknown.status_code == 404
    assert response.status_code == 200
    assert response.json()["status"] == "declined"
    assert response.json()["decision_note"] == "Numbers are fine for this room"
    assert again.status_code == 404
    assert _got(db, event.organiser_id, NotificationType.CANCELLATION_DECLINED) == 1
    assert _stored(db, event).status is EventStatus.CONFIRMED
    assert _status(db, booking) is BookingStatus.CONFIRMED


@pytest.mark.story("SCRUM-115")
async def test_the_coordinator_cancels_on_their_own_and_answers_a_waiting_request(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    service.request_cancellation(db, event.id, event.organiser_id, "Please cancel", _NOW)

    async with make_client(coordinator) as client:
        missing = await client.post(_url(event, "cancel"), json={})
        response = await client.post(_url(event, "cancel"), json={"reason": "Venue flooded"})

    assert missing.status_code == 422
    assert missing.json()["detail"] == [{"field": "reason", "reason": "is required"}]
    assert response.status_code == 200
    assert response.json()["cancellation_reason"] == "Venue flooded"
    assert [row.status for row in service.requests_of(db, event)] == [RequestStatus.APPLIED]


@pytest.mark.story("SCRUM-115")
async def test_applying_a_request_that_is_not_waiting_is_not_found(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _confirmed(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(
            _url(event, "cancel"), json={"request_id": str(uuid.uuid4()), "reason": "x"}
        )

    assert response.status_code == 404
    assert _stored(db, event).status is EventStatus.CONFIRMED


@pytest.mark.story("SCRUM-115")
async def test_the_requests_are_for_the_owner_the_coordinator_and_leads(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    service.request_cancellation(db, event.id, event.organiser_id, "Please cancel", _NOW)
    organiser = db.get(User, event.organiser_id)
    hold_staff = db.get(User, booking.held_by_id)
    assert organiser is not None and hold_staff is not None

    for user in [organiser, coordinator, make_user("coordinator_lead")]:
        async with make_client(user) as client:
            response = await client.get(_url(event, "cancellation"))
        assert response.status_code == 200
        assert [row["reason"] for row in response.json()["requests"]] == ["Please cancel"]
    for user in [make_user("coordinator"), hold_staff, make_user("attendee")]:
        async with make_client(user) as client:
            assert (await client.get(_url(event, "cancellation"))).status_code == 403


# --------------------------------------------------------------------------- AC2, AC3


@pytest.mark.story("SCRUM-115")
async def test_only_the_current_assigned_coordinator_cancels(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, _ = _confirmed(db, make_user)
    organiser = db.get(User, event.organiser_id)
    hold_staff = db.get(User, booking.held_by_id)

    for user in [organiser, make_user("coordinator"), make_user("coordinator_lead"), hold_staff]:
        async with make_client(user) as client:
            response = await client.post(_url(event, "cancel"), json={"reason": "No"})
        assert response.status_code == 403
    assert _stored(db, event).status is EventStatus.CONFIRMED


@pytest.mark.story("SCRUM-115")
async def test_cancelling_records_who_when_and_why(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _confirmed(db, make_user)

    async with make_client(coordinator) as client:
        response = await client.post(_url(event, "cancel"), json={"reason": " Storm warning "})

    assert response.status_code == 200
    stored = _stored(db, event)
    assert stored.status is EventStatus.CANCELLED
    assert stored.cancelled_by_id == coordinator.id
    assert stored.cancelled_at is not None
    assert stored.cancellation_reason == "Storm warning"
    assert response.json()["cancelled_at"] is not None


@pytest.mark.story("SCRUM-115")
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (EventStatus.DRAFT, "Only a submitted, planning or confirmed event can be cancelled"),
        (EventStatus.REJECTED, "Only a submitted, planning or confirmed event can be cancelled"),
        (EventStatus.COMPLETED, "A completed event cannot be cancelled"),
    ],
)
async def test_draft_rejected_and_completed_events_are_refused(
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
    status: EventStatus,
    message: str,
) -> None:
    coordinator = make_user("coordinator")
    organiser = make_user("organiser")
    event = make_draft(db, organiser)
    event.status = status
    event.coordinator_id = coordinator.id
    db.flush()

    async with make_client(coordinator) as client:
        cancel = await client.post(_url(event, "cancel"), json={"reason": "x"})
    async with make_client(organiser) as client:
        ask = await client.post(_url(event, "cancellation-requests"), json={"reason": "x"})

    assert cancel.status_code == 409
    assert cancel.json()["detail"] == message
    assert ask.status_code == 409
    assert _stored(db, event).status is status


@pytest.mark.story("SCRUM-115")
async def test_a_submitted_event_can_be_cancelled(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    coordinator = make_user("coordinator")
    event = make_draft(db, make_user("organiser"))
    event.status = EventStatus.SUBMITTED
    event.coordinator_id = coordinator.id
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.post(_url(event, "cancel"), json={"reason": "Withdrawn"})

    assert response.status_code == 200
    assert _stored(db, event).status is EventStatus.CANCELLED


# --------------------------------------------------------------------------- AC4, AC5


@pytest.mark.story("SCRUM-115")
def test_a_confirmed_event_releases_its_booking_and_equipment(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    other, other_booking = _other_event(db, make_user)
    before = _reservations(db, event)
    assert [row.released_at for row in before] == [None]
    nobody = uuid.uuid4()
    assert catalogue_repo.reserved_quantity(db, "Projector", _START, _END, nobody) == 3
    assert booking.venue_id in booking_repo.venue_ids_with_confirmed_overlap(db, _START, _END)

    service.cancel(db, event.id, coordinator.id, "Storm warning", None, _NOW)

    db.expire_all()
    cancelled = db.get(VenueBooking, booking.id)
    assert cancelled is not None and cancelled.status is BookingStatus.CANCELLED
    assert cancelled.cancelled_by_id == coordinator.id
    assert cancelled.cancellation_reason == "Storm warning"
    # The original row and who held it stay.
    assert cancelled.held_by_id == booking.held_by_id is not None
    assert booking.venue_id not in booking_repo.venue_ids_with_confirmed_overlap(db, _START, _END)
    after = _reservations(db, event)
    assert [(row.quantity, row.released_at, row.released_by_id) for row in after] == [
        (1, _NOW, coordinator.id)
    ]
    # Only the other event's two Projectors are still held.
    assert catalogue_repo.reserved_quantity(db, "Projector", _START, _END, nobody) == 2
    assert [row.released_at for row in _reservations(db, other)] == [None]
    assert _status(db, other_booking) is BookingStatus.PENDING


@pytest.mark.story("SCRUM-115")
def test_a_planning_event_cancels_its_request_and_hold_and_keeps_the_rest(
    db: Session, make_user: MakeUser
) -> None:
    event, hold, coordinator = ready_event(db, make_user)
    pending = _booking(db, event, BookingStatus.PENDING)
    rejected = _booking(db, event, BookingStatus.REJECTED)
    assert _status(db, hold) is BookingStatus.TENTATIVE

    service.cancel(db, event.id, coordinator.id, "No budget", None, _NOW)

    db.expire_all()
    assert _status(db, hold) is BookingStatus.CANCELLED
    assert _status(db, pending) is BookingStatus.CANCELLED
    assert _status(db, rejected) is BookingStatus.REJECTED
    assert _stored(db, event).status is EventStatus.CANCELLED


# --------------------------------------------------------------------------- AC6


@pytest.mark.story("SCRUM-115")
def test_registrations_are_cancelled_and_withdrawn_ones_kept(
    db: Session, make_user: MakeUser
) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    event.registration_opened_at = _NOW
    db.flush()
    pending = _register(db, event, make_user)
    accepted = _register(db, event, make_user)
    waitlisted = _register(db, event, make_user)
    withdrawn = _register(db, event, make_user)
    # Each step at its own time, so history reads back in a fixed order.
    decided = _NOW + timedelta(minutes=1)
    registration_repo.decide(
        db, accepted, event.organiser_id, RegistrationStatus.ACCEPTED, decided, None
    )
    registration_repo.decide(
        db, waitlisted, event.organiser_id, RegistrationStatus.WAITLISTED, decided, None
    )
    event_registrations.withdraw(db, event.id, withdrawn.attendee_id, decided)
    later = _NOW + timedelta(hours=1)

    service.cancel(db, event.id, coordinator.id, "Storm warning", None, later)

    db.expire_all()
    stored = _stored(db, event)
    assert stored.registration_closed_at == later
    statuses = {
        row.id: row.status
        for row in db.scalars(
            select(EventRegistration).where(EventRegistration.event_request_id == event.id)
        )
    }
    assert statuses == {
        pending.id: RegistrationStatus.CANCELLED,
        accepted.id: RegistrationStatus.CANCELLED,
        waitlisted.id: RegistrationStatus.CANCELLED,
        withdrawn.id: RegistrationStatus.WITHDRAWN,
    }
    history = registration_repo.list_history(db, accepted.id)
    assert [(row.previous_status, row.status) for row in history][-1] == (
        RegistrationStatus.ACCEPTED,
        RegistrationStatus.CANCELLED,
    )
    assert history[-1].actor_id == coordinator.id
    kept = registration_repo.list_history(db, withdrawn.id)
    assert kept[-1].status is RegistrationStatus.WITHDRAWN


@pytest.mark.story("SCRUM-115")
def test_intake_that_never_opened_gets_no_close_marker(db: Session, make_user: MakeUser) -> None:
    event, _, coordinator = _confirmed(db, make_user)

    service.cancel(db, event.id, coordinator.id, "Storm warning", None, _NOW)

    assert _stored(db, event).registration_closed_at is None


# --------------------------------------------------------------------------- AC7


@pytest.mark.story("SCRUM-115")
async def test_nothing_reconfirms_or_replans_a_cancelled_event(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    service.cancel(db, event.id, coordinator.id, "Storm warning", None, _NOW)

    async with make_client(coordinator) as client:
        confirm = await client.post(_url(event, "confirm"))
        again = await client.post(_url(event, "cancel"), json={"reason": "Again"})
    with pytest.raises(NotAuthorisedError):
        event_change_requests.decide(
            db, event.id, uuid.uuid4(), coordinator.id, Decision.APPROVE, "ok", _NOW
        )

    assert confirm.status_code == 409
    assert again.status_code == 409
    assert again.json()["detail"] == "This event is already cancelled"
    assert _stored(db, event).status is EventStatus.CANCELLED


# --------------------------------------------------------------------------- AC8


@pytest.mark.story("SCRUM-115")
def test_a_failure_leaves_everything_as_it_was(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    event.registration_opened_at = _NOW
    db.flush()
    registration = _register(db, event, make_user)
    request = service.request_cancellation(db, event.id, event.organiser_id, "Please", _NOW)
    db.commit()

    def broken(*_: object) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(reservation_repo, "release_for_event", broken)
    with pytest.raises(RuntimeError):
        service.cancel(db, event.id, coordinator.id, None, request.id, _NOW)
    db.rollback()
    monkeypatch.undo()

    stored = _stored(db, event)
    assert stored.status is EventStatus.CONFIRMED
    assert stored.cancelled_at is None
    assert stored.registration_closed_at is None
    assert _status(db, booking) is BookingStatus.CONFIRMED
    kept = db.get(EventRegistration, registration.id)
    assert kept is not None and kept.status is RegistrationStatus.PENDING
    assert [row.released_at for row in _reservations(db, event)] == [None]
    pending = db.get(EventCancellationRequest, request.id)
    assert pending is not None and pending.status is RequestStatus.PENDING
    assert _got(db, event.organiser_id, NotificationType.EVENT_CANCELLED) == 0


@pytest.mark.story("SCRUM-115")
def test_a_repeat_releases_and_notifies_nothing_more(db: Session, make_user: MakeUser) -> None:
    event, _, coordinator = _confirmed(db, make_user)
    service.cancel(db, event.id, coordinator.id, "Storm warning", None, _NOW)
    first = _reservations(db, event)
    history_rows = len(list(db.scalars(select(EventRegistrationHistory))))

    with pytest.raises(service.NotCancellableError):
        service.cancel(db, event.id, coordinator.id, "Again", None, _NOW + timedelta(hours=1))
    db.rollback()
    # Staging the same notification again collides on its key.
    lifecycle.cancelled(db, _stored(db, event), set(), _NOW + timedelta(hours=1))
    db.commit()

    assert [row.released_at for row in _reservations(db, event)] == [
        row.released_at for row in first
    ]
    assert len(list(db.scalars(select(EventRegistrationHistory)))) == history_rows
    assert _stored(db, event).cancellation_reason == "Storm warning"
    assert _got(db, event.organiser_id, NotificationType.EVENT_CANCELLED) == 1
    assert _got(db, coordinator.id, NotificationType.EVENT_CANCELLED) == 1


# --------------------------------------------------------------------------- AC9


@pytest.mark.story("SCRUM-115")
def test_the_organiser_coordinator_and_staff_who_took_part_are_told(
    db: Session, make_user: MakeUser
) -> None:
    event, booking, coordinator = _confirmed(db, make_user)
    hold_staff = booking.held_by_id
    tech = next(row.created_by_id for row in _reservations(db, event))
    officer = next(row.decided_by_id for row in safety_repo.list_for_event(db, event.id))
    bystanders = [make_user("venue_staff").id, make_user(Role.SAFETY_OFFICER.value).id]

    service.cancel(db, event.id, coordinator.id, "Storm warning", None, _NOW)

    for person in [event.organiser_id, coordinator.id, hold_staff, tech, officer]:
        assert _got(db, person, NotificationType.EVENT_CANCELLED) == 1, person
    for person in bystanders:
        assert _got(db, person, NotificationType.EVENT_CANCELLED) == 0
