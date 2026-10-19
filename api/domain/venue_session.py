"""Session rules for a venue request (SCRUM-111). Pure, no database.

A venue request names one session of its parent event: a distinguishable label and the
period the session needs the venue for. The period may be shorter than the event and
sessions may overlap at different venues, but each session must sit inside the parent
event period. The booking row's own `start_at/end_at` is the session period once this
lands; the parent event period is only the outer boundary.
"""

from datetime import datetime

from domain.validation import FieldProblem

MAX_SESSION_LABEL_LENGTH = 120


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def session_problems(
    session_label: str | None,
    start_at: datetime | None,
    end_at: datetime | None,
    event_start: datetime,
    event_end: datetime,
) -> list[FieldProblem]:
    """What is wrong with a session label and period, if anything.

    Empty means the session is valid: a non-blank label, timezone-aware start/end with
    end strictly after start, and the whole period inside the parent event period.
    Exact parent boundaries are allowed, so a whole-event session stays valid.
    """
    problems: list[FieldProblem] = []
    if session_label is None or not session_label.strip():
        problems.append(FieldProblem("session_label", "must name the session"))
    elif len(session_label.strip()) > MAX_SESSION_LABEL_LENGTH:
        problems.append(
            FieldProblem(
                "session_label",
                f"must be at most {MAX_SESSION_LABEL_LENGTH} characters",
            )
        )
    if start_at is None:
        problems.append(FieldProblem("start_at", "must give the session start"))
    elif not _is_aware(start_at):
        problems.append(FieldProblem("start_at", "must include a time zone"))
    if end_at is None:
        problems.append(FieldProblem("end_at", "must give the session end"))
    elif not _is_aware(end_at):
        problems.append(FieldProblem("end_at", "must include a time zone"))
    if problems:
        return problems
    assert start_at is not None and end_at is not None
    if end_at <= start_at:
        return [FieldProblem("end_at", "must be after the session start")]
    if start_at < event_start:
        problems.append(FieldProblem("start_at", "must not be before the event starts"))
    if end_at > event_end:
        problems.append(FieldProblem("end_at", "must not be after the event ends"))
    return problems
