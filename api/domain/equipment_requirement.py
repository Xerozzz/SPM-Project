"""Rules for the equipment an event needs (SCRUM-43). Pure, no database.

An event's equipment requirements are records, not a sentence: each one names a type from
the catalogue Technical Support Staff maintain (SCRUM-84) and says how many are needed.
The organiser picks the first one when raising the request; after that the assigned
Coordinator maintains them, and the same records are the ones Technical Support Staff
assess (SCRUM-44).

Nothing here knows about the database, HTTP or the ORM (ADR-0003), so every rule below is
covered by fast unit tests rather than by standing up an API.
"""

from dataclasses import dataclass
from enum import StrEnum

from domain.validation import FieldProblem

# The smallest useful quantity. Asking for none of something is not a requirement.
MINIMUM_QUANTITY = 1

# How long a free-text technical note may be, matching the catalogue's description field.
MAX_TECHNICAL_REQUIREMENTS = 1000


class RequirementReview(StrEnum):
    """What Technical Support Staff have said about a requirement (SCRUM-44).

    The whole vocabulary lives here so it is one closed list, but SCRUM-43 only ever sets
    `PENDING_REVIEW`: the other three are outcomes SCRUM-44 records. Writing them down now
    means that story extends a list rather than inventing a second one.
    """

    PENDING_REVIEW = "pending_review"
    AVAILABLE = "available"
    PARTIALLY_AVAILABLE = "partially_available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class RequirementFields:
    """What a Coordinator supplies for one requirement. All optional, because the caller
    may be part-way through a form; completeness is what `validate_requirement` checks."""

    equipment_type: str | None = None
    quantity: int | None = None
    technical_requirements: str | None = None


def validate_new_requirement(
    fields: RequirementFields,
    catalogue_types: frozenset[str],
    types_already_on_the_event: frozenset[str],
) -> list[FieldProblem]:
    """Every problem that blocks adding a requirement; empty means it may be saved.

    `catalogue_types` are the types currently active in the catalogue, and
    `types_already_on_the_event` are the ones this event already asks for. Both are passed
    in rather than looked up, so this stays pure and the service owns where they come from.
    """
    problems: list[FieldProblem] = []
    problems.extend(
        _type_problems(fields.equipment_type, catalogue_types, types_already_on_the_event)
    )
    problems.extend(_change_problems(fields.quantity, fields.technical_requirements))
    return problems


def validate_change(quantity: int | None, technical_requirements: str | None) -> list[FieldProblem]:
    """Every problem that blocks changing a requirement that already exists.

    Deliberately says nothing about the equipment type. The type cannot be changed (AC4
    makes one type one line), and re-checking it against the *active* catalogue would mean
    that deactivating the last entry of a type froze every requirement already asking for
    it: the Coordinator would be told to fix a field they cannot send, and their only way
    out would be to delete the line. The type was legal when the line was created, and
    whether it can still be supplied is SCRUM-44's question, not a reason to refuse an
    edit to the quantity.
    """
    return _change_problems(quantity, technical_requirements)


def _change_problems(
    quantity: int | None, technical_requirements: str | None
) -> list[FieldProblem]:
    """The rules that apply to a requirement's own values, whether new or changed."""
    return _quantity_problems(quantity) + _technical_problems(technical_requirements)


def _type_problems(
    equipment_type: str | None,
    catalogue_types: frozenset[str],
    types_already_on_the_event: frozenset[str],
) -> list[FieldProblem]:
    if equipment_type is None or not equipment_type.strip():
        return [FieldProblem("equipment_type", "is required")]
    chosen = equipment_type.strip()
    # AC3: an active catalogue type. A deactivated one is refused the same way an invented
    # one is, because neither can be supplied (ADR-0012, ADR-0025).
    if chosen not in catalogue_types:
        return [FieldProblem("equipment_type", "is not an active catalogue type")]
    # AC4: one line per type. Two lines for the same thing is an edit, not an addition,
    # and allowing both would leave two answers to "how many do we need".
    if chosen in types_already_on_the_event:
        return [FieldProblem("equipment_type", "is already required for this event")]
    return []


def _quantity_problems(quantity: int | None) -> list[FieldProblem]:
    if quantity is None:
        return [FieldProblem("quantity", "is required")]
    # AC3 asks for a positive whole number. `bool` is an `int` in Python, and `True` would
    # otherwise pass as a quantity of one, so it is refused explicitly.
    if isinstance(quantity, bool) or quantity < MINIMUM_QUANTITY:
        return [FieldProblem("quantity", f"must be at least {MINIMUM_QUANTITY}")]
    return []


def _technical_problems(technical_requirements: str | None) -> list[FieldProblem]:
    if technical_requirements is None:
        return []
    if len(technical_requirements) > MAX_TECHNICAL_REQUIREMENTS:
        return [
            FieldProblem(
                "technical_requirements",
                f"must be {MAX_TECHNICAL_REQUIREMENTS} characters or fewer",
            )
        ]
    return []


def review_after_change() -> RequirementReview:
    """AC5: a new or changed requirement has to be assessed again.

    A function rather than a constant so the reason has somewhere to live: whatever
    Technical Support Staff last said is about a requirement that no longer exists in that
    form, so keeping it would tell the Coordinator something untrue (SCRUM-44).
    """
    return RequirementReview.PENDING_REVIEW
