"""API contracts for operational safety review (SCRUM-79)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.equipment_requirement import RequirementReview
from domain.equipment_reservation import ReservationState
from domain.safety_review import (
    MAX_COMMENT_LENGTH,
    PlanSnapshot,
    SafetyDecision,
    blockers,
    fingerprint,
    returns_to_coordinator,
)
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
    #: AC5: does this decision send the plan back to the Coordinator? Sent rather than
    #: left for the client to work out from `decision`, because that would put the rule
    #: in a second place: a fourth outcome added later would quietly read as an approval
    #: on every screen that compared against "approve" itself.
    returns_to_coordinator: bool

    @classmethod
    def of(cls, review: SafetyReview) -> "SafetyReviewRead":
        return cls(
            id=review.id,
            event_request_id=review.event_request_id,
            decision=SafetyDecision(review.decision),
            comment=review.comment,
            plan_fingerprint=review.plan_fingerprint,
            decided_by_id=review.decided_by_id,
            decided_at=review.decided_at,
            returns_to_coordinator=returns_to_coordinator(SafetyDecision(review.decision)),
        )


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
    #: The newest decision on this event, whatever it was, or null if there has never
    #: been one. Whether it is still outstanding is `latest_decision.returns_to_
    #: coordinator`: an approval that follows a rejection clears it with no second
    #: write, the same choice ADR-0033 made for a flagged reservation.
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
            latest_decision=(SafetyReviewRead.of(latest) if latest is not None else None),
        )


class SafetyDecisionCreate(BaseModel):
    """AC4 and AC7: what the Officer decided, and which plan they decided it against."""

    model_config = ConfigDict(extra="forbid")

    decision: SafetyDecision
    #: Capped like every other reason a decision carries (SCRUM-40's rejection reason),
    #: so one screen cannot write something another cannot show.
    comment: str = Field(max_length=MAX_COMMENT_LENGTH)
    #: Taken from the plan the screen was showing, so a stale decision can be refused.
    plan_fingerprint: str
