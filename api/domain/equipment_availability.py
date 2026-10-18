"""Whether there is enough equipment for a requirement (SCRUM-52). Pure, no database.

Technical Support Staff ask this before they record a review (SCRUM-44), so the answer is
one of the same three outcomes `RequirementReview` already names rather than a second
vocabulary. Nothing here reserves anything or moves stock (AC6): it only does arithmetic
on numbers the service hands it.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from domain.equipment import OPERATIONAL_STATUSES
from domain.equipment_requirement import RequirementReview

# AC3: the one catalogue status that can be lent out. Every other value in
# OPERATIONAL_STATUSES (Damaged, Under Maintenance) is left out of stock, and so is any
# value added to that list later until someone decides it counts.
IN_SERVICE_STATUS = OPERATIONAL_STATUSES[0]


@dataclass(frozen=True)
class StockEntry:
    """The parts of one catalogue entry that decide whether it counts toward stock."""

    total_quantity: int
    operational_status: str
    is_active: bool


@dataclass(frozen=True)
class Availability:
    """AC4: the numbers behind a result, so the person reading it can see why."""

    stock: int
    reserved: int
    available: int
    result: RequirementReview


def count_in_service(entries: Iterable[StockEntry]) -> int:
    """AC3: how many of a type exist that could be used, across every location.

    A deactivated entry is retired (ADR-0025), and a damaged or maintained one cannot be
    handed out, so neither counts however many it holds.
    """
    return sum(
        entry.total_quantity
        for entry in entries
        if entry.is_active and entry.operational_status == IN_SERVICE_STATUS
    )


def classify(requested: int, in_service_stock: int, reserved_elsewhere: int) -> RequirementReview:
    """AC2 and AC4: enough, some but not enough, or none.

    What is left is never negative: reservations above stock mean nothing is free, not
    that a requirement is owed equipment.
    """
    remaining = max(0, in_service_stock - reserved_elsewhere)
    if remaining >= requested:
        return RequirementReview.AVAILABLE
    if remaining >= 1:
        return RequirementReview.PARTIALLY_AVAILABLE
    return RequirementReview.UNAVAILABLE


def assess(requested: int, in_service_stock: int, reserved_elsewhere: int) -> Availability:
    """`classify`, with the stock, reservations and remainder it was decided from."""
    return Availability(
        stock=in_service_stock,
        reserved=reserved_elsewhere,
        available=max(0, in_service_stock - reserved_elsewhere),
        result=classify(requested, in_service_stock, reserved_elsewhere),
    )
