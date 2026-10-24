"""Stage event change, safety and lifecycle notifications (SCRUM-50, ADR-0060).

Every function here stages and never commits. The source action calls it inside its own
transaction, so a notification exists only if the action did, and a rollback leaves none
(AC9). SCRUM-99's (recipient, source) uniqueness makes retries and overlapping roles
harmless. Whole-event cancellation is SCRUM-115's and is not sent from here (AC6).
"""

import uuid
from collections.abc import Iterable
from datetime import datetime

from core.database import Session
from domain.event_status import EventStatus
from domain.lifecycle_notifications import (
    affected_staff,
    confirmation_key,
    replan_key,
    review_due_key,
)
from domain.notifications import NotificationSource, NotificationType
from domain.safety_review import PlanSnapshot, blockers, fingerprint
from models.event_request import EventRequest
from repositories import event_closures
from repositories import lifecycle_recipients as recipients
from repositories import notifications as notifications_repo
from repositories import safety_reviews as safety_repo


def change_proposed(db: Session, event: EventRequest, change_id: uuid.UUID, now: datetime) -> None:
    """AC1: a committed proposal goes to the current assigned Coordinator."""
    _send(
        db,
        event,
        [event.coordinator_id],
        NotificationType.CHANGE_PROPOSED,
        NotificationSource.CHANGE_REQUEST,
        str(change_id),
        now,
    )


def change_decided(
    db: Session, event: EventRequest, change_id: uuid.UUID, approved: bool, now: datetime
) -> None:
    """AC1: the decision goes to the owning Organiser, the type naming the outcome."""
    kind = NotificationType.CHANGE_APPROVED if approved else NotificationType.CHANGE_REJECTED
    _send(
        db,
        event,
        [event.organiser_id],
        kind,
        NotificationSource.CHANGE_DECISION,
        str(change_id),
        now,
    )


def safety_decided(
    db: Session, event: EventRequest, kind: NotificationType, review_id: uuid.UUID, now: datetime
) -> None:
    """AC3: the owning Organiser hears the decision too. SCRUM-79 already tells the
    Coordinator. The comment is not copied, it stays in the staff-side history."""
    _send(
        db, event, [event.organiser_id], kind, NotificationSource.SAFETY_REVIEW, str(review_id), now
    )


def review_due(db: Session, event: EventRequest, plan_now: PlanSnapshot, now: datetime) -> None:
    """AC2: tell the Safety Officers once per plan version that it is ready for review.

    Ready means the event is in planning, nothing blocks a review, and no decision has
    been taken on this exact plan. Keyed on the fingerprint, so polling an unchanged plan
    never notifies twice, and a changed plan is announced again.
    """
    if event.status is not EventStatus.APPROVED or blockers(plan_now):
        return
    current = fingerprint(plan_now)
    decided = {review.plan_fingerprint for review in safety_repo.list_for_event(db, event.id)}
    if current in decided:
        return
    _send(
        db,
        event,
        recipients.active_safety_officers(db),
        NotificationType.SAFETY_REVIEW_DUE,
        NotificationSource.SAFETY_PLAN,
        review_due_key(event.id, current),
        now,
    )


def confirmed(db: Session, event: EventRequest, now: datetime) -> None:
    """AC4: a confirmation or reconfirmation goes to the Organiser and the Coordinator."""
    assert event.confirmed_at is not None
    _send(
        db,
        event,
        [event.organiser_id, event.coordinator_id],
        NotificationType.EVENT_CONFIRMED,
        NotificationSource.EVENT_CONFIRMATION,
        confirmation_key(event.id, event.confirmed_at),
        now,
    )


def replanned(db: Session, event: EventRequest, cause: str, source: object, now: datetime) -> None:
    """AC5: affected venue and technical staff and live-registration attendees.

    The Coordinator's own closure alert is SCRUM-81's, so it is not repeated here.
    """
    actors = event_closures.acted_on_event(db, event.id)
    staff = affected_staff(actors, recipients.roles_of(db, actors))
    _send(
        db,
        event,
        staff | recipients.live_attendees(db, event.id),
        NotificationType.EVENT_REPLANNED,
        NotificationSource.EVENT_REPLAN,
        replan_key(cause, source),
        now,
    )


def completed(db: Session, event: EventRequest, now: datetime) -> None:
    """AC7: completion goes to the Organiser and the Coordinator."""
    _send(
        db,
        event,
        [event.organiser_id, event.coordinator_id],
        NotificationType.EVENT_COMPLETED,
        NotificationSource.EVENT_COMPLETION,
        str(event.id),
        now,
    )


def _send(
    db: Session,
    event: EventRequest,
    to: Iterable[uuid.UUID | None],
    kind: NotificationType,
    source: NotificationSource,
    source_id: str,
    now: datetime,
) -> None:
    for recipient in {person for person in to if person is not None}:
        notifications_repo.stage(
            db,
            recipient_id=recipient,
            event_request_id=event.id,
            type=kind,
            source_type=source,
            source_id=source_id,
            occurred_at=now,
        )
