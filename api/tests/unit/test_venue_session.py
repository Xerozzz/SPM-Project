"""SCRUM-111 TC-111-01: session label and period validation."""

from datetime import UTC, datetime, timedelta

import pytest

from domain.venue_session import session_problems

EVENT_START = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
EVENT_END = datetime(2026, 11, 10, 17, 0, tzinfo=UTC)


def problems(
    label: str | None = "Opening keynote",
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[tuple[str, str]]:
    start = EVENT_START + timedelta(hours=1) if start is None else start
    end = EVENT_START + timedelta(hours=2) if end is None else end
    found = session_problems(label, start, end, EVENT_START, EVENT_END)
    return [(p.field, p.reason) for p in found]


@pytest.mark.story("SCRUM-111")
def test_valid_shorter_internal_session_passes() -> None:
    assert problems() == []


@pytest.mark.story("SCRUM-111")
def test_exact_parent_boundaries_pass() -> None:
    assert problems(start=EVENT_START, end=EVENT_END) == []


@pytest.mark.story("SCRUM-111")
def test_blank_and_missing_labels_are_rejected() -> None:
    assert problems(label=None)[0][0] == "session_label"
    assert problems(label="")[0][0] == "session_label"
    assert problems(label="   ")[0][0] == "session_label"


@pytest.mark.story("SCRUM-111")
def test_naive_datetimes_are_rejected() -> None:
    naive = datetime(2026, 11, 10, 10, 0, tzinfo=UTC).replace(tzinfo=None)
    assert ("start_at", "must include a time zone") in problems(start=naive)
    assert ("end_at", "must include a time zone") in problems(end=naive)


@pytest.mark.story("SCRUM-111")
def test_equal_or_reversed_period_is_rejected() -> None:
    moment = EVENT_START + timedelta(hours=1)
    assert problems(start=moment, end=moment) == [("end_at", "must be after the session start")]
    assert problems(start=moment + timedelta(hours=1), end=moment) == [
        ("end_at", "must be after the session start")
    ]


@pytest.mark.story("SCRUM-111")
def test_overlong_label_is_rejected() -> None:
    assert problems(label="x" * 121) == [("session_label", "must be at most 120 characters")]


@pytest.mark.story("SCRUM-111")
def test_missing_start_and_end_are_rejected() -> None:
    start = EVENT_START + timedelta(hours=1)
    end = EVENT_START + timedelta(hours=2)
    missing_start = session_problems("Opening keynote", None, end, EVENT_START, EVENT_END)
    assert ("start_at", "must give the session start") in [
        (p.field, p.reason) for p in missing_start
    ]
    missing_end = session_problems("Opening keynote", start, None, EVENT_START, EVENT_END)
    assert ("end_at", "must give the session end") in [(p.field, p.reason) for p in missing_end]


@pytest.mark.story("SCRUM-111")
def test_period_outside_either_parent_boundary_is_rejected() -> None:
    assert ("start_at", "must not be before the event starts") in problems(
        start=EVENT_START - timedelta(minutes=1)
    )
    assert ("end_at", "must not be after the event ends") in problems(
        end=EVENT_END + timedelta(minutes=1)
    )
