"""Submit pending venue booking requests for approved events (SCRUM-38), check
whether one can be approved without a conflict (SCRUM-73), and approve it safely under
concurrency (SCRUM-74, which also absorbs SCRUM-40's approve action — see ADR-0017).
The assigned Coordinator cancels one arrangement of an event (SCRUM-109, ADR-0056)."""

import uuid
from datetime import datetime

from core.database import Session
from domain import (
    venue_booking,
    venue_cancellation,
    venue_hold,
    venue_replacement,
    venue_session,
    venue_suitability,
)
from domain.booking_conflict import BookedPeriod, UnavailablePeriod, ensure_no_conflict
from domain.event_request import (
    EQUIPMENT_REQUIREMENT_FACILITIES,
    EventRequestFields,
    field_names,
    validate_event_request,
)
from domain.notifications import NotificationSource, NotificationType
from domain.validation import FieldProblem
from domain.venue_booking import BookingStatus
from domain.venue_buffer import VenueBuffers, effective_interval
from models.event_request import EventRequest
from models.venue import Venue
from models.venue_booking import VenueBooking
from repositories import equipment_requirements as requirement_repo
from repositories import event_requests as event_repo
from repositories import notifications as notifications_repo
from repositories import users as users_repo
from repositories import venue_availability as booking_repo
from repositories import venues as venue_repo
from services import venue_buffer_review as buffer_review
from services import venue_hold_expiry


class InvalidBookingRequestError(Exception):
    def __init__(self, problems: list[FieldProblem]) -> None:
        self.problems = problems


class BookingNotFoundError(Exception):
    """No venue booking has that id."""


class InvalidHoldError(Exception):
    """SCRUM-83: the hold's expiry is not acceptable, field by field."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("invalid tentative hold")
        self.problems = problems


class InvalidCancellationError(Exception):
    """SCRUM-109 AC4: the cancellation's input is not acceptable, field by field."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("invalid venue arrangement cancellation")
        self.problems = problems


class EventNotInPlanningError(Exception):
    """SCRUM-109 AC7, AC9: the event's status does not allow cancelling an arrangement."""

    def __init__(self, refusal: venue_cancellation.EventRefusal) -> None:
        super().__init__(f"cannot cancel a venue arrangement: {refusal}")
        self.refusal = refusal


def evaluate(
    db: Session, event: EventRequest, venue_id: uuid.UUID, now: datetime
) -> venue_suitability.SuitabilityResult:
    venue = _validated_venue(db, event, venue_id, now)
    assert event.expected_attendance is not None
    required_facilities = _facilities_needed(db, event)
    # `venue_requirement` is retained as event context, but Venue has no comparable
    # venue-type field yet. SCRUM-38 therefore cannot include it in suitability scoring.
    return venue_suitability.evaluate_suitability(
        venue_suitability.SuitabilityEvent(
            expected_attendance=event.expected_attendance,
            required_facilities=required_facilities,
            accessibility_need=event.accessibility_requirement,
            layout_need=event.layout_requirement,
        ),
        venue_suitability.SuitabilityVenue(
            maximum_capacity=venue.maximum_capacity,
            facilities=venue.facilities,
            accessibility_features=venue.accessibility_features,
            supported_layouts=venue.supported_layouts,
        ),
    )


def _facilities_needed(db: Session, event: EventRequest) -> list[str]:
    """SCRUM-43: what the event's maintained requirements ask the venue to provide.

    Read from `event_equipment_requirements`, not from the organiser's
    `equipment_requirement` string. That column is the original submission and the
    Coordinator does not write back to it (ADR-0033), so once they add, change or remove
    anything the two disagree, and suitability was scoring the stale one. It also only
    ever named a single type, so an event needing three things was judged on one of them.

    `EQUIPMENT_REQUIREMENT_FACILITIES` still bridges the two vocabularies. Equipment types
    and venue facilities are separate lists (ADR-0031, ADR-0032): a venue offers a fixed
    projector, it does not offer the portable things that arrive from the store room. A
    requirement with no counterpart is therefore not a missing facility and is left
    unscored, exactly as it is today, rather than reported as something the venue lacks.
    """
    return [
        EQUIPMENT_REQUIREMENT_FACILITIES[requirement.equipment_type]
        for requirement in requirement_repo.list_for_event(db, event.id)
        if requirement.equipment_type in EQUIPMENT_REQUIREMENT_FACILITIES
    ]


