"""Clarification note vocabulary (SCRUM-106).

An event's clarification thread is a sequence of internal notes written by whoever is
currently the assigned coordinator. Each note keeps the REQUEST kind recorded when it
is written, by the endpoint only the assignee can call. RESPONSE stays in the enum so
rows written by the superseded SCRUM-30 exchange still read back; no endpoint writes
it anymore.
"""

from enum import StrEnum


class ClarificationKind(StrEnum):
    """Which side of the exchange wrote a message. Stored as its lowercase value."""

    REQUEST = "request"
    RESPONSE = "response"
