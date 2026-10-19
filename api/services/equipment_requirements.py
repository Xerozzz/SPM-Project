"""The assigned Coordinator maintains an event's equipment requirements (SCRUM-43).

Three operations, and each one does the same three things: check the record would be valid
as it would be afterwards, write it, and record who did it (AC8). The validity rules are in
`domain.equipment_requirement`; this module decides where the catalogue and the event's
existing types come from.

Removal is soft (AC7), so a removed requirement keeps its row and its history while no
longer counting toward anything. Nothing here reserves equipment (AC9): a requirement is a
statement of what is needed, and SCRUM-53 is what turns one into a commitment.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from domain.equipment_availability import Availability, StockEntry, assess, count_in_service
from domain.equipment_requirement import (
    RequirementFields,
    RequirementReview,
    ReviewRefusal,
    review_after_change,
    review_refusal,
    validate_change,
    validate_new_requirement,
)
from domain.validation import FieldProblem
from models.equipment_requirement_change import EquipmentRequirementChange, RequirementAction
from models.event_equipment_requirement import EventEquipmentRequirement
from models.event_request import EventRequest
from repositories import equipment as catalogue_repo
from repositories import equipment_requirements as repo
from repositories import event_requests as event_request_repo


class RequirementError(Exception):
    """Base class for every refusal this service raises."""


class RequirementNotFoundError(RequirementError):
    """No such requirement on this event."""


class ReviewNotAllowedError(RequirementError):
    """SCRUM-44: the requirement's event is not in planning, so it cannot be reviewed."""


class InvalidRequirementError(RequirementError):
    """AC3 and AC4: the requirement cannot be saved, with the fields to fix."""

    def __init__(self, problems: list[FieldProblem]) -> None:
        super().__init__("invalid equipment requirement")
        self.problems = problems


def list_for_event(db: Session, event: EventRequest) -> list[EventEquipmentRequirement]:
    """AC1: the live requirements for this event, which is what the Coordinator maintains."""
    return repo.list_for_event(db, event.id)


def add(
    db: Session,
    event: EventRequest,
    fields: RequirementFields,
    actor_id: uuid.UUID,
    now: datetime,
) -> EventEquipmentRequirement:
    """AC2 and AC3: add a requirement to an event the Coordinator is maintaining."""
    _ensure_valid(db, event, fields)
    assert fields.equipment_type is not None and fields.quantity is not None
    requirement = EventEquipmentRequirement(
        event_request_id=event.id,
        equipment_type=fields.equipment_type.strip(),
        quantity=fields.quantity,
        technical_requirements=fields.technical_requirements,
        review_status=review_after_change(),
        created_at=now,
        updated_at=now,
    )
    db.add(requirement)
    # Flushed so the audit row can reference it; both commit together in `repo.save`.
    db.flush()
    _record(
        db,
        requirement,
        actor_id,
        now,
        RequirementAction.ADDED,
        old_quantity=None,
        old_technical=None,
        new_quantity=requirement.quantity,
        new_technical=requirement.technical_requirements,
    )
    try:
        return repo.save(db, requirement)
    except repo.DuplicateRequirementError as exc:
        # Two coordinators added the same type at the same moment and the index refused
        # the second. Reported as the rule it broke, so the loser sees what the check
        # would have told them rather than a 500.
        raise InvalidRequirementError(
            [FieldProblem("equipment_type", "is already required for this event")]
        ) from exc


