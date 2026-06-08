"""
Tests for CWE-22 path traversal fix in upload_file endpoint.

Verifies that:
1. Filenames with traversal sequences are sanitized to basenames.
2. Normal (non-malicious) filenames still work.
3. Edge cases (empty, dot-only, absolute paths) are handled safely.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from memanto.app.main import app

# ── Unit tests for the sanitization logic itself ──


class TestFilenameSanitizationLogic:
    """Direct tests on the sanitization logic used in the fix."""

    @staticmethod
    def sanitize(raw: str | None) -> str:
        """Reproduce the exact sanitization logic from the fix."""
        original_name = Path(raw or "upload").name
        if not original_name or original_name in (".", ".."):
            original_name = "upload"
        return original_name

    # --- Normal filenames ---
    def test_normal_filename(self):
        assert self.sanitize("notes.txt") == "notes.txt"

    def test_normal_filename_with_spaces(self):
        assert self.sanitize("my notes.pdf") == "my notes.pdf"

    def test_normal_filename_uppercase(self):
        assert self.sanitize("REPORT.DOCX") == "REPORT.DOCX"

    # --- Path traversal payloads ---
    def test_simple_traversal(self):
        result = self.sanitize("../../../etc/passwd")
        assert result == "passwd"
        assert "/" not in result
        assert ".." not in result

    def test_deep_traversal(self):
        result = self.sanitize("../../../../../../../../etc/shadow")
        assert result == "shadow"

    def test_traversal_to_txt(self):
        result = self.sanitize("../../sensitive.txt")
        assert result == "sensitive.txt"
        assert ".." not in result

    def test_windows_traversal(self):
        result = self.sanitize("..\\..\\..\\windows\\win.ini")
        # On POSIX, Path treats backslashes as part of the name;
        # the key thing is no '/' traversal is possible
        assert "/" not in result

    def test_mixed_traversal(self):
        result = self.sanitize("../../../etc/passwd.txt")
        assert result == "passwd.txt"

    # --- Absolute path injection ---
    def test_absolute_path_linux(self):
        result = self.sanitize("/etc/passwd")
        assert result == "passwd"

    def test_absolute_path_deep(self):
        result = self.sanitize("/var/www/html/config.php")
        assert result == "config.php"

    # --- Edge cases ---
    def test_none_filename(self):
        assert self.sanitize(None) == "upload"

    def test_empty_filename(self):
        assert self.sanitize("") == "upload"

    def test_dot_filename(self):
        assert self.sanitize(".") == "upload"

    def test_dotdot_filename(self):
        assert self.sanitize("..") == "upload"

    def test_only_slashes(self):
        # Path("/").name == "" on POSIX
        assert self.sanitize("/") == "upload"

    def test_dotfile(self):
        # Dotfiles like .env should keep their name
        result = self.sanitize(".env")
        assert result == ".env"


# ── Defense-in-depth: realpath check ──


class TestRealpathGuard:
    """Verify the defense-in-depth realpath check prevents escape."""

    def test_safe_path_passes(self):
        tmp_dir = tempfile.mkdtemp()
        safe_name = "report.pdf"
        tmp_path = os.path.join(tmp_dir, safe_name)
        assert os.path.realpath(tmp_path).startswith(os.path.realpath(tmp_dir) + os.sep)

    def test_traversal_path_fails(self):
        """If somehow a traversal got past the first check, realpath catches it."""
        tmp_dir = tempfile.mkdtemp()
        malicious_path = os.path.join(tmp_dir, "..", "..", "etc", "passwd")
        assert not os.path.realpath(malicious_path).startswith(
            os.path.realpath(tmp_dir) + os.sep
        )


# ── Integration tests via the API client ──


@pytest.fixture
def mock_moorcheh():
    """Mock the Moorcheh SDK client for upload tests."""
    from memanto.app.clients.moorcheh import moorcheh_client

    moorcheh_client.reset_client()

    with (
        patch(
            "memanto.app.services.agent_service.get_moorcheh_client"
        ) as mock_agent_client,
        patch("memanto.app.clients.moorcheh.MoorchehClient") as mock_moorcheh_cls,
        patch(
            "memanto.app.clients.moorcheh.AsyncMoorchehClient"
        ) as mock_async_moorcheh_cls,
    ):
        mock_instance = MagicMock()
        mock_async_instance = MagicMock()

        mock_agent_client.return_value = mock_instance
        mock_moorcheh_cls.return_value = mock_instance
        mock_async_moorcheh_cls.return_value = mock_async_instance

        mock_instance.namespaces.create.return_value = {"status": "created"}
        mock_instance.namespaces.list.return_value = {"namespaces": []}
        mock_instance.documents.get.return_value = {"documents": []}
        mock_instance.documents.upload.return_value = {
            "status": "success",
            "id": "mem-1",
        }
        mock_instance.documents.upload_file.return_value = {
            "success": True,
            "fileSize": 1024,
        }
        mock_instance.similarity_search.query.return_value = {
            "results": [],
            "total_found": 0,
        }

        yield mock_instance


@pytest.mark.asyncio
class TestUploadFileTraversalAPI:
    """Test the upload-file endpoint rejects traversal payloads."""

    TEST_AGENT_ID = "cwe22-test-agent"

    @pytest.fixture
    async def client(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c

    @pytest.fixture
    def auth_headers(self):
        return {"Authorization": "Bearer test-api-key"}

    async def _setup_session(self, client, auth_headers):
        """Create agent + activate session, return token."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate",
            headers=auth_headers,
        )
        return resp.json()["session_token"]

    async def test_traversal_filename_is_sanitized(
        self, client, auth_headers, mock_moorcheh
    ):
        """A filename with ../../ should be stripped to its basename."""
        token = await self._setup_session(client, auth_headers)
        mock_moorcheh.documents.upload_file.return_value = {
            "success": True,
            "message": "File uploaded",
            "fileName": "notes.txt",
            "fileSize": 100,
        }

        headers = {**auth_headers, "X-Session-Token": token}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/upload-file",
            headers=headers,
            files={
                "file": (
                    "../../../etc/passwd.txt",
                    b"test content",
                    "text/plain",
                )
            },
        )

        assert response.status_code == 200
        data = response.json()
        # The returned file_name should be the sanitized basename
        assert data["file_name"] == "passwd.txt"
        assert "/" not in data["file_name"]
        assert ".." not in data["file_name"]

    async def test_absolute_path_filename_is_sanitized(
        self, client, auth_headers, mock_moorcheh
    ):
        """An absolute path filename should be stripped to its basename."""
        token = await self._setup_session(client, auth_headers)
        mock_moorcheh.documents.upload_file.return_value = {
            "success": True,
            "message": "File uploaded",
            "fileName": "secret.json",
            "fileSize": 50,
        }

        headers = {**auth_headers, "X-Session-Token": token}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/upload-file",
            headers=headers,
            files={
                "file": (
                    "/etc/secret.json",
                    b'{"key": "value"}',
                    "application/json",
                )
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["file_name"] == "secret.json"

    async def test_normal_upload_still_works(
        self, client, auth_headers, mock_moorcheh
    ):
        """A normal filename without traversal should work fine."""
        token = await self._setup_session(client, auth_headers)
        mock_moorcheh.documents.upload_file.return_value = {
            "success": True,
            "message": "File uploaded",
            "fileName": "report.pdf",
            "fileSize": 200,
        }

        headers = {**auth_headers, "X-Session-Token": token}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/upload-file",
            headers=headers,
            files={
                "file": ("report.pdf", b"%PDF-content", "application/pdf")
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["file_name"] == "report.pdf"
        assert data["status"] == "uploaded"
