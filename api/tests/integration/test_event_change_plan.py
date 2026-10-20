"""SCRUM-37: the values and choices the Organiser's change form starts from."""

import pytest
from sqlalchemy.orm import Session

from domain.event_status import EventStatus
from tests.integration.test_event_change_requests import _planned
from tests.integration.test_submit_event_request import MakeClient, MakeUser


def _url(event_id: object) -> str:
    return f"/api/event-requests/{event_id}/change-requests/plan"


@pytest.mark.story("SCRUM-37")
async def test_the_organiser_sees_current_values_sessions_and_equipment(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _, session = _planned(db, make_user)

    async with make_client(organiser) as client:
        response = await client.get(_url(event.id))

    assert response.status_code == 200
    plan = response.json()
    assert plan["event"]["expected_attendance"] == event.expected_attendance
    assert [s["id"] for s in plan["sessions"]] == [str(session.id)]
    assert plan["sessions"][0]["session_label"] == "Keynote"
    assert len(plan["equipment"]) >= 1
    assert "Microphone" in plan["equipment_types"]
    assert isinstance(plan["venue_options"], list)


@pytest.mark.story("SCRUM-37")
async def test_only_the_owning_organiser_reads_the_form_values(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, _, coordinator, _ = _planned(db, make_user)

    for user in (coordinator, make_user("organiser")):
        async with make_client(user) as client:
            response = await client.get(_url(event.id))
        assert response.status_code == 403


@pytest.mark.story("SCRUM-37")
async def test_a_rejected_event_has_no_change_form(
    db: Session, make_user: MakeUser, make_client: MakeClient
) -> None:
    event, organiser, _, _ = _planned(db, make_user, EventStatus.REJECTED)

    async with make_client(organiser) as client:
        response = await client.get(_url(event.id))

    assert response.status_code == 403
