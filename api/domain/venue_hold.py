"""Tentative venue hold rules (SCRUM-83). Pure, no database.

A hold keeps a pending request's venue for its event while the Coordinator finalises
arrangements, but only until its expiry, so it can never hold a venue indefinitely
(Week 7 change 4). ADR-0029 records why a hold is placed on a pending request.
"""

from datetime import datetime

from domain.validation import FieldProblem


def expiry_problems(
    expires_at: datetime, now: datetime, event_start: datetime
) -> list[FieldProblem]:
    """What is wrong with a hold's expiry, if anything. Empty means it is valid.

    The expiry must carry a time zone (AGENTS.md section 3) and lie in the future, or the
    hold would end as soon as it was placed. It may not be after the event starts: the
    hold is for finalising arrangements before the event, not for the event itself, which
    needs an approved booking.
    """
    if expires_at.tzinfo is None or expires_at.tzinfo.utcoffset(expires_at) is None:
        return [FieldProblem("expires_at", "must include a time zone")]
    if expires_at <= now:
        return [FieldProblem("expires_at", "must be in the future")]
    if expires_at > event_start:
        return [FieldProblem("expires_at", "must not be after the event starts")]
    return []
