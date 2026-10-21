"""The FastAPI application.

Built by a factory so that router registration is one obvious list rather than a set of
scattered decorators, and so a test can build a second app with overridden dependencies
without disturbing the one the server is running.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from core.config import get_settings
from core.database import engine
from core.hold_expiry import HoldExpiryTimer
from routers import (
    auth,
    equipment,
    equipment_requirements,
    event_change_requests,
    event_clarifications,
    event_requests,
    notifications,
    safety_reviews,
    venue_booking_decisions,
    venue_bookings,
    venue_calendar,
    venue_unavailabilities,
    venues,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """SCRUM-108: the minute timer that expires tentative venue holds runs while the app
    is up (ADR-0030). Test clients that do not start the app never start it."""
    timer = HoldExpiryTimer()
    timer.start()
    yield
    timer.stop()


def create_app() -> FastAPI:
    """Build the application: middleware, routers, and the health endpoint."""
    settings = get_settings()
    app = FastAPI(title="ConnectSphere API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Report readiness, including the database.

        CI polls this before starting Playwright, so "ok" has to mean the whole stack is
        usable — an API that answers while its database is unreachable is not ready.
        """
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database unreachable",
            ) from exc
        return {"status": "ok"}

    # Feature routers are registered here, one line each, as stories land:
    app.include_router(auth.router, prefix="/api")
    app.include_router(equipment.router, prefix="/api")
    # SCRUM-43. Shares the /event-requests prefix with the router below; the order does
    # not matter, because every template on that prefix has a distinct literal second
    # segment. The ordering that does matter is inside the router itself.
    app.include_router(equipment_requirements.router, prefix="/api")
    # SCRUM-44: Technical Support Staff review requirements across events.
    app.include_router(equipment_requirements.review_router, prefix="/api")
    app.include_router(event_change_requests.router, prefix="/api")
    app.include_router(event_clarifications.router, prefix="/api")
    app.include_router(notifications.router)
    app.include_router(event_requests.router, prefix="/api")
    app.include_router(safety_reviews.router, prefix="/api")
    app.include_router(venue_bookings.router, prefix="/api")
    # Venue Staff decisions share /venue-bookings: approve is venue_bookings.decisions
    # (SCRUM-74), list and reject are venue_booking_decisions (SCRUM-40).
    app.include_router(venue_bookings.decisions, prefix="/api")
    app.include_router(venue_booking_decisions.router, prefix="/api")
    app.include_router(venues.router, prefix="/api")
    app.include_router(venue_unavailabilities.router, prefix="/api")
    app.include_router(venue_calendar.router, prefix="/api")

    return app


app = create_app()
