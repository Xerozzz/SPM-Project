"""The FastAPI application.

Built by a factory so tests can construct an app without importing module-level state,
and so router registration is one obvious list rather than scattered decorators.
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from core.config import get_settings
from core.database import engine


def create_app() -> FastAPI:
    """Build the application: middleware, routers, and the health endpoint."""
    settings = get_settings()
    app = FastAPI(title="ConnectSphere API", version="0.1.0")

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
    #     app.include_router(auth.router, prefix="/api")

    return app


app = create_app()