def submit(
    db: Session,
    event: EventRequest,
    venue_id: uuid.UUID,
    now: datetime,
    session_label: str,
    start_at: datetime,
    end_at: datetime,
    replaces_booking_id: uuid.UUID | None = None,
) -> tuple[VenueBooking, venue_suitability.SuitabilityResult]:
    """SCRUM-78/SCRUM-111: a new Pending request for one session of the event.

    SCRUM-116: with `replaces_booking_id` it is a replacement for an affected arrangement
    of the same event and session. The event row lock taken here also serialises two
    replacements for the same arrangement, so only one can be in progress (AC6).
    """
    locked = event_repo.get_for_update(db, event.id)
    assert locked is not None and locked.coordinator_id is not None
    assert locked.start_at is not None and locked.end_at is not None
    # Suitability first: it owns the event-level requirement checks, so an invalid
    # event still reports those rather than a session error about its own times.
    suitability = evaluate(db, locked, venue_id, now)
    # SCRUM-111: the request names one session and its own period, which must sit
    # inside the parent event period. Suitability still scores the event's recorded
    # requirements (AC4); there is no per-session attendance.
    problems = venue_session.session_problems(
        session_label, start_at, end_at, locked.start_at, locked.end_at
    )
    if problems:
        raise InvalidBookingRequestError(problems)
    if replaces_booking_id is not None:
        _ensure_replaceable(db, locked, replaces_booking_id, session_label, start_at, end_at, now)
    venue = venue_repo.get(db, venue_id)
    assert venue is not None  # evaluate() has already refused an unknown venue.
    effective_start, effective_end = effective_interval(start_at, end_at, _buffers(venue))
    booking = VenueBooking(
        event_request_id=locked.id,
        venue_id=venue_id,
        requested_by_id=locked.coordinator_id,
        session_label=session_label.strip(),
        start_at=start_at,
        end_at=end_at,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=BookingStatus.PENDING,
        replaces_booking_id=replaces_booking_id,
    )
    # SCRUM-49: notify every active Venue Staff member of the new Pending request.
    # Staged before the commit so the booking and its notifications land or roll back
    # together; the occurrence time is the submission time, not a second clock read;
    # the (venue_request, booking id) source pair makes a retry collide instead of
    # duplicating (ADR-0022). Revised requests (replaces_booking_id set) are owned by
    # SCRUM-127 and stay silent here. With no active Venue Staff the loop stages
    # nothing and the booking still commits (AC4).
    if replaces_booking_id is None:
        db.add(booking)
        db.flush()
        for staff in users_repo.list_active_venue_staff(db):
            notifications_repo.stage(
                db,
                recipient_id=staff.id,
                event_request_id=locked.id,
                type=NotificationType.VENUE_REQUEST_SUBMITTED,
                source_type=NotificationSource.VENUE_REQUEST,
                source_id=str(booking.id),
                occurred_at=now,
            )
        db.commit()
        db.refresh(booking)
        return booking, suitability
    # SCRUM-127 AC1/AC2: a revised (replacement) Pending request needing review alerts
    # responsible active Venue Staff — active review-role staff, since no venue→staff
    # mapping exists. Staged before the commit so the revision and its alerts land or
    # roll back together (ADR-0060); the (venue_revision, replacement id) source pair
    # makes a retry collide while a later distinct revision stays distinct (ADR-0022).
    # A Pending revision alone creates no occupancy (ADR-0002 covers Tentative+ only).
    db.add(booking)
    db.flush()
    for staff in users_repo.list_active_venue_staff(db):
        notifications_repo.stage(
            db,
            recipient_id=staff.id,
            event_request_id=locked.id,
            type=NotificationType.VENUE_REVISION_SUBMITTED,
            source_type=NotificationSource.VENUE_REVISION,
            source_id=str(booking.id),
            occurred_at=now,
        )
    db.commit()
    db.refresh(booking)
    return booking_repo.save_booking(db, booking), suitability


