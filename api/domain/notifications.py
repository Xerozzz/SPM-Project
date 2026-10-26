"""Notification vocabulary for the in-app inbox (SCRUM-99).

Pure: no I/O, no ORM imports. The type list is finite and stored as stable string
values; later trigger stories (SCRUM-96, SCRUM-102, SCRUM-95, SCRUM-94) add their
types here without changing the storage shape. See ADR-0022.
"""

from enum import StrEnum


class NotificationType(StrEnum):
    """What triggered a notification. Stored as its lowercase value."""

    # SCRUM-99 seeds the vocabulary with a generic placeholder so the inbox,
    # repository, and API can land before the first business trigger. Trigger
    # stories replace direct use of this with their own specific types.
    GENERAL = "general"
    # SCRUM-108 AC3: the venue hold for one of your events has expired.
    VENUE_HOLD_EXPIRED = "venue_hold_expired"
    # SCRUM-96: an event request was submitted unassigned and needs Lead triage.
    UNASSIGNED_SUBMISSION = "unassigned_submission"
    # SCRUM-102 AC3: the request was assigned or reassigned — the type names which,
    # so a recipient can tell without opening the event.
    COORDINATOR_ASSIGNED = "coordinator_assigned"
    COORDINATOR_REASSIGNED = "coordinator_reassigned"
    # SCRUM-94: the request was approved or rejected — the type names the decision,
    # so the owning organiser can tell without opening the event.
    REQUEST_APPROVED = "request_approved"
    REQUEST_REJECTED = "request_rejected"
    # SCRUM-81 AC4: a venue closure now covers one of your event's arrangements.
    VENUE_CLOSURE_IMPACT = "venue_closure_impact"
    # SCRUM-79 AC5: the Safety Officer decided on your event's plan. The type names
    # the decision, as SCRUM-94's do, so the Coordinator can tell whether the plan is
    # back with them without opening the event.
    SAFETY_APPROVED = "safety_approved"
    SAFETY_REJECTED = "safety_rejected"
    SAFETY_CHANGES_REQUESTED = "safety_changes_requested"
    # SCRUM-49 AC1/AC2: a new Pending venue request needs Venue Staff review. The type
    # names the new-request action, so staff can tell it apart from later revised
    # requests (SCRUM-127) without opening the event.
    VENUE_REQUEST_SUBMITTED = "venue_request_submitted"
    # SCRUM-124 AC1/AC2: a new or changed equipment requirement needs Technical
    # Support review. The type names the review action, so staff can tell it apart
    # from later review/reservation outcomes (SCRUM-125) without opening the event.
    EQUIPMENT_REVIEW_NEEDED = "equipment_review_needed"
    # SCRUM-50: event changes, safety and lifecycle. Each type names the action, and for
    # an event the status it is now in, so a recipient can tell without opening it.
    CHANGE_PROPOSED = "change_proposed"
    CHANGE_APPROVED = "change_approved"
    CHANGE_REJECTED = "change_rejected"
    SAFETY_REVIEW_DUE = "safety_review_due"
    EVENT_CONFIRMED = "event_confirmed"
    EVENT_REPLANNED = "event_replanned"
    EVENT_COMPLETED = "event_completed"
    # SCRUM-42/SCRUM-114: an attendee's own registration lifecycle changed. The
    # type preserves the outcome recorded by the immutable history source action.
    REGISTRATION_PENDING = "registration_pending"
    REGISTRATION_ACCEPTED = "registration_accepted"
    REGISTRATION_WAITLISTED = "registration_waitlisted"
    REGISTRATION_WITHDRAWN = "registration_withdrawn"
    # SCRUM-115: an Organiser asked for their event to be cancelled, the Coordinator
    # declined that, or the event was cancelled.
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLATION_DECLINED = "cancellation_declined"
    EVENT_CANCELLED = "event_cancelled"
    # SCRUM-85 AC5: arrangements for one of your events are still incomplete with the
    # event approaching. Which of them is read live from the event (ADR-0022 keeps
    # presentation out of the row), so a reminder can never name stale work.
    ARRANGEMENTS_INCOMPLETE = "arrangements_incomplete"


