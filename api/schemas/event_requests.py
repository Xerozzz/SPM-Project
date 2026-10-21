"""Request/response contracts for event requests (SCRUM-46)."""

import uuid
from datetime import UTC, datetime
from typing import Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    computed_field,
    field_validator,
)

from domain.event_status import EventAction, EventStatus, allowed_actions
from models.event_coordinator_assignment import EventCoordinatorAssignment
from models.event_request import EventRequest


class EventRequestCreate(BaseModel):
    """The complete information collected when an organiser creates an event request (SCRUM-28).

    The separate submit endpoint is responsible for moving a created request to review.
    """

    name: str
    purpose: str
    description: str
    start_at: AwareDatetime
    end_at: AwareDatetime
    expected_attendance: int
    venue_requirement: str
    accessibility_requirement: str
    equipment_requirement: str
    layout_requirement: str
    registration_requirement: str

    @field_validator("start_at", "end_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class EventRequestUpdate(BaseModel):
    """Fields an organiser may change on a draft. All optional: a PATCH sends only what
    changed, and a draft is allowed to be incomplete until it is submitted."""

    # extra="forbid": a field name the API does not know (a typo such as "descripton") is
    # a 422, not a silent no-op that leaves the organiser thinking their edit was saved.
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    purpose: str | None = None
    description: str | None = None
    # AwareDatetime: a value without a UTC offset is rejected at the door (AGENTS.md §3),
    # so a naive datetime can never reach the database through this endpoint ...
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    expected_attendance: int | None = None
    venue_requirement: str | None = None
    accessibility_requirement: str | None = None
    equipment_requirement: str | None = None
    layout_requirement: str | None = None
    registration_requirement: str | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _to_utc(cls, value: datetime | None) -> datetime | None:
        """... and an aware one in another zone is converted, so the invariant is UTC at
        every layer rather than merely "has a timezone". The instant is unchanged."""
        return None if value is None else value.astimezone(UTC)


class EventRequestPlanningUpdate(BaseModel):
    """SCRUM-36: the ordinary planning fields the assigned coordinator may change.

    extra="forbid" is what keeps AC3: a body that includes start_at, end_at,
    expected_attendance, venue_requirement, equipment_requirement, layout_requirement or
    accessibility_requirement is a 422 and nothing is saved, so those fields cannot
    change through this flow (ADR-0046).
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    purpose: str | None = None
    description: str | None = None
    registration_requirement: str | None = None


class EventRequestDraftCreate(EventRequestUpdate):
    """Fields an organiser may provide when first saving a draft.

    Same optional contract as an update: SCRUM-29 allows a draft to be incomplete until
    the organiser chooses to submit it.
    """


class EventCalendarEntryRead(BaseModel):
    """SCRUM-87: read-only calendar details, with no implied edit permissions."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None
    start_at: AwareDatetime
    end_at: AwareDatetime
    status: EventStatus


class EventRequestRead(BaseModel):
    """An event request as the organiser sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: EventStatus
    name: str | None
    purpose: str | None
    description: str | None
    start_at: datetime | None
    end_at: datetime | None
    expected_attendance: int | None
    venue_requirement: str | None
    accessibility_requirement: str | None
    equipment_requirement: str | None
    layout_requirement: str | None
    registration_requirement: str | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    # SCRUM-34: who was auto-assigned on first submission, and when.
    coordinator_id: uuid.UUID | None
    assigned_at: datetime | None
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    rejection_reason: str | None

    @computed_field
    def status_permits(self) -> list[EventAction]:
        """What the status permits, sorted for a stable response (SCRUM-35)."""
        return sorted(allowed_actions(self.status))


class EventRequestRejection(BaseModel):
    """The reason required before a coordinator can reject a request."""

    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("is required")
        return value


class FieldProblemRead(BaseModel):
    """One field the organiser must fix before the request can be submitted (AC2)."""

    field: str
    reason: str


class UnassignedEventRequestRead(BaseModel):
    """SCRUM-101: one row of the Coordinator Lead unassigned queue.

    Only the fields the acceptance criteria require: event ID, name, organiser email,
    start/end, expected attendance, and submission time. No unrelated private fields.
    """

    id: uuid.UUID
    name: str | None
    organiser_email: str
    start_at: datetime | None
    end_at: datetime | None
    expected_attendance: int | None
    submitted_at: datetime | None

    @classmethod
    def from_row(cls, request: EventRequest, organiser_email: str) -> Self:
        """Build a queue row from the request and its organiser's email."""
        return cls(
            id=request.id,
            name=request.name,
            organiser_email=organiser_email,
            start_at=request.start_at,
            end_at=request.end_at,
            expected_attendance=request.expected_attendance,
            submitted_at=request.submitted_at,
        )


class EventRequestAssign(BaseModel):
    """SCRUM-98: the Lead's chosen owner for an unassigned Submitted request."""

    coordinator_id: uuid.UUID


class EventRequestReassign(BaseModel):
    """SCRUM-97: the Lead's replacement owner plus the owner the Lead saw.

    `expected_current_coordinator_id` is optimistic concurrency: the service refuses
    with 409 when the locked row no longer has this owner, so a stale screen cannot
    silently overwrite a concurrent reassignment.
    """

    coordinator_id: uuid.UUID
    expected_current_coordinator_id: uuid.UUID


class AssignmentHistoryRead(BaseModel):
    """SCRUM-97: one immutable assignment entry, oldest first.

    `previous_coordinator_id` is None only for the first assignment after this story's
    migration landed; requests assigned earlier have no history rows at all (ADR-0021).

    SCRUM-105 (ADR-0047) adds each person's email beside their id. An email is None
    when its user row is missing; the UI shows "Unknown user" for it. A None
    `previous_coordinator_email` with a None id is the first assignment, not a missing user.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    previous_coordinator_id: uuid.UUID | None
    previous_coordinator_email: str | None
    new_coordinator_id: uuid.UUID
    new_coordinator_email: str | None
    acted_by_id: uuid.UUID
    acted_by_email: str | None
    assigned_at: datetime

    @classmethod
    def from_row(
        cls,
        entry: EventCoordinatorAssignment,
        previous_coordinator_email: str | None,
        new_coordinator_email: str | None,
        acted_by_email: str | None,
    ) -> Self:
        """Build one entry from the history row and the three emails joined to it."""
        return cls(
            id=entry.id,
            previous_coordinator_id=entry.previous_coordinator_id,
            previous_coordinator_email=previous_coordinator_email,
            new_coordinator_id=entry.new_coordinator_id,
            new_coordinator_email=new_coordinator_email,
            acted_by_id=entry.acted_by_id,
            acted_by_email=acted_by_email,
            assigned_at=entry.assigned_at,
        )


class AssignableCoordinatorRead(BaseModel):
    """SCRUM-98: one eligible owner the Lead may pick — active Event Coordinators only."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str


class ActiveAssignmentRead(BaseModel):
    """SCRUM-100: one row of the Lead active-assignment overview.

    Current ownership only: `coordinator_email` is the present owner's email or None
    (rendered as Unassigned). Historical owners never appear here. SCRUM-97 adds
    `coordinator_id` — the current owner's id (None when unassigned) — so the Lead UI
    can send it back as `expected_current_coordinator_id` for optimistic concurrency
    (ADR-0021). It is the same owner the email names, not a second source of truth.
    """

    id: uuid.UUID
    name: str | None
    status: EventStatus
    organiser_email: str
    start_at: datetime | None
    end_at: datetime | None
    coordinator_id: uuid.UUID | None
    coordinator_email: str | None

    @classmethod
    def from_row(
        cls, request: EventRequest, organiser_email: str, coordinator_email: str | None
    ) -> Self:
        """Build an overview row from the request and its owners' emails."""
        return cls(
            id=request.id,
            name=request.name,
            status=request.status,
            organiser_email=organiser_email,
            start_at=request.start_at,
            end_at=request.end_at,
            coordinator_id=request.coordinator_id,
            coordinator_email=coordinator_email,
        )
