"""Operational safety review of an event's plan (SCRUM-79).

Its own router behind `require_role(Role.SAFETY_OFFICER)`, the same shape SCRUM-44 used
for Technical Support. A separate router rather than widening `require_event_access`, so
no other role gains access to anything by accident.

AC1 says the Officer gets the event and arrangement context they need for the check and
**not** internal clarification comments, so nothing here exposes them.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_user, require_role
from domain.roles import Role
from models.event_request import EventRequest
from repositories import event_requests as event_repo
from schemas.safety_reviews import EventPlanRead, SafetyDecisionCreate, SafetyReviewRead
from services import safety_reviews as service

router = APIRouter(prefix="/safety-reviews", tags=["safety-reviews"])

SafetyOfficer = Annotated[dict[str, object], Depends(require_role(Role.SAFETY_OFFICER))]
AnyOfficer = Annotated[dict[str, object], Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]


def _user_id(user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(user["sub"]))


def _event_in_planning(db: Session, request_id: uuid.UUID) -> EventRequest:
    """The event, or the refusal the Officer should see instead."""
    event = event_repo.get(db, request_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found")
    if event.status is not service.PLANNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Event is not in planning")
    return event


@router.get("", response_model=list[EventPlanRead])
def list_worklist(_: SafetyOfficer, db: Db) -> list[EventPlanRead]:
    """AC1: every event in planning, with its plan, its prerequisites and the last word.

    Events that cannot be reviewed yet are included, with the reasons, so the Officer can
    see what a Coordinator still owes them rather than finding an event missing.
    """
    return [
        EventPlanRead.of(event, plan, latest)
        for event, plan, latest in service.worklist(db, datetime.now(UTC))
    ]


@router.get("/{request_id}", response_model=EventPlanRead)
def read_plan(request_id: uuid.UUID, _: SafetyOfficer, db: Db) -> EventPlanRead:
    """AC3: one event's current plan, with the fingerprint to decide against."""
    event = _event_in_planning(db, request_id)
    plan = service.plan_of(db, event, datetime.now(UTC))
    history = service.history_for_event(db, event)
    return EventPlanRead.of(event, plan, history[-1] if history else None)


@router.get("/{request_id}/history", response_model=list[SafetyReviewRead])
def read_history(request_id: uuid.UUID, _: AnyOfficer, db: Db) -> list[SafetyReviewRead]:
    """AC9: every decision on this event, oldest first.

    Readable by any signed-in participant rather than Safety Officers alone: the
    Coordinator has to act on a rejection (AC5), so they have to be able to read it.
    """
    event = event_repo.get(db, request_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event request not found")
    return [SafetyReviewRead.model_validate(row) for row in service.history_for_event(db, event)]


@router.post("/{request_id}", response_model=SafetyReviewRead, status_code=status.HTTP_201_CREATED)
def record_decision(
    request_id: uuid.UUID, body: SafetyDecisionCreate, user: SafetyOfficer, db: Db
) -> SafetyReviewRead:
    """AC4, AC5 and AC7: record a decision against the plan it was taken against.

    409 when the plan cannot be reviewed or has moved since the Officer read it, with the
    reasons or the current fingerprint so the screen can say what happened rather than
    just refusing. 422 for a blank comment, which is a malformed decision rather than a
    conflict with the world.
    """
    event = _event_in_planning(db, request_id)
    try:
        recorded = service.record(
            db,
            event,
            body.decision,
            body.comment,
            body.plan_fingerprint,
            _user_id(user),
            datetime.now(UTC),
        )
    except service.BlankCommentError as exc:
        raise HTTPException(422, [{"field": "comment", "reason": "is required"}]) from exc
    except service.PlanNotReviewableError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"reason": "plan_not_reviewable", "blockers": exc.reasons}
        ) from exc
    except service.StalePlanError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"reason": "plan_changed", "plan_fingerprint": exc.current_fingerprint},
        ) from exc
    return SafetyReviewRead.model_validate(recorded)
