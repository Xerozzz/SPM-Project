"""Shared authorisation dependencies. Routers use these; never inline role checks."""

import uuid
from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import decode_access_token
from domain.event_cancellation import may_read_cancellation
from domain.event_change import accepts_change_request
from domain.event_completion import may_read_closure
from domain.event_request import accepts_ordinary_update
from domain.event_status import EventStatus
from domain.roles import Role
from models.event_request import EventRequest
from repositories import event_closures
from repositories import event_requests as event_request_repo

_bearer = HTTPBearer(auto_error=False)

# SCRUM-86 AC4: the staff roles whose participation in an event can be recorded.
_CLOSURE_STAFF_ROLES = frozenset(
    {Role.VENUE_STAFF.value, Role.TECH_SUPPORT.value, Role.SAFETY_OFFICER.value}
)


class EventAccess(StrEnum):
    """The event-request access modes routes may ask for.

    VIEW and EDIT cover the request itself (SCRUM-29). Clarification notes (SCRUM-106)
    are internal to the assigned coordinator: only they may list or record them, and
    recording is pinned to review (SUBMITTED). Reading the notes needs no status pin —
    the assignee keeps their notes after a decision — but it still needs the current
    assignment, so reassignment transfers access immediately. Assignment history
    (SCRUM-105) is readable by any Lead, the owning Organiser and the current assignee.
    Safety decisions (SCRUM-79) are staff-side: the Safety Officer, any Lead and the
    current assignee, but not the Organiser. Confirmation (SCRUM-80) is the current
    assignee's alone. Cancelling one venue arrangement (SCRUM-109) is for the current
    assignee only. Completing an event (SCRUM-86) is the current assignee's, and its
    closure record is for the owner, the assignee, any Lead and staff who took part.
    Asking for a cancellation (SCRUM-115) is the owner's, applying or declining it is the
    current assignee's, and the requests are readable by both and by any Lead.
    The event history (SCRUM-88) is readable by the assignment-history audience.
    """

    VIEW = "view"
    EDIT = "edit"
    DECIDE = "decide"
    SUBMIT_VENUE_BOOKING = "submit_venue_booking"
    MAINTAIN_EQUIPMENT = "maintain_equipment"
    CHECK_EQUIPMENT_AVAILABILITY = "check_equipment_availability"
    REQUEST_CLARIFICATION = "request_clarification"
    READ_CLARIFICATIONS = "read_clarifications"
    UPDATE_PLANNING_INFO = "update_planning_info"
    PROPOSE_CHANGE = "propose_change"
    READ_CHANGE_REQUESTS = "read_change_requests"
    DECIDE_CHANGE_REQUEST = "decide_change_request"
    READ_ASSIGNMENT_HISTORY = "read_assignment_history"
    READ_SAFETY_REVIEWS = "read_safety_reviews"
    CONFIRM_EVENT = "confirm_event"
    MANAGE_REMINDERS = "manage_reminders"
    READ_REGISTRATION_SETTINGS = "read_registration_settings"
    READ_REGISTRATIONS = "read_registrations"
    MANAGE_REGISTRATION = "manage_registration"
    CANCEL_VENUE_ARRANGEMENT = "cancel_venue_arrangement"
    COMPLETE_EVENT = "complete_event"
    READ_EVENT_CLOSURE = "read_event_closure"
    REQUEST_EVENT_CANCELLATION = "request_event_cancellation"
    CANCEL_EVENT = "cancel_event"
    READ_EVENT_CANCELLATION = "read_event_cancellation"
    READ_EVENT_HISTORY = "read_event_history"


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, object]:
    """Return the JWT claims, or 401 when missing or invalid."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return decode_access_token(credentials.credentials)
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        ) from exc


def require_role(*allowed: Role) -> Callable[[dict[str, object]], dict[str, object]]:
    """Dependency factory: allow only tokens carrying one of the given roles.

    Takes `Role` members, not strings, so a misspelt role fails at import time rather than
    as a 403 nobody can explain.
    """
    allowed_values = {role.value for role in allowed}

    def check(
        user: Annotated[dict[str, object], Depends(get_current_user)],
    ) -> dict[str, object]:
        if not allowed_values & _granted_roles(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return check


def require_event_access(permission: EventAccess) -> Callable[..., EventRequest]:
    """Dependency factory for one event request: view it, edit it, or take part in its
    clarification exchange.

    Draft visibility is deliberately narrower than submitted visibility: coordinators may
    see submitted requests, but not drafts before submission. An Organiser sees only their
    own requests (SCRUM-112, ADR-0039); same-organisation peers get no access here.
    """

    def check(
        request_id: uuid.UUID,
        user: Annotated[dict[str, object], Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> EventRequest:
        request = event_request_repo.get(db, request_id)
        if request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Event request not found"
            )

        roles = _granted_roles(user)
        viewer_id = _user_id(user)

        is_owner = Role.ORGANISER.value in roles and request.organiser_id == viewer_id

        if permission is EventAccess.EDIT:
            if is_owner:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # Clarification notes are internal to the assigned coordinator (SCRUM-106):
        # recording is part of review, so it is pinned to SUBMITTED; reading keeps no
        # status pin so the assignee keeps their notes after a decision. Both refuse
        # without disclosure when the caller is not the current assignee.
        if permission is EventAccess.REQUEST_CLARIFICATION:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned and request.status is EventStatus.SUBMITTED:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if permission is EventAccess.READ_CLARIFICATIONS:
            if may_read_clarifications(request, roles, viewer_id):
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if permission is EventAccess.DECIDE:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned and request.status is EventStatus.SUBMITTED:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-36: after submission the organiser asks the coordinator for changes, so the
        # ordinary update belongs to the assigned coordinator while the request is Submitted
        # or Approved. A Confirmed event is changed through change control instead.
        if permission is EventAccess.UPDATE_PLANNING_INFO:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned and accepts_ordinary_update(request.status):
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-37: after submission the owning Organiser proposes significant changes
        # rather than editing (AC1, AC7). Reading them is for the owner and the event's
        # current assigned Coordinator, so a reassignment moves it at once (AC6).
        if permission is EventAccess.PROPOSE_CHANGE:
            if is_owner and accepts_change_request(request.status):
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-47 AC1: only the current assigned Coordinator decides, and only while the
        # event can still take a change request.
        if permission is EventAccess.DECIDE_CHANGE_REQUEST:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned and accepts_change_request(request.status):
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if permission is EventAccess.READ_CHANGE_REQUESTS:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_owner or is_assigned:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-105 (ADR-0047): the assignment history is for any Lead, as before, plus
        # the owning Organiser and the current assigned Coordinator. No status pin, so a
        # Lead still reads a draft's empty history. Each role is checked on its own, so
        # an outgoing Coordinator who is also the owner or a Lead keeps that access.
        # SCRUM-88 (ADR-0062): the event history has the same audience today. Kept as its
        # own member so either can be widened on its own, written once so that widening
        # one is a deliberate edit rather than two branches drifting apart.
        if permission in (EventAccess.READ_ASSIGNMENT_HISTORY, EventAccess.READ_EVENT_HISTORY):
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if Role.COORDINATOR_LEAD.value in roles or is_owner or is_assigned:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # Two separate permissions that happen to ask the same question today: the
        # assigned coordinator, while the event is being planned. The codebase calls that
        # phase APPROVED (see the note on ACTIVE_STATUSES), which is the "Approved or
        # Planning" SCRUM-43 AC10 describes. SUBMITTED is too early and CONFIRMED too
        # late, since AC11 sends a post-confirmation change through the significant-change
        # process instead.
        #
        # Kept as two members rather than one, because they mean different things and
        # either could be widened on its own. The rule is written once so that widening
        # one is a deliberate edit rather than two branches silently drifting apart.
        if permission in (EventAccess.MAINTAIN_EQUIPMENT, EventAccess.SUBMIT_VENUE_BOOKING):
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned and request.status is EventStatus.APPROVED:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-52 AC5: Technical Support Staff, who assess every event's equipment, and
        # the event's assigned coordinator. No status here: outside planning the service
        # answers 409, which says more than a 403 to someone who may see the event.
        if permission is EventAccess.CHECK_EQUIPMENT_AVAILABILITY:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned or Role.TECH_SUPPORT.value in roles:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-80 AC1: only the event's current assigned Coordinator may confirm it,
        # or ask whether it can be. Deliberately not pinned to a status, following
        # CHECK_EQUIPMENT_AVAILABILITY below: outside planning the service answers 409
        # naming that, which tells the assignee more than a bare 403 would.
        # SCRUM-85 AC2: the reminder schedule belongs to the event's current assigned
        # Coordinator, for reading as well as changing — it is their own working
        # arrangement, not a record of the event. A Lead or the owning Organiser gets
        # nothing from those roles alone, and reassignment transfers it at once because
        # the check is against the event's current assignee. No status pin: the service
        # answers for an event outside planning, which says more than a bare 403.
        if permission is EventAccess.MANAGE_REMINDERS:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if permission is EventAccess.CONFIRM_EVENT:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-109 AC6 (ADR-0056): only the event's current assigned Coordinator cancels
        # one of its venue arrangements, so a reassignment moves the right at once. No
        # status pin, for the reason CHECK_EQUIPMENT_AVAILABILITY gives: the service says
        # why an event outside planning is refused, which a 403 could not (AC7, AC9).
        if permission is EventAccess.CANCEL_VENUE_ARRANGEMENT:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-86 AC1: only the current assigned Coordinator completes the event or
        # corrects its closure record. No status pin: the service says why an event that
        # is not Confirmed, or has not ended, is refused.
        if permission is EventAccess.COMPLETE_EVENT:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-86 AC4 (ADR-0059): the owner, the current assignee, any Lead, and venue,
        # technical or safety staff recorded as acting on this event. A past assignment
        # alone gives nothing, because only the current coordinator_id is compared.
        if permission is EventAccess.READ_EVENT_CLOSURE:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            is_staff = bool(roles & _CLOSURE_STAFF_ROLES)
            if may_read_closure(
                is_owner=is_owner,
                is_assigned=is_assigned,
                is_lead=Role.COORDINATOR_LEAD.value in roles,
                is_participating_staff=is_staff
                and viewer_id in event_closures.acted_on_event(db, request.id),
            ):
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-115 AC1: only the owning Organiser asks for their event to be cancelled.
        # No status pin: the service says why an event that is not active is refused.
        if permission is EventAccess.REQUEST_EVENT_CANCELLATION:
            if is_owner:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-115 AC2: only the current assigned Coordinator cancels the event or
        # declines a request, so a reassignment moves the right at once.
        if permission is EventAccess.CANCEL_EVENT:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_assigned:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-115 AC1: the owner, the current assignee and any Lead see the requests.
        if permission is EventAccess.READ_EVENT_CANCELLATION:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if may_read_cancellation(
                is_owner=is_owner,
                is_assigned=is_assigned,
                is_lead=Role.COORDINATOR_LEAD.value in roles,
            ):
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-113: the owner controls intake; the current assigned Coordinator may
        # inspect its state but cannot change it merely by holding that assignment.
        if permission is EventAccess.MANAGE_REGISTRATION:
            if is_owner:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if permission is EventAccess.READ_REGISTRATION_SETTINGS:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_owner or is_assigned:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-114: reviewing attendee submissions belongs to the event owner and the
        # currently assigned Coordinator. Intake state is deliberately irrelevant here:
        # closure prevents new submissions, not review of the existing record.
        if permission is EventAccess.READ_REGISTRATIONS:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if is_owner or is_assigned:
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-79 AC9: the Safety Officer who records decisions, the assigned
        # Coordinator who has to act on one (AC5), and any Lead for oversight. Not the
        # owning Organiser and not an attendee: a decision's comment is an internal
        # operational judgement about an event's arrangements ("the exit route is
        # blocked"), which SCRUM-106 already decided is staff-side rather than something
        # the Organiser reads. No status pin — a decision stays readable afterwards.
        if permission is EventAccess.READ_SAFETY_REVIEWS:
            is_assigned = Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id
            if (
                Role.SAFETY_OFFICER.value in roles
                or Role.COORDINATOR_LEAD.value in roles
                or is_assigned
            ):
                return request
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-112 (ADR-0039): organisation membership grants no view of a peer's
        # request. Peers see only the organisation calendar's fields, through its own
        # route; an Organiser who also holds a staff role falls through to it below.
        if is_owner:
            return request

        if request.status is EventStatus.DRAFT:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # SCRUM-104: an ordinary Coordinator sees only the event currently assigned to
        # them. A Lead keeps allocation visibility for every event, including through a
        # dual Lead+Coordinator account, so the Lead check comes first.
        if Role.COORDINATOR_LEAD.value in roles:
            return request

        if Role.COORDINATOR.value in roles and request.coordinator_id != viewer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        if Role.COORDINATOR.value in roles:
            return request

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return check


def may_read_clarifications(request: EventRequest, roles: set[str], viewer_id: uuid.UUID) -> bool:
    """SCRUM-106: only the event's current assigned Coordinator reads its internal notes.

    The one statement of that rule. READ_CLARIFICATIONS asks it to guard the notes route,
    and the event history (SCRUM-88, ADR-0062) asks it to decide whether to include note
    entries, so the history can never show more or fewer notes than that route allows.
    """
    return Role.COORDINATOR.value in roles and request.coordinator_id == viewer_id


def clarification_visibility(
    user: Annotated[dict[str, object], Depends(get_current_user)],
) -> Callable[[EventRequest], bool]:
    """SCRUM-88: `may_read_clarifications` for the signed-in caller, to apply to an event
    the route has already loaded and authorised, so the request is not loaded twice."""
    roles, viewer_id = _granted_roles(user), _user_id(user)
    return lambda request: may_read_clarifications(request, roles, viewer_id)


def _granted_roles(user: dict[str, object]) -> set[str]:
    # Only string elements count as roles. The claim is ours and signed, but a malformed
    # one (say, `roles: [{}]`) must still be a 403, not a TypeError from set arithmetic.
    claimed = user.get("roles")
    return (
        {role for role in claimed if isinstance(role, str)} if isinstance(claimed, list) else set()
    )


def _user_id(user: dict[str, object]) -> uuid.UUID:
    try:
        return uuid.UUID(str(user["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
