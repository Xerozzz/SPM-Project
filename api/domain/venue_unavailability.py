"""Pure validation for SCRUM-62 venue closure periods."""

from dataclasses import dataclass
from datetime import UTC, datetime

from domain.validation import FieldProblem


@dataclass(frozen=True)
class VenueUnavailabilityFields:
    """The staff-supplied contents of one closure period."""

    starts_at: datetime | None = None
    ends_at: datetime | None = None
    reason: str | None = None


def validate_unavailability(fields: VenueUnavailabilityFields) -> list[FieldProblem]:
    """Return every reason this closure cannot be stored."""
    problems = _datetime_problems(fields.starts_at, "starts_at")
    problems.extend(_datetime_problems(fields.ends_at, "ends_at"))
    if (
        fields.starts_at is not None
        and fields.ends_at is not None
        and _is_utc(fields.starts_at)
        and _is_utc(fields.ends_at)
        and fields.ends_at <= fields.starts_at
    ):
        problems.append(FieldProblem("ends_at", "must be after the start time"))
    if fields.reason is None or not fields.reason.strip():
        problems.append(FieldProblem("reason", "is required"))
    return problems


def _datetime_problems(value: datetime | None, field: str) -> list[FieldProblem]:
    if value is None:
        return [FieldProblem(field, "is required")]
    if not _is_utc(value):
        return [FieldProblem(field, "must be given in UTC")]
    return []


def _is_utc(value: datetime | None) -> bool:
    return value is not None and value.tzinfo == UTC
