"""
Tests for unauthenticated API schema disclosure fix (#1852).

The server binds 0.0.0.0 by default, so the interactive docs and the OpenAPI
schema must be disabled by default (MEMANTO_ENABLE_DOCS=false) instead of
being enumerable by any network peer. MEMANTO_ENABLE_DOCS=true opts back in.
"""

import importlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from memanto.app.config import settings

DOCS_ENDPOINTS = ("/docs", "/redoc", "/openapi.json")


# memanto.app.main builds the FastAPI app at import time from the settings
# singleton, so toggling the flag requires a fresh module import.
@pytest.fixture
def reloaded_main(monkeypatch):
    import memanto.app.main as main

    def _reload(enabled: bool) -> None:
        monkeypatch.setattr(settings, "MEMANTO_ENABLE_DOCS", enabled)
        importlib.reload(main)

    yield _reload
    # Restore the shipped default state for later tests, regardless of order.
    monkeypatch.setattr(settings, "MEMANTO_ENABLE_DOCS", False)
    importlib.reload(main)


class TestDocsAccessDefault:
    """Docs/schema are inaccessible unless MEMANTO_ENABLE_DOCS is set."""

    def test_enable_docs_defaults_to_false(self):
        assert settings.MEMANTO_ENABLE_DOCS is False

    def test_docs_routes_disabled_on_default_app(self):
        import memanto.app.main as main

        assert main.app.docs_url is None
        assert main.app.redoc_url is None
        assert main.app.openapi_url is None

        with patch(
            "memanto.app.main._validate_startup_dependencies", return_value=None
        ):
            with TestClient(main.app) as client:
                for path in DOCS_ENDPOINTS:
                    assert client.get(path).status_code == 404, (
                        f"{path} must be disabled by default"
                    )


class TestDocsAccessEnabled:
    """MEMANTO_ENABLE_DOCS=true re-enables docs and the OpenAPI schema."""

    def test_schema_disclosure_opt_in(self, reloaded_main):
        reloaded_main(enabled=True)
        import memanto.app.main as main

        assert main.app.docs_url == "/docs"
        assert main.app.redoc_url == "/redoc"
        assert main.app.openapi_url == "/openapi.json"

        with patch(
            "memanto.app.main._validate_startup_dependencies", return_value=None
        ):
            with TestClient(main.app) as client:
                for path in DOCS_ENDPOINTS:
                    assert client.get(path).status_code == 200, (
                        f"{path} must be reachable when MEMANTO_ENABLE_DOCS=true"
                    )

    def test_flag_toggles_back_to_disabled(self, reloaded_main):
        reloaded_main(enabled=True)
        reloaded_main(enabled=False)
        import memanto.app.main as main

        assert main.app.docs_url is None
        with patch(
            "memanto.app.main._validate_startup_dependencies", return_value=None
        ):
            with TestClient(main.app) as client:
                assert client.get("/docs").status_code == 404
