"""SCRUM-79 API evidence: a Safety Officer reviews an event's current plan.

Against real PostgreSQL, so the worklist queries, the decision row and its constraints
are exercised rather than just the pure rule.

Every test starts from `arranged_event`, which is the only state AC2 lets a review begin
from: an approved event with a held venue and an equipment requirement that has been
reviewed as available and actually reserved. Each test then breaks one thing.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from domain.equipment_requirement import RequirementFields, RequirementReview
from domain.event_status import EventStatus
from domain.roles import Role
from domain.venue_booking import BookingStatus
from models.event_request import EventRequest
from models.user import User
from models.venue_booking import VenueBooking
from services import equipment_requirements as requirement_service
from services import equipment_reservations as reservation_service
from services import venue_bookings as booking_service
from tests.integration.test_equipment_requirements import catalogue
from tests.integration.test_submit_event_request import MakeClient, MakeUser
from tests.integration.test_submit_venue_booking import approved_event
from tests.integration.test_venue_search import effective_for, make_venue

_NOW = datetime(2030, 3, 1, tzinfo=UTC)
_START = datetime(2030, 3, 4, 10, tzinfo=UTC)


def arranged_event(
    db: Session, make_user: MakeUser, *, reserve: bool = True
) -> tuple[EventRequest, VenueBooking, User]:
    """An approved event whose plan is complete enough for AC2 to allow a review."""
    catalogue(db, "Projector")
    coordinator = make_user("coordinator")
    event = approved_event(
        db, make_user("organiser"), coordinator, start_at=_START, end_at=_START + timedelta(hours=2)
    )
    venue = make_venue(db, name=f"Hall {uuid.uuid4()}")
    effective_start, effective_end = effective_for(venue, _START, _START + timedelta(hours=2))
    booking = VenueBooking(
        venue_id=venue.id,
        event_request_id=event.id,
        requested_by_id=coordinator.id,
        session_label="Main hall",
        start_at=_START,
        end_at=_START + timedelta(hours=2),
        effective_start_at=effective_start,
        effective_end_at=effective_end,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.flush()
    # SCRUM-110: approving a request places the hold, so this is what "arranged" means.
    booking_service.hold(
        db, booking.id, make_user("venue_staff").id, _START + timedelta(days=1), _NOW
    )

    requirement = requirement_service.add(
        db, event, RequirementFields(equipment_type="Projector", quantity=1), coordinator.id, _NOW
    )
    requirement_service.review(db, requirement.id, RequirementReview.AVAILABLE, _NOW)
    if reserve:
        reservation_service.reserve(
            db, event.id, requirement.id, None, make_user("tech_support").id, _NOW
        )
    db.flush()
    return event, booking, coordinator


def officer(make_user: MakeUser) -> User:
    return make_user(Role.SAFETY_OFFICER.value)


def plan_of(response: httpx.Response, event: EventRequest) -> dict[str, Any]:
    return next(row for row in response.json() if row["event_request_id"] == str(event.id))


DecisionBody = Callable[..., dict[str, object]]


def body(fingerprint: str, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "decision": "approve",
        "comment": "Checked crowd movement and emergency access.",
        "plan_fingerprint": fingerprint,
    }
    values.update(overrides)
    return values


# --------------------------------------------------------------------------- AC1


@pytest.mark.story("SCRUM-79")
async def test_only_a_safety_officer_reaches_the_worklist(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    arranged_event(db, make_user)

    async with make_client(make_user("coordinator")) as client:
        response = await client.get("/api/safety-reviews")

    assert response.status_code == 403


@pytest.mark.story("SCRUM-79")
async def test_the_worklist_shows_an_event_with_the_plan_to_judge(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, booking, _ = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        response = await client.get("/api/safety-reviews")

    assert response.status_code == 200, response.text
    row = plan_of(response, event)
    # AC3: what the Officer needs for attendance, layout, accessibility and equipment.
    assert row["expected_attendance"] == 150
    assert row["accessibility_requirement"] is not None
    assert [venue["booking_id"] for venue in row["venues"]] == [str(booking.id)]
    assert row["venues"][0]["session_label"] == "Main hall"
    assert [item["equipment_type"] for item in row["equipment"]] == ["Projector"]
    assert row["may_review"] is True
    assert row["blockers"] == []
    assert row["latest_decision"] is None


@pytest.mark.story("SCRUM-79")
async def test_an_event_outside_planning_is_not_on_the_worklist(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, _ = arranged_event(db, make_user)
    event.status = EventStatus.CONFIRMED
    db.flush()

    async with make_client(officer(make_user)) as client:
        response = await client.get("/api/safety-reviews")

    assert [row["event_request_id"] for row in response.json()] == []


# --------------------------------------------------------------------------- AC2


@pytest.mark.story("SCRUM-79")
async def test_a_plan_whose_equipment_is_unreserved_says_why_it_cannot_be_reviewed(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # The Officer still sees the event: AC2's reasons are shown, not hidden by omission.
    event, _, _ = arranged_event(db, make_user, reserve=False)

    async with make_client(officer(make_user)) as client:
        response = await client.get("/api/safety-reviews")

    row = plan_of(response, event)
    assert row["may_review"] is False
    assert row["blockers"] == ["equipment_not_fulfilled"]


@pytest.mark.story("SCRUM-79")
async def test_a_decision_on_an_unreviewable_plan_is_refused_with_its_reasons(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, _ = arranged_event(db, make_user, reserve=False)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        response = await client.post(
            f"/api/safety-reviews/{event.id}", json=body(str(plan["plan_fingerprint"]))
        )

    assert response.status_code == 409
    assert response.json()["detail"]["blockers"] == ["equipment_not_fulfilled"]


@pytest.mark.story("SCRUM-79")
async def test_an_expired_hold_blocks_a_decision(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """ADR-0030 expires a hold on a sweep, so one can run out between sweeps.

    The prerequisite is read against the clock at decision time rather than trusting the
    stored status, which is the only way a safety approval cannot rest on a dead hold.
    """
    event, booking, _ = arranged_event(db, make_user)
    booking.expires_at = _NOW - timedelta(minutes=1)
    db.flush()

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        response = await client.post(
            f"/api/safety-reviews/{event.id}", json=body(str(plan["plan_fingerprint"]))
        )

    assert response.status_code == 409
    assert response.json()["detail"]["blockers"] == ["hold_expired"]


# ---------------------------------------------------------------- AC4, AC5, AC8


@pytest.mark.story("SCRUM-79")
async def test_an_approval_is_recorded_against_the_plan_it_judged(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, _ = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        response = await client.post(
            f"/api/safety-reviews/{event.id}", json=body(str(plan["plan_fingerprint"]))
        )

    assert response.status_code == 201, response.text
    recorded = response.json()
    assert recorded["decision"] == "approve"
    assert recorded["plan_fingerprint"] == plan["plan_fingerprint"]
    assert recorded["decided_at"] is not None and recorded["decided_by_id"] is not None
    # AC8: approval does not confirm the event.
    db.refresh(event)
    assert event.status.value == "approved"


@pytest.mark.story("SCRUM-79")
@pytest.mark.parametrize("decision", ["reject", "request_changes"])
async def test_neither_refusal_rejects_or_cancels_the_event(
    db: Session, make_user: MakeUser, make_client: MakeClient, decision: str
) -> None:
    # AC5: both send the plan back; neither makes the event terminally Rejected.
    event, booking, _ = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        response = await client.post(
            f"/api/safety-reviews/{event.id}",
            json=body(str(plan["plan_fingerprint"]), decision=decision),
        )

    assert response.status_code == 201, response.text
    db.refresh(event)
    db.refresh(booking)
    assert event.status.value == "approved"
    assert booking.status.value == "tentative"


@pytest.mark.story("SCRUM-79")
async def test_a_blank_comment_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, _ = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        response = await client.post(
            f"/api/safety-reviews/{event.id}",
            json=body(str(plan["plan_fingerprint"]), comment="   "),
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "comment"


# --------------------------------------------------------------------------- AC7


@pytest.mark.story("SCRUM-79")
async def test_a_decision_against_a_plan_that_has_moved_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """The heart of AC7: an approval cannot authorise a plan nobody looked at."""
    event, _, coordinator = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        # The Coordinator changes the event while the Officer is deciding.
        event.expected_attendance = 400
        db.flush()
        response = await client.post(
            f"/api/safety-reviews/{event.id}", json=body(str(plan["plan_fingerprint"]))
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["reason"] == "plan_changed"
    # The current fingerprint comes back, so the screen can reload rather than guess.
    assert detail["plan_fingerprint"] != plan["plan_fingerprint"]


@pytest.mark.story("SCRUM-79")
async def test_a_decision_is_accepted_again_once_the_officer_rereads_the_plan(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC6: the revised plan is reviewed again, and the second decision sticks.
    event, _, _ = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        event.expected_attendance = 400
        db.flush()
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        response = await client.post(
            f"/api/safety-reviews/{event.id}", json=body(str(plan["plan_fingerprint"]))
        )

    assert response.status_code == 201, response.text


# --------------------------------------------------------------------------- AC9


@pytest.mark.story("SCRUM-79")
async def test_decisions_are_kept_in_order_and_the_latest_is_the_one_that_counts(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, _ = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        await client.post(
            f"/api/safety-reviews/{event.id}",
            json=body(str(plan["plan_fingerprint"]), decision="reject", comment="Exit blocked."),
        )
        await client.post(
            f"/api/safety-reviews/{event.id}",
            json=body(str(plan["plan_fingerprint"]), decision="approve", comment="Exit cleared."),
        )
        history = await client.get(f"/api/safety-reviews/{event.id}/history")
        current = await client.get(f"/api/safety-reviews/{event.id}")

    assert [row["decision"] for row in history.json()] == ["reject", "approve"]
    # AC5: the approval clears what the rejection left outstanding, with no second write.
    assert current.json()["latest_decision"]["decision"] == "approve"


@pytest.mark.story("SCRUM-79")
async def test_the_coordinator_can_read_the_decisions_they_have_to_act_on(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    # AC5 puts the follow-up on the Coordinator, so the history cannot be Officer-only.
    event, _, coordinator = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        await client.post(
            f"/api/safety-reviews/{event.id}",
            json=body(str(plan["plan_fingerprint"]), decision="request_changes", comment="Widen."),
        )

    async with make_client(coordinator) as client:
        response = await client.get(f"/api/safety-reviews/{event.id}/history")

    assert response.status_code == 200
    assert [row["comment"] for row in response.json()] == ["Widen."]
