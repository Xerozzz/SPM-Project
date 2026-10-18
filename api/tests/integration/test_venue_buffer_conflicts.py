"""SCRUM-82 AC3 to AC7: setup and turnaround applied to every rule that asks if a venue
is free, against real PostgreSQL so the repository queries and the overlap constraint are
exercised rather than just the domain rule.

Every test uses the same arrangement: a venue with 30 minutes setup and 45 minutes
turnaround, and a confirmed booking from 10:00 to 12:00 UTC, which therefore occupies the
venue from 09:30 to 12:45. The interesting periods are the ones that clash *only* because
of the buffers, since those are what this story changes.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain.booking_conflict import BookingConflictError, VenueUnavailableError
from domain.venue_booking import BookingStatus
from domain.venue_buffer import VenueBuffers, bookings_clash
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_unavailability import VenueUnavailability
from services import venue_bookings as booking_service
from services import venue_calendar as calendar_service
from services import venue_search as search_service
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_search import effective_for, make_venue

_SETUP, _TURNAROUND = 30, 45
_DAY = datetime(2030, 3, 4, tzinfo=UTC)
_MINUTE = timedelta(minutes=1)


def at(hours: float) -> datetime:
    return _DAY + timedelta(hours=hours)


def buffered_venue(db: Session, **overrides: object) -> Venue:
    """The venue from this module's docstring: 30 minutes setup, 45 turnaround."""
    values: dict[str, object] = {"setup_minutes": _SETUP, "turnaround_minutes": _TURNAROUND}
    values.update(overrides)
    return make_venue(db, **values)


def booking_for(
    db: Session,
    coordinator: User,
    venue: Venue,
    start_at: datetime,
    end_at: datetime,
    status: BookingStatus = BookingStatus.CONFIRMED,
) -> VenueBooking:
    event = approved_event(db, coordinator, coordinator, start_at=start_at, end_at=end_at)
    effective_start, effective_end = effective_for(venue, start_at, end_at)
    booking = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        start_at=start_at,
        end_at=end_at,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=status,
    )
    db.add(booking)
    db.flush()
    return booking


def closure_for(db: Session, venue: Venue, starts_at: datetime, ends_at: datetime) -> None:
    db.add(
        VenueUnavailability(
            venue_id=venue.id, starts_at=starts_at, ends_at=ends_at, reason="Maintenance"
        )
    )
    db.flush()


# --------------------------------------------------- AC3, what gets stored on submit


@pytest.mark.story("SCRUM-82")
async def test_submitting_stores_the_effective_interval(db: Session, make_user: MakeUser) -> None:
    # AC3, the worked example: a 10:00 to 12:00 event at this venue occupies 09:30 to 12:45.
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    event = approved_event(db, coordinator, coordinator, start_at=at(10), end_at=at(12))

    booking, _ = booking_service.submit(db, event, venue.id, datetime.now(UTC))

    assert booking.effective_start_at == at(9.5)
    assert booking.effective_end_at == at(12.75)


@pytest.mark.story("SCRUM-82")
async def test_a_venue_without_buffers_stores_the_event_period(
    db: Session, make_user: MakeUser
) -> None:
    # AC7: no buffers, so the occupied interval is the event period and nothing changes.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    event = approved_event(db, coordinator, coordinator, start_at=at(10), end_at=at(12))

    booking, _ = booking_service.submit(db, event, venue.id, datetime.now(UTC))

    assert (booking.effective_start_at, booking.effective_end_at) == (at(10), at(12))


# ------------------------------------------- AC4 and AC6, conflict detection


@pytest.mark.story("SCRUM-82")
async def test_a_back_to_back_request_is_refused_once_the_venue_needs_turnaround(
    db: Session, make_user: MakeUser
) -> None:
    # The behaviour the story exists for. 12:00 to 13:00 straight after a 10:00 to 12:00
    # booking does not overlap on event times, but the first event's reset and the
    # second's setup do, so approval must be refused and the clash named (AC4, AC6).
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    confirmed = booking_for(db, coordinator, venue, at(10), at(12))
    request = booking_for(db, coordinator, venue, at(12), at(13), BookingStatus.PENDING)

    with pytest.raises(BookingConflictError) as refusal:
        booking_service.check_approvable(db, request.id)

    assert str(confirmed.id) in str(refusal.value)


