"""
Regression tests for bugs found and fixed as part of Issue #770 bounty.

Bug 1 (Critical): Permanent memory loss in update_memory — delete-before-upload
  race condition meant a failed upload left the namespace with no document.
  Fix: upload new version first, then delete the old one.

Bug 2 (High): Query injection via metadata_filters — unsanitized key/value pairs
  were interpolated directly into the Moorcheh #key:value filter string.
  Fix: strip '#' and whitespace from caller-supplied filter keys and values.

Bug 3 (High): TTL bypass via malformed expires_at — when expires_at could not
  be parsed the memory was kept (fail-open), allowing it to outlive its TTL.
  Fix: fail closed — exclude the memory when expiry cannot be determined.

Bug 4 (Medium): batch_store_memories silent count mismatch — memories rejected
  for namespace mismatch were counted in total_submitted but not in successful
  or failed, so successful + failed < total_submitted with no explanation.
  Fix: track rejected count separately and include it in the response.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# moorcheh_sdk is a private package not available in CI — stub it out so
# the service modules can be imported without a real installation.
def _stub_moorcheh_sdk() -> None:
    sdk = ModuleType("moorcheh_sdk")
    sdk.MoorchehClient = MagicMock  # type: ignore[attr-defined]
    sdk.AsyncMoorchehClient = MagicMock  # type: ignore[attr-defined]
    types_mod = ModuleType("moorcheh_sdk.types")
    doc_mod = ModuleType("moorcheh_sdk.types.document")
    doc_mod.Document = dict  # type: ignore[attr-defined]
    sdk.types = types_mod  # type: ignore[attr-defined]
    types_mod.document = doc_mod
    exc_mod = ModuleType("moorcheh_sdk.exceptions")
    exc_mod.ConflictError = type("ConflictError", (Exception,), {})  # type: ignore[attr-defined]
    sdk.exceptions = exc_mod  # type: ignore[attr-defined]
    sys.modules.setdefault("moorcheh_sdk", sdk)
    sys.modules.setdefault("moorcheh_sdk.types", types_mod)
    sys.modules.setdefault("moorcheh_sdk.types.document", doc_mod)
    sys.modules.setdefault("moorcheh_sdk.exceptions", exc_mod)

_stub_moorcheh_sdk()


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_moorcheh_client(upload_result=None, delete_result=None, get_result=None):
    client = MagicMock()
    client.documents.upload.return_value = upload_result or {"status": "queued"}
    client.documents.delete.return_value = delete_result or {"actual_deletions": 1}
    client.documents.get.return_value = get_result or {"items": []}
    return client


def _make_existing_memory_data():
    return {
        "id": "mem-001",
        "title": "Original title",
        "content": "Original content",
        "metadata": {
            "type": "fact",
            "scope_type": "agent",
            "scope_id": "agent-42",
            "actor_id": "agent-42",
            "source": "system",
            "confidence": 0.9,
            "status": "active",
            "tags": [],
        },
    }


# ── Bug 1: update_memory race condition ──────────────────────────────────────

class TestUpdateMemoryRaceCondition:

    def test_upload_happens_before_delete_on_success(self):
        """Upload must precede delete so a failed upload cannot lose the original."""
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = _make_moorcheh_client()
        service = MemoryWriteService(client)

        existing = _make_existing_memory_data()
        with patch.object(
            service, "_ensure_namespace", return_value="memanto_agent_agent-42"
        ):
            from memanto.app.services.memory_read_service import MemoryReadService
            with patch.object(
                MemoryReadService, "get_memory", return_value=existing
            ):
                service.update_memory(
                    memory_id="mem-001",
                    namespace="memanto_agent_agent-42",
                    updates={"content": "Updated content"},
                )

        # upload must be called BEFORE delete
        upload_idx = None
        delete_idx = None
        for i, c in enumerate(client.mock_calls):
            if "upload" in str(c):
                upload_idx = i
            if "delete" in str(c):
                delete_idx = i

        assert upload_idx is not None, "upload was never called"
        assert delete_idx is not None, "delete was never called"
        assert upload_idx < delete_idx, (
            f"delete (call #{delete_idx}) happened before upload (call #{upload_idx}) "
            "— a failed upload would permanently destroy the original memory"
        )

        # Verify the uploaded document carries the new content so we know the
        # new version survived into storage before the old one was removed.
        upload_call = client.documents.upload.call_args
        assert upload_call is not None, "upload was never called with arguments"
        documents = upload_call.kwargs.get("documents") or (
            upload_call.args[1] if len(upload_call.args) > 1 else upload_call.args[0] if upload_call.args else []
        )
        assert documents, "upload was called with no documents"
        assert "Updated content" in str(documents), (
            "uploaded document does not contain the updated content — new version was not committed"
        )

    def test_original_preserved_when_upload_fails(self):
        """If upload raises, delete must never be called (original stays intact)."""
        from memanto.app.services.memory_write_service import MemoryWriteService
        from memanto.app.utils.errors import MemoryError

        client = _make_moorcheh_client()
        client.documents.upload.side_effect = RuntimeError("network error")
        service = MemoryWriteService(client)

        existing = _make_existing_memory_data()
        with patch.object(
            service, "_ensure_namespace", return_value="memanto_agent_agent-42"
        ):
            from memanto.app.services.memory_read_service import MemoryReadService
            with patch.object(
                MemoryReadService, "get_memory", return_value=existing
            ):
                with pytest.raises(MemoryError):
                    service.update_memory(
                        memory_id="mem-001",
                        namespace="memanto_agent_agent-42",
                        updates={"content": "Updated content"},
                    )

        client.documents.delete.assert_not_called()


# ── Bug 2: query injection via metadata_filters ───────────────────────────────

class TestQueryInjection:

    def _build(self, query: str, metadata_filters: dict) -> str:
        from memanto.app.services.memory_read_service import MemoryReadService
        svc = MemoryReadService(MagicMock())
        return svc._build_filtered_query(query=query, metadata_filters=metadata_filters)

    def test_hash_in_value_is_stripped(self):
        """A '#' in a filter value must not inject additional filter tokens."""
        result = self._build("test", {"foo": "bar #status:active"})
        # Should not contain the injected #status:active token separately
        assert result.count("#status") == 0, (
            "injected '#status:active' appeared in query — filter injection not blocked"
        )

    def test_hash_in_key_is_stripped(self):
        result = self._build("test", {"#foo": "bar"})
        # The '#' prefix on the key must not double up to '##foo'
        assert "##" not in result

    def test_spaces_in_value_do_not_split_tokens(self):
        """Spaces in filter values must not create multiple tokens."""
        result = self._build("test", {"status": "active extra tokens"})
        # value becomes 'active_extra_tokens' — only one filter token
        token_count = result.count("#status:")
        assert token_count == 1, f"expected 1 #status: token, got {token_count}"
        # the exact normalised token must appear verbatim
        assert "#status:active_extra_tokens" in result, (
            f"expected '#status:active_extra_tokens' in query, got: {result!r}"
        )

    def test_clean_filter_passes_through(self):
        """Normal filters with no injection chars must work correctly."""
        result = self._build("what language does Alex use", {"topic": "python"})
        assert "#topic:python" in result

    def test_empty_key_or_value_skipped(self):
        """Filters that reduce to empty strings after sanitization are dropped."""
        result = self._build("query", {"#": "# "})
        # Both key and value become empty after stripping — no token appended
        assert result.strip() == "query"


# ── Bug 3: TTL bypass via malformed expires_at ────────────────────────────────

class TestTTLEnforcement:

    def _filter(self, memories: list[dict]) -> list[dict]:
        from memanto.app.services.memory_read_service import MemoryReadService
        svc = MemoryReadService(MagicMock())
        return svc._filter_expired_memories(memories)

    def _memory(self, expires_at) -> dict:
        return {"id": "m1", "content": "test", "expires_at": expires_at}

    def test_malformed_expires_at_excludes_memory(self):
        """A memory with an unparseable expires_at must be excluded (fail closed)."""
        result = self._filter([self._memory("not-a-date")])
        assert result == [], (
            "memory with malformed expires_at was kept — TTL bypass possible"
        )

    def test_past_expires_at_excludes_memory(self):
        result = self._filter([self._memory("2020-01-01T00:00:00+00:00")])
        assert result == []

    def test_future_expires_at_keeps_memory(self):
        result = self._filter([self._memory("2099-01-01T00:00:00+00:00")])
        assert len(result) == 1

    def test_no_expires_at_keeps_memory(self):
        result = self._filter([{"id": "m1", "content": "test"}])
        assert len(result) == 1

    def test_none_expires_at_keeps_memory(self):
        result = self._filter([self._memory(None)])
        assert len(result) == 1

    def test_integer_expires_at_excludes_memory(self):
        """A non-string, non-datetime expires_at (e.g. integer) must exclude the memory."""
        result = self._filter([self._memory(12345)])
        assert result == [], (
            "integer expires_at kept the memory — unknown types should fail closed"
        )


# ── Bug 4: batch_store_memories count mismatch ───────────────────────────────

class TestBatchCountMismatch:

    def _make_records(self, n: int, scope_id: str = "agent-42"):
        from memanto.app.core import MemoryRecord
        records = []
        for i in range(n):
            r = MemoryRecord(
                type="fact",
                title=f"Memory {i}",
                content=f"Content {i}",
                scope_type="agent",
                scope_id=scope_id,
                actor_id=scope_id,
                source="test",
                confidence=0.9,
            )
            records.append(r)
        return records

    def test_rejected_counted_separately(self):
        """successful + failed + rejected must equal total_submitted."""
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = _make_moorcheh_client()
        service = MemoryWriteService(client)

        # Two records in different namespaces — one will be rejected
        records = self._make_records(1, scope_id="agent-A") + self._make_records(1, scope_id="agent-B")

        result = service.batch_store_memories(records)

        total = result["total_submitted"]
        accounted = result["successful"] + result["failed"] + result.get("rejected", 0)
        assert accounted == total, (
            f"successful({result['successful']}) + failed({result['failed']}) + "
            f"rejected({result.get('rejected', 'MISSING')}) = {accounted} "
            f"!= total_submitted({total}) — callers cannot trust the counts"
        )

    def test_rejected_key_present_in_response(self):
        """Response must include a 'rejected' key so callers can detect silent drops."""
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = _make_moorcheh_client()
        service = MemoryWriteService(client)
        records = self._make_records(1)

        result = service.batch_store_memories(records)
        assert "rejected" in result, "batch response missing 'rejected' count field"

    def test_same_namespace_has_zero_rejected(self):
        """A clean batch with one namespace must have rejected=0."""
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = _make_moorcheh_client()
        service = MemoryWriteService(client)
        records = self._make_records(3, scope_id="agent-42")

        result = service.batch_store_memories(records)
        assert result.get("rejected", 0) == 0