def update(
    db: Session,
    event: EventRequest,
    requirement_id: uuid.UUID,
    changes: dict[str, object],
    actor_id: uuid.UUID,
    now: datetime,
) -> EventEquipmentRequirement:
    """AC2 and AC5: change a requirement, which sends it back for review.

    `changes` holds only what the caller actually sent, so a field left out keeps its
    value and is not quietly erased. The record is validated as it would be *after* the
    change, the same way `services.venues.update` does it, so sending an invalid quantity
    is refused whether or not the other field came with it.

    The type is not changed here. AC4 makes one type one line, so moving a line to a
    different type is a removal and an addition, which keeps the history honest about
    what was asked for and when.
    """
    requirement = _live_requirement(db, event, requirement_id)
    merged_quantity = changes.get("quantity", requirement.quantity)
    merged_technical = changes.get("technical_requirements", requirement.technical_requirements)
    problems = validate_change(
        merged_quantity if isinstance(merged_quantity, int) else None,
        merged_technical if isinstance(merged_technical, str) else None,
    )
    if problems:
        raise InvalidRequirementError(problems)
    assert isinstance(merged_quantity, int)
    old_quantity, old_technical = requirement.quantity, requirement.technical_requirements
    requirement.quantity = merged_quantity
    requirement.technical_requirements = (
        merged_technical if isinstance(merged_technical, str) else None
    )
    requirement.review_status = review_after_change()
    requirement.updated_at = now
    _record(
        db,
        requirement,
        actor_id,
        now,
        RequirementAction.UPDATED,
        old_quantity=old_quantity,
        old_technical=old_technical,
        new_quantity=requirement.quantity,
        new_technical=requirement.technical_requirements,
    )
    return repo.save(db, requirement)


def remove(
    db: Session,
    event: EventRequest,
    requirement_id: uuid.UUID,
    actor_id: uuid.UUID,
    now: datetime,
) -> EventEquipmentRequirement:
    """AC7: take a requirement out of the live set without losing that it was ever asked for.

    The row stays, so the event's history still shows it and the same type can be asked
    for again later. Any reservation for it is left in place: flagging it (AC6) is a
    later story, and releasing it is Event Change Management's work.
    """
    requirement = _live_requirement(db, event, requirement_id)
    requirement.removed_at = now
    requirement.updated_at = now
    _record(
        db,
        requirement,
        actor_id,
        now,
        RequirementAction.REMOVED,
        old_quantity=requirement.quantity,
        old_technical=requirement.technical_requirements,
        new_quantity=None,
        new_technical=None,
    )
    return repo.save(db, requirement)


def history_for_event(db: Session, event: EventRequest) -> list[EquipmentRequirementChange]:
    """AC7 and AC8: every add, change and removal on this event, oldest first."""
    return repo.changes_for_event(db, event.id)


def list_for_review(db: Session) -> list[tuple[EventEquipmentRequirement, EventRequest]]:
    """SCRUM-44 AC1: what Technical Support Staff have to assess, with each event's timing."""
    return repo.list_for_review(db)


def review(
    db: Session, requirement_id: uuid.UUID, outcome: RequirementReview, now: datetime
) -> EventEquipmentRequirement:
    """SCRUM-44 AC2: record whether a requirement can be fulfilled.

    Only the status changes. Nothing is reserved and no stock moves (AC5): SCRUM-53 is what
    turns a requirement into a commitment. No audit row is written, because
    `equipment_requirement_changes` has no column for a review outcome and adding one is a
    migration this story does not make.
    """
    requirement = repo.get(db, requirement_id)
    if requirement is None:
        raise RequirementNotFoundError
    event = event_request_repo.get(db, requirement.event_request_id)
    # The foreign key guarantees the event exists; this only narrows the type for mypy.
    assert event is not None
    refusal = review_refusal(event.status, removed=requirement.removed_at is not None)
    if refusal is ReviewRefusal.REQUIREMENT_REMOVED:
        raise RequirementNotFoundError
    if refusal is ReviewRefusal.EVENT_NOT_IN_PLANNING:
        raise ReviewNotAllowedError
    requirement.review_status = outcome
    requirement.updated_at = now
    return repo.save(db, requirement)