@pytest.mark.story("SCRUM-82")
async def test_the_same_request_is_approvable_when_the_venue_has_no_buffers(
    db: Session, make_user: MakeUser
) -> None:
    # AC7, the other half of the test above: identical arrangement, no buffers, allowed.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    booking_for(db, coordinator, venue, at(10), at(12))
    request = booking_for(db, coordinator, venue, at(12), at(13), BookingStatus.PENDING)

    assert booking_service.check_approvable(db, request.id) is not None


@pytest.mark.story("SCRUM-82")
@pytest.mark.parametrize(
    ("request_start", "is_refused"),
    [
        (at(13.25) - _MINUTE, True),
        (at(13.25), False),
        (at(13.25) + _MINUTE, False),
    ],
)
async def test_effective_intervals_that_only_touch_do_not_clash(
    db: Session, make_user: MakeUser, request_start: datetime, is_refused: bool
) -> None:
    # AC6 at the boundary. The confirmed booking occupies until 12:45; a request starting
    # at 13:15 has its setup begin exactly then, which is not an overlap (half-open).
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    booking_for(db, coordinator, venue, at(10), at(12))
    request = booking_for(
        db,
        coordinator,
        venue,
        request_start,
        request_start + timedelta(hours=1),
        BookingStatus.PENDING,
    )

    if is_refused:
        with pytest.raises(BookingConflictError):
            booking_service.check_approvable(db, request.id)
    else:
        assert booking_service.check_approvable(db, request.id) is not None


# --------------------------------------------------------------- AC5, closures


@pytest.mark.story("SCRUM-82")
async def test_setup_running_into_a_closure_is_refused(db: Session, make_user: MakeUser) -> None:
    # AC5: the request's own setup starts at 09:30, and the closure runs to 09:31.
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    closure_for(db, venue, at(9), at(9.5) + _MINUTE)
    request = booking_for(db, coordinator, venue, at(10), at(12), BookingStatus.PENDING)

    with pytest.raises(VenueUnavailableError):
        booking_service.check_approvable(db, request.id)


@pytest.mark.story("SCRUM-82")
async def test_a_closure_ending_exactly_when_setup_begins_does_not_clash(
    db: Session, make_user: MakeUser
) -> None:
    # AC5 with the half-open rule, and the asymmetry: the closure is not itself widened,
    # so a closure ending at 09:30 leaves the 09:30 setup clear.
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    closure_for(db, venue, at(8), at(9.5))
    request = booking_for(db, coordinator, venue, at(10), at(12), BookingStatus.PENDING)

    assert booking_service.check_approvable(db, request.id) is not None


# ------------------------------------------------------ AC4, search and availability


@pytest.mark.story("SCRUM-82")
async def test_search_excludes_a_venue_that_only_clashes_through_buffers(
    db: Session, make_user: MakeUser
) -> None:
    # AC4: searching for 12:00 to 13:00 must not offer this venue, because a booking made
    # for that period could not then be approved.
    venue = buffered_venue(db)
    booking_for(db, make_user("coordinator"), venue, at(10), at(12))

    found = search_service.search(db, at(12), at(13))

    assert venue.id not in {match.id for match in found}


@pytest.mark.story("SCRUM-82")
async def test_search_offers_the_venue_once_the_buffers_are_clear(
    db: Session, make_user: MakeUser
) -> None:
    # The same search 15 minutes later: setup now begins exactly when turnaround ends.
    venue = buffered_venue(db)
    booking_for(db, make_user("coordinator"), venue, at(10), at(12))

    found = search_service.search(db, at(13.25), at(14))

    assert venue.id in {match.id for match in found}


@pytest.mark.story("SCRUM-82")
async def test_search_excludes_a_venue_whose_setup_would_run_into_a_closure(
    db: Session, make_user: MakeUser
) -> None:
    # AC4 and AC5 together, on the search path rather than the approval path.
    venue = buffered_venue(db)
    closure_for(db, venue, at(9), at(9.5) + _MINUTE)

    found = search_service.search(db, at(10), at(12))

    assert venue.id not in {match.id for match in found}


