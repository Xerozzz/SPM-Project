"""The clarification message vocabulary shared by the API and the UI."""

import pytest

from domain.event_clarification import ClarificationKind


@pytest.mark.story("SCRUM-30")
def test_kinds_are_the_two_sides_of_the_exchange_in_lowercase() -> None:
    assert [k.value for k in ClarificationKind] == ["request", "response"]


@pytest.mark.story("SCRUM-30")
def test_an_unknown_kind_is_an_error_not_a_silent_miss() -> None:
    with pytest.raises(ValueError):
        ClarificationKind("question")