def _ensure_replaceable(
    db: Session,
    event: EventRequest,
    original_id: uuid.UUID,
    session_label: str,
    start_at: datetime,
    end_at: datetime,
    now: datetime,
) -> None:
    """SCRUM-116 AC1, AC2, AC6: the request may replace this arrangement.

    "Needs attention" is the same derived answer the Coordinator's list shows (SCRUM-89,
    SCRUM-81), so the button and this check can never disagree.
    """
    row = booking_repo.get_booking(db, original_id)
    original = None
    if row is not None:
        original = venue_replacement.Original(
            event_request_id=row.event_request_id,
            status=row.status,
            session_label=row.session_label,
            start_at=row.start_at,
            end_at=row.end_at,
            needs_attention=row.id in buffer_review.problems_by_booking(db, [row], now),
            has_live_replacement=booking_repo.has_live_replacement(db, row.id),
        )
    problems = venue_replacement.replacement_problems(
        original, event.id, session_label, start_at, end_at
    )
    if problems:
        raise InvalidBookingRequestError(problems)


def list_for_event(db: Session, event: EventRequest) -> list[VenueBooking]:
    """SCRUM-71: read retained booking requests for an approved assigned event."""
    return booking_repo.list_bookings_for_event(db, event.id)


def check_approvable(db: Session, booking_id: uuid.UUID) -> VenueBooking:
    """SCRUM-73: raise a `domain.booking_conflict.BookingConflictError` naming whatever
    blocks approving this booking, or return it if nothing does.

    A read-only preview: it neither locks nor changes status. `approve` runs the same
    check on a locked row, and the exclusion constraint backs it up (ADR-0002, ADR-0017).
    """
    booking = booking_repo.get_booking(db, booking_id)
    if booking is None:
        raise BookingNotFoundError
    _ensure_no_conflict(db, booking)
    return booking


def approve(
    db: Session,
    booking_id: uuid.UUID,
    decided_by_id: uuid.UUID,
    decided_at: datetime,
    expires_at: datetime,
) -> VenueBooking:
    """SCRUM-110 (superseding SCRUM-74's direct confirmation and SCRUM-107's
    hold confirmation): approving a pending request places the SCRUM-83 tentative hold
    until `expires_at`, never a confirmation. Approval IS the hold, so this delegates
    to `hold()`: the same row lock, expiry validation, SCRUM-73 check, effective
    interval refresh and exclusion-constraint commit. Neither a Pending nor a Tentative
    row can become Confirmed through Venue Staff approval (AC4); SCRUM-80 owns the
    later event-confirmation step. SCRUM-75 AC2: the approving staff and UTC action
    time are stored as the hold's `held_by_id`/`held_at` in the same commit."""
    return hold(db, booking_id, decided_by_id, expires_at, decided_at)


def hold(
    db: Session,
    booking_id: uuid.UUID,
    held_by_id: uuid.UUID,
    expires_at: datetime,
    now: datetime,
) -> VenueBooking:
    """SCRUM-83 AC1: Venue Staff put a pending request on a tentative hold until
    `expires_at`. The request already names the venue, the event and its period, and was
    made by the event's assigned Coordinator, so the hold is for all of them (ADR-0029).

    The steps are approve's, because a hold occupies the venue the same way (AC3):
    lock the row and check the transition, check the expiry, run the SCRUM-73 check for a
    named refusal, refresh the effective interval from the venue's current buffers, and
    commit under the exclusion constraint, which covers tentative holds since 0021.
    """
    # SCRUM-108: holds that ran out stop blocking before anything is checked.
    venue_hold_expiry.expire_due_holds(db, now)
    booking = booking_repo.get_booking_for_update(db, booking_id)
    if booking is None:
        raise BookingNotFoundError
    # SCRUM-122: read the event before mutating the booking. A later read would
    # autoflush the pending UPDATE and fire the exclusion constraint outside the
    # save below that translates it into a domain conflict.
    event = event_repo.get(db, booking.event_request_id)
    assert event is not None
    held = venue_booking.hold(booking.status)
    problems = venue_hold.expiry_problems(expires_at, now, booking.start_at)
    if problems:
        raise InvalidHoldError(problems)
    _ensure_no_conflict(db, booking)
    venue = venue_repo.get(db, booking.venue_id)
    assert venue is not None
    booking.effective_start_at, booking.effective_end_at = effective_interval(
        booking.start_at, booking.end_at, _buffers(venue)
    )
    booking.status = held
    booking.expires_at = expires_at
    booking.held_by_id = held_by_id
    booking.held_at = now
    # SCRUM-122 AC1/AC2: the current Coordinator hears of the approval. Staged before
    # the commit so the hold and its notification land or roll back together; the
    # occurrence time is the approval time, not a second clock read. The source_id
    # carries the approval time because a booking id alone cannot tell a retry of one
    # approval from a later distinct decision on the same row. With no Coordinator
    # assigned the helper stages nothing and the hold still commits.
    _stage_venue_decision(
        db,
        event,
        NotificationType.VENUE_BOOKING_APPROVED,
        f"{booking.id}:{now.isoformat()}",
        now,
    )
    return booking_repo.save_confirmed_booking(db, booking)


