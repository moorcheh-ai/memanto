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
        assert self.fn(None, base_dir=self._base(tmp_path)) is None

    def test_valid_path_inside_base(self, tmp_path):
        base = self._base(tmp_path)
        result = self.fn(
            str(base / "summaries" / "agent1_2026-06-25.md"), base_dir=base
        )
        assert result is not None
        assert str(result).startswith(str(base))

    def test_relative_path_anchored_to_base(self, tmp_path):
        base = self._base(tmp_path)
        result = self.fn("summaries/agent1.md", base_dir=base)
        assert result == (base / "summaries" / "agent1.md").resolve()

    def test_absolute_traversal_rejected(self, tmp_path):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self.fn("/etc/passwd", base_dir=self._base(tmp_path))
        assert exc.value.status_code == 400

    def test_dotdot_traversal_rejected(self, tmp_path):
        from fastapi import HTTPException

        base = self._base(tmp_path)
        evil = str(base / ".." / ".." / "etc" / "cron.d" / "evil")
        with pytest.raises(HTTPException) as exc:
            self.fn(evil, base_dir=base)
        assert exc.value.status_code == 400

    def test_cron_path_rejected(self, tmp_path):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            self.fn("/etc/cron.d/backdoor", base_dir=self._base(tmp_path))

    def test_ssh_authorized_keys_rejected(self, tmp_path):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            self.fn("/root/.ssh/authorized_keys", base_dir=self._base(tmp_path))


class TestDailyAnalysisOutputPath:
    """validate_output_path is called from DailyAnalysisService.generate_summary."""

    def test_traversal_raises_http_400(self, tmp_path):
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
        from memanto.app.utils.validation import validate_output_path

        base = tmp_path / ".memanto"
        base.mkdir(parents=True)
        result = validate_output_path(str(base / "out.md"), base_dir=base)
        assert result is not None


class TestMemoryExportOutputPath:
    """memory_export_service also applies the guard when output_path is given."""

    def test_traversal_raises(self, tmp_path):
        from fastapi import HTTPException

        from memanto.app.services.memory_export_service import MemoryExportService

        svc = MemoryExportService.__new__(MemoryExportService)
        svc.exports_dir = tmp_path / ".memanto" / "exports"
        svc.exports_dir.mkdir(parents=True)

        with pytest.raises(HTTPException) as exc:
            svc.write_memory_md("agent1", "# content", output_path="/etc/passwd")
        assert exc.value.status_code == 400