class NotificationSource(StrEnum):
    """What business record a notification was raised from. Stored as its value.

    Event ID alone cannot deduplicate: one event receives many clarifications and
    assignment changes. The (source_type, source_id) pair names the exact action —
    e.g. one clarification message, one assignment-history row — so retrying the
    same action collides (idempotent) while distinct actions stay distinct.
    """

    GENERAL = "general"
    # SCRUM-108: one venue booking row, so each expired hold notifies exactly once.
    VENUE_BOOKING = "venue_booking"
    # SCRUM-96: the source is the submission of one event request — the request id
    # is the source_id, so retrying the same submission collides (idempotent) while
    # a later submission of a different request stays distinct.
    EVENT_SUBMISSION = "event_submission"
    # SCRUM-102: one assignment-history row, so retrying the same assignment action
    # collides per recipient while a later reassignment (a new history row) stays
    # distinct. The history row id is the source_id.
    COORDINATOR_ASSIGNMENT = "coordinator_assignment"
    # SCRUM-94: the decision on one event request — the request id is the source_id,
    # so retrying the same decision collides (idempotent). A later decision on the
    # same request (reject, resubmit, reject again) is a new decision with a new
    # decision time, so the source_id carries the decision time to stay distinct.
    EVENT_DECISION = "event_decision"
    # SCRUM-81: one closure period hitting one arrangement. The source_id is a stable
    # key of (closure, period, booking), so re-saving the same closure does not notify
    # twice, while moving it to a new period does (domain.venue_closure_impact).
    VENUE_CLOSURE = "venue_closure"
    # SCRUM-79: one safety decision. Decisions are never updated, only added, so the
    # review row's id is a stable key: the same decision cannot notify twice and a
    # later decision on the same event is a new row and so a new notification.
    SAFETY_REVIEW = "safety_review"
    # SCRUM-85: one configured reminder occurrence. The schedule row is the occurrence,
    # so its id is a stable key: a retry or a second worker collides rather than
    # sending twice, and another lead time on the same event stays distinct.
    EVENT_REMINDER = "event_reminder"
    # SCRUM-49: one new Pending venue request. The booking row's id is the source_id,
    # so retrying the same submission collides per recipient (idempotent) while a
    # later distinct request for the same event stays distinct. SCRUM-127 owns
    # revised requests and uses its own source identity.
    VENUE_REQUEST = "venue_request"
    # SCRUM-124: one add or change of an equipment requirement. The audit row's id is
    # the source_id, so retrying the same change collides per recipient (idempotent)
    # while a later distinct change on the same requirement stays distinct.
    EQUIPMENT_REQUIREMENT_CHANGE = "equipment_requirement_change"
    # SCRUM-50: one change request. Its id is the source_id for the proposal and, as a
    # different source type, for its decision, so each notifies once.
    CHANGE_REQUEST = "change_request"
    CHANGE_DECISION = "change_decision"
    # SCRUM-50: one version of a plan becoming reviewable, keyed by the plan fingerprint,
    # so polling an unchanged plan never notifies again (domain.lifecycle_notifications).
    SAFETY_PLAN = "safety_plan"
    # SCRUM-50: one confirmation, keyed by its time, so a reconfirmation is new news.
    EVENT_CONFIRMATION = "event_confirmation"
    # SCRUM-50: one return to planning, keyed by what caused it.
    EVENT_REPLAN = "event_replan"
    # SCRUM-50: the completion of one event. Completed is terminal, so the event id is
    # the source_id.
    EVENT_COMPLETION = "event_completion"
    # One append-only registration-history row is one source action. This makes a
    # retry collide while a later, distinct status transition stays visible.
    REGISTRATION_STATUS = "registration_status"
    # SCRUM-115: one cancellation request, its id the source_id for the request and, as a
    # different source type, for a decline. The cancellation of an event is terminal, so
    # the event id is the source_id for that.
    CANCELLATION_REQUEST = "cancellation_request"
    CANCELLATION_DECISION = "cancellation_decision"
    EVENT_CANCELLATION = "event_cancellation"
