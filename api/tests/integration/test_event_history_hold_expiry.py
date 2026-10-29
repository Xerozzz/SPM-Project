"""SCRUM-136: hold expiry changes, recorded by the SCRUM-121 writer and read through
GET /event-requests/{id}/history.

Changes are made through the real PATCH, so each entry is read from exactly what the
writer recorded. The record is written in the update's transaction (ADR-0070), so a
refused or rolled-back update must leave no row and no entry. Access is the SCRUM-88
route's, unchanged (ADR-0062).
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic.config import Config
from sqlalchemy import event as sa_event
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from core.database import SessionLocal, engine
from core.security import hash_password
from domain.venue_hold import InactiveHoldError
from models.notification import Notification
from models.user import User
from models.venue_booking import VenueBooking
from models.venue_hold_expiry_change import VenueHoldExpiryChange
from repositories import venue_availability
from services import venue_bookings
from services.venue_hold_expiry import expire_due_holds
from tests.integration.test_approve_venue_booking import _committed_requests, _delete_committed
from tests.integration.test_event_history_venue_changes import Planning, history, of, planning
from tests.integration.test_submit_event_request import MakeClient, MakeUser

_TABLE = "venue_hold_expiry_changes"


def _days(n: int) -> datetime:
    return (datetime.now(UTC) + timedelta(days=n)).replace(microsecond=0)


async def _patch(make_client: MakeClient, caller: User, row: VenueBooking, value: object) -> int:
    async with make_client(caller) as client:
        response = await client.patch(
            f"/api/venue-bookings/{row.id}/hold", json={"expires_at": value}
        )
    return response.status_code


def _recorded(db: Session, booking: VenueBooking) -> list[VenueHoldExpiryChange]:
    statement = select(VenueHoldExpiryChange).where(VenueHoldExpiryChange.booking_id == booking.id)
    return list(db.scalars(statement.order_by(VenueHoldExpiryChange.changed_at)))


# ------------------------------------------------------------------- migration 0044


def _tables() -> set[str]:
    return set(inspect(engine).get_table_names())


@pytest.mark.story("SCRUM-136")
def test_migration_adds_and_removes_only_the_expiry_change_table() -> None:
    command.downgrade(Config("alembic.ini"), "0043")
    try:
        assert _TABLE not in _tables()
        command.upgrade(Config("alembic.ini"), "0044")
        assert _TABLE in _tables()
        foreign_keys = {
            (fk["constrained_columns"][0], fk["referred_table"])
            for fk in inspect(engine).get_foreign_keys(_TABLE)
        }
        assert foreign_keys == {("booking_id", "venue_bookings"), ("changed_by_id", "users")}
        checks = {c["name"] for c in inspect(engine).get_check_constraints(_TABLE)}
        assert checks == {"venue_hold_expiry_changes_is_a_change"}
        nullable = {c["name"]: c["nullable"] for c in inspect(engine).get_columns(_TABLE)}
        assert not any(nullable.values())
    finally:
        command.upgrade(Config("alembic.ini"), "head")
    # Downgrading took nothing else with it.
    assert "expires_at" in {c["name"] for c in inspect(engine).get_columns("venue_bookings")}


@pytest.mark.story("SCRUM-136")
def test_the_database_refuses_a_row_that_changes_nothing(db: Session, make_user: MakeUser) -> None:
    p = planning(db, make_user)
    same = _days(7)
    refused = pytest.raises(IntegrityError, match="venue_hold_expiry_changes_is_a_change")
    with refused, db.begin_nested():
        db.execute(
            text(
                f"INSERT INTO {_TABLE} (id, booking_id, old_expires_at, new_expires_at, "
                "changed_by_id, changed_at) VALUES (:id, :booking, :at, :at, :by, now())"
            ),
            {"id": uuid.uuid4(), "booking": p.first.id, "at": same, "by": p.staff.id},
        )


# ------------------------------------------------------------- AC1 the writer records


@pytest.mark.story("SCRUM-136")
async def test_an_expiry_update_records_old_new_who_and_when(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = planning(db, make_user)
    old = p.first.expires_at
    new = _days(7)
    before = datetime.now(UTC)

    assert await _patch(make_client, p.staff, p.first, new.isoformat()) == 200

    [row] = _recorded(db, p.first)
    assert (row.old_expires_at, row.new_expires_at, row.changed_by_id) == (old, new, p.staff.id)
    assert before <= row.changed_at <= datetime.now(UTC)
    assert row.changed_at.utcoffset() == timedelta(0)


@pytest.mark.story("SCRUM-136")
async def test_an_update_to_the_same_expiry_records_nothing(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = planning(db, make_user)
    new = _days(7)
    assert await _patch(make_client, p.staff, p.first, new.isoformat()) == 200

    # A retried PATCH: answered as before, and not a second change.
    assert await _patch(make_client, p.staff, p.first, new.isoformat()) == 200

    assert len(_recorded(db, p.first)) == 1


# ------------------------------------------------------ AC4 refused records nothing


@pytest.mark.story("SCRUM-136")
@pytest.mark.parametrize(
    ("kind", "expected"),
    [("past", 422), ("after_start", 422), ("not_staff", 403), ("inactive", 409)],
)
async def test_a_refused_update_records_nothing_and_shows_nothing(
    kind: str, expected: int, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = planning(db, make_user)
    assert p.event.start_at is not None
    before = await history(make_client, p.owner, p.event)
    value = _days(7)
    caller = p.staff
    if kind == "past":
        value = datetime.now(UTC) - timedelta(minutes=1)
    elif kind == "after_start":
        value = p.event.start_at + timedelta(seconds=1)
    elif kind == "not_staff":
        caller = p.coordinator
    else:
        p.first.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.flush()

    assert await _patch(make_client, caller, p.first, value.isoformat()) == expected

    assert _recorded(db, p.first) == []
    after = await history(make_client, p.owner, p.event)
    assert of(after, "hold_expiry_changed") == []
    assert [e["id"] for e in after] == [e["id"] for e in before]


@pytest.mark.story("SCRUM-136")
def test_a_failed_save_rolls_back_the_expiry_and_its_record(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC5: one transaction. The change row is staged with the update and goes with it."""
    p = planning(db, make_user)
    db.commit()  # a savepoint release here, so the writer's rollback keeps the hold.
    original = p.first.expires_at

    def fail_after_flush(db: Session, booking: VenueBooking) -> VenueBooking:
        db.flush()
        raise RuntimeError("forced failure")

    monkeypatch.setattr(venue_availability, "save_booking", fail_after_flush)
    with pytest.raises(RuntimeError, match="forced failure"):
        venue_bookings.update_hold_expiry(db, p.first.id, _days(7), datetime.now(UTC), p.staff.id)

    db.refresh(p.first)
    assert p.first.expires_at == original
    assert _recorded(db, p.first) == []