def check_availability(
    db: Session, event: EventRequest
) -> list[tuple[EventEquipmentRequirement, Availability]]:
    """SCRUM-52: whether each live requirement could be met over the event's window.

    Planning only, by the same rule as a review, because this is the question a review
    answers. Read-only (AC6): nothing is added to the session and nothing is committed.
    """
    if review_refusal(event.status, removed=False) is ReviewRefusal.EVENT_NOT_IN_PLANNING:
        raise ReviewNotAllowedError
    # Submission refuses an event without both times (domain.event_request), and only a
    # submitted event can be approved; this narrows the types for mypy.
    assert event.start_at is not None and event.end_at is not None
    requirements = repo.list_for_event(db, event.id)
    entries = catalogue_repo.list_by_types(db, {row.equipment_type for row in requirements})
    results = []
    for row in requirements:
        stock = count_in_service(
            StockEntry(e.total_quantity, e.operational_status, e.is_active)
            for e in entries
            if e.equipment_type == row.equipment_type
        )
        reserved = catalogue_repo.reserved_quantity(
            db, row.equipment_type, event.start_at, event.end_at, excluding_event_id=event.id
        )
        results.append((row, assess(row.quantity, stock, reserved)))
    return results


def _live_requirement(
    db: Session, event: EventRequest, requirement_id: uuid.UUID
) -> EventEquipmentRequirement:
    requirement = repo.get(db, requirement_id)
    # A requirement belonging to another event is reported as missing rather than
    # forbidden, so the route cannot be used to discover that an id exists elsewhere.
    if (
        requirement is None
        or requirement.event_request_id != event.id
        or requirement.removed_at is not None
    ):
        raise RequirementNotFoundError
    return requirement


def _ensure_valid(db: Session, event: EventRequest, fields: RequirementFields) -> None:
    problems = validate_new_requirement(
        fields,
        frozenset(catalogue_repo.list_distinct_active_types(db)),
        repo.live_types_for_event(db, event.id),
    )
    if problems:
        raise InvalidRequirementError(problems)


def _record(
    db: Session,
    requirement: EventEquipmentRequirement,
    actor_id: uuid.UUID,
    now: datetime,
    action: RequirementAction,
    *,
    old_quantity: int | None,
    old_technical: str | None,
    new_quantity: int | None,
    new_technical: str | None,
) -> None:
    """AC8: who did what, when, and both sides of it.

    Both sides are passed in rather than read off the requirement, because for a removal
    there is no new value rather than an unchanged one, and a default that guessed which
    case it was in would be one more thing to get wrong.
    """
    repo.record_change(
        db,
        EquipmentRequirementChange(
            requirement_id=requirement.id,
            event_request_id=requirement.event_request_id,
            changed_by_id=actor_id,
            changed_at=now,
            action=action,
            equipment_type=requirement.equipment_type,
            old_quantity=old_quantity,
            new_quantity=new_quantity,
            old_technical_requirements=old_technical,
            new_technical_requirements=new_technical,
        ),
    )


def seed_from_event(db: Session, event: EventRequest, now: datetime) -> None:
    """AC1: carry the organiser's chosen type across when the event is approved.

    Approval is where an event stops being the organiser's draft and becomes the assigned
    Coordinator's to plan, so it is where the single type they picked (ADR-0024) becomes
    the first maintained requirement. Without this, AC1 would hold only for events that
    existed when migration 0023 ran and never for new ones.

    Added to the session, not committed: the caller's save commits it with the approval,
    so an approval that fails leaves no requirement behind.

    Idempotent, which matters for migration 0023: that backfills a requirement for every
    approved event, so an event approved before the migration and re-read after it must
    not gain a second line. An approved event cannot return to SUBMITTED, so approval
    itself never runs twice. Quiet about quantity, because a field that never held a
    number can only honestly become one.

    No audit row is written. AC8 records what a person did to a requirement, and nobody
    added this one; the approval carried it across. The same is true of 0023's backfill.
    """
    chosen = (event.equipment_requirement or "").strip()
    if not chosen or repo.list_for_event(db, event.id):
        return
    db.add(
        EventEquipmentRequirement(
            event_request_id=event.id,
            equipment_type=chosen,
            quantity=1,
            technical_requirements=None,
            review_status=review_after_change(),
            created_at=now,
            updated_at=now,
        )
    )
