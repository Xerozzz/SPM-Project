"""The /health endpoint. It is what CI polls before it trusts the stack."""

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.exc import OperationalError

import main

MakeClient = Callable[..., httpx.AsyncClient]


@pytest.mark.story("US-0")
async def test_health_reports_ok_when_the_database_is_reachable(make_client: MakeClient) -> None:
    async with make_client() as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.story("US-0")
async def test_health_reports_unavailable_when_the_database_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, make_client: MakeClient
) -> None:
    # "ok" has to cover the database as well, otherwise CI starts Playwright against a
    # stack that cannot serve a single query. The route reads `main.engine` at call time,
    # so swapping it here is seen by the app the fixture built.
    class UnreachableEngine:
        def connect(self) -> object:
            raise OperationalError("SELECT 1", None, Exception("connection refused"))

    monkeypatch.setattr(main, "engine", UnreachableEngine())

    async with make_client() as client:
        response = await client.get("/health")

    assert response.status_code == 503
