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
        db,
        booking.id,
        make_user("venue_staff").id,
        # SCRUM-83: a hold may not outlast the event start, so it sits between.
        _START - timedelta(days=1),
        _NOW,
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
    assert row["expected_attendance"] == event.expected_attendance
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
    # Against the real clock, not the fixture's: the route reads `datetime.now`, and a
    # hold dated in 2030 is still live however the fixtures are arranged.
    booking.expires_at = datetime.now(UTC) - timedelta(minutes=1)
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


@pytest.mark.story("SCRUM-79")
async def test_an_arrangement_that_was_rejected_is_not_part_of_the_plan(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """A rejected request is history, and history must not block a review for good.

    An event keeps every booking row it ever had (SCRUM-40 retains the rejection so the
    Coordinator can read the reason). Nobody can clear one, so judging it would mean a
    single refused request in an event's past made its plan unreviewable forever.
    """
    event, held, coordinator = arranged_event(db, make_user)
    venue = make_venue(db, name=f"Hall {uuid.uuid4()}")
    effective_start, effective_end = effective_for(venue, _START, _START + timedelta(hours=2))
    db.add(
        VenueBooking(
            venue_id=venue.id,
            event_request_id=event.id,
            requested_by_id=coordinator.id,
            session_label="Tried and refused",
            start_at=_START,
            end_at=_START + timedelta(hours=2),
            effective_start_at=effective_start,
            effective_end_at=effective_end,
            status=BookingStatus.REJECTED,
        )
    )
    db.flush()

    async with make_client(officer(make_user)) as client:
        response = await client.get(f"/api/safety-reviews/{event.id}")

    plan = response.json()
    assert plan["blockers"] == []
    assert plan["may_review"] is True
    # AC3: the Officer is shown the arrangement that stands, not the one that did not.
    assert [venue["booking_id"] for venue in plan["venues"]] == [str(held.id)]


@pytest.mark.story("SCRUM-79")
async def test_a_hold_that_was_swept_does_not_block_the_arrangement_that_replaced_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """ADR-0030 keeps a swept hold for its history; the live hold beside it is the plan."""
    event, held, coordinator = arranged_event(db, make_user)
    venue = make_venue(db, name=f"Hall {uuid.uuid4()}")
    effective_start, effective_end = effective_for(venue, _START, _START + timedelta(hours=2))
    db.add(
        VenueBooking(
            venue_id=venue.id,
            event_request_id=event.id,
            requested_by_id=coordinator.id,
            session_label="Ran out",
            start_at=_START,
            end_at=_START + timedelta(hours=2),
            effective_start_at=effective_start,
            effective_end_at=effective_end,
            status=BookingStatus.EXPIRED,
            expires_at=_NOW - timedelta(days=1),
        )
    )
    db.flush()

    async with make_client(officer(make_user)) as client:
        response = await client.get(f"/api/safety-reviews/{event.id}")

    plan = response.json()
    assert plan["blockers"] == []
    assert [venue["booking_id"] for venue in plan["venues"]] == [str(held.id)]


@pytest.mark.story("SCRUM-79")
async def test_a_request_still_waiting_on_venue_staff_blocks_the_review(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """The other half of the same rule: a pending request *is* part of the plan.

    It is not history, it is an arrangement nobody has decided yet, and the Coordinator
    can get it decided. Dropping it with the dead rows would let a review approve a plan
    half of which no venue has agreed to.
    """
    event, _, coordinator = arranged_event(db, make_user)
    venue = make_venue(db, name=f"Hall {uuid.uuid4()}")
    effective_start, effective_end = effective_for(venue, _START, _START + timedelta(hours=2))
    db.add(
        VenueBooking(
            venue_id=venue.id,
            event_request_id=event.id,
            requested_by_id=coordinator.id,
            session_label="Second room, still waiting",
            start_at=_START,
            end_at=_START + timedelta(hours=2),
            effective_start_at=effective_start,
            effective_end_at=effective_end,
            status=BookingStatus.PENDING,
        )
    )
    db.flush()

    async with make_client(officer(make_user)) as client:
        response = await client.get(f"/api/safety-reviews/{event.id}")

    assert response.json()["blockers"] == ["venue_not_held"]
    assert response.json()["may_review"] is False


@pytest.mark.story("SCRUM-79")
async def test_a_decision_notifies_the_coordinator_who_has_to_act_on_it(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5: the plan going back to the Coordinator has to actually reach them.

    Without this the decision is a row nobody is told about, and "it goes back to the
    Coordinator" is true only in the sense that someone could go looking for it.
    """
    event, _, coordinator = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        response = await client.post(
            f"/api/safety-reviews/{event.id}",
            json=body(str(plan["plan_fingerprint"]), decision="reject", comment="Exit blocked."),
        )
    assert response.status_code == 201

    async with make_client(coordinator) as client:
        inbox = (await client.get("/api/notifications")).json()

    safety = [row for row in inbox if str(row["type"]).startswith("safety")]
    assert [row["type"] for row in safety] == ["safety_rejected"]
    assert safety[0]["event_request_id"] == str(event.id)
    # The reason itself stays in the authorised history, as SCRUM-94 keeps a rejection
    # reason out of the notification.
    assert "Exit blocked." not in str(safety[0])


@pytest.mark.story("SCRUM-79")
async def test_each_decision_notifies_once_and_names_itself(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """A later decision is a new row, so it is a new notification, not a swallowed one."""
    event, _, coordinator = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        fingerprint = str(plan["plan_fingerprint"])
        await client.post(
            f"/api/safety-reviews/{event.id}",
            json=body(fingerprint, decision="request_changes", comment="Widen the aisle."),
        )
        await client.post(
            f"/api/safety-reviews/{event.id}",
            json=body(fingerprint, decision="approve", comment="Aisle widened."),
        )

    async with make_client(coordinator) as client:
        inbox = (await client.get("/api/notifications")).json()

    safety = sorted(
        (row for row in inbox if str(row["type"]).startswith("safety")),
        key=lambda row: str(row["occurred_at"]),
    )
    assert {row["type"] for row in safety} == {"safety_changes_requested", "safety_approved"}


@pytest.mark.story("SCRUM-79")
async def test_an_unrelated_signed_in_user_cannot_read_an_events_safety_decisions(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC9 is for the people doing the work, not for anyone holding a token.

    A decision's comment is an internal judgement about an event's arrangements, so an
    attendee, an organiser and a coordinator the event is not assigned to are all
    refused — the same line SCRUM-106 drew for clarification notes.
    """
    event, _, _ = arranged_event(db, make_user)

    for role in ("attendee", "organiser", "venue_staff", "tech_support"):
        async with make_client(make_user(role)) as client:
            response = await client.get(f"/api/safety-reviews/{event.id}/history")
        assert response.status_code == 403, f"{role} could read the decisions"

    # A Coordinator who is not the one assigned to this event is refused too.
    async with make_client(make_user("coordinator")) as client:
        response = await client.get(f"/api/safety-reviews/{event.id}/history")
    assert response.status_code == 403


@pytest.mark.story("SCRUM-79")
async def test_the_people_doing_the_work_can_read_the_decisions(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5 and AC9: the assigned Coordinator, any Lead, and the Safety Officer."""
    event, _, coordinator = arranged_event(db, make_user)

    for who in (coordinator, officer(make_user), make_user("coordinator_lead")):
        async with make_client(who) as client:
            response = await client.get(f"/api/safety-reviews/{event.id}/history")
        assert response.status_code == 200, f"{who.email} was refused"


@pytest.mark.story("SCRUM-79")
async def test_a_decision_says_whether_it_goes_back_to_the_coordinator(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC5, as the API's answer rather than something each screen works out again."""
    event, _, _ = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        returned = (
            await client.post(
                f"/api/safety-reviews/{event.id}",
                json=body(str(plan["plan_fingerprint"]), decision="reject", comment="Unsafe."),
            )
        ).json()
        after = (await client.get(f"/api/safety-reviews/{event.id}")).json()

    assert returned["returns_to_coordinator"] is True
    assert after["latest_decision"]["returns_to_coordinator"] is True


@pytest.mark.story("SCRUM-79")
async def test_a_reason_longer_than_the_cap_is_refused(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    """AC4: capped like SCRUM-40's rejection reason, so one screen cannot write
    something another cannot show."""
    event, _, _ = arranged_event(db, make_user)

    async with make_client(officer(make_user)) as client:
        plan = (await client.get(f"/api/safety-reviews/{event.id}")).json()
        response = await client.post(
            f"/api/safety-reviews/{event.id}",
            json=body(str(plan["plan_fingerprint"]), comment="x" * 1001),
        )

    assert response.status_code == 422
