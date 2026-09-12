"""The closed role vocabulary shared by the token, the database and the UI."""

import pytest

from domain.roles import Role


@pytest.mark.story("SCRUM-27")
def test_roles_are_the_five_roles_the_brief_names_in_lowercase() -> None:
    assert [r.value for r in Role] == [
        "organiser",
        "coordinator",
        "venue_staff",
        "tech_support",
        "attendee",
    ]


@pytest.mark.story("SCRUM-27")
def test_an_unknown_role_is_an_error_not_a_silent_miss() -> None:
    with pytest.raises(ValueError):
        Role("organizer")
