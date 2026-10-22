"""The closed role vocabulary shared by the token, the database and the UI."""

import pytest

from domain.roles import Role


@pytest.mark.story("SCRUM-27")
@pytest.mark.story("SCRUM-101")
@pytest.mark.story("SCRUM-79")
def test_roles_are_the_ones_the_brief_names_in_lowercase() -> None:
    assert [r.value for r in Role] == [
        "organiser",
        "coordinator",
        # SCRUM-101: the Coordinator Lead triages the unassigned queue.
        "coordinator_lead",
        "venue_staff",
        "tech_support",
        "attendee",
        # SCRUM-79: the Safety Officer decides whether a plan has passed safety review.
        "safety_officer",
    ]


@pytest.mark.story("SCRUM-27")
def test_an_unknown_role_is_an_error_not_a_silent_miss() -> None:
    with pytest.raises(ValueError):
        Role("organizer")
