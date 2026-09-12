"""Regression tests for the migration-endpoint hardening (bounty #1852).

Two previously unguarded primitives are covered here:

1. ``normalize_host`` must only accept the official Langfuse cloud regions.
   A caller-controlled ``host`` previously reached any URL the server process
   could connect to, letting an attacker pivot requests (and leak the Basic
   auth header) toward arbitrary destinations (SSRF).
2. ``_safe_migrate_source_path`` must confine the ``file`` parameter of the
   migrate endpoints to the provider's migrate directory. Previously any
   server-side ``.md``/JSON path was parsed and reflected back in the dry-run
   response (arbitrary file read).
"""

import pytest

from memanto.cli.analyze.langfuse_export import normalize_host


class TestLangfuseHostAllowlist:
    def test_defaults_to_eu_cloud(self):
        assert normalize_host(None) == "https://cloud.langfuse.com"
        assert normalize_host("") == "https://cloud.langfuse.com"

    def test_accepts_official_regions(self):
        assert normalize_host("https://us.cloud.langfuse.com") == (
            "https://us.cloud.langfuse.com"
        )
        assert (
            normalize_host("us.cloud.langfuse.com") == "https://us.cloud.langfuse.com"
        )
        # Trailing slash is normalized away before the allowlist check.
        assert normalize_host("https://cloud.langfuse.com/") == (
            "https://cloud.langfuse.com"
        )

    @pytest.mark.parametrize(
        "host",
        [
            "http://127.0.0.1:9999",
            "http://localhost:3000",
            "http://169.254.169.254/latest/meta-data",
            "http://[::1]:3000",
            "https://langfuse.internal",
            "http://10.0.0.5:8080",
            "file:///etc/passwd",
        ],
    )
    def test_rejects_arbitrary_and_internal_hosts(self, host):
        with pytest.raises(ValueError, match="official cloud regions"):
            normalize_host(host)


class TestMigrateFileConfinement:
    """The migrate ``file`` parameter must not escape the migrate directory."""

    @pytest.fixture()
    def guard(self, tmp_path, monkeypatch):
        from memanto.app.ui.routes import ui_router

        class _StubManager:
            def get_migrate_dir(self, provider: str):
                base = tmp_path / "migrate" / provider
                base.mkdir(parents=True, exist_ok=True)
                return base

        monkeypatch.setattr(ui_router, "_config_manager", _StubManager())
        return ui_router._safe_migrate_source_path

    def test_relative_path_resolves_inside_migrate_dir(self, guard, tmp_path):
        target = tmp_path / "migrate" / "okf" / "bundle.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")

        resolved = guard("bundle.json", "okf")
        assert resolved == target.resolve()

    def test_absolute_path_inside_migrate_dir_allowed(self, guard, tmp_path):
        target = tmp_path / "migrate" / "mem0" / "export.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")

        resolved = guard(str(target), "mem0")
        assert resolved == target.resolve()

    def test_absolute_path_outside_rejected(self, guard, tmp_path):
        secret = tmp_path / "secret.md"
        secret.write_text("victim data", encoding="utf-8")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            guard(str(secret), "okf")
        assert exc.value.status_code == 400

    def test_traversal_escape_rejected(self, guard):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            guard("../../../../etc/passwd", "okf")
        assert exc.value.status_code == 400

    def test_provider_dirs_are_isolated(self, guard, tmp_path):
        """A file valid for provider A must not be readable through provider B."""
        other = tmp_path / "migrate" / "mem0" / "export.json"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("{}", encoding="utf-8")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            guard(str(other), "okf")
        assert exc.value.status_code == 400
