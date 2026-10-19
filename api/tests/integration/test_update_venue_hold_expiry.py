"""SCRUM-121: Venue Staff revise an active Tentative hold's current expiry."""

import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.database import SessionLocal
from domain.venue_booking import BookingStatus
from domain.venue_hold import InactiveHoldError
from models.notification import Notification
from models.user import User
from models.venue_booking import VenueBooking
from repositories import venue_availability
from services import venue_bookings
from services.venue_hold_expiry import expire_due_holds
from tests.integration.test_approve_venue_booking import _committed_requests, _delete_committed
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_venue_holds import _START, _held, _request
from tests.integration.test_venue_search import make_venue


async def _update(client: httpx.AsyncClient, row: VenueBooking, value: object) -> httpx.Response:
    return await client.patch(f"/api/venue-bookings/{row.id}/hold", json={"expires_at": value})


async def _active(
    db: Session, make_client: MakeClient, staff: User, coordinator: User
) -> VenueBooking:
    return await _held(db, make_client, staff, _request(db, coordinator, make_venue(db)))


@pytest.mark.story("SCRUM-121")
async def test_staff_update_one_hold_twice_and_only_the_latest_expiry_is_kept(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _active(db, make_client, staff, make_user("coordinator"))
    first = datetime.now(UTC).replace(microsecond=0) + timedelta(days=4)
    second = first + timedelta(days=1)

    async with make_client(staff) as client:
        first_response = await _update(client, held, first.isoformat())
        second_response = await _update(client, held, second.isoformat())

    assert datetime.fromisoformat(first_response.json()["expires_at"]) == first
    assert datetime.fromisoformat(second_response.json()["expires_at"]) == second
    db.refresh(held)
    assert (held.status, held.expires_at) == (BookingStatus.TENTATIVE, second)
    assert db.scalar(select(func.count()).where(VenueBooking.id == held.id)) == 1


@pytest.mark.story("SCRUM-121")
@pytest.mark.parametrize("kind", ["missing", "naive", "past", "after_start"])
async def test_invalid_new_expiry_is_field_specific_and_does_not_mutate(
    kind: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _active(db, make_client, staff, make_user("coordinator"))
    original = held.expires_at
    values = {
        "naive": "2030-01-01T09:00:00",
        "past": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "after_start": (_START + timedelta(seconds=1)).isoformat(),
    }
    body = {} if kind == "missing" else {"expires_at": values[kind]}

    async with make_client(staff) as client:
        response = await client.patch(f"/api/venue-bookings/{held.id}/hold", json=body)

    assert response.status_code == 422
    if kind in {"past", "after_start"}:
        assert response.json()["detail"][0]["field"] == "expires_at"
    db.refresh(held)
    assert held.expires_at == original


@pytest.mark.story("SCRUM-121")
async def test_a_due_hold_cannot_be_revived_and_the_worker_still_alerts_once(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    staff = make_user("venue_staff")
    held = await _active(db, make_client, staff, make_user("coordinator"))
    old_expiry = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=1)
    held.expires_at = old_expiry
    db.flush()

    async with make_client(staff) as client:
        response = await _update(client, held, (old_expiry + timedelta(days=1)).isoformat())

    assert response.status_code == 409
    db.refresh(held)
    assert (held.status, held.expires_at) == (BookingStatus.TENTATIVE, old_expiry)
    assert expire_due_holds(db, old_expiry) == [held.id]
    assert expire_due_holds(db, old_expiry + timedelta(hours=1)) == []
    assert db.scalar(select(func.count()).where(Notification.source_id == str(held.id))) == 1


@pytest.mark.story("SCRUM-121")
@pytest.mark.parametrize(
    ("status", "role", "expected"),
    [
        *[
            (status, "venue_staff", 409)
            for status in BookingStatus
            if status is not BookingStatus.TENTATIVE
        ],
        *[
            (BookingStatus.TENTATIVE, role, 403)
            for role in ("coordinator", "organiser", "tech_support", "attendee")
        ],
        (BookingStatus.TENTATIVE, None, 401),
    ],
)
async def test_only_staff_may_update_an_active_tentative_hold(
    status: BookingStatus,
    role: str | None,
    expected: int,
    db: Session,
    make_user: MakeUser,
    make_client: MakeClient,
) -> None:
    staff = make_user("venue_staff")
    coordinator = make_user("coordinator")
    row = (
        await _active(db, make_client, staff, coordinator)
        if status is BookingStatus.TENTATIVE
        else _request(db, coordinator, make_venue(db), status=status)
    )
    original = row.expires_at
    caller = None if role is None else staff if role == "venue_staff" else make_user(role)

    async with make_client(caller) as client:
        response = await _update(client, row, (_START - timedelta(days=1)).isoformat())

    assert response.status_code == expected
    db.refresh(row)
    assert (row.status, row.expires_at) == (status, original)


@pytest.mark.story("SCRUM-121")
def test_a_failed_save_rolls_back_the_expiry_change(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = _request(db, make_user("coordinator"), make_venue(db))
    venue_bookings.hold(
        db,
        held.id,
        make_user("venue_staff").id,
        datetime.now(UTC) + timedelta(days=2),
        datetime.now(UTC),
    )
    original = held.expires_at

    def fail_after_flush(db: Session, booking: VenueBooking) -> VenueBooking:
        db.flush()
        raise RuntimeError("forced failure")

    monkeypatch.setattr(venue_availability, "save_booking", fail_after_flush)
    with pytest.raises(RuntimeError, match="forced failure"):
        venue_bookings.update_hold_expiry(
            db, held.id, _START - timedelta(days=2), datetime.now(UTC)
        )

    db.refresh(held)
    assert held.expires_at == original


@pytest.mark.story("SCRUM-121")
def test_an_edit_racing_expiry_has_one_valid_serial_outcome() -> None:
    committed = _committed_requests(1)
    booking_id = committed.booking_ids[0]
    old_expiry = datetime.now(UTC).replace(microsecond=0) + timedelta(days=2)
    new_expiry = old_expiry + timedelta(days=1)
    start_together = threading.Barrier(2)
    outcomes: list[str] = []

    with SessionLocal() as setup:
        venue_bookings.approve(setup, booking_id, committed.user_id, datetime.now(UTC), old_expiry)

    def update() -> None:
        with SessionLocal() as session:
            start_together.wait()
            try:
                venue_bookings.update_hold_expiry(
                    session, booking_id, new_expiry, old_expiry - timedelta(seconds=1)
                )
                outcomes.append("updated")
            except InactiveHoldError:
                outcomes.append("inactive")

    def expire() -> None:
        with SessionLocal() as session:
            start_together.wait()
            outcomes.append("expired" if expire_due_holds(session, old_expiry) else "skipped")

    try:
        threads = [threading.Thread(target=update), threading.Thread(target=expire)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        with SessionLocal() as check:
            row = check.get(VenueBooking, booking_id)
            assert row is not None
            final = (row.status, row.expires_at)
        assert (tuple(sorted(outcomes)), final) in {
            (("skipped", "updated"), (BookingStatus.TENTATIVE, new_expiry)),
            (("expired", "inactive"), (BookingStatus.EXPIRED, old_expiry)),
        }
    finally:
        with SessionLocal() as cleanup:
            cleanup.query(Notification).filter(Notification.source_id == str(booking_id)).delete()
            cleanup.commit()
        _delete_committed(committed)
