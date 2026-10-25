"""Who hears about event changes, safety and lifecycle actions (SCRUM-50). Pure.

Each source action gets one stable key, and SCRUM-99's unique (recipient, source)
constraint does the rest: a retry, an unchanged poll or a person reached through two
roles collides instead of notifying twice (AC9, ADR-0060).
"""

import uuid
from collections.abc import Iterable
from datetime import datetime

from domain.roles import Role

# Fixed namespace for derived keys. Changing it would make every old action look new.
_NAMESPACE = uuid.UUID("5c0e8a3b-5c1a-4b4e-9f50-50a1f0c0de50")

#: AC5: staff roles responsible for an event's arrangements.
ARRANGEMENT_STAFF_ROLES = frozenset({Role.VENUE_STAFF.value, Role.TECH_SUPPORT.value})


def _key(*parts: object) -> str:
    return str(uuid.uuid5(_NAMESPACE, "|".join(str(part) for part in parts)))


def review_due_key(event_id: uuid.UUID, plan_fingerprint: str) -> str:
    """AC2: one key per plan version, so an unchanged plan is announced once."""
    return _key("review", event_id, plan_fingerprint)


def confirmation_key(event_id: uuid.UUID, confirmed_at: datetime) -> str:
    """AC4: one key per confirmation, so a reconfirmation after replanning is new."""
    return _key("confirm", event_id, confirmed_at.isoformat())


def replan_key(cause: str, source: object) -> str:
    """AC5: one key per return to planning, named by its cause and source record."""
    return _key("replan", cause, source)


def affected_staff(
    actor_ids: Iterable[uuid.UUID], roles_of: dict[uuid.UUID, list[str]]
) -> set[uuid.UUID]:
    """AC5: venue and technical staff who acted on the event's arrangements."""
    return {actor for actor in actor_ids if ARRANGEMENT_STAFF_ROLES & set(roles_of.get(actor, []))}
