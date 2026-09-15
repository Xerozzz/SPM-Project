"""Round-robin Event Coordinator assignment (SCRUM-34).

Pure: no I/O. Callers (services/event_requests.py) supply the ordered pool of active
coordinators, who was assigned last (to continue the rotation), and which coordinators
are already unavailable for the requested date. See
docs/adr/0008-coordinator-round-robin-assignment.md for why the rotation is derived
from assignment history rather than kept in a dedicated pointer table.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

_ORG_TZ = ZoneInfo("Asia/Singapore")


class NoAvailableCoordinatorError(Exception):
    """Raised when every active coordinator already has an approved event that date."""


def select_next_coordinator(
    active_coordinator_ids: list[UUID],
    last_assigned_id: UUID | None,
    unavailable_ids: set[UUID],
) -> UUID:
    """Pick the next coordinator in rotation, skipping unavailable ones.

    `active_coordinator_ids` is the fixed, externally-ordered pool (rotation order).
    Rotation resumes immediately after whoever was assigned last; with no prior
    assignment, or if that coordinator has since left the pool, it starts at the
    front. The pool is walked at most once per call, wrapping around.
    """
    if not active_coordinator_ids:
        raise NoAvailableCoordinatorError

    pool_size = len(active_coordinator_ids)
    start = 0
    if last_assigned_id in active_coordinator_ids:
        start = (active_coordinator_ids.index(last_assigned_id) + 1) % pool_size

    for offset in range(pool_size):
        candidate = active_coordinator_ids[(start + offset) % pool_size]
        if candidate not in unavailable_ids:
            return candidate

    raise NoAvailableCoordinatorError


def org_day_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """Return the `[start, end)` UTC window corresponding to the organisation's
    (Singapore, UTC+8) calendar day containing `moment`.

    "Same date" for round-robin conflict purposes is the customer's local
    business day, not the UTC calendar day — AGENTS.md's tz-aware-UTC rule
    governs storage/comparison format, not which timezone defines a day
    boundary. Bounds are computed in SGT then converted back to UTC so callers
    still compare against UTC-stored datetimes.
    """
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    local_moment = moment.astimezone(_ORG_TZ)
    local_start = local_moment.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)
