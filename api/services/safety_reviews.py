"""A Safety Officer reviews an event's current plan (SCRUM-79).

Two jobs, and the split matters.

`plan_of` gathers what an event's plan actually is right now: its venue arrangements,
its equipment, and the few event fields that bear on safety. Everything about *judging*
that plan lives in `domain.safety_review`; this module only decides where the parts come
from and reads ADR-0030's expiry for each hold, which the pure rule cannot do.

`record` saves a decision against the plan the Officer was looking at, refusing one taken
against a plan that has since moved (AC7).

Nothing here changes the event. AC8 says an approval does not confirm it and AC5 says a
rejection leaves it in planning, so a decision writes one row and nothing else.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from domain.equipment_requirement import RequirementReview
from domain.event_status import EventStatus
from domain.notifications import NotificationSource, NotificationType
from domain.safety_review import (
    STANDING_STATUSES,
    PlannedEquipment,
    PlannedVenue,
    PlanSnapshot,
    SafetyDecision,
    blockers,
    fingerprint,
    is_stale,
)
from domain.venue_hold import is_due
from models.event_request import EventRequest
from models.safety_review import SafetyReview
from repositories import equipment_requirements as requirement_repo
from repositories import notifications as notifications_repo
from repositories import safety_reviews as repo
from repositories import venue_availability as booking_repo
from services import equipment_requirements as requirement_service
from services import lifecycle_notifications as lifecycle

#: AC5: which notification each decision raises. The type names the decision, as
#: SCRUM-94's do, so the Coordinator can tell whether the plan is back with them
#: without opening the event. Keyed by every member, so a fourth outcome added later
#: fails here rather than silently notifying nobody.
_NOTIFICATION_OF: dict[SafetyDecision, NotificationType] = {
    SafetyDecision.APPROVE: NotificationType.SAFETY_APPROVED,
    SafetyDecision.REJECT: NotificationType.SAFETY_REJECTED,
    SafetyDecision.REQUEST_CHANGES: NotificationType.SAFETY_CHANGES_REQUESTED,
}

#: AC2 and AC5: the codebase calls the planning phase APPROVED (see ACTIVE_STATUSES and
#: the SCRUM-43 work). There is no separate Planning status to wait for.
PLANNING = EventStatus.APPROVED


class SafetyReviewError(Exception):
    """Base class for every refusal this service raises."""


class EventNotInPlanningError(SafetyReviewError):
    """AC2: an event outside planning has no current plan to review."""


class PlanNotReviewableError(SafetyReviewError):
    """AC2: the plan is not arranged enough to judge, with the reasons to fix."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("the plan cannot be reviewed yet")
        self.reasons = reasons


class StalePlanError(SafetyReviewError):
    """AC7: the plan moved between the Officer reading it and saving a decision."""

    def __init__(self, current_fingerprint: str) -> None:
        super().__init__("the plan changed before the decision was saved")
        self.current_fingerprint = current_fingerprint


class BlankCommentError(SafetyReviewError):
    """AC4: a decision without a reason is not a review."""


def plan_of(db: Session, event: EventRequest, now: datetime) -> PlanSnapshot:
    """AC3: everything a safety decision is taken against, as it stands now.

    `now` is used only to read each hold's expiry. ADR-0030 expires a hold by changing
    its status on a sweep, so between sweeps a hold that has run out still reads as
    tentative; a safety prerequisite must not be satisfied by one of those, which is why
    the comparison happens here rather than being left to the stored status.
    """
    # Only the arrangements that still stand. The repository returns every row the event
    # ever had, rejections and swept holds included, and those are its history rather
    # than its plan (see STANDING_STATUSES). The equipment side already drops removed
    # requirements, so the two halves of the plan now mean the same thing by "current".
    bookings = [
        booking
        for booking in booking_repo.list_bookings_for_event(db, event.id)
        if booking.status in STANDING_STATUSES
    ]
    requirements = requirement_repo.list_for_event(db, event.id)
    summaries = requirement_service.reservation_summaries(db, requirements)
    return PlanSnapshot(
        expected_attendance=event.expected_attendance,
        accessibility_requirement=event.accessibility_requirement,
        layout_requirement=event.layout_requirement,
        event_start_at=event.start_at,
        event_end_at=event.end_at,
        venues=[
            PlannedVenue(
                booking_id=booking.id,
                venue_id=booking.venue_id,
                session_label=booking.session_label,
                start_at=booking.start_at,
                end_at=booking.end_at,
                status=booking.status,
                hold_expired=is_due(booking.status, booking.expires_at, now),
            )
            for booking in bookings
        ],
        equipment=[
            PlannedEquipment(
                requirement_id=requirement.id,
                equipment_type=requirement.equipment_type,
                quantity=requirement.quantity,
                # Coerced, not passed through: `review_status` is mapped as a plain
                # String rather than an Enum, so it comes back from the database as a
                # str whatever the annotation says, and the pure rule compares enums.
                review_status=RequirementReview(requirement.review_status),
                reservation_state=summary.reservation_state,
                has_flagged_reservation=summary.has_flagged_reservation,
            )
            for requirement, summary in zip(requirements, summaries, strict=True)
        ],
    )