@pytest.mark.story("SCRUM-82")
async def test_the_availability_check_reports_a_buffer_clash_as_unavailable(
    db: Session, make_user: MakeUser
) -> None:
    # AC4: SCRUM-76's verdict for 12:00 to 13:00, which clashes only through buffers.
    venue = buffered_venue(db)
    booking_for(db, make_user("coordinator"), venue, at(10), at(12))

    result = calendar_service.availability(db, venue.id, at(12), at(13))

    assert result.available is False
    # The booking behind the answer is reported even though its event period sits outside
    # the period asked about, so an unavailable venue is never unexplained.
    assert [entry.kind for entry in result.entries] == ["booking"]


@pytest.mark.story("SCRUM-82")
async def test_the_availability_check_is_unchanged_without_buffers(
    db: Session, make_user: MakeUser
) -> None:
    # AC7: the same question against a venue with no buffers still answers free.
    venue = make_venue(db)
    booking_for(db, make_user("coordinator"), venue, at(10), at(12))

    assert calendar_service.availability(db, venue.id, at(12), at(13)).available is True


@pytest.mark.story("SCRUM-82")
async def test_the_calendar_lists_a_booking_whose_buffer_reaches_into_the_window(
    db: Session, make_user: MakeUser
) -> None:
    # AC4: a window of 12:30 to 12:40 contains no event, but the venue is occupied by the
    # 10:00 to 12:00 booking's turnaround, so the calendar has to show it.
    venue = buffered_venue(db)
    confirmed = booking_for(db, make_user("coordinator"), venue, at(10), at(12))

    listed = calendar_service.entries(db, at(12.5), at(12.65), venue.id)

    assert [entry.id for entry in listed] == [confirmed.id]


@pytest.mark.story("SCRUM-82")
async def test_a_calendar_entry_reports_both_the_event_and_the_held_period(
    db: Session, make_user: MakeUser
) -> None:
    """AC4: the entry carries the effective interval alongside the event's own times.

    Both are needed: the calendar now lists a booking whose setup or reset reaches into
    the window while its event sits outside it, so showing only the event times would
    leave the entry unexplained.
    """
    venue = buffered_venue(db)
    booking_for(db, make_user("coordinator"), venue, at(10), at(12))

    entry = calendar_service.entries(db, at(9), at(13), venue.id)[0]

    assert (entry.start_at, entry.end_at) == (at(10), at(12))
    assert (entry.effective_start_at, entry.effective_end_at) == (at(9.5), at(12.75))


@pytest.mark.story("SCRUM-82")
async def test_a_closure_entry_is_held_for_exactly_its_own_period(
    db: Session, make_user: MakeUser
) -> None:
    # AC5's asymmetry, visible in the calendar: a closure is never widened.
    venue = buffered_venue(db)
    closure_for(db, venue, at(10), at(12))

    entry = calendar_service.entries(db, at(9), at(13), venue.id)[0]

    assert (entry.effective_start_at, entry.effective_end_at) == (at(10), at(12))


@pytest.mark.story("SCRUM-82")
async def test_an_entry_at_a_venue_without_buffers_is_held_for_its_event_period(
    db: Session, make_user: MakeUser
) -> None:
    # AC7: the frontend hides the held-period line when these match, so this is what
    # keeps the common case uncluttered.
    venue = make_venue(db)
    booking_for(db, make_user("coordinator"), venue, at(10), at(12))

    entry = calendar_service.entries(db, at(9), at(13), venue.id)[0]

    assert (entry.effective_start_at, entry.effective_end_at) == (entry.start_at, entry.end_at)


@pytest.mark.story("SCRUM-82")
async def test_the_calendar_leaves_out_a_booking_whose_buffer_clears_the_window(
    db: Session, make_user: MakeUser
) -> None:
    # Just after turnaround ends at 12:45, so nothing holds the venue.
    venue = buffered_venue(db)
    booking_for(db, make_user("coordinator"), venue, at(10), at(12))

    assert calendar_service.entries(db, at(12.75), at(13), venue.id) == []


