"""The /health endpoint. It is what CI polls before it trusts the stack."""

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import OperationalError

import main


async def get(app: FastAPI, path: str) -> httpx.Response:
    """Call the app in-process — no network, no running server."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.story("US-0")
async def test_health_reports_ok_when_the_database_is_reachable() -> None:
    response = await get(main.app, "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.story("US-0")
async def test_health_reports_unavailable_when_the_database_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # "ok" has to cover the database as well, otherwise CI starts Playwright against a
    # stack that cannot serve a single query.
    class UnreachableEngine:
        def connect(self) -> object:
            raise OperationalError("SELECT 1", None, Exception("connection refused"))

    monkeypatch.setattr(main, "engine", UnreachableEngine())

    response = await get(main.app, "/health")

    assert response.status_code == 503
