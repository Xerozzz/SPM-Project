"""Stage private registration-status inbox entries from committed source actions.

The caller supplies the immutable history row it just created and commits the
surrounding registration transaction.  No event-wide or staff routing belongs here.
"""

from core.database import Session
from domain.notifications import NotificationSource, NotificationType
from domain.registration import RegistrationStatus
from models.event_registration import EventRegistration, EventRegistrationHistory
from models.event_request import EventRequest
from repositories import notifications as notifications_repo

_TYPE_FOR_STATUS = {
    RegistrationStatus.PENDING: NotificationType.REGISTRATION_PENDING,
    RegistrationStatus.ACCEPTED: NotificationType.REGISTRATION_ACCEPTED,
    RegistrationStatus.WAITLISTED: NotificationType.REGISTRATION_WAITLISTED,
    RegistrationStatus.WITHDRAWN: NotificationType.REGISTRATION_WITHDRAWN,
}


def status_changed(
    db: Session,
    event: EventRequest,
    registration: EventRegistration,
    action: EventRegistrationHistory,
) -> None:
    """Stage the affected Attendee's notification for one supported history action."""
    notifications_repo.stage(
        db,
        recipient_id=registration.attendee_id,
        event_request_id=event.id,
        type=_TYPE_FOR_STATUS[action.status],
        source_type=NotificationSource.REGISTRATION_STATUS,
        source_id=str(action.id),
        occurred_at=action.occurred_at,
    )