# -------------------------------------------- AC4, the concurrent-approval safeguard


@pytest.mark.story("SCRUM-82")
async def test_the_database_refuses_two_confirmed_bookings_that_clash_through_buffers(
    db: Session, make_user: MakeUser
) -> None:
    """AC4: the constraint is measured on effective intervals, not event times.

    Written against the database directly rather than through the service, because the
    point is that the guarantee holds for any code path, including one that skips the
    application check (ADR-0002, ADR-0019).
    """
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    booking_for(db, coordinator, venue, at(10), at(12))

    with pytest.raises(IntegrityError):
        # Event periods are adjacent and would have been allowed before SCRUM-82.
        booking_for(db, coordinator, venue, at(12), at(13))


@pytest.mark.story("SCRUM-82")
async def test_approving_refreshes_the_stored_interval_from_the_current_buffers(
    db: Session, make_user: MakeUser
) -> None:
    """ADR-0019: the snapshot is rewritten on approval, because buffers may have changed.

    Without this, a request submitted when the venue had no buffers would be confirmed
    with its event period as the occupied one, and the constraint would then guarantee
    the wrong thing.
    """
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    request = booking_for(db, coordinator, venue, at(10), at(12), BookingStatus.PENDING)
    assert request.effective_start_at == at(10)

    venue.setup_minutes, venue.turnaround_minutes = _SETUP, _TURNAROUND
    db.flush()
    # decided_by_id has a foreign key to users, so it cannot be an arbitrary uuid.
    staff = make_user("venue_staff")
    approved = booking_service.approve(db, request.id, staff.id, datetime.now(UTC))

    assert (approved.effective_start_at, approved.effective_end_at) == (at(9.5), at(12.75))


@pytest.mark.story("SCRUM-82")
async def test_a_buffer_change_never_writes_to_a_booking(db: Session, make_user: MakeUser) -> None:
    """ADR-0019 and SCRUM-89 AC5: raising a buffer leaves confirmed bookings untouched.

    The stored snapshot deliberately goes stale. What must not happen is the change being
    refused or a booking row being rewritten, because SCRUM-89 needs the problematic state
    to exist in order to flag it.
    """
    venue = buffered_venue(db, setup_minutes=0, turnaround_minutes=0)
    coordinator = make_user("coordinator")
    first = booking_for(db, coordinator, venue, at(10), at(12))
    second = booking_for(db, coordinator, venue, at(12), at(13))

    venue.setup_minutes, venue.turnaround_minutes = _SETUP, _TURNAROUND
    db.flush()

    db.refresh(first)
    db.refresh(second)
    assert (first.effective_start_at, first.effective_end_at) == (at(10), at(12))
    assert (second.effective_start_at, second.effective_end_at) == (at(12), at(13))
    # And the live rule now sees the clash that the stale snapshots do not, which is
    # exactly what SCRUM-89 will report. Nothing here refuses the buffer change.
    buffers = VenueBuffers(setup_minutes=_SETUP, turnaround_minutes=_TURNAROUND)
    assert bookings_clash(first.start_at, first.end_at, second.start_at, second.end_at, buffers)


# ------------------------------------- what Venue Staff are actually told (AC3, AC4)
#
# Reported from testing SCRUM-82: a request was refused for clashing with a booking
# whose quoted period did not overlap it. The rule was right; the explanation quoted the
# event period, and the buffers that caused the clash appeared nowhere. Someone deciding
# on a request cannot act on a reason that contradicts itself, so the payload behind that
# screen has to carry the period the venue is actually held for.


