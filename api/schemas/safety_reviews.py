"""API contracts for operational safety review (SCRUM-79)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from domain.equipment_requirement import RequirementReview
from domain.equipment_reservation import ReservationState
from domain.safety_review import PlanSnapshot, SafetyDecision, blockers, fingerprint
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.safety_review import SafetyReview


class PlannedVenueRead(BaseModel):
    """One venue arrangement as the Officer sees it (AC3)."""

    booking_id: uuid.UUID
    venue_id: uuid.UUID
    session_label: str
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    hold_expired: bool


class PlannedEquipmentRead(BaseModel):
    """One equipment requirement as the Officer sees it (AC3)."""

    requirement_id: uuid.UUID
    equipment_type: str
    quantity: int
    review_status: RequirementReview
    reservation_state: ReservationState
    has_flagged_reservation: bool


class SafetyReviewRead(BaseModel):
    """AC9: one decision, as it was taken."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_request_id: uuid.UUID
    decision: SafetyDecision
    comment: str
    plan_fingerprint: str
    decided_by_id: uuid.UUID
    decided_at: datetime


class EventPlanRead(BaseModel):
    """AC1, AC2 and AC3: one event's plan, whether it may be reviewed, and the last word.

    `plan_fingerprint` is what the Officer must send back with a decision, so the API can
    refuse one taken against a plan that has since moved (AC7). `blockers` is empty
    exactly when `may_review` is true; both are sent because the screen needs the reasons
    and the button state, and deriving one from the other on the client would be a second
    place for the rule to live.
    """

    event_request_id: uuid.UUID
    event_name: str | None
    event_start_at: datetime | None
    event_end_at: datetime | None
    expected_attendance: int | None
    accessibility_requirement: str | None
    layout_requirement: str | None
    venues: list[PlannedVenueRead]
    equipment: list[PlannedEquipmentRead]
    plan_fingerprint: str
    may_review: bool
    blockers: list[str]
    #: AC5: the decision the Coordinator still has to act on, or null once cleared.
    latest_decision: SafetyReviewRead | None

    @classmethod
    def of(
        cls, event: EventRequest, plan: PlanSnapshot, latest: SafetyReview | None
    ) -> "EventPlanRead":
        reasons = [reason.value for reason in blockers(plan)]
        return cls(
            event_request_id=event.id,
            event_name=event.name,
            event_start_at=event.start_at,
            event_end_at=event.end_at,
            expected_attendance=plan.expected_attendance,
            accessibility_requirement=plan.accessibility_requirement,
            layout_requirement=plan.layout_requirement,
            venues=[PlannedVenueRead(**vars(venue)) for venue in plan.venues],
            equipment=[PlannedEquipmentRead(**vars(item)) for item in plan.equipment],
            plan_fingerprint=fingerprint(plan),
            may_review=not reasons,
            blockers=reasons,
            latest_decision=(
                SafetyReviewRead.model_validate(latest) if latest is not None else None
            ),
        )


class SafetyDecisionCreate(BaseModel):
    """AC4 and AC7: what the Officer decided, and which plan they decided it against."""

    model_config = ConfigDict(extra="forbid")

    decision: SafetyDecision
    comment: str
    #: Taken from the plan the screen was showing, so a stale decision can be refused.
    plan_fingerprint: str
