"""API contracts for the venue catalogue (SCRUM-59, SCRUM-82, SCRUM-89).

Mirrors domain/venue.py.
"""

import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict

from domain.venue_booking import BookingStatus
from schemas.venue_booking_decisions import ConflictRead


class VenueCreate(BaseModel):
    """Everything Venue Staff supply when adding a venue.

    Required here only in the sense of "present in the payload"; whether each value is
    acceptable is domain/venue.py's decision, so one missing field and one invalid field
    are reported the same way (AC5) instead of one as a 422 body and the other as a
    Pydantic error in a different shape.
    """

    name: str | None = None
    location: str | None = None
    maximum_capacity: int | None = None
    facilities: list[str] | None = None
    supported_layouts: list[str] | None = None
    accessibility_features: list[str] | None = None
    opens_at: time | None = None
    closes_at: time | None = None
    # SCRUM-82 AC1: `int` is what refuses a non-numeric buffer, with the field named in
    # the Pydantic error. Whether the number is acceptable is domain/venue.py's decision,
    # as for maximum_capacity. Absent means no buffer, so an existing payload still saves.
    setup_minutes: int | None = None
    turnaround_minutes: int | None = None


class VenueUpdate(VenueCreate):
    """Fields Venue Staff may change. All optional: a PATCH sends only what changed, and
    the service validates the record as it would be afterwards."""


class VenueRead(BaseModel):
    """A venue as the catalogue shows it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    location: str
    maximum_capacity: int
    facilities: list[str]
    supported_layouts: list[str]
    accessibility_features: list[str]
    opens_at: time
    closes_at: time
    # SCRUM-82 AC2: readable by anyone who may read the catalogue, so an Event Coordinator
    # can see the buffers. Only Venue Staff reach the POST and PATCH routes that set them.
    setup_minutes: int
    turnaround_minutes: int
    is_active: bool


class VenueProblemRead(BaseModel):
    """One field Venue Staff must fix before the record can be saved (AC5)."""

    field: str
    reason: str


class ProblemBookingRead(BaseModel):
    """SCRUM-89 AC3: one booking that cannot stand under the venue's current buffers.

    `conflict` is the shared shape from SCRUM-75, not a second one, so Venue Staff read a
    clash the same way wherever they meet it.
    """

    booking_id: uuid.UUID
    # Who to talk to. The panel tells Venue Staff the Coordinator decides what moves, so
    # without the event it names nobody and cannot be acted on. Same fields the decisions
    # panel already carries for its sibling screen (schemas/venue_booking_decisions.py).
    event_request_id: uuid.UUID
    event_name: str | None
    start_at: datetime
    end_at: datetime
    # SCRUM-89: a tentative hold is reviewed alongside a confirmed booking, so the panel
    # has to say which it is looking at. The two need different answers from the
    # Coordinator: a hold can be left to expire, a confirmed booking cannot.
    status: BookingStatus
    conflict: ConflictRead


class BufferChangeRead(BaseModel):
    """SCRUM-89 AC6: what saving a venue did to its bookings.

    `changed` is false when the save did not touch the buffers at all, which is different
    from a buffer change that affected nothing: the second has `changed` true and an empty
    `problems`, and that is the case AC6 asks Venue Staff to be told about explicitly.
    """

    changed: bool
    problems: list[ProblemBookingRead]


class VenueUpdateRead(VenueRead):
    """What a PATCH returns: the venue, plus what the save did to its bookings.

    A superset of VenueRead rather than a wrapper around it, so a reader that only wants
    the venue keeps working unchanged.
    """

    buffer_change: BufferChangeRead


class VenueProblemsRead(BaseModel):
    """SCRUM-89 AC4: one venue and the bookings there that need attention."""

    venue_id: uuid.UUID
    venue_name: str
    venue_location: str
    setup_minutes: int
    turnaround_minutes: int
    is_active: bool
    problems: list[ProblemBookingRead]