@pytest.mark.story("SCRUM-136")
def test_racing_the_expiry_sweep_records_a_change_only_if_the_update_won() -> None:
    """The SCRUM-121 race, with the record checked against its serial outcome."""
    committed = _committed_requests(1)
    booking_id = committed.booking_ids[0]
    old_expiry = _days(2)
    new_expiry = old_expiry + timedelta(days=1)
    start_together = threading.Barrier(2)
    outcomes: list[str] = []

    with SessionLocal() as setup:
        venue_bookings.approve(setup, booking_id, committed.user_id, datetime.now(UTC), old_expiry)
        staff = User(
            email=f"{uuid.uuid4()}@example.com",
            password_hash=hash_password("password123"),
            roles=["venue_staff"],
            organisation_id=committed.organisation_id,
        )
        setup.add(staff)
        setup.commit()
        staff_id = staff.id

    def update() -> None:
        with SessionLocal() as session:
            start_together.wait()
            try:
                venue_bookings.update_hold_expiry(
                    session, booking_id, new_expiry, old_expiry - timedelta(seconds=1), staff_id
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
            statement = select(VenueHoldExpiryChange).where(
                VenueHoldExpiryChange.booking_id == booking_id
            )
            recorded = [(r.old_expires_at, r.new_expires_at) for r in check.scalars(statement)]
        if "updated" in outcomes:
            assert recorded == [(old_expiry, new_expiry)]
        else:
            assert sorted(outcomes) == ["expired", "inactive"]
            assert recorded == []
    finally:
        with SessionLocal() as cleanup:
            cleanup.query(Notification).filter(
                Notification.event_request_id.in_(committed.event_ids)
            ).delete(synchronize_session=False)
            cleanup.query(VenueHoldExpiryChange).filter(
                VenueHoldExpiryChange.booking_id == booking_id
            ).delete(synchronize_session=False)
            cleanup.query(User).filter(User.id == staff_id).delete(synchronize_session=False)
            cleanup.commit()
        _delete_committed(committed)


# --------------------------------------------------- AC2, AC3 shown in the history


@pytest.mark.story("SCRUM-136")
async def test_a_recorded_change_appears_once_with_both_expiries_actor_and_time(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = planning(db, make_user)
    old = p.first.expires_at
    assert old is not None
    new = _days(7)
    await _patch(make_client, p.staff, p.first, new.isoformat())
    [row] = _recorded(db, p.first)

    [entry] = of(await history(make_client, p.owner, p.event), "hold_expiry_changed")

    assert (entry["source_type"], entry["source_id"]) == ("venue_hold_expiry_change", str(row.id))
    assert (entry["actor_id"], entry["actor_email"]) == (str(p.staff.id), p.staff.email)
    assert datetime.fromisoformat(entry["occurred_at"]) == row.changed_at
    assert entry["session_label"] == "Main session"
    [changed] = entry["changes"]
    assert (changed["field"], changed["label"], changed["kind"]) == (
        "expires_at",
        "Held until",
        "datetime",
    )
    assert datetime.fromisoformat(changed["old"]) == old
    assert datetime.fromisoformat(changed["new"]) == new


@pytest.mark.story("SCRUM-136")
async def test_several_changes_appear_in_the_order_made_and_the_hold_shows_the_latest(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = planning(db, make_user)
    extended, shortened = _days(9), _days(6)
    await _patch(make_client, p.staff, p.first, extended.isoformat())
    await _patch(make_client, p.staff, p.first, shortened.isoformat())

    body = await history(make_client, p.owner, p.event)

    news = [datetime.fromisoformat(e["changes"][0]["new"]) for e in of(body, "hold_expiry_changed")]
    assert news == [extended, shortened]
    [hold] = [e for e in of(body, "hold_created") if e["source_id"] == str(p.first.id)]
    assert datetime.fromisoformat(hold["hold_expires_at"]) == shortened


@pytest.mark.story("SCRUM-136")
async def test_a_hold_with_no_recorded_change_shows_only_its_latest_expiry(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC6: a change made before SCRUM-136 left no row, so nothing is shown for it."""
    p = planning(db, make_user)
    latest = _days(8)
    p.first.expires_at = latest  # as SCRUM-121 left it, with no record.
    db.flush()

    body = await history(make_client, p.owner, p.event)

    assert of(body, "hold_expiry_changed") == []
    [hold] = [e for e in of(body, "hold_created") if e["source_id"] == str(p.first.id)]
    assert datetime.fromisoformat(hold["hold_expires_at"]) == latest


# ------------------------------------------------------- AC7 access, privacy, no writes


async def _with_a_change(db: Session, make_user: MakeUser, make_client: MakeClient) -> Planning:
    p = planning(db, make_user)
    await _patch(make_client, p.staff, p.first, _days(7).isoformat())
    return p


@pytest.mark.story("SCRUM-136")
async def test_owner_assignee_and_lead_see_the_same_expiry_change(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = await _with_a_change(db, make_user, make_client)

    bodies = [
        await history(make_client, viewer, p.event)
        for viewer in (p.owner, p.coordinator, p.lead, make_user("coordinator_lead"))
    ]

    assert len(of(bodies[0], "hold_expiry_changed")) == 1
    assert all(body == bodies[0] for body in bodies)


@pytest.mark.story("SCRUM-136")
@pytest.mark.parametrize(
    "caller_kind",
    ["unassigned_coordinator", "peer_organiser", "venue_staff", "tech_support", "attendee"],
)
async def test_everyone_else_still_gets_a_bare_403(
    caller_kind: str, db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """Venue Staff who made the change still may not read the event's history."""
    p = await _with_a_change(db, make_user, make_client)
    callers = {
        "unassigned_coordinator": lambda: make_user("coordinator"),
        "peer_organiser": lambda: make_user("organiser", organisation_id=p.owner.organisation_id),
        "venue_staff": lambda: p.staff,
    }
    caller = callers.get(caller_kind, lambda: make_user(caller_kind))()

    async with make_client(caller) as client:
        response = await client.get(f"/api/event-requests/{p.event.id}/history")

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


@pytest.mark.story("SCRUM-136")
async def test_reading_expiry_changes_issues_only_selects(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    p = await _with_a_change(db, make_user, make_client)
    statements: list[str] = []
    flushes: list[object] = []

    def capture(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    def count_flush(*_args: object) -> None:
        flushes.append(object())

    connection = db.connection()
    sa_event.listen(connection, "before_cursor_execute", capture)
    sa_event.listen(db, "before_flush", count_flush)
    try:
        for viewer in (p.owner, p.coordinator, p.lead):
            await history(make_client, viewer, p.event)
    finally:
        sa_event.remove(connection, "before_cursor_execute", capture)
        sa_event.remove(db, "before_flush", count_flush)

    assert statements
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
    assert flushes == []
