"""Forwarded requests need a usable client identity for keyless local trust."""

import asyncio

import httpx
import pytest
from fastapi import Depends, FastAPI, Response

from memanto.app.clients.backend import Backend
from memanto.app.config import settings
from memanto.app.routes.auth_deps import require_management_access

_KEY = "synthetic-management-key-for-tests"


@pytest.mark.parametrize(
    "headers,peer,status",
    [
        ([("X-Forwarded-Proto", "https")], "127.0.0.1", 401),
        ([("X-Forwarded-Host", "example.invalid")], "127.0.0.1", 401),
        ([("X-Forwarded-For", "")], "127.0.0.1", 401),
        ([("X-Forwarded-For", "127.0.0.1,")], "127.0.0.1", 401),
        ([("X-Real-IP", " ")], "127.0.0.1", 401),
        ([("Forwarded", "")], "127.0.0.1", 401),
        ([("Forwarded", "proto=https;host=localhost")], "127.0.0.1", 401),
        ([("Forwarded", "by=127.0.0.1")], "127.0.0.1", 401),
        ([("X-Forwarded-For", "127.0.0.1"), ("X-Forwarded-For", "")], "127.0.0.1", 401),
        ([], "127.0.0.1", 204),
        ([], "::1", 204),
        ([("X-Forwarded-For", "127.0.0.1"), ("X-Forwarded-Proto", "https")], "127.0.0.1", 204),
        ([("X-Real-IP", "::1")], "127.0.0.1", 204),
        ([("Forwarded", 'for="[::1]:1234";proto=https')], "127.0.0.1", 204),
        ([("Forwarded", "for=127.0.0.1;by=127.0.0.1")], "127.0.0.1", 204),
        ([("X-Forwarded-For", "192.0.2.1")], "127.0.0.1", 401),
        ([("X-Forwarded-For", "127.0.0.1"), ("X-Forwarded-For", "192.0.2.1")], "127.0.0.1", 401),
        ([("Forwarded", 'for="[2001:db8::1]:1234"')], "127.0.0.1", 401),
        ([("Forwarded", 'for="127.0.0.1')], "127.0.0.1", 401),
        ([], "192.0.2.1", 401),
        ([("Origin", "https://example.invalid")], "127.0.0.1", 403),
        ([("X-Forwarded-Proto", "https"), ("X-Api-Key", _KEY)], "127.0.0.1", 204),
        ([("X-Forwarded-Proto", "https"), ("Authorization", "Bearer " + _KEY)], "127.0.0.1", 204),
        ([("X-Forwarded-Proto", "https"), ("X-Api-Key", "wrong-key")], "127.0.0.1", 401),
    ],
)
def test_management_forwarded_identity(monkeypatch, headers, peer, status):
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", Backend.ON_PREM.value)
    monkeypatch.setattr(settings, "MEMANTO_SECRET_KEY", _KEY)
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", ["http://localhost"])
    monkeypatch.setattr(settings, "CORS_ORIGIN_REGEX", None)
    app = FastAPI()
    invoked = []

    @app.post("/management", dependencies=[Depends(require_management_access)])
    def management_operation():
        invoked.append(True)
        return Response(status_code=204)

    async def run():
        transport = httpx.ASGITransport(app=app, client=(peer, 1234))
        async with httpx.AsyncClient(transport=transport, base_url="https://localhost") as client:
            return await client.post("/management", headers=headers)

    response = asyncio.run(run())
    assert response.status_code == status
    assert len(invoked) == (1 if status == 204 else 0)
