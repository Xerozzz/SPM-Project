"""SCRUM-89: changing a venue's buffers identifies the bookings it caught out.

Against real PostgreSQL, so the audit row and the queries behind the review are exercised
rather than just the pure rule. The arrangement throughout is one venue with no buffers
and two back-to-back confirmed bookings, 10:00 to 12:00 and 12:00 to 13:00, which are
compatible until the venue needs any turnaround.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.venue_booking import BookingStatus
from models.user import User
from models.venue import Venue
from models.venue_booking import VenueBooking
from models.venue_buffer_change import VenueBufferChange
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_buffer_conflicts import at, booking_for, closure_for
from tests.integration.test_venue_search import effective_for, make_venue

_SETUP, _TURNAROUND = 30, 45


def _every_column(booking: VenueBooking) -> dict[str, object]:
    """Every stored value on a booking, so AC5 is checked against the whole row.

    Derived from the table rather than listed, so a column added later is compared too
    instead of quietly falling outside the assertion.
    """
    return {c.name: getattr(booking, c.name) for c in VenueBooking.__table__.columns}


def audit_rows(db: Session) -> list[VenueBufferChange]:
    return list(db.scalars(select(VenueBufferChange).order_by(VenueBufferChange.changed_at)))


def flagged(response: httpx.Response) -> list[str]:
    problems: list[dict[str, object]] = response.json()["buffer_change"]["problems"]
    return [str(problem["booking_id"]) for problem in problems]


def back_to_back(db: Session, coordinator: User, venue: Venue) -> tuple[VenueBooking, VenueBooking]:
    """Two confirmed bookings that only clash once the venue needs turnaround."""
    first = booking_for(db, coordinator, venue, at(10), at(12))
    second = booking_for(db, coordinator, venue, at(12), at(13))
    return first, second


# --------------------------------------------------------------- AC1, AC2 and AC3


@pytest.mark.story("SCRUM-89")
async def test_raising_a_buffer_identifies_the_bookings_it_caught_out(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    first, second = back_to_back(db, make_user("coordinator"), venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND}
        )

    assert response.status_code == 200, response.text
    assert response.json()["buffer_change"]["changed"] is True
    assert sorted(flagged(response)) == sorted([str(first.id), str(second.id)])


@pytest.mark.story("SCRUM-89")
async def test_each_flagged_booking_says_what_it_now_clashes_with(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC3: a Coordinator cannot act on "this is a problem" without knowing what with.
    venue = make_venue(db)
    first, second = back_to_back(db, make_user("coordinator"), venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND}
        )

    by_id = {
        str(problem["booking_id"]): problem
        for problem in response.json()["buffer_change"]["problems"]
    }
    assert by_id[str(first.id)]["conflict"]["id"] == str(second.id)
    assert by_id[str(second.id)]["conflict"]["id"] == str(first.id)
    assert by_id[str(first.id)]["conflict"]["kind"] == "booking"


@pytest.mark.story("SCRUM-89")
async def test_a_buffer_that_reaches_a_closure_is_identified(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC2's other half. Setup would begin 09:30 and the venue is shut until 09:36.
    venue = make_venue(db)
    booking = booking_for(db, make_user("coordinator"), venue, at(10), at(12))
    closure_for(db, venue, at(9), at(9.6))

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(f"/api/venues/{venue.id}", json={"setup_minutes": _SETUP})

    assert flagged(response) == [str(booking.id)]
    problem = response.json()["buffer_change"]["problems"][0]
    assert problem["conflict"]["kind"] == "unavailability"


@pytest.mark.story("SCRUM-89")
async def test_a_past_booking_is_not_identified(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC1 says future bookings. Nothing can be done about a venue that was occupied last
    # year, so flagging it would be noise the Coordinator cannot act on.
    venue = make_venue(db)
    gone = datetime.now(UTC) - timedelta(days=30)
    booking_for(db, make_user("coordinator"), venue, gone, gone + timedelta(hours=2))
    booking_for(
        db, make_user("coordinator"), venue, gone + timedelta(hours=2), gone + timedelta(hours=3)
    )

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND}
        )

    assert response.json()["buffer_change"]["problems"] == []


@pytest.mark.story("SCRUM-89")
async def test_a_pending_request_is_not_identified(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC1 says confirmed bookings. A pending request holds nothing, so it cannot be
    # caught out by a buffer change; approving it is where the check belongs (SCRUM-74).
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    booking_for(db, coordinator, venue, at(10), at(12))
    booking_for(db, coordinator, venue, at(12), at(13), BookingStatus.PENDING)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND}
        )

    assert response.json()["buffer_change"]["problems"] == []


# --------------------------------------------------------------------------- AC5


@pytest.mark.story("SCRUM-89")
async def test_the_change_is_saved_and_no_booking_is_touched(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC5: identifying a problem must never resolve it by rewriting a booking, and the
    # buffer change itself is never refused because of one.
    venue = make_venue(db)
    first, second = back_to_back(db, make_user("coordinator"), venue)
    before = [_every_column(b) for b in (first, second)]

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND}
        )

    assert response.status_code == 200, response.text
    assert response.json()["turnaround_minutes"] == _TURNAROUND
    db.expire_all()
    reloaded = [db.get(VenueBooking, first.id), db.get(VenueBooking, second.id)]
    assert all(b is not None for b in reloaded)
    assert [_every_column(b) for b in reloaded if b is not None] == before


# --------------------------------------------------------------------------- AC6


@pytest.mark.story("SCRUM-89")
async def test_a_buffer_change_that_affects_nothing_says_so(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC6: the buffers moved, and Venue Staff are told explicitly that nothing was hit.
    venue = make_venue(db)
    booking_for(db, make_user("coordinator"), venue, at(10), at(12))

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(f"/api/venues/{venue.id}", json={"setup_minutes": 5})

    assert response.json()["buffer_change"] == {"changed": True, "problems": []}


@pytest.mark.story("SCRUM-89")
async def test_a_save_that_leaves_the_buffers_alone_is_not_a_buffer_change(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # Different from the case above: renaming a venue is not a buffer change, so there is
    # nothing to report and nothing to record.
    venue = make_venue(db, setup_minutes=_SETUP, turnaround_minutes=_TURNAROUND)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(f"/api/venues/{venue.id}", json={"location": "Level 4"})

    assert response.json()["buffer_change"] == {"changed": False, "problems": []}
    assert audit_rows(db) == []


# --------------------------------------------------------------------------- AC7


@pytest.mark.story("SCRUM-89")
async def test_reducing_a_buffer_clears_what_it_had_identified(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC7: nothing has to clear a marker, because the answer is recomputed each time.
    #
    # The venue starts with no buffers, which is not incidental: the overlap constraint
    # from ADR-0019 refuses two confirmed bookings that already overlap, so a venue whose
    # buffers are high enough to clash cannot have these two bookings created on it. They
    # can only come about the way this story describes, by the buffers growing afterwards.
    venue = make_venue(db)
    back_to_back(db, make_user("coordinator"), venue)

    async with make_client(make_user("venue_staff")) as client:
        raised = await client.patch(f"/api/venues/{venue.id}", json={"turnaround_minutes": 60})
        lowered = await client.patch(f"/api/venues/{venue.id}", json={"turnaround_minutes": 0})

    assert len(raised.json()["buffer_change"]["problems"]) == 2
    assert lowered.json()["buffer_change"]["problems"] == []


# --------------------------------------------------------------------------- AC8


@pytest.mark.story("SCRUM-89")
async def test_the_change_is_recorded_with_the_actor_and_both_values(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    first, second = back_to_back(db, make_user("coordinator"), venue)
    # The 10 minutes has to be set after the bookings exist, for the reason in
    # test_reducing_a_buffer_clears_what_it_had_identified: they could not be created on a
    # venue that already held them apart. Set on the model rather than through the API so
    # this arrangement does not itself produce an audit row for the test to filter out.
    venue.setup_minutes = 10
    db.flush()
    staff = make_user("venue_staff")
    before = datetime.now(UTC)

    async with make_client(staff) as client:
        await client.patch(f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND})

    rows = audit_rows(db)
    assert len(rows) == 1
    assert rows[0].venue_id == venue.id
    assert rows[0].changed_by_id == staff.id
    assert (rows[0].old_setup_minutes, rows[0].old_turnaround_minutes) == (10, 0)
    assert (rows[0].new_setup_minutes, rows[0].new_turnaround_minutes) == (10, _TURNAROUND)
    assert sorted(rows[0].flagged_booking_ids) == sorted([first.id, second.id])
    assert before <= rows[0].changed_at <= datetime.now(UTC)


@pytest.mark.story("SCRUM-89")
async def test_a_refused_change_records_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # An invalid change saves nothing at all, including no audit row. Note this refusal
    # happens in validation, before the review runs, so it does not by itself prove the
    # audit row and the venue share a commit. That property comes from `record_change`
    # only calling `db.add`, with the single commit in `repositories.venues.save`.
    venue = make_venue(db)
    back_to_back(db, make_user("coordinator"), venue)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}",
            json={"turnaround_minutes": _TURNAROUND, "maximum_capacity": -1},
        )

    assert response.status_code == 422
    db.expire_all()
    assert audit_rows(db) == []
    stored = db.get(Venue, venue.id)
    assert stored is not None
    assert stored.turnaround_minutes == 0


@pytest.mark.story("SCRUM-89")
async def test_each_change_adds_its_own_record(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC8 is a history, not a current state: lowering a buffer does not erase the record
    # of having raised it.
    venue = make_venue(db)

    async with make_client(make_user("venue_staff")) as client:
        await client.patch(f"/api/venues/{venue.id}", json={"setup_minutes": 30})
        await client.patch(f"/api/venues/{venue.id}", json={"setup_minutes": 0})

    rows = audit_rows(db)
    assert [(r.old_setup_minutes, r.new_setup_minutes) for r in rows] == [(0, 30), (30, 0)]


# --------------------------------------------------------------------- authorisation


@pytest.mark.story("SCRUM-89")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "attendee"])
async def test_only_venue_staff_can_trigger_a_review(
    db: Session, make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    # The review rides on the venue PATCH, which SCRUM-82 AC2 already restricts.
    venue = make_venue(db)

    async with make_client(make_user(role)) as client:
        response = await client.patch(f"/api/venues/{venue.id}", json={"setup_minutes": 30})

    assert response.status_code == 403
    assert audit_rows(db) == []


@pytest.mark.story("SCRUM-89")
async def test_bookings_at_another_venue_are_not_reviewed(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    other = make_venue(db, name="Hall B")
    back_to_back(db, make_user("coordinator"), other)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND}
        )

    assert response.json()["buffer_change"]["problems"] == []
    assert uuid.UUID(response.json()["id"]) == venue.id


# --------------------------------------------------------------------------- AC4


@pytest.mark.story("SCRUM-89")
async def test_venue_staff_see_every_booking_needing_attention(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    first, second = back_to_back(db, make_user("coordinator"), venue)
    venue.turnaround_minutes = _TURNAROUND
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venues/booking-problems")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["venue_id"] == str(venue.id)
    assert body[0]["turnaround_minutes"] == _TURNAROUND
    assert sorted(p["booking_id"] for p in body[0]["problems"]) == sorted(
        [str(first.id), str(second.id)]
    )


@pytest.mark.story("SCRUM-89")
async def test_a_venue_with_nothing_wrong_is_left_out(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # An empty list means nothing anywhere needs attention, not that no venues exist.
    make_venue(db)
    booking_for(db, make_user("coordinator"), make_venue(db, name="Hall B"), at(10), at(12))

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venues/booking-problems")

    assert response.json() == []


@pytest.mark.story("SCRUM-89")
async def test_a_deactivated_venue_still_reports_its_problems(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # A venue retired under ADR-0012 keeps the bookings already made for it, and those are
    # the ones nobody is watching, so leaving them out would hide the worst cases.
    venue = make_venue(db)
    back_to_back(db, make_user("coordinator"), venue)
    venue.turnaround_minutes = _TURNAROUND
    venue.is_active = False
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venues/booking-problems")

    assert [entry["venue_id"] for entry in response.json()] == [str(venue.id)]
    assert response.json()[0]["is_active"] is False


@pytest.mark.story("SCRUM-89")
@pytest.mark.parametrize("role", ["coordinator", "organiser", "attendee"])
async def test_only_venue_staff_may_list_booking_problems(
    make_user: MakeUser, make_client: MakeClient, role: str
) -> None:
    async with make_client(make_user(role)) as client:
        response = await client.get("/api/venues/booking-problems")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-89")
async def test_the_assigned_coordinator_sees_the_marker_on_their_own_event(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC4's other half: the Coordinator who has to act finds out on the event they own,
    # without being sent to a Venue Staff screen they cannot see.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    first, second = back_to_back(db, coordinator, venue)
    venue.turnaround_minutes = _TURNAROUND
    db.flush()

    async with make_client(coordinator) as client:
        response = await client.get(f"/api/event-requests/{first.event_request_id}/venue-bookings")

    assert response.status_code == 200, response.text
    booking = next(b for b in response.json() if b["id"] == str(first.id))
    assert booking["conflict"] is not None
    assert booking["conflict"]["id"] == str(second.id)


@pytest.mark.story("SCRUM-89")
async def test_a_booking_with_nothing_wrong_carries_no_marker(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    booking = booking_for(db, coordinator, venue, at(10), at(12))

    async with make_client(coordinator) as client:
        response = await client.get(
            f"/api/event-requests/{booking.event_request_id}/venue-bookings"
        )

    assert [b["conflict"] for b in response.json()] == [None]


@pytest.mark.story("SCRUM-89")
async def test_lowering_the_buffer_removes_the_marker_the_coordinator_sees(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC7 through the read surface rather than the save response: nothing cleared the
    # marker, the question simply has a different answer now.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    first, _ = back_to_back(db, coordinator, venue)
    venue.turnaround_minutes = _TURNAROUND
    db.flush()
    url = f"/api/event-requests/{first.event_request_id}/venue-bookings"

    async with make_client(coordinator) as client:
        flagged_now = await client.get(url)
        venue.turnaround_minutes = 0
        db.flush()
        cleared = await client.get(url)

    assert next(b for b in flagged_now.json() if b["id"] == str(first.id))["conflict"] is not None
    assert next(b for b in cleared.json() if b["id"] == str(first.id))["conflict"] is None


# ------------------------------------------------- the live-turnaround boundary


@pytest.mark.story("SCRUM-89")
async def test_a_booking_whose_turnaround_is_still_running_still_blocks_the_next_one(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """The review cuts on the effective end, not the event's end.

    Found in review. An event that finished minutes ago still holds the venue while its
    turnaround runs, so leaving it out made a genuinely unapprovable booking look fine.
    Cutting on `end_at` alone passed every other test in this file, because they all use
    bookings either four years out or thirty days past.
    """
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    now = datetime.now(UTC)
    ended = booking_for(
        db, coordinator, venue, now - timedelta(hours=2), now - timedelta(minutes=5)
    )
    follows = booking_for(
        db, coordinator, venue, now + timedelta(minutes=25), now + timedelta(hours=1)
    )

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(f"/api/venues/{venue.id}", json={"turnaround_minutes": 60})

    # The finished event is still in the way, so both are reported.
    assert sorted(flagged(response)) == sorted([str(ended.id), str(follows.id)])


@pytest.mark.story("SCRUM-89")
async def test_a_booking_whose_turnaround_has_finished_is_left_out(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # The other side of the same boundary: once the effective interval has passed, nothing
    # can be done about it and it can no longer be in anyone's way.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    now = datetime.now(UTC)
    booking_for(db, coordinator, venue, now - timedelta(hours=4), now - timedelta(hours=3))
    follows = booking_for(
        db, coordinator, venue, now + timedelta(minutes=25), now + timedelta(hours=1)
    )

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(f"/api/venues/{venue.id}", json={"turnaround_minutes": 60})

    assert flagged(response) == []
    assert follows.id is not None


# ------------------------------------------------- AC1 and AC2: holds, not just bookings
#
# Reopened in Sprint 4. The reassessment only ever loaded confirmed bookings, so a
# tentative hold was invisible to it twice over: a hold a buffer change caught out was
# never reported, and a hold that something else now clashed with was never seen as being
# in the way. A hold occupies the venue exactly as a booking does (SCRUM-83 AC3).


def hold_for(
    db: Session,
    coordinator: User,
    venue: Venue,
    start_at: datetime,
    end_at: datetime,
    *,
    expires_at: datetime | None = None,
) -> VenueBooking:
    """A tentative hold at this venue, as SCRUM-83 places one.

    Built in one insert rather than by mutating a confirmed row afterwards: a tentative
    hold without its expiry and holder is refused by the table's own check constraint,
    which is what caught the first version of this helper.
    """
    event = approved_event(db, coordinator, coordinator, start_at=start_at, end_at=end_at)
    effective_start, effective_end = effective_for(venue, start_at, end_at)
    hold = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        session_label="Opening keynote",
        start_at=start_at,
        end_at=end_at,
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=BookingStatus.TENTATIVE,
        expires_at=expires_at if expires_at is not None else at(200),
        held_by_id=coordinator.id,
        held_at=at(0),
    )
    db.add(hold)
    db.flush()
    return hold


@pytest.mark.story("SCRUM-89")
async def test_a_hold_caught_out_by_a_buffer_change_is_reported(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # hold versus booking. The confirmed booking ends when the hold starts, so they are
    # compatible until the venue needs turnaround.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    booking = booking_for(db, coordinator, venue, at(10), at(12))
    hold = hold_for(db, coordinator, venue, at(12), at(13))

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND}
        )

    assert response.status_code == 200, response.text
    assert set(flagged(response)) == {str(booking.id), str(hold.id)}


@pytest.mark.story("SCRUM-89")
async def test_two_holds_that_now_overlap_are_both_reported(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # hold versus hold. Neither is confirmed, so before this change the venue looked
    # entirely clear however the buffers moved.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    first = hold_for(db, coordinator, venue, at(10), at(12))
    second = hold_for(db, coordinator, venue, at(12), at(13))

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND}
        )

    assert set(flagged(response)) == {str(first.id), str(second.id)}


@pytest.mark.story("SCRUM-89")
async def test_a_hold_whose_setup_now_runs_into_a_closure_is_reported(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # hold versus unavailability.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    hold = hold_for(db, coordinator, venue, at(10), at(12))
    # The closure ends at 09:45 and the event starts at 10:00, so the event itself never
    # touches it. Only the 30 minutes of setup, reaching back to 09:30, does.
    closure_for(db, venue, at(8), at(9.75))

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(f"/api/venues/{venue.id}", json={"setup_minutes": _SETUP})

    assert flagged(response) == [str(hold.id)]


@pytest.mark.story("SCRUM-89")
async def test_a_hold_whose_setup_meets_a_closure_exactly_is_not_reported(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # The boundary, half-open as everywhere else: a closure ending exactly when setup
    # begins is not an overlap.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    hold_for(db, coordinator, venue, at(10), at(12))
    closure_for(db, venue, at(8), at(9.5))

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(f"/api/venues/{venue.id}", json={"setup_minutes": 30})

    assert flagged(response) == []


@pytest.mark.story("SCRUM-89")
async def test_an_expired_hold_is_neither_reported_nor_in_anything_else_way(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """ADR-0030: expiry is a status, so an expired hold simply is not a candidate.

    The clock is not compared here. A hold that has run out but has not been swept yet is
    still `tentative` and still blocks, which is the lag ADR-0030 accepted for search, the
    calendar and the availability check; this surface agrees with them rather than
    inventing a second answer.
    """
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    booking = booking_for(db, coordinator, venue, at(10), at(12))
    expired = hold_for(db, coordinator, venue, at(12), at(13))
    expired.status = BookingStatus.EXPIRED
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND}
        )

    # The confirmed booking has nothing left to clash with, so nobody is reported.
    assert flagged(response) == []
    assert str(booking.id) not in flagged(response)


@pytest.mark.story("SCRUM-89")
@pytest.mark.parametrize(
    "status", [BookingStatus.PENDING, BookingStatus.REJECTED, BookingStatus.CANCELLED]
)
async def test_a_request_that_holds_nothing_is_never_in_the_way(
    db: Session, make_user: MakeUser, make_client: MakeClient, status: BookingStatus
) -> None:
    # Only a confirmed booking or a live hold occupies the venue. A pending request is
    # not a commitment, and a rejected or cancelled one is not anything at all.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    booking_for(db, coordinator, venue, at(10), at(12))
    booking_for(db, coordinator, venue, at(12), at(13), status=status)

    async with make_client(make_user("venue_staff")) as client:
        response = await client.patch(
            f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND}
        )

    assert flagged(response) == []


@pytest.mark.story("SCRUM-89")
async def test_the_audit_record_names_the_hold_it_caught_out(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC8: the stored snapshot is written from the same review, so a hold reaches it
    # without a second code path.
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    booking = booking_for(db, coordinator, venue, at(10), at(12))
    hold = hold_for(db, coordinator, venue, at(12), at(13))

    async with make_client(make_user("venue_staff")) as client:
        await client.patch(f"/api/venues/{venue.id}", json={"turnaround_minutes": _TURNAROUND})

    rows = audit_rows(db)
    assert len(rows) == 1
    assert set(rows[0].flagged_booking_ids) == {booking.id, hold.id}


@pytest.mark.story("SCRUM-89")
async def test_the_problems_panel_says_which_rows_are_holds(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: a hold and a confirmed booking need different answers from the Coordinator.

    A hold can be left to expire; a confirmed booking has to be moved. A panel that
    showed the two identically would be asking for the wrong decision.
    """
    venue = make_venue(db)
    coordinator = make_user("coordinator")
    booking = booking_for(db, coordinator, venue, at(10), at(12))
    hold = hold_for(db, coordinator, venue, at(12), at(13))
    # Buffers raised afterwards, as they are in life. Creating the venue already needing
    # turnaround would have the overlap constraint refuse the second row outright, which
    # is the constraint working: this state only arises from a later change.
    venue.turnaround_minutes = _TURNAROUND
    db.flush()

    async with make_client(make_user("venue_staff")) as client:
        response = await client.get("/api/venues/booking-problems")

    assert response.status_code == 200, response.text
    rows = next(v for v in response.json() if v["venue_id"] == str(venue.id))["problems"]
    by_id = {row["booking_id"]: row["status"] for row in rows}
    assert by_id[str(hold.id)] == "tentative"
    assert by_id[str(booking.id)] == "confirmed"
