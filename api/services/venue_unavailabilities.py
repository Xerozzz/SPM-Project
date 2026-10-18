"""Venue-unavailability orchestration for SCRUM-62."""

import uuid
from datetime import datetime

from core.database import Session
from domain.validation import FieldProblem
from domain.venue_buffer import VenueBuffers, booking_clashes_with_closure
from domain.venue_unavailability import VenueUnavailabilityFields, validate_unavailability
from models.venue import Venue
from models.venue_unavailability import VenueUnavailability
from repositories import venue_availability as booking_repo
from repositories import venue_unavailabilities as repo
from services import venues


class VenueUnavailabilityError(Exception):
    """Base class for closures the service cannot perform."""


class VenueUnavailabilityNotFoundError(VenueUnavailabilityError):
    """The named closure does not exist at this venue."""


class InactiveVenueError(VenueUnavailabilityError):
    """New closure records only make sense for selectable venues."""


class ConfirmedBookingInTheWayError(VenueUnavailabilityError):
    """The venue is already committed to an event for part of this period.

    Recording a closure over a confirmed booking would leave the venue both promised and
    shut, which nothing downstream can resolve: SCRUM-73 refuses an approval that clashes
    with a closure, but this booking is already approved.
    """

    def __init__(self, booking_id: uuid.UUID) -> None:
        # Written for the Venue Staff member who is being refused, because this string is
        # what the screen shows them. The id trails it so a conflict can still be traced.
        super().__init__(
            "This venue is already committed to a confirmed booking for part of that "
            f"period, so it cannot be closed. Booking {booking_id}."
        )
        self.booking_id = booking_id


class InvalidVenueUnavailabilityError(VenueUnavailabilityError):
    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("the unavailability period is not valid")
        self.problems = problems


def list_for_venue(db: Session, venue_id: uuid.UUID) -> list[VenueUnavailability]:
    venues.get(db, venue_id)
    return repo.list_for_venue(db, venue_id)


def create(
    db: Session, venue_id: uuid.UUID, fields: VenueUnavailabilityFields, now: datetime
) -> VenueUnavailability:
    venue = venues.get(db, venue_id)
    if not venue.is_active:
        raise InactiveVenueError
    _ensure_valid(fields, now)
    _ensure_no_confirmed_booking(db, venue, fields)
    return repo.save(db, VenueUnavailability(venue_id=venue_id, **_stored_values(fields)))


def update(
    db: Session,
    venue_id: uuid.UUID,
    unavailability_id: uuid.UUID,
    fields: VenueUnavailabilityFields,
    now: datetime,
) -> VenueUnavailability:
    record = _get_for_venue(db, venue_id, unavailability_id)
    _ensure_valid(fields, now)
    # Moving a closure asks the same question as recording one, against the period it
    # would occupy afterwards. Without this, `update` is a way round `create`'s check:
    # record a closure somewhere clear, then edit it on top of a confirmed booking.
    _ensure_no_confirmed_booking(db, venues.get(db, venue_id), fields)
    for name, value in _stored_values(fields).items():
        setattr(record, name, value)
    return repo.save(db, record)


def delete(db: Session, venue_id: uuid.UUID, unavailability_id: uuid.UUID) -> None:
    repo.delete(db, _get_for_venue(db, venue_id, unavailability_id))


def _get_for_venue(
    db: Session, venue_id: uuid.UUID, unavailability_id: uuid.UUID
) -> VenueUnavailability:
    record = repo.get(db, unavailability_id)
    if record is None or record.venue_id != venue_id:
        raise VenueUnavailabilityNotFoundError
    return record


def _ensure_valid(fields: VenueUnavailabilityFields, now: datetime) -> None:
    problems = validate_unavailability(fields, now)
    if problems:
        raise InvalidVenueUnavailabilityError(problems)


def _stored_values(fields: VenueUnavailabilityFields) -> dict[str, object]:
    assert fields.starts_at is not None
    assert fields.ends_at is not None
    assert fields.reason is not None
    return {
        "starts_at": fields.starts_at,
        "ends_at": fields.ends_at,
        "reason": fields.reason.strip(),
    }


def _ensure_no_confirmed_booking(
    db: Session, venue: Venue, fields: VenueUnavailabilityFields
) -> None:
    """Refuse a closure that would sit on top of a booking the venue is committed to.

    The same comparison booking approval runs, from the other side: the booking is
    widened by the venue's setup and turnaround and the closure is not (SCRUM-82 AC5), so
    a closure that eats into a confirmed event's preparation time is a clash even when it
    misses the event itself.

    Only confirmed bookings are in the way. A pending request is not a commitment, and
    refusing a closure because of one would let an unapproved request block maintenance.
    """
    assert fields.starts_at is not None and fields.ends_at is not None
    buffers = VenueBuffers(
        setup_minutes=venue.setup_minutes, turnaround_minutes=venue.turnaround_minutes
    )
    for booking in booking_repo.confirmed_bookings_from(db, venue.id, fields.starts_at):
        if booking_clashes_with_closure(
            booking.start_at, booking.end_at, fields.starts_at, fields.ends_at, buffers
        ):
            raise ConfirmedBookingInTheWayError(booking.id)
