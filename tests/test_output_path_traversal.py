"""
Tests for output_path traversal fix (#770).

Verifies that an authenticated caller cannot write AI-generated summaries to
arbitrary filesystem paths via the output_path parameter.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("MOORCHEH_API_KEY", "test-api-key")


class TestValidateOutputPath:
    """Unit tests for validate_output_path()."""

    def setup_method(self):
        from memanto.app.utils.validation import validate_output_path

        self.fn = validate_output_path

    def _base(self, tmp_path: Path) -> Path:
        base = tmp_path / ".memanto"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def test_none_returns_none(self, tmp_path):
        """Verify passing None returns None without error."""
        assert self.fn(None, base_dir=self._base(tmp_path)) is None

    def test_valid_path_inside_base(self, tmp_path):
        """Verify valid path located inside base directory is accepted."""
        base = self._base(tmp_path)
        result = self.fn(
            str(base / "summaries" / "agent1_2026-06-25.md"), base_dir=base
        )
        assert result is not None
        assert str(result).startswith(str(base))

    def test_relative_path_anchored_to_base(self, tmp_path):
        """Verify relative path resolves properly relative to base directory."""
        base = self._base(tmp_path)
        result = self.fn("summaries/agent1.md", base_dir=base)
        assert result == (base / "summaries" / "agent1.md").resolve()

    def test_absolute_traversal_rejected(self, tmp_path):
        """Verify absolute path escaping base directory is rejected with 400."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self.fn("/etc/passwd", base_dir=self._base(tmp_path))
        assert exc.value.status_code == 400

    def test_dotdot_traversal_rejected(self, tmp_path):
        """Verify parent directory traversal (..) is rejected with 400."""
        from fastapi import HTTPException

        base = self._base(tmp_path)
        evil = str(base / ".." / ".." / "etc" / "cron.d" / "evil")
        with pytest.raises(HTTPException) as exc:
            self.fn(evil, base_dir=base)
        assert exc.value.status_code == 400

    def test_cron_path_rejected(self, tmp_path):
        """Verify targeting cron.d paths is rejected with 400."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            self.fn("/etc/cron.d/backdoor", base_dir=self._base(tmp_path))

    def test_ssh_authorized_keys_rejected(self, tmp_path):
        """Verify targeting ssh authorized_keys is rejected with 400."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            self.fn("/root/.ssh/authorized_keys", base_dir=self._base(tmp_path))

    def test_root_directory_target_rejected(self, tmp_path):
        """Verify targeting base directory root directly is rejected with 400."""
        from fastapi import HTTPException

        base = self._base(tmp_path)
        with pytest.raises(HTTPException) as exc:
            self.fn(".", base_dir=base)
        assert exc.value.status_code == 400
        assert "root storage directory" in exc.value.detail

        with pytest.raises(HTTPException) as exc2:
            self.fn(str(base), base_dir=base)
        assert exc2.value.status_code == 400

    def test_reserved_internal_targets_rejected(self, tmp_path):
        """Verify targeting reserved internal directories and files is rejected with 400."""
        from fastapi import HTTPException

        base = self._base(tmp_path)
        for target in [
            "agents/victim.json",
            "sessions/active.json",
            "tokens/token.json",
            "config.json",
            "secret_key",
            ".env",
            "exports",
            "exports/victim_bundle",
        ]:
            with pytest.raises(HTTPException) as exc:
                self.fn(target, base_dir=base)
            assert exc.value.status_code == 400
            assert "reserved internal path" in exc.value.detail


class TestDailyAnalysisOutputPath:
    """validate_output_path is called from DailyAnalysisService.generate_summary."""

    def test_traversal_raises_http_400(self, tmp_path):
        """Verify summary generation with traversal path raises HTTPException 400."""
        from fastapi import HTTPException

        from memanto.app.services.daily_analysis_service import DailyAnalysisService

        svc = DailyAnalysisService.__new__(DailyAnalysisService)
        svc.sessions_dir = tmp_path / "sessions"
        svc.sessions_dir.mkdir(parents=True)
        svc.summaries_dir = tmp_path / ".memanto" / "summaries"
        svc.summaries_dir.mkdir(parents=True)

        with pytest.raises(HTTPException) as exc:
            with patch(
                "memanto.app.services.daily_analysis_service.validate_output_path",
                side_effect=HTTPException(status_code=400, detail="traversal blocked"),
            ):
                svc.generate_summary(
                    "agent1", "2026-06-25", output_path="/etc/cron.d/evil"
                )
        assert exc.value.status_code == 400

    def test_valid_output_path_accepted(self, tmp_path):
        """Verify valid output path is returned successfully."""
        from memanto.app.utils.validation import validate_output_path

        base = tmp_path / ".memanto"
        base.mkdir(parents=True)
        result = validate_output_path(str(base / "out.md"), base_dir=base)
        assert result is not None


class TestMemoryExportOutputPath:
    """memory_export_service also applies the guard when output_path is given."""

    def test_traversal_raises(self, tmp_path):
        """Verify MemoryExportService rejects traversal output path."""
        from fastapi import HTTPException

        from memanto.app.services.memory_export_service import MemoryExportService

        svc = MemoryExportService.__new__(MemoryExportService)
        svc.exports_dir = tmp_path / ".memanto" / "exports"
        svc.exports_dir.mkdir(parents=True)

        with pytest.raises(HTTPException) as exc:
            svc.write_memory_md("agent1", "# content", output_path="/etc/passwd")
        assert exc.value.status_code == 400
