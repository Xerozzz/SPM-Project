"""Pure SCRUM-115 manual registration-decision transition evidence."""

import pytest

from domain.registration import RegistrationStatus
from domain.registration_decision import RegistrationDecisionError, decide


@pytest.mark.story("SCRUM-115")
@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RegistrationStatus.PENDING, RegistrationStatus.ACCEPTED),
        (RegistrationStatus.WAITLISTED, RegistrationStatus.ACCEPTED),
        (RegistrationStatus.PENDING, RegistrationStatus.WAITLISTED),
        (RegistrationStatus.ACCEPTED, RegistrationStatus.WAITLISTED),
    ],
)
def test_manual_decision_allows_only_the_four_requested_transitions(
    current: RegistrationStatus, target: RegistrationStatus
) -> None:
    assert decide(current, target) is target


@pytest.mark.story("SCRUM-115")
@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RegistrationStatus.PENDING, RegistrationStatus.PENDING),
        (RegistrationStatus.ACCEPTED, RegistrationStatus.ACCEPTED),
        (RegistrationStatus.WAITLISTED, RegistrationStatus.WAITLISTED),
        (RegistrationStatus.WITHDRAWN, RegistrationStatus.ACCEPTED),
        (RegistrationStatus.CANCELLED, RegistrationStatus.WAITLISTED),
        (RegistrationStatus.ACCEPTED, RegistrationStatus.PENDING),
    ],
)
def test_manual_decision_refuses_every_other_transition(
    current: RegistrationStatus, target: RegistrationStatus
) -> None:
    with pytest.raises(RegistrationDecisionError):
        decide(current, target)