def record(
    db: Session,
    event: EventRequest,
    decision: SafetyDecision,
    comment: str,
    reviewed_fingerprint: str,
    officer_id: uuid.UUID,
    now: datetime,
) -> SafetyReview:
    """AC4, AC5 and AC7: save a decision against the plan it was actually taken against.

    `reviewed_fingerprint` is what the Officer's screen was showing. It is compared with
    the plan as it is now, so a decision cannot be saved against something that has since
    changed, and an approval can never authorise a plan nobody looked at.

    The prerequisites are checked again here rather than trusted from the read: the
    screen's answer is a moment old, and a hold can expire between loading the plan and
    deciding on it.
    """
    if event.status is not PLANNING:
        raise EventNotInPlanningError
    cleaned = comment.strip()
    if not cleaned:
        raise BlankCommentError

    plan = plan_of(db, event, now)
    reasons = [reason.value for reason in blockers(plan)]
    if reasons:
        raise PlanNotReviewableError(reasons)

    current = fingerprint(plan)
    if is_stale(reviewed_fingerprint, current):
        raise StalePlanError(current)

    recorded = repo.add(
        db,
        SafetyReview(
            event_request_id=event.id,
            decision=decision,
            comment=cleaned,
            plan_fingerprint=current,
            decided_by_id=officer_id,
            decided_at=now,
        ),
    )
    # AC5: the plan going back to the Coordinator has to actually reach them. Without
    # this the decision is recorded and nobody is told, which is the whole of AC5 left
    # undone. An approval is sent too: the Coordinator is the one who acts on it next,
    # and the customer's answer on confirmation makes safety approval a thing they have
    # to wait for. The comment is deliberately not copied into the notification, as
    # SCRUM-94 does with a rejection reason: it is read through the authorised history.
    if event.coordinator_id is not None:
        notifications_repo.stage(
            db,
            recipient_id=event.coordinator_id,
            event_request_id=event.id,
            type=_NOTIFICATION_OF[decision],
            source_type=NotificationSource.SAFETY_REVIEW,
            source_id=str(recorded.id),
            occurred_at=now,
        )
    # SCRUM-50 AC3: the owning Organiser hears the decision as well.
    lifecycle.safety_decided(db, event, _NOTIFICATION_OF[decision], recorded.id, now)
    db.commit()
    db.refresh(recorded)
    return recorded


def history_for_event(db: Session, event: EventRequest) -> list[SafetyReview]:
    """AC9: every decision on this event, oldest first."""
    return repo.list_for_event(db, event.id)


def worklist(
    db: Session, now: datetime
) -> list[tuple[EventRequest, PlanSnapshot, SafetyReview | None]]:
    """AC1: every event in planning, with its plan and its newest decision.

    Events that cannot be reviewed yet are included on purpose. The Officer sees why
    (AC2's reasons come from the plan) rather than finding an event simply missing.
    """
    events = repo.reviewable_events(db, PLANNING.value)
    latest = repo.latest_for_events(db, [event.id for event in events])
    return [(event, plan_of(db, event, now), latest.get(event.id)) for event in events]