def update_hold_expiry(
    db: Session, booking_id: uuid.UUID, expires_at: datetime, now: datetime
) -> VenueBooking:
    """SCRUM-121: replace the current expiry of one active Tentative hold.

    The row lock serialises this edit with another edit or the SCRUM-108 worker. Both
    the old and new expiry are checked against the same supplied UTC action time. The
    occupied interval and status do not change, so the existing exclusion constraint
    continues to protect buffered overlaps without another conflict check.
    """
    booking = booking_repo.get_booking_for_update(db, booking_id)
    if booking is None:
        raise BookingNotFoundError
    venue_hold.ensure_active(booking.status, booking.expires_at, now)
    problems = venue_hold.expiry_problems(expires_at, now, booking.start_at)
    if problems:
        raise InvalidHoldError(problems)
    # SCRUM-122: read the event before mutating, as in hold(), so no later read
    # autoflushes the pending UPDATE outside the save below.
    event = event_repo.get(db, booking.event_request_id)
    assert event is not None
    booking.expires_at = expires_at
    # SCRUM-122 AC1/AC2: the current Coordinator hears of each expiry edit. Staged
    # before the commit so the edit and its notification land or roll back together.
    # The source_id carries the new expiry, so a later edit is a distinct item while
    # a retried HTTP call collides per recipient (idempotent).
    _stage_venue_decision(
        db,
        event,
        NotificationType.VENUE_HOLD_EXPIRY_UPDATED,
        f"{booking.id}:{expires_at.isoformat()}",
        now,
    )
    try:
        return booking_repo.save_booking(db, booking)
    except Exception:
        db.rollback()
        raise


def stage_cancellation(
    db: Session,
    event_id: uuid.UUID,
    booking_id: uuid.UUID,
    cancelled_by_id: uuid.UUID,
    reason: str | None,
    now: datetime,
    *,
    venue_change: bool = False,
) -> VenueBooking:
    """SCRUM-109: cancel one arrangement of an event, in the caller's transaction.

    Flushes and does **not** commit, so SCRUM-115 (cancel a whole event) and SCRUM-116
    (replace a venue) can cancel several arrangements and commit once; a refusal leaves
    nothing written, and rolling the caller's transaction back undoes a cancellation.
    The caller has already checked who is acting (CANCEL_VENUE_ARRANGEMENT).

    The event row is locked first and then the booking row, the order `submit` already
    uses, so a cancellation never waits on a lock in the opposite order (ADR-0056). Under
    the booking lock the row is re-read as committed, so a hold the expiry timer has just
    expired, or a request Venue Staff have just decided, is judged as it now is (AC10).
    Nothing else of the event is touched: not its status (AC8), not its other bookings
    (AC1). The decision and hold columns stay as they were (AC2).

    SCRUM-118: `venue_change` is set only by `services.venue_changes`, which has the
    Coordinator's confirmation; it allows a Confirmed event instead of a planning one.
    """
    event = event_repo.get_for_update(db, event_id)
    if event is None:
        raise BookingNotFoundError
    refusal = venue_cancellation.event_refusal(event.status, venue_change)
    if refusal is not None:
        raise EventNotInPlanningError(refusal)
    booking = booking_repo.get_booking_for_update(db, booking_id)
    # An arrangement of another event is not found here, rather than refused, so the id
    # of someone else's booking discloses nothing.
    if booking is None or booking.event_request_id != event.id:
        raise BookingNotFoundError
    stage_booking_cancellation(booking, cancelled_by_id, reason, now)
    db.flush()
    return booking


def stage_booking_cancellation(
    booking: VenueBooking, cancelled_by_id: uuid.UUID, reason: str | None, now: datetime
) -> None:
    """Cancel one booking the caller has already locked, with who, when and why.

    The one place a booking becomes Cancelled. `stage_cancellation` calls it after its
    planning-only event check, and SCRUM-115 calls it for each live booking when a whole
    event is cancelled, including a Confirmed event, under its own event lock.
    """
    cancelled = venue_cancellation.cancel(booking.status, booking.expires_at, now)
    problems = venue_cancellation.reason_problems(reason)
    if problems:
        raise InvalidCancellationError(problems)
    assert reason is not None  # reason_problems refuses None
    booking.status = cancelled
    booking.cancelled_by_id = cancelled_by_id
    booking.cancelled_at = now
    booking.cancellation_reason = reason.strip()