@pytest.mark.story("SCRUM-82")
async def test_the_decision_queue_reports_the_held_period_and_the_buffers(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    booking = booking_for(db, coordinator, venue, at(10), at(12), status=BookingStatus.PENDING)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venue-bookings")

    assert response.status_code == 200, response.text
    row = next(r for r in response.json() if r["id"] == str(booking.id))
    assert row["setup_minutes"] == _SETUP
    assert row["turnaround_minutes"] == _TURNAROUND
    assert row["effective_start_at"] == at(9.5).isoformat().replace("+00:00", "Z")
    assert row["effective_end_at"] == at(12.75).isoformat().replace("+00:00", "Z")


@pytest.mark.story("SCRUM-82")
async def test_a_clash_names_the_held_period_of_the_booking_in_the_way(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """The reported case: the two events are back to back and still clash.

    10:00-12:00 is confirmed; 12:44-14:00 is requested. Neither period overlaps the
    other, so the conflict is only explicable through the first booking's 45 minutes of
    turnaround. The payload has to say 12:45, not 12:00.
    """
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    confirmed = booking_for(db, coordinator, venue, at(10), at(12))
    requested = booking_for(
        db, coordinator, venue, at(12.75) - _MINUTE, at(14), status=BookingStatus.PENDING
    )

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venue-bookings")

    row = next(r for r in response.json() if r["id"] == str(requested.id))
    conflict = row["conflict"]
    assert conflict is not None, "the clash itself is SCRUM-73; this test is about reporting it"
    assert conflict["id"] == str(confirmed.id)
    # The event period, unchanged: 10:00 to 12:00.
    assert conflict["start_at"] == at(10).isoformat().replace("+00:00", "Z")
    assert conflict["end_at"] == at(12).isoformat().replace("+00:00", "Z")
    # The part that was missing: when the venue stops being held.
    assert conflict["effective_end_at"] == at(12.75).isoformat().replace("+00:00", "Z")
    assert conflict["effective_start_at"] == at(9.5).isoformat().replace("+00:00", "Z")


@pytest.mark.story("SCRUM-82")
async def test_a_closure_is_reported_at_its_own_width(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC5: a closure is never widened, so the two pairs agree and nothing implies the
    # closure was stretched to meet the booking.
    venue = buffered_venue(db)
    coordinator = make_user("coordinator")
    closure_for(db, venue, at(8), at(9))
    # 09:15 less 30 minutes of setup is 08:45, inside the closure. At 09:30 the setup
    # would touch 09:00 exactly, which is not an overlap.
    requested = booking_for(db, coordinator, venue, at(9.25), at(11), status=BookingStatus.PENDING)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venue-bookings")

    conflict = next(r for r in response.json() if r["id"] == str(requested.id))["conflict"]
    assert conflict["kind"] == "unavailability"
    assert (
        conflict["effective_start_at"]
        == conflict["start_at"]
        == at(8).isoformat().replace("+00:00", "Z")
    )
    assert (
        conflict["effective_end_at"]
        == conflict["end_at"]
        == at(9).isoformat().replace("+00:00", "Z")
    )


@pytest.mark.story("SCRUM-82")
async def test_the_held_period_follows_the_venue_not_the_stored_snapshot(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """ADR-0019: the stored effective columns are a snapshot and may be stale.

    They are written when a booking is submitted, approved or held, and a later buffer
    change deliberately does not rewrite them. The clash shown beside them is computed
    from the venue as it is now, so what the screen calls the held period has to be too,
    or one card contradicts itself for exactly the bookings SCRUM-89 exists to flag.
    """
    venue = buffered_venue(db, setup_minutes=0, turnaround_minutes=0)
    coordinator = make_user("coordinator")
    booking = booking_for(db, coordinator, venue, at(10), at(12), status=BookingStatus.PENDING)
    assert (booking.effective_start_at, booking.effective_end_at) == (at(10), at(12))

    venue.setup_minutes, venue.turnaround_minutes = _SETUP, _TURNAROUND
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.get(
            f"/api/event-requests/{booking.event_request_id}/venue-bookings"
        )

    assert response.status_code == 200, response.text
    row = next(r for r in response.json() if r["id"] == str(booking.id))
    assert row["effective_start_at"] == at(9.5).isoformat().replace("+00:00", "Z")
    assert row["effective_end_at"] == at(12.75).isoformat().replace("+00:00", "Z")
    # The row itself is untouched, which is the state SCRUM-89 reports on.
    db.refresh(booking)
    assert (booking.effective_start_at, booking.effective_end_at) == (at(10), at(12))
