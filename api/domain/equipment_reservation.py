"""How much of a requirement can be reserved, and how reserved it is (SCRUM-53). Pure.

Stock and the reservations held against it are counted by `domain.equipment_availability`
and the repositories; this module only decides what to do with those numbers, so every
rule below is a millisecond unit test rather than an API call.
"""

from enum import StrEnum


class ReservationState(StrEnum):
    """How much of a requirement's quantity is reserved. Derived, never stored."""

    NOT_RESERVED = "not_reserved"
    PARTIALLY_RESERVED = "partially_reserved"
    RESERVED = "reserved"


class ReservationRefusal(StrEnum):
    """Why nothing was reserved."""

    # More was asked for than the requirement still needs.
    ABOVE_OUTSTANDING = "above_outstanding"
    # AC3: more was asked for than is free over the event's window.
    ABOVE_FREE = "above_free"
    # The requirement is already fully reserved, so there is nothing to add.
    NOTHING_OUTSTANDING = "nothing_outstanding"
    # AC3 and AC4: none of this type is free over the event's window.
    NOTHING_FREE = "nothing_free"


def reservation_state(requested: int, reserved: int) -> ReservationState:
    """Reserved, partially reserved or not reserved, from the two quantities.

    At or above what is requested counts as reserved: a Coordinator can lower a
    requirement's quantity after some was reserved, and holding more than is now needed
    is still not short.
    """
    if reserved >= requested:
        return ReservationState.RESERVED
    if reserved >= 1:
        return ReservationState.PARTIALLY_RESERVED
    return ReservationState.NOT_RESERVED


def outstanding_quantity(requested: int, reserved: int) -> int:
    """How much of the requirement is still unreserved. Never negative."""
    return max(0, requested - reserved)


def free_quantity(in_service_stock: int, reserved_elsewhere: int, held_by_this_event: int) -> int:
    """AC3 and AC5: how many of a type nobody holds over the window. Never negative.

    `reserved_elsewhere` is what overlapping events hold; `held_by_this_event` is what this
    event already holds of the type, which `reserved_elsewhere` leaves out by design
    (SCRUM-52) but which is no longer free to reserve a second time.
    """
    return max(0, in_service_stock - reserved_elsewhere - held_by_this_event)


def quantity_to_reserve(asked: int | None, outstanding: int, free: int) -> int | ReservationRefusal:
    """How many to reserve now, or why none can be.

    With a quantity, it is reserved exactly or not at all: someone who asked for three and
    silently got two would not know they were short. Without one, as much of what is
    still needed as is free (partial reservation), and a refusal only when that is none.
    """
    if asked is not None:
        if asked > outstanding:
            return ReservationRefusal.ABOVE_OUTSTANDING
        if asked > free:
            return ReservationRefusal.ABOVE_FREE
        return asked
    if outstanding == 0:
        return ReservationRefusal.NOTHING_OUTSTANDING
    if free == 0:
        return ReservationRefusal.NOTHING_FREE
    return min(outstanding, free)