def cancel_arrangement(
    db: Session,
    event_id: uuid.UUID,
    booking_id: uuid.UUID,
    cancelled_by_id: uuid.UUID,
    reason: str | None,
    now: datetime,
) -> VenueBooking:
    """SCRUM-109 AC1: the Coordinator's single cancellation, staged and committed.

    SCRUM-123: every active Venue Staff member is alerted in the same transaction,
    so the cancellation and its notifications land or roll back together (ADR-0060).
    The (venue_cancellation, booking id) source pair makes a retry collide instead
    of duplicating (ADR-0022). With no active Venue Staff the loop stages nothing
    and the cancellation still commits (AC1). Replacements (SCRUM-116), venue
    changes (SCRUM-118) and whole-event cancellations (SCRUM-115) cancel through
    their own paths and stay silent here.
    """
    booking = stage_cancellation(db, event_id, booking_id, cancelled_by_id, reason, now)
    for staff in users_repo.list_active_venue_staff(db):
        notifications_repo.stage(
            db,
            recipient_id=staff.id,
            event_request_id=booking.event_request_id,
            type=NotificationType.VENUE_ARRANGEMENT_CANCELLED,
            source_type=NotificationSource.VENUE_CANCELLATION,
            source_id=str(booking.id),
            occurred_at=now,
        )
    return booking_repo.save_booking(db, booking)


def _buffers(venue: Venue) -> VenueBuffers:
    """SCRUM-82: the venue's current setup and turnaround, as the domain takes them."""
    return VenueBuffers(
        setup_minutes=venue.setup_minutes, turnaround_minutes=venue.turnaround_minutes
    )


def _stage_venue_decision(
    db: Session,
    event: EventRequest,
    type: NotificationType,
    source_id: str,
    now: datetime,
) -> None:
    """SCRUM-122 AC1/AC2: notify the current Coordinator of a venue decision.

    The recipient is resolved at action time, so a reassigned event notifies the new
    Coordinator and the former one gets nothing. No commit here: the caller's save
    commits the decision and this row together, so a rolled-back action notifies
    nobody. With no Coordinator assigned nothing is staged and the action commits.

    The insert runs without autoflush: flushing here would fire the booking's pending
    UPDATE early, raising the exclusion violation outside the save below that
    translates it into a domain conflict.
    """
    if event.coordinator_id is None:
        return
    with db.no_autoflush:
        notifications_repo.stage(
            db,
            recipient_id=event.coordinator_id,
            event_request_id=event.id,
            type=type,
            source_type=NotificationSource.VENUE_DECISION,
            source_id=source_id,
            occurred_at=now,
        )


def _ensure_no_conflict(db: Session, booking: VenueBooking) -> None:
    """SCRUM-82 AC4: the check compares effective occupied intervals.

    Buffers are read from the venue now rather than from the booking's stored effective
    columns, so a buffer change takes effect on the next check without touching any
    booking row. The stored columns exist only for the overlap constraint; ADR-0019 says
    why the two can differ and which story closes the gap.
    """
    venue = venue_repo.get(db, booking.venue_id)
    assert venue is not None  # a booking cannot exist without its venue (foreign key).
    others = [
        BookedPeriod(id=row.id, status=row.status, start_at=row.start_at, end_at=row.end_at)
        for row in booking_repo.other_bookings_overlapping(db, booking)
    ]
    closures = [
        UnavailablePeriod(id=row.id, starts_at=row.starts_at, ends_at=row.ends_at)
        for row in booking_repo.unavailabilities_overlapping(db, booking)
    ]
    ensure_no_conflict(booking.start_at, booking.end_at, others, closures, _buffers(venue))


def _validated_venue(db: Session, event: EventRequest, venue_id: uuid.UUID, now: datetime) -> Venue:
    fields = EventRequestFields(**{name: getattr(event, name) for name in field_names()})
    problems = validate_event_request(fields, now)
    venue = venue_repo.get(db, venue_id)
    if venue is None:
        problems.append(FieldProblem("venue_id", "does not identify a venue"))
    elif not venue.is_active:
        problems.append(FieldProblem("venue_id", "must identify an active venue"))
    if problems:
        raise InvalidBookingRequestError(problems)
    assert venue is not None
    return venue
