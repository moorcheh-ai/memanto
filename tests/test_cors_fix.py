"""
Tests for CORS misconfiguration fix (#770).

Verifies that:
1.  CORS_ALLOW_CREDENTIALS defaults to False.
2.  _validate_cors_settings() (the production guard in main.py) raises ValueError
    when wildcard origins and allow_credentials are combined.
3.  Wildcard origins + credentials=False does NOT send
    Access-Control-Allow-Credentials: true in responses.
"""

import pytest


# Patch the live settings singleton directly: memanto.app.config.settings is
# instantiated once at import time (during test collection), so
# monkeypatch.setenv() here would never reach code that reads it.
@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    from memanto.app.config import settings

    monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "test-api-key")


class TestCorsCredentialsDefault:
    """CORS_ALLOW_CREDENTIALS defaults to False."""

    def test_default_is_false(self):
        from memanto.app.config import Settings

        s = Settings()
        assert s.CORS_ALLOW_CREDENTIALS is False

    def test_explicit_true_accepted(self):
        from memanto.app.config import Settings

        s = Settings(CORS_ALLOW_CREDENTIALS=True)
        assert s.CORS_ALLOW_CREDENTIALS is True


class TestValidateCorsSettings:
    """Tests against the production guard function in main.py."""

    def _guard(self, allowed_origins, allow_credentials):
        from memanto.app.main import _validate_cors_settings

        _validate_cors_settings(allowed_origins, allow_credentials)

    def test_wildcard_with_credentials_raises(self):
        with pytest.raises(ValueError, match="CORS misconfiguration"):
            self._guard(["*"], True)

    def test_wildcard_without_credentials_ok(self):
        self._guard(["*"], False)  # must not raise

    def test_explicit_origin_with_credentials_ok(self):
        self._guard(["https://app.example.com"], True)  # must not raise

    def test_empty_origins_with_credentials_ok(self):
        self._guard([], True)  # must not raise


@pytest.mark.asyncio
class TestCorsHeaderBehavior:
    """CORS response headers with default config (wildcard, no credentials)."""

    async def test_no_credentials_header_with_wildcard(self):
        """With wildcard origins + credentials=False, Access-Control-Allow-Credentials
        must not be 'true' — otherwise browsers allow credentialed cross-origin requests."""
        from unittest.mock import patch

        import httpx

        with patch(
            "memanto.app.main._validate_startup_dependencies", return_value=None
        ):
            from memanto.app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as ac:
            resp = await ac.get("/health", headers={"Origin": "https://evil.com"})

        cred_header = resp.headers.get("access-control-allow-credentials", "").lower()
        assert cred_header != "true", (
            "Access-Control-Allow-Credentials must not be 'true' when using wildcard origins"
        )

    async def test_wildcard_returns_star_not_reflected_origin(self):
        """With wildcard + credentials=False, Starlette returns '*', not the request Origin.
        A reflected Origin here would prove credentials mode is still active."""
        from unittest.mock import patch

        import httpx

        with patch(
            "memanto.app.main._validate_startup_dependencies", return_value=None
        ):
            from memanto.app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as ac:
            resp = await ac.get("/health", headers={"Origin": "https://evil.com"})

        origin_header = resp.headers.get("access-control-allow-origin", "")
        assert origin_header in ("", "*"), (
            f"Expected '*' or absent, got '{origin_header}' — "
            "reflected origin means credentials mode is still on"
        )
