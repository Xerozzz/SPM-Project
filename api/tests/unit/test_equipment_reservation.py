"""SCRUM-53: how much of a requirement to reserve, and how reserved it is. Pure."""

import pytest

from domain.equipment_reservation import (
    ReservationRefusal,
    ReservationState,
    free_quantity,
    outstanding_quantity,
    quantity_to_reserve,
    reservation_state,
)


@pytest.mark.story("SCRUM-53")
@pytest.mark.parametrize(
    ("requested", "reserved", "state"),
    [
        (3, 0, ReservationState.NOT_RESERVED),
        (3, 1, ReservationState.PARTIALLY_RESERVED),
        (3, 2, ReservationState.PARTIALLY_RESERVED),
        (3, 3, ReservationState.RESERVED),
        # The Coordinator lowered the quantity after it was reserved: still not short.
        (2, 3, ReservationState.RESERVED),
    ],
)
def test_reservation_state(requested: int, reserved: int, state: ReservationState) -> None:
    assert reservation_state(requested, reserved) is state


@pytest.mark.story("SCRUM-53")
@pytest.mark.parametrize(
    ("requested", "reserved", "outstanding"), [(3, 0, 3), (3, 2, 1), (2, 3, 0)]
)
def test_outstanding_is_never_negative(requested: int, reserved: int, outstanding: int) -> None:
    assert outstanding_quantity(requested, reserved) == outstanding


@pytest.mark.story("SCRUM-53")
@pytest.mark.parametrize(
    ("stock", "elsewhere", "here", "free"),
    [(10, 0, 0, 10), (10, 4, 0, 6), (10, 4, 2, 4), (10, 8, 2, 0), (3, 5, 0, 0)],
)
def test_free_subtracts_both_other_events_and_this_one(
    stock: int, elsewhere: int, here: int, free: int
) -> None:
    assert free_quantity(stock, elsewhere, here) == free


@pytest.mark.story("SCRUM-53")
@pytest.mark.parametrize(
    ("asked", "outstanding", "free", "decided"),
    [
        # Left out: as much as is needed and free.
        (None, 3, 5, 3),
        (None, 3, 1, 1),
        (None, 3, 0, ReservationRefusal.NOTHING_FREE),
        (None, 0, 5, ReservationRefusal.NOTHING_OUTSTANDING),
        # Given: exactly that, or nothing.
        (2, 3, 5, 2),
        (3, 3, 3, 3),
        (4, 3, 5, ReservationRefusal.ABOVE_OUTSTANDING),
        (2, 3, 1, ReservationRefusal.ABOVE_FREE),
        # Above both: needing less is the first thing to tell the caller.
        (4, 3, 1, ReservationRefusal.ABOVE_OUTSTANDING),
    ],
)
def test_quantity_to_reserve(
    asked: int | None, outstanding: int, free: int, decided: int | ReservationRefusal
) -> None:
    assert quantity_to_reserve(asked, outstanding, free) == decided
