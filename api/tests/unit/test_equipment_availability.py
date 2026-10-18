"""SCRUM-52: the pure availability rules, without a database."""

import pytest

from domain.equipment import OPERATIONAL_STATUSES
from domain.equipment_availability import (
    IN_SERVICE_STATUS,
    Availability,
    StockEntry,
    assess,
    classify,
    count_in_service,
)
from domain.equipment_requirement import RequirementReview

EXCLUDED_STATUSES = [s for s in OPERATIONAL_STATUSES if s != IN_SERVICE_STATUS]


@pytest.mark.story("SCRUM-52")
def test_the_in_service_status_is_one_the_catalogue_allows() -> None:
    assert IN_SERVICE_STATUS == "Operational"
    assert EXCLUDED_STATUSES == ["Damaged", "Under Maintenance"]


# ------------------------------------------------------------------------ classify


@pytest.mark.story("SCRUM-52")
@pytest.mark.parametrize(
    ("requested", "stock", "reserved", "expected"),
    [
        # Boundary: exactly the requested quantity left is enough.
        (3, 3, 0, RequirementReview.AVAILABLE),
        (3, 10, 7, RequirementReview.AVAILABLE),
        (3, 10, 0, RequirementReview.AVAILABLE),
        # One short of the boundary, and the bottom of the partial range.
        (3, 2, 0, RequirementReview.PARTIALLY_AVAILABLE),
        (3, 10, 9, RequirementReview.PARTIALLY_AVAILABLE),
        (3, 1, 0, RequirementReview.PARTIALLY_AVAILABLE),
        # Nothing left, including more reserved than exists.
        (3, 0, 0, RequirementReview.UNAVAILABLE),
        (3, 10, 10, RequirementReview.UNAVAILABLE),
        (3, 2, 5, RequirementReview.UNAVAILABLE),
        # A quantity of one is never partial.
        (1, 1, 0, RequirementReview.AVAILABLE),
        (1, 0, 0, RequirementReview.UNAVAILABLE),
    ],
)
def test_classify_gives_each_outcome(
    requested: int, stock: int, reserved: int, expected: RequirementReview
) -> None:
    assert classify(requested, stock, reserved) is expected


@pytest.mark.story("SCRUM-52")
def test_assess_reports_the_numbers_and_never_a_negative_remainder() -> None:
    assert assess(4, 2, 5) == Availability(
        stock=2, reserved=5, available=0, result=RequirementReview.UNAVAILABLE
    )
    assert assess(4, 10, 3) == Availability(
        stock=10, reserved=3, available=7, result=RequirementReview.AVAILABLE
    )


# -------------------------------------------------------------------------- stock


@pytest.mark.story("SCRUM-52")
def test_stock_sums_every_active_in_service_entry() -> None:
    entries = [StockEntry(4, IN_SERVICE_STATUS, True), StockEntry(6, IN_SERVICE_STATUS, True)]
    assert count_in_service(entries) == 10


@pytest.mark.story("SCRUM-52")
@pytest.mark.parametrize("status", EXCLUDED_STATUSES)
def test_stock_leaves_out_an_entry_that_is_not_in_service(status: str) -> None:
    entries = [StockEntry(4, IN_SERVICE_STATUS, True), StockEntry(6, status, True)]
    assert count_in_service(entries) == 4


@pytest.mark.story("SCRUM-52")
def test_stock_leaves_out_an_unknown_status() -> None:
    assert count_in_service([StockEntry(6, "operational", True)]) == 0


@pytest.mark.story("SCRUM-52")
def test_stock_leaves_out_an_inactive_entry() -> None:
    entries = [StockEntry(4, IN_SERVICE_STATUS, True), StockEntry(6, IN_SERVICE_STATUS, False)]
    assert count_in_service(entries) == 4


@pytest.mark.story("SCRUM-52")
def test_stock_of_nothing_is_zero() -> None:
    assert count_in_service([]) == 0
