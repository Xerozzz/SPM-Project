"""Pure transition rules for an Organiser's manual registration decisions."""

from domain.registration import RegistrationStatus


class RegistrationDecisionError(Exception):
    """The requested registration transition is not an Organiser decision."""


_ALLOWED_TRANSITIONS = frozenset(
    {
        (RegistrationStatus.PENDING, RegistrationStatus.ACCEPTED),
        (RegistrationStatus.WAITLISTED, RegistrationStatus.ACCEPTED),
        (RegistrationStatus.PENDING, RegistrationStatus.WAITLISTED),
        (RegistrationStatus.ACCEPTED, RegistrationStatus.WAITLISTED),
    }
)


def decide(current: RegistrationStatus, target: RegistrationStatus) -> RegistrationStatus:
    """Return a permitted manual outcome, otherwise leave the lifecycle untouched."""
    if (current, target) not in _ALLOWED_TRANSITIONS:
        raise RegistrationDecisionError(f"cannot change registration from {current} to {target}")
    return target
