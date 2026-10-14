"""SCRUM-82 AC1: the venue is the only place a setup or turnaround buffer can be set.

A contract test rather than a behavioural one. It asserts that no booking payload can
express a buffer, which is what makes "a booking cannot override the venue's values"
true by construction instead of by a rule somebody has to remember to apply.
"""

import pytest

from domain.venue import BUFFER_FIELDS, field_names
from schemas.venue_bookings import VenueBookingCreate
from schemas.venues import VenueCreate, VenueRead


@pytest.mark.story("SCRUM-82")
def test_a_booking_request_cannot_name_a_buffer_at_all() -> None:
    # Pydantic ignores unknown keys, so a payload carrying `setup_minutes` is accepted and
    # the value silently dropped. The guarantee is that there is no such field to read.
    assert "venue_id" in VenueBookingCreate.model_fields
    assert not set(BUFFER_FIELDS) & set(VenueBookingCreate.model_fields)


@pytest.mark.story("SCRUM-82")
def test_the_venue_contract_can_both_set_and_report_the_buffers() -> None:
    # AC1 sets them on the venue record; AC2 lets a Coordinator read them back. The route
    # that accepts VenueCreate is Venue Staff only, which test_venue_buffers.py covers.
    assert set(BUFFER_FIELDS) <= set(VenueCreate.model_fields)
    assert set(BUFFER_FIELDS) <= set(VenueRead.model_fields)


@pytest.mark.story("SCRUM-82")
def test_the_buffers_are_part_of_the_venue_record() -> None:
    # services/venues.py copies values across by field_names(), so a buffer missing from
    # the domain dataclass would be silently dropped on create and update.
    assert set(BUFFER_FIELDS) <= set(field_names())
