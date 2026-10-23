"""Pure rules for SCRUM-113's registration intake controls."""

from dataclasses import dataclass
from datetime import datetime

from domain.event_status import EventStatus


class RegistrationIntakeError(Exception):
    """A requested intake operation is not valid for the current settings."""


@dataclass(frozen=True)
class Settings:
    """The operational registration state, independent of event planning fields."""

    opened_at: datetime | None
    closes_at: datetime | None
    suspended_at: datetime | None


def is_enabled(requirement: str | None) -> bool:
    """A non-blank existing registration requirement opts an event into intake."""
    return bool(requirement and requirement.strip())


def intake_is_open(status: EventStatus, settings: Settings, now: datetime) -> bool:
    """New attendee intake is possible only while its operational guard is satisfied."""
    return (
        status is EventStatus.CONFIRMED
        and settings.opened_at is not None
        and settings.suspended_at is None
        and (settings.closes_at is None or now < settings.closes_at)
    )


def validate_open(closes_at: datetime | None, now: datetime) -> None:
    """An optional deadline must follow the opening instant and still be future-facing."""
    if closes_at is not None and closes_at <= now:
        raise RegistrationIntakeError("Registration closing deadline must be in the future")


def validate_extension(current: Settings, closes_at: datetime, now: datetime) -> None:
    """Only a configured deadline may be extended, never shortened or created here."""
    if current.closes_at is None:
        raise RegistrationIntakeError("Registration has no closing deadline to extend")
    if closes_at <= now:
        raise RegistrationIntakeError("Registration closing deadline must be in the future")
    if closes_at <= current.closes_at:
        raise RegistrationIntakeError(
            "Registration closing deadline must be later than its current deadline"
        )
