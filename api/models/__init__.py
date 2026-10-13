"""SQLAlchemy ORM models. Every change here ships with an Alembic migration.

Every model module is re-exported from this package, and alembic/env.py imports the
package. That is what puts a new table into `Base.metadata` and therefore into
`alembic revision --autogenerate` — a model that nothing imports is invisible to it.

Add each new model here as you write it:

    from models.user import User as User
"""

from core.database import Base as Base
from models.equipment import Equipment as Equipment
from models.event_clarification import EventClarification as EventClarification
from models.event_coordinator_assignment import (
    EventCoordinatorAssignment as EventCoordinatorAssignment,
)
from models.event_request import EventRequest as EventRequest
from models.notification import Notification as Notification
from models.organisation import Organisation as Organisation
from models.user import User as User
from models.venue import Venue as Venue
from models.venue_booking import VenueBooking as VenueBooking
from models.venue_buffer_change import VenueBufferChange as VenueBufferChange
from models.venue_unavailability import VenueUnavailability as VenueUnavailability
