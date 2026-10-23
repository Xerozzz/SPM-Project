"""May this event be confirmed? (SCRUM-80). Pure, no database.

Confirmation is the moment an event's arrangements stop being provisional: the holds
Venue Staff placed become real bookings and preparation can begin. The customer's answer
is explicit about what has to be true first (Customer Clarification 3):

> The Event Coordinator marks the event Confirmed only after required venue and technical
> approvals **and the Safety Officer's operational safety approval** are complete.

So the question splits in two, and both halves already have a home:

* **Is the plan arranged?** Exactly the question SCRUM-79 asks before a safety review may
  begin — every standing venue arrangement held and unexpired, every equipment
  requirement assessed and fulfilled. `domain.safety_review.blockers` is that rule, and
  it is reused here rather than restated, so the two can never drift into disagreeing
  about what "arranged" means (AC2, AC3, AC10).
* **Is there a safety approval, and is it about *this* plan?** That is the part only
  confirmation asks. AC7 says a previous approval for a changed plan cannot authorise
  confirmation, which is what the stored fingerprint is for (ADR-0048): an approval
  carries the plan it judged, and if the plan has moved since, the approval is spent.

Nothing here reads a clock or a database. Whether a hold has run out is decided by the
caller and arrives inside the snapshot, as it does for the safety rule.
"""

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from domain.event_status import EventStatus
from domain.safety_review import (
    PlanSnapshot,
    ReviewBlocker,
    SafetyDecision,
    fingerprint,
)
from domain.safety_review import (
    blockers as arrangement_blockers,
)

#: AC2: the status an event is confirmed *from*. The codebase calls the planning phase
#: APPROVED (see ACTIVE_STATUSES and the SCRUM-43 work); there is no separate Planning.
PLANNING = EventStatus.APPROVED


class ConfirmationBlocker(StrEnum):
    """AC2 and AC7: why confirmation cannot happen yet, beyond the arrangements.

    The arrangement reasons keep SCRUM-79's vocabulary (`ReviewBlocker`) rather than
    being restated here, so a screen that already explains one explains both.
    """

    #: The event is not in planning: already confirmed, still submitted, or rejected.
    NOT_IN_PLANNING = "not_in_planning"
    #: AC3's "unresolved issue": a closure or a buffer change has left a standing
    #: arrangement clashing (SCRUM-81, SCRUM-89). The hold is still Tentative and has not
    #: expired, so nothing about its status says anything is wrong — but Venue Staff have
    #: already flagged it, and committing it would make a broken arrangement final.
    ARRANGEMENT_NEEDS_ATTENTION = "arrangement_needs_attention"
    #: No Safety Officer has decided on this event at all.
    SAFETY_NOT_REVIEWED = "safety_not_reviewed"
    #: The latest decision sent the plan back rather than approving it.
    SAFETY_NOT_APPROVED = "safety_not_approved"
    #: AC7: the approval was for a plan that has since changed, so it authorises nothing.
    SAFETY_APPROVAL_STALE = "safety_approval_stale"


@dataclass(frozen=True)
class SafetyStanding:
    """The latest safety decision on an event, and the plan it was taken against.

    `None` means no decision has ever been recorded. The fingerprint travels with the
    decision because that is the whole point of ADR-0048: an approval is a statement
    about one version of the plan, not about the event forever.
    """

    decision: SafetyDecision
    plan_fingerprint: str
    #: SCRUM-130: the event went back to planning after this approval (ADR-0052).
    invalidated: bool = False


@dataclass(frozen=True)
class ConfirmationProblems:
    """Everything standing between this event and confirmation, in two vocabularies.

    Kept apart rather than flattened into one list because they are owed by different
    people: the arrangement reasons are work for the Coordinator, Venue Staff and
    Technical Support, while the safety reasons are the Officer's to clear or the
    Coordinator's to trigger again by fixing the plan.
    """

    #: What the plan is still missing. Mostly SCRUM-79's vocabulary, reused rather than
    #: restated, plus AC3's unresolved-issue reason which only confirmation asks about.
    arrangement: tuple[ReviewBlocker | ConfirmationBlocker, ...]
    #: What confirmation additionally requires: a safety approval, about this plan.
    safety: tuple[ConfirmationBlocker, ...]

    @property
    def blocked(self) -> bool:
        return bool(self.arrangement or self.safety)

    def reasons(self) -> list[str]:
        """Every reason as its stored value, arrangements first."""
        return [reason.value for reason in self.arrangement] + [
            reason.value for reason in self.safety
        ]


def problems(
    status: EventStatus,
    plan: PlanSnapshot,
    standing: SafetyStanding | None,
    needing_attention: Collection[UUID] = (),
) -> ConfirmationProblems:
    """AC2, AC3, AC7 and AC10: every reason this event cannot be confirmed right now.

    All of them rather than the first, so a Coordinator chasing three people can see all
    three at once instead of learning about the next only after fixing the last.

    An event outside planning reports only that: asking whether its arrangements are in
    order is a question about an event that is already confirmed or was never approved,
    and answering it would invite a caller to act on the rest of the list.
    """
    if status is not PLANNING:
        return ConfirmationProblems((), (ConfirmationBlocker.NOT_IN_PLANNING,))

    return current_plan_problems(plan, standing, needing_attention)


def current_plan_problems(
    plan: PlanSnapshot,
    standing: SafetyStanding | None,
    needing_attention: Collection[UUID] = (),
    *,
    require_current_safety_fingerprint: bool = True,
) -> ConfirmationProblems:
    """The current arrangement and safety checks shared with registration opening.

    Confirmation additionally requires that the event is in planning; registration
    instead requires it already be Confirmed. Both must judge the same live plan.
    """
    arrangement: list[ReviewBlocker | ConfirmationBlocker] = list(arrangement_blockers(plan))
    # AC3: a hold that is held and unexpired can still be one Venue Staff have flagged.
    if any(venue.booking_id in needing_attention for venue in plan.venues):
        arrangement.append(ConfirmationBlocker.ARRANGEMENT_NEEDS_ATTENTION)

    return ConfirmationProblems(
        tuple(arrangement),
        tuple(_safety_problems(plan, standing, require_current_safety_fingerprint)),
    )


def _safety_problems(
    plan: PlanSnapshot,
    standing: SafetyStanding | None,
    require_current_safety_fingerprint: bool = True,
) -> list[ConfirmationBlocker]:
    """AC2 and AC7: is there an approval, and is it about the plan in front of us?"""
    if standing is None:
        return [ConfirmationBlocker.SAFETY_NOT_REVIEWED]
    if standing.decision is not SafetyDecision.APPROVE:
        return [ConfirmationBlocker.SAFETY_NOT_APPROVED]
    # SCRUM-130: the event went back to planning since, so the approval judged a plan
    # that is no longer the confirmed one, even if its fingerprint still matches.
    if standing.invalidated:
        return [ConfirmationBlocker.SAFETY_APPROVAL_STALE]
    # The approval named a plan. If the plan has moved since — a session retimed, a
    # requirement added, a hold replaced — then nobody has judged what is in front of us
    # now, and an approval of something else cannot stand in for that (ADR-0048).
    if require_current_safety_fingerprint and standing.plan_fingerprint != fingerprint(plan):
        return [ConfirmationBlocker.SAFETY_APPROVAL_STALE]
    return []


def may_confirm(status: EventStatus, plan: PlanSnapshot, standing: SafetyStanding | None) -> bool:
    """AC2, as a single question for callers that do not need the reasons."""
    return not problems(status, plan, standing).blocked
