"""The shape a validation failure takes across the domain layer.

`FieldProblem` started in `event_request.py` for SCRUM-46 and is shared from here so the
venue catalogue (SCRUM-59) reports failures the same way: one problem per field, naming
the field and the reason, so a router can turn the list straight into a 422 body and the
UI can put each message next to its input.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldProblem:
    """One thing the user has to fix, and which field it is on."""

    field: str
    reason: str
