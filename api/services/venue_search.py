"""Coordinator venue search for SCRUM-55.

Loads the selectable catalogue, applies the pure domain rules (static criteria plus
operating hours), then removes venues blocked by a confirmed booking or an
unavailability block overlapping the requested slot. Pending requests never block.
"""

from datetime import UTC, date, datetime, time

from core.database import Session
from domain.venue_search import (
    SearchableVenue,
    VenueSearchCriteria,
    is_within_operating_hours,
    venue_matches_criteria,
)
from models.venue import Venue
from repositories import venue_availability as availability_repo
from repositories import venues as venues_repo


def search(
    db: Session,
    day: date,
    start: time,
    end: time,
    minimum_capacity: int | None = None,
    location: str | None = None,
    accessibility: list[str] | None = None,
    facility: list[str] | None = None,
    layout: str | None = None,
) -> list[Venue]:
    """Active venues satisfying every supplied criterion and free for the slot."""
    criteria = VenueSearchCriteria(
        minimum_capacity=minimum_capacity,
        location=location,
        required_facilities=facility,
        required_accessibility=accessibility,
        required_layout=layout,
    )
    start_at = datetime.combine(day, start, tzinfo=UTC)
    end_at = datetime.combine(day, end, tzinfo=UTC)
    blocked = availability_repo.venue_ids_with_confirmed_overlap(
        db, start_at, end_at
    ) | availability_repo.venue_ids_with_unavailability_overlap(db, start_at, end_at)
    matches: list[Venue] = []
    for venue in venues_repo.list_active(db):
        if venue.id in blocked:
            continue
        if not is_within_operating_hours(venue.opens_at, venue.closes_at, start, end):
            continue
        if not venue_matches_criteria(_searchable(venue), criteria):
            continue
        matches.append(venue)
    return matches


def _searchable(venue: Venue) -> SearchableVenue:
    """The static attributes the domain criteria compare against."""
    return SearchableVenue(
        maximum_capacity=venue.maximum_capacity,
        location=venue.location,
        facilities=list(venue.facilities),
        accessibility_features=list(venue.accessibility_features),
        supported_layouts=list(venue.supported_layouts),
    )
