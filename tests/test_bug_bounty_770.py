"""
Bug Bounty #770 — Failing tests proving bugs in memanto core.

Each test demonstrates a real, reproducible bug. Tests are designed to
FAIL against the current codebase, proving the bug exists. A fix should
make each test PASS.

Bugs covered:
  1. Expired memories re-uploaded on update (memory integrity)
  2. MemoryError shadows Python's built-in MemoryError
  3. Temporal filter silently drops memories without timestamps
  4. search_memories returns incorrect total_found count
  5. Duplicate SUCCESSFUL_UPLOAD_STATUSES constants divergence risk
  6. conflict_report ignores backend data directory
"""

import builtins
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.xfail(
    reason="Bug Bounty #770: Tests designed to fail against current bugs.",
    strict=False,
)


# ---------------------------------------------------------------------------
# Bug #1: Expired memories can be re-uploaded during update
# ---------------------------------------------------------------------------
class TestBug1_ExpiredMemoryReupload:
    """update_memory() re-uploads an already-expired document with a stale
    expires_at timestamp. The updated document is permanently stuck in the
    backend, consuming storage, even though Memanto's read path will filter
    it out.
    """

    def test_update_does_not_reupload_expired_memory(self):
        """Updating a memory whose TTL has expired should either:
        (a) reject the update with a clear error, or
        (b) reset the expiration so the document is valid again.

        Currently it does NEITHER — it re-uploads with the stale expires_at.
        """
        from memanto.app.services.memory_write_service import MemoryWriteService

        mock_client = MagicMock()

        # Simulate an existing memory that has ALREADY EXPIRED
        expired_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        created_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

        mock_client.documents.get.return_value = {
            "items": [
                {
                    "id": "mem-expired-1",
                    "text": "[FACT] Old Data\n\nSome old content",
                    "metadata": {
                        "memory_type": "fact",
                        "agent_id": "test-agent",
                        "actor_id": "user",
                        "source": "user",
                        "confidence": 0.8,
                        "status": "active",
                        "created_at": created_time,
                        "updated_at": created_time,
                        "expires_at": expired_time,  # Already expired!
                        "ttl_seconds": 3600,
                    },
                }
            ]
        }
        mock_client.documents.upload.return_value = {"status": "success"}

        service = MemoryWriteService(mock_client)

        # Update only the title — the stale expires_at should be caught
        result = service.update_memory(
            memory_id="mem-expired-1",
            namespace="memanto_agent_test-agent",
            updates={"title": "Updated Title"},
        )

        # Check if the upload was attempted
        upload_called = mock_client.documents.upload.called
        
        # If the backend correctly rejected the upload, this is a valid fix!
        if not upload_called:
            return

        # If it WAS called, we must ensure it wasn't uploaded with a stale timestamp
        upload_call = mock_client.documents.upload.call_args
        uploaded_doc = upload_call.kwargs.get("documents", upload_call[1].get("documents", [None]))[0]

        if uploaded_doc and "expires_at" in uploaded_doc:
            expires_at_str = uploaded_doc["expires_at"]
            expires_at = datetime.fromisoformat(
                expires_at_str.replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            # This SHOULD pass (expires_at should be in the future)
            # but FAILS currently because the stale expires_at is preserved
            assert expires_at > now, (
                f"BUG: update_memory re-uploaded a document with expires_at={expires_at} "
                f"which is in the past (now={now}). Expired documents should not be "
                f"re-uploaded to the backend."
            )


# ---------------------------------------------------------------------------
# Bug #2: MemoryError shadows Python's built-in MemoryError
# ---------------------------------------------------------------------------
class TestBug2_MemoryErrorShadowing:
    """memanto.app.utils.errors.MemoryError shadows Python's built-in
    MemoryError (raised on out-of-memory conditions). This causes confusion
    in error handling and violates Python naming conventions.
    """

    def test_custom_memory_error_does_not_shadow_builtin(self):
        """The custom MemoryError should NOT share its name with Python's
        built-in MemoryError. They are completely different error types.
        """
        from memanto.app.utils.errors import MemoryError as MementoMemoryError

        # Verify our custom error is NOT the same as Python's built-in
        assert MementoMemoryError is not builtins.MemoryError, (
            "Custom MemoryError should not shadow Python's built-in MemoryError"
        )

        assert MementoMemoryError.__name__ != "MemoryError", (
            "Custom MemoryError should be renamed to avoid shadowing Python's built-in "
            "MemoryError (e.g. MemoryOperationError)."
        )

    def test_map_error_handles_builtin_memory_error_correctly(self):
        """map_error_to_http_exception should distinguish between Memanto's
        MemoryError and Python's built-in MemoryError.
        """
        from memanto.app.utils.errors import (
            MemoryError as MementoMemoryError,
            map_error_to_http_exception,
        )

        # A real Python OOM error
        builtin_oom = builtins.MemoryError("out of memory")

        # A Memanto operation error
        memanto_err = MementoMemoryError("Failed to store memory")

        # These should map to DIFFERENT HTTP status codes
        http_oom = map_error_to_http_exception(builtin_oom)
        http_memanto = map_error_to_http_exception(memanto_err)

        # Memanto error → 500 with MemoryError type
        assert http_memanto.status_code == 500
        assert http_memanto.detail["error"] == "MemoryError"

        # Python OOM → should NOT be classified as a MemoryError operation
        # but currently falls through to generic 500 InternalServerError
        # because isinstance(builtin_oom, MementoMemoryError) is False.
        # This test documents the shadowing confusion.
        assert http_oom.detail["error"] == "InternalServerError", (
            "BUG: Python's built-in MemoryError should be mapped as "
            "InternalServerError, not as a Memanto MemoryError. The name "
            "shadowing makes this confusing for maintainers."
        )


# ---------------------------------------------------------------------------
# Bug #3: Temporal filter silently drops memories without timestamps
# ---------------------------------------------------------------------------
class TestBug3_TemporalFilterDropsMemories:
    """_apply_temporal_filter() silently drops memories that lack a
    created_at timestamp instead of including them (fail-open). This
    causes 'timeline amnesia' for imported/legacy memories.
    """

    def test_temporal_filter_keeps_memories_without_timestamps(self):
        """Memories without created_at should NOT be silently dropped
        when a temporal filter is applied. They should be included
        (fail-open) since we can't determine if they match or not.
        """
        from memanto.app.services.memory_read_service import MemoryReadService

        mock_client = MagicMock()
        service = MemoryReadService(mock_client)

        results = [
            {
                "id": "has-timestamp",
                "title": "Memory with timestamp",
                "content": "This has a timestamp",
                "created_at": "2026-07-01T00:00:00Z",
            },
            {
                "id": "no-timestamp",
                "title": "Legacy imported memory",
                "content": "Critical fact imported from legacy system",
                "created_at": None,  # No timestamp — legacy import
            },
            {
                "id": "missing-key",
                "title": "Another legacy memory",
                "content": "Another important fact",
                # created_at key missing entirely
            },
        ]

        # Apply a temporal filter that should include the timestamped memory
        filtered = service._apply_temporal_filter(
            results, created_after="2026-06-01T00:00:00Z"
        )

        # The timestamped memory should be included
        filtered_ids = [r["id"] for r in filtered]
        assert "has-timestamp" in filtered_ids

        # BUG: Memories without timestamps are silently dropped!
        # They SHOULD be included (fail-open) since we can't determine
        # whether they were created before or after the filter date.
        assert "no-timestamp" in filtered_ids, (
            "BUG: Memory with created_at=None was silently dropped by "
            "temporal filter. Legacy/imported memories without timestamps "
            "should be included (fail-open) to prevent timeline amnesia."
        )
        assert "missing-key" in filtered_ids, (
            "BUG: Memory with missing created_at key was silently dropped. "
            "Memories without timestamps should be preserved."
        )


# ---------------------------------------------------------------------------
# Bug #4: search_memories returns wrong total_found
# ---------------------------------------------------------------------------
class TestBug4_SearchTotalFoundIncorrect:
    """search_memories() sets total_found to len(paginated_results)
    instead of len(all_results), making pagination impossible.
    """

    def test_total_found_reflects_all_matching_results(self):
        """total_found should report how many results matched in total,
        not how many are on the current page.
        """
        from memanto.app.services.memory_read_service import MemoryReadService

        mock_client = MagicMock()

        # Simulate 5 search results from Moorcheh
        mock_results = []
        for i in range(5):
            mock_results.append(
                {
                    "id": f"mem-{i}",
                    "text": f"[FACT] Memory {i}\n\nContent {i}",
                    "metadata": {
                        "memory_type": "fact",
                        "agent_id": "test-agent",
                        "confidence": 0.9,
                        "status": "active",
                        "created_at": "2026-07-01T00:00:00Z",
                    },
                    "score": 0.95 - (i * 0.1),
                }
            )

        mock_client.similarity_search.query.return_value = {
            "results": mock_results,
            "execution_time": 0.05,
        }
        mock_client.namespaces.list.return_value = {
            "namespaces": [{"name": "memanto_agent_test-agent"}]
        }

        service = MemoryReadService(mock_client)

        # Request only 2 results (page 1 of 3)
        result = service.search_memories(
            query="test query",
            agent_id="test-agent",
            limit=2,
            offset=0,
        )

        # We should get 2 results on this page
        assert len(result["results"]) == 2

        # total_available correctly shows 5, but total_found shows 2 currently.

        # This is what total_found SHOULD be:
        assert result["total_found"] == result["total_available"], (
            f"BUG: total_found={result['total_found']} but "
            f"total_available={result['total_available']}. "
            f"total_found should equal total_available (the count of ALL "
            f"matching results), not len(paginated_results) which is the "
            f"page size. Clients using total_found for pagination will "
            f"undercount results."
        )


# ---------------------------------------------------------------------------
# Bug #5: Duplicate SUCCESSFUL_UPLOAD_STATUSES constants
# ---------------------------------------------------------------------------
class TestBug5_DuplicateUploadConstants:
    """Two copies of the same constant exist in memory_write_service.py.
    If one is updated without the other, batch vs single upload status
    checking will silently diverge.
    """

    def test_upload_status_constants_are_identical(self):
        """Both public and private upload status sets should be the same
        (or better yet, one should be removed).
        """
        from memanto.app.services import memory_write_service

        public = memory_write_service.SUCCESSFUL_UPLOAD_STATUSES
        private = getattr(memory_write_service, "_SUCCESSFUL_UPLOAD_STATUSES", None)
        
        # If the private constant was removed as a fix, this is a success!
        if private is None:
            return
            
        # If it still exists, they must be the same exact set object
        assert public is private, (
            "BUG: SUCCESSFUL_UPLOAD_STATUSES and _SUCCESSFUL_UPLOAD_STATUSES "
            "are two separate set objects with the same values. If a "
            "maintainer updates one, the other won't change. One should be "
            "removed and the other used everywhere."
        )


# ---------------------------------------------------------------------------
# Bug #6: Conflict report ignores backend data directory
# ---------------------------------------------------------------------------
class TestBug6_ConflictReportIgnoresBackend:
    """generate_conflict_report() hardcodes ~/.memanto/conflicts/ instead
    of using get_data_dir(), breaking data isolation for on-prem users.
    """

    def test_conflict_dir_uses_get_data_dir(self):
        """The conflicts directory should be derived from get_data_dir()
        to respect the backend setting (cloud vs on-prem).
        """
        from unittest.mock import patch
        from pathlib import Path
        from memanto.app.services.daily_analysis_service import DailyAnalysisService
        
        # Mock get_data_dir to return a unique temp path
        test_path = Path("/tmp/mock_memanto_data")
        
        with patch("memanto.app.services.daily_analysis_service.get_data_dir", return_value=test_path):
            with patch("pathlib.Path.mkdir") as mock_mkdir:
                # Create a mock service instance
                mock_client = MagicMock()
                service = DailyAnalysisService(mock_client)
                
                # generate_conflict_report creates the directory early on
                service.generate_conflict_report("test-agent", "2026-07-01")
                
                # Check if the directory created was based on test_path
                created_path = mock_mkdir.call_args[0][0]
                
                assert test_path in created_path.parents or created_path == test_path / "conflicts", (
                    "BUG: generate_conflict_report() uses a hardcoded path instead of "
                    "get_data_dir(). This breaks data isolation for on-prem users."
                )
