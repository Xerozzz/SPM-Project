"""Operational safety review of an event's current plan (SCRUM-79). Pure, no database.

Three questions live here, and keeping them together is deliberate: all three are asked
about the same thing, the plan as it stands right now.

* **May a review begin?** (AC2) Only when every venue arrangement is actually held and
  every equipment requirement is settled. A half-arranged plan is not a thing anyone can
  judge the safety of, so the prerequisites are refusals rather than warnings.
* **What exactly was judged?** (AC4, AC8) A decision records a fingerprint of the plan it
  was taken against.
* **Is a decision still about the plan in front of us?** (AC7) The fingerprint is
  recomputed and compared. If it moved, the decision is stale and cannot authorise
  anything.

Nothing here reads a clock, a database or a request. `hold_expired` is passed in as a
decided fact, because whether a hold has run out is the caller's reading of ADR-0030's
status, not a comparison this module should make.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from domain.equipment_requirement import RequirementReview
from domain.equipment_reservation import ReservationState
from domain.venue_booking import BookingStatus


class SafetyDecision(StrEnum):
    """AC4: what a Safety Officer may record.

    `REQUEST_CHANGES` is separate from `REJECT` on purpose. Both send the plan back
    (AC5), and neither rejects the event, but the customer asked for the difference to be
    visible: one says this plan is unsafe, the other says it is nearly there.
    """

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


#: AC4: how long a reason may be, matching SCRUM-40's rejection reason so the two
#: screens that record a judgement on an event agree on what fits.
MAX_COMMENT_LENGTH = 1000

#: AC5: the two decisions that send the plan back to the Coordinator. Written down once
#: so a third outcome cannot quietly behave like an approval.
RETURNS_TO_COORDINATOR: frozenset[SafetyDecision] = frozenset(
    {SafetyDecision.REJECT, SafetyDecision.REQUEST_CHANGES}
)


class ReviewBlocker(StrEnum):
    """AC2: why a review cannot begin. Several can apply at once."""

    NO_VENUE_ARRANGEMENT = "no_venue_arrangement"
    VENUE_NOT_HELD = "venue_not_held"
    HOLD_EXPIRED = "hold_expired"
    EQUIPMENT_UNREVIEWED = "equipment_unreviewed"
    EQUIPMENT_NOT_FULFILLED = "equipment_not_fulfilled"
    RESERVATION_NEEDS_RECONSIDERING = "reservation_needs_reconsidering"


@dataclass(frozen=True)
class PlannedVenue:
    """One venue arrangement as safety needs to see it (SCRUM-111 sessions included)."""

    booking_id: UUID
    venue_id: UUID
    session_label: str
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    #: ADR-0030 reads expiry as a status, so the caller decides this, not the clock here.
    hold_expired: bool


@dataclass(frozen=True)
class PlannedEquipment:
    """One equipment requirement as safety needs to see it."""

    requirement_id: UUID
    equipment_type: str
    quantity: int
    review_status: RequirementReview
    reservation_state: ReservationState
    has_flagged_reservation: bool


@dataclass(frozen=True)
class PlanSnapshot:
    """Everything a safety decision is taken against.

    Only what could change the answer. The event's own name and purpose are not here: a
    rename is not a reason to review the plan again, and including it would invalidate
    sound approvals for nothing.
    """

    expected_attendance: int | None
    accessibility_requirement: str | None
    layout_requirement: str | None
    event_start_at: datetime | None
    event_end_at: datetime | None
    venues: Sequence[PlannedVenue]
    equipment: Sequence[PlannedEquipment]


def blockers(plan: PlanSnapshot) -> list[ReviewBlocker]:
    """AC2: every reason this plan cannot be reviewed yet, in a stable order.

    All of them rather than the first, because a Coordinator fixing one at a time learns
    about the next only after another round trip, and the screen has room to say so.

    An event with no venue arrangement at all is blocked: there is no plan to judge.
    """
    found: list[ReviewBlocker] = []

    if not plan.venues:
        found.append(ReviewBlocker.NO_VENUE_ARRANGEMENT)
    for venue in plan.venues:
        if venue.status is BookingStatus.TENTATIVE and venue.hold_expired:
            # A hold that has run out is not an arrangement, whatever the row still says.
            found.append(ReviewBlocker.HOLD_EXPIRED)
        elif venue.status not in _HELD_STATUSES:
            found.append(ReviewBlocker.VENUE_NOT_HELD)

    for item in plan.equipment:
        if item.review_status is RequirementReview.PENDING_REVIEW:
            found.append(ReviewBlocker.EQUIPMENT_UNREVIEWED)
        elif item.review_status is not RequirementReview.AVAILABLE:
            # Partially available or unavailable: AC2 calls both unresolved.
            found.append(ReviewBlocker.EQUIPMENT_NOT_FULFILLED)
        elif item.reservation_state is not ReservationState.RESERVED:
            # Reviewed as available but not actually committed, which is the "partial"
            # case AC2 names: the equipment has been judged, not secured.
            found.append(ReviewBlocker.EQUIPMENT_NOT_FULFILLED)
        if item.has_flagged_reservation:
            # SCRUM-43 AC6: something changed after it was reserved, so what is held no
            # longer matches what is needed until Technical Support have looked again.
            found.append(ReviewBlocker.RESERVATION_NEEDS_RECONSIDERING)

    # Each reason once, in first-seen order: three expired holds is one thing to fix.
    return list(dict.fromkeys(found))


#: A venue arrangement counts when it is held now (SCRUM-110 made approval a hold) or was
#: confirmed under the earlier flow and is untouched.
_HELD_STATUSES: frozenset[BookingStatus] = frozenset(
    {BookingStatus.TENTATIVE, BookingStatus.CONFIRMED}
)

#: Which of an event's booking rows are its *plan*, as opposed to its history.
#:
#: An event keeps every booking row it ever had: SCRUM-40 retains a rejection so the
#: Coordinator can read the reason, and ADR-0030 keeps a swept hold because "no longer
#: holds the venue" is not the same as "never happened". None of those three arrange
#: anything, and none of them can be cleared by anybody, so judging them would block a
#: review for good: one rejected request in an event's past and no Coordinator could ever
#: get a plan reviewed. They are also not what the Officer is looking at (AC3), and
#: letting them into the fingerprint would invalidate a sound approval (AC7) because a
#: dead row appeared next to the live one.
STANDING_STATUSES: frozenset[BookingStatus] = frozenset(
    {BookingStatus.PENDING, BookingStatus.TENTATIVE, BookingStatus.CONFIRMED}
)


def may_review(plan: PlanSnapshot) -> bool:
    """AC2, as a single question for callers that do not need the reasons."""
    return not blockers(plan)


def fingerprint(plan: PlanSnapshot) -> str:
    """AC4 and AC7: a stable identifier for exactly this plan.

    A hash rather than a timestamp. `updated_at` moves when anything on a row is written,
    including columns safety does not care about, so a timestamp would invalidate sound
    approvals for changes that cannot affect a safety judgement. This moves only when
    something in `PlanSnapshot` moves, which is the definition of the plan.

    Sorted by id before hashing, so the order rows come back in cannot change the answer.
    Datetimes go in as ISO-8601, which is exact for the timezone-aware UTC values this
    codebase stores (AGENTS.md section 3).
    """
    payload = {
        "attendance": plan.expected_attendance,
        "accessibility": plan.accessibility_requirement,
        "layout": plan.layout_requirement,
        "starts": _moment(plan.event_start_at),
        "ends": _moment(plan.event_end_at),
        "venues": sorted(
            [
                {
                    "id": str(venue.booking_id),
                    "venue": str(venue.venue_id),
                    "session": venue.session_label,
                    "starts": _moment(venue.start_at),
                    "ends": _moment(venue.end_at),
                    "status": venue.status.value,
                    "expired": venue.hold_expired,
                }
                for venue in plan.venues
            ],
            key=_by_id,
        ),
        "equipment": sorted(
            [
                {
                    "id": str(item.requirement_id),
                    "type": item.equipment_type,
                    "quantity": item.quantity,
                    "review": item.review_status.value,
                    "reservation": item.reservation_state.value,
                    "flagged": item.has_flagged_reservation,
                }
                for item in plan.equipment
            ],
            key=_by_id,
        ),
    }
    # sort_keys so the same plan always produces the same bytes, whatever order the
    # dictionary happened to be built in.
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def is_stale(recorded: str, current: str) -> bool:
    """AC7: was this decision taken against a plan that no longer exists?"""
    return recorded != current


def returns_to_coordinator(decision: SafetyDecision) -> bool:
    """AC5: does this decision send the plan back rather than clear it?"""
    return decision in RETURNS_TO_COORDINATOR


def _moment(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _by_id(entry: Mapping[str, object]) -> str:
    return str(entry["id"])
