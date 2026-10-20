"""Request/response contracts for significant-change requests (SCRUM-37)."""

import uuid
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator

from domain.change_decision import Decision
from domain.event_change import (
    Catalogue,
    CurrentPlan,
    EquipmentProposal,
    Proposal,
    SessionProposal,
)


def _utc(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(UTC)


class EventFieldChanges(BaseModel):
    """AC2: the event's own fields a change may touch. Send only the ones being changed.

    extra="forbid", so an ordinary field such as `name` is a 422: those belong to the
    Coordinator's ordinary update (SCRUM-36), not to this flow.
    """

    model_config = ConfigDict(extra="forbid")

    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    expected_attendance: int | None = None
    venue_requirement: str | None = None
    accessibility_requirement: str | None = None
    layout_requirement: str | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _to_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value)


class SessionChange(BaseModel):
    """New values for one existing venue request (session) of the event."""

    model_config = ConfigDict(extra="forbid")

    booking_id: uuid.UUID
    session_label: str | None = None
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _to_utc(cls, value: datetime | None) -> datetime | None:
        return _utc(value)


class EquipmentChange(BaseModel):
    """Add a line (no `requirement_id`), change one, or remove one (`remove: true`)."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: uuid.UUID | None = None
    equipment_type: str | None = None
    quantity: int | None = None
    technical_requirements: str | None = None
    remove: bool = False


class EventChangeRequestCreate(BaseModel):
    """One submit action. `submission_key` is new per action and reused on a retry (AC8)."""

    model_config = ConfigDict(extra="forbid")

    submission_key: uuid.UUID
    reason: str
    event: EventFieldChanges = EventFieldChanges()
    sessions: list[SessionChange] = []
    equipment: list[EquipmentChange] = []

    def to_proposal(self) -> Proposal:
        """Only the event fields actually sent count as proposed."""
        sent = self.event.model_fields_set
        return Proposal(
            reason=self.reason,
            event={name: getattr(self.event, name) for name in sent},
            sessions=tuple(SessionProposal(**s.model_dump()) for s in self.sessions),
            equipment=tuple(EquipmentProposal(**e.model_dump()) for e in self.equipment),
        )


class EventChangeItemRead(BaseModel):
    """One changed value next to the value it would replace (AC3)."""

    model_config = ConfigDict(from_attributes=True)

    target: str
    target_id: uuid.UUID | None
    field: str
    current_value: object | None
    proposed_value: object | None
    # SCRUM-47: applied or needs_replanning once approved, null before.
    outcome: str | None


class EventChangeRequestRead(BaseModel):
    """A change request as the Organiser and the assigned Coordinator see it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_request_id: uuid.UUID
    requested_by_id: uuid.UUID
    reason: str
    status: str
    event_updated_at: datetime
    created_at: datetime
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    items: list[EventChangeItemRead]


class ChangeDecisionCreate(BaseModel):
    """SCRUM-47 AC1: approve or reject, always with a note."""

    model_config = ConfigDict(extra="forbid")

    decision: Decision
    note: str


class PlannedSessionRead(BaseModel):
    """One live session the Organiser may propose to move or rename."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_label: str
    start_at: datetime
    end_at: datetime


class RequirementRead(BaseModel):
    """One live equipment line the Organiser may propose to change or remove."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    equipment_type: str
    quantity: int
    technical_requirements: str | None


class ChangePlanRead(BaseModel):
    """What a proposal starts from (AC2) and the catalogue choices it may use (AC4)."""

    event: dict[str, object]
    sessions: list[PlannedSessionRead]
    equipment: list[RequirementRead]
    venue_options: list[str]
    equipment_types: list[str]

    @classmethod
    def build(cls, plan: CurrentPlan, catalogue: Catalogue) -> "ChangePlanRead":
        return cls(
            event=dict(plan.event),
            sessions=[PlannedSessionRead.model_validate(s) for s in plan.sessions],
            equipment=[RequirementRead.model_validate(r) for r in plan.equipment],
            venue_options=list(catalogue.venue_names),
            equipment_types=sorted(catalogue.equipment_types),
        )
