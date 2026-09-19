"""Clarification message vocabulary (SCRUM-30).

A clarification thread is a sequence of messages on one event request. Each message is
either the assigned coordinator asking, or the owning organiser answering. The kind is
recorded when the message is written, by the endpoint that only that side can call, so
the history can be read without guessing from who the author was.
"""

from enum import StrEnum


class ClarificationKind(StrEnum):
    """Which side of the exchange wrote a message. Stored as its lowercase value."""

    REQUEST = "request"
    RESPONSE = "response"
