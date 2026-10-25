"""SQLAlchemy ORM models. Every change here ships with an Alembic migration.

Every model module is re-exported from this package, and alembic/env.py imports the
package. That is what puts a new table into `Base.metadata` and therefore into
`alembic revision --autogenerate` — a model that nothing imports is invisible to it.

Add each new model here as you write it:

    from models.user import User as User
"""

from core.database import Base as Base
from models.equipment import Equipment as Equipment
from models.equipment_requirement_change import (
    EquipmentRequirementChange as EquipmentRequirementChange,
)
from models.equipment_reservation import EquipmentReservation as EquipmentReservation
from models.event_cancellation_request import (
    EventCancellationRequest as EventCancellationRequest,
)
from models.event_change_request import EventChangeItem as EventChangeItem
from models.event_change_request import EventChangeRequest as EventChangeRequest
from models.event_clarification import EventClarification as EventClarification
from models.event_closure_note import EventClosureNote as EventClosureNote
from models.event_coordinator_assignment import (
    EventCoordinatorAssignment as EventCoordinatorAssignment,
)
from models.event_equipment_requirement import (
    EventEquipmentRequirement as EventEquipmentRequirement,
)
from models.event_registration import EventRegistration as EventRegistration
from models.event_registration import EventRegistrationHistory as EventRegistrationHistory
from models.event_request import EventRequest as EventRequest
from models.notification import Notification as Notification
from models.organisation import Organisation as Organisation
from models.safety_review import SafetyReview as SafetyReview
from models.user import User as User
from models.venue import Venue as Venue
from models.venue_booking import VenueBooking as VenueBooking
from models.venue_buffer_change import VenueBufferChange as VenueBufferChange
from models.venue_closure_impact import VenueClosureImpact as VenueClosureImpact
from models.venue_unavailability import VenueUnavailability as VenueUnavailability
