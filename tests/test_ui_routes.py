"""
Tests for the web UI's per-page URLs.

The UI is a single-page app: /ui and every /ui/<page> must return the same
index.html (the client picks the page from the URL), while /ui/static/* must
still be served by the static mount.
"""

import pytest
from fastapi.testclient import TestClient

from memanto.app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("path", ["/ui", "/ui/agents", "/ui/unknown-page"])
def test_ui_paths_serve_index(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "no-store" in r.headers["cache-control"]
    assert 'data-page="dashboard"' in r.text


def test_static_assets_not_shadowed_by_page_route(client):
    r = client.get("/ui/static/logo.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")


def test_nested_ui_paths_are_not_found(client):
    assert client.get("/ui/agents/extra").status_code == 404
