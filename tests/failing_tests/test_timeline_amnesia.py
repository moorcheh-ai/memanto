"""
Regression test: Timeline Amnesia in search_as_of (issue #770)

验证 search_as_of 的 supersession 时间判断已修复：
  - 优先用 superseded_at（独立时间戳）判断
  - fallback 到 updated_at（向后兼容旧数据）
  - validate()/detect_contradiction() 不再污染 superseded memory 的 updated_at

运行方式：
    uv run --group dev python -m pytest tests/failing_tests/test_timeline_amnesia.py -v
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_read_service import MemoryReadService


def _iso(dt: datetime) -> str:
    """转成 ISO 字符串（带 Z 后缀，模拟 Moorcheh 存储格式）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _make_memory(
    memory_id: str,
    created_at: datetime,
    updated_at: datetime,
    *,
    superseded_by: str | None = None,
    superseded_at: str | None = None,
    status: str = "active",
    title: str = "memory",
    content: str = "content",
) -> dict:
    """构造一个 _format_memory_item 格式的 memory dict。"""
    return {
        "id": memory_id,
        "title": title,
        "content": content,
        "text": f"[FACT] {title}\n\n{content}",
        "type": "fact",
        "memory_type": "fact",
        "confidence": 0.9,
        "status": status,
        "tags": [],
        "created_at": _iso(created_at),
        "updated_at": _iso(updated_at),
        "superseded_at": superseded_at,
        "expires_at": None,
        "ttl_seconds": None,
        "actor_id": "user-1",
        "source": "user",
        "source_ref": None,
        "scope_type": "agent",
        "scope_id": "agent-1",
        "score": 0.95,
        "provenance": "explicit_statement",
        "validation_count": 0,
        "contradiction_detected": False,
        "superseded_by": superseded_by,
    }


class TestTimelineAmnesiaAsOf:
    """验证 search_as_of 的 supersession 时间判断。"""

    @pytest.fixture
    def read_service(self) -> MemoryReadService:
        """构造一个 MemoryReadService，client 全 mock。"""
        client = MagicMock()
        client.documents.fetch_text_data.return_value = {"items": []}
        return MemoryReadService(client)

    def test_superseded_memory_excluded_when_superseded_at_before_as_of(
        self, read_service, monkeypatch
    ):
        """
        场景：A 在 2026-02-01 被 supersede（superseded_at=2026-02-01），
              但 updated_at 被 validate() 污染到 2026-03-01。
              查询 as_of=2026-02-15。
        期望：A 不应出现（superseded_at=2026-02-01 <= as_of=2026-02-15）。
        """
        memory_a = _make_memory(
            "mem-A",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),  # 被 validate 污染
            superseded_by="mem-B",
            superseded_at=_iso(datetime(2026, 2, 1, tzinfo=timezone.utc)),
            status="superseded",
            title="用户喜欢咖啡",
            content="用户偏好：咖啡",
        )
        memory_b = _make_memory(
            "mem-B",
            created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            status="active",
            title="用户喜欢茶",
            content="用户偏好：茶",
        )

        monkeypatch.setattr(
            read_service,
            "_fetch_all_memories",
            lambda namespaces, **kw: [memory_a, memory_b],
        )

        result = read_service.search_as_of(
            as_of_date="2026-02-15T00:00:00Z",
            agent_id="agent-1",
        )
        result_ids = [m["id"] for m in result["results"]]

        assert "mem-A" not in result_ids, (
            "superseded_at=2026-02-01 <= as_of=2026-02-15，A 应被排除。"
        )
        assert "mem-B" in result_ids

    def test_superseded_memory_included_when_superseded_at_after_as_of(
        self, read_service, monkeypatch
    ):
        """
        场景：A 在 2026-03-01 被 supersede（superseded_at=2026-03-01）。
              查询 as_of=2026-02-15。
        期望：A 应出现（supersession 发生在 as_of 之后，A 当时仍有效）。
        """
        memory_a = _make_memory(
            "mem-A",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
            superseded_by="mem-B",
            superseded_at=_iso(datetime(2026, 3, 1, tzinfo=timezone.utc)),
            status="superseded",
            title="用户喜欢咖啡",
            content="用户偏好：咖啡",
        )

        monkeypatch.setattr(
            read_service,
            "_fetch_all_memories",
            lambda namespaces, **kw: [memory_a],
        )

        result = read_service.search_as_of(
            as_of_date="2026-02-15T00:00:00Z",
            agent_id="agent-1",
        )
        result_ids = [m["id"] for m in result["results"]]

        assert "mem-A" in result_ids, (
            "superseded_at=2026-03-01 > as_of=2026-02-15，A 在 as_of 时仍有效，应出现。"
        )

    def test_legacy_data_falls_back_to_updated_at(self, read_service, monkeypatch):
        """
        向后兼容：旧数据没有 superseded_at，fallback 到 updated_at。
        A.updated_at=2026-02-01 <= as_of=2026-02-15 → A 被排除。
        """
        memory_a = _make_memory(
            "mem-A",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),  # 没有 superseded_at
            superseded_by="mem-B",
            superseded_at=None,
            status="superseded",
        )

        monkeypatch.setattr(
            read_service,
            "_fetch_all_memories",
            lambda namespaces, **kw: [memory_a],
        )

        result = read_service.search_as_of(
            as_of_date="2026-02-15T00:00:00Z",
            agent_id="agent-1",
        )
        result_ids = [m["id"] for m in result["results"]]

        assert "mem-A" not in result_ids, (
            "旧数据 fallback 到 updated_at=2026-02-01 <= as_of=2026-02-15，A 应被排除。"
        )


class TestMemoryRecordSupersession:
    """验证 MemoryRecord 的 supersession 行为。"""

    def test_mark_superseded_sets_superseded_at(self):
        """mark_superseded 应设置独立的 superseded_at 字段。"""
        memory = MemoryRecord(
            id="mem-A",
            type="preference",
            title="测试",
            content="内容",
            scope_type="agent",
            scope_id="agent-1",
            actor_id="user-1",
            source="user",
        )
        assert memory.superseded_at is None

        memory.mark_superseded("mem-B")

        assert memory.superseded_at is not None
        assert memory.superseded_by == "mem-B"
        assert memory.status == "superseded"
        assert memory.updated_at == memory.superseded_at

    def test_validate_skips_superseded_memory(self):
        """validate() 不应操作 superseded memory，避免污染 updated_at。"""
        memory = MemoryRecord(
            id="mem-A",
            type="preference",
            title="测试",
            content="内容",
            scope_type="agent",
            scope_id="agent-1",
            actor_id="user-1",
            source="user",
        )
        memory.mark_superseded("mem-B")
        updated_at_before = memory.updated_at
        validation_count_before = memory.validation_count

        memory.validate()  # 应该被跳过

        assert memory.updated_at == updated_at_before, "updated_at 不应被污染"
        assert memory.validation_count == validation_count_before, "validation_count 不应增加"

    def test_detect_contradiction_skips_superseded_memory(self):
        """detect_contradiction() 不应操作 superseded memory。"""
        memory = MemoryRecord(
            id="mem-A",
            type="fact",
            title="测试",
            content="内容",
            scope_type="agent",
            scope_id="agent-1",
            actor_id="user-1",
            source="user",
        )
        memory.mark_superseded("mem-B")
        updated_at_before = memory.updated_at

        memory.detect_contradiction()  # 应该被跳过

        assert memory.updated_at == updated_at_before, "updated_at 不应被污染"

    def test_validate_works_on_active_memory(self):
        """validate() 仍正常作用于 active memory。"""
        memory = MemoryRecord(
            id="mem-A",
            type="preference",
            title="测试",
            content="内容",
            scope_type="agent",
            scope_id="agent-1",
            actor_id="user-1",
            source="user",
        )
        memory.validate()

        assert memory.validation_count == 1
        assert memory.validated_at is not None

    def test_to_moorcheh_document_includes_superseded_at(self):
        """to_moorcheh_document 应包含 superseded_at 字段。"""
        memory = MemoryRecord(
            id="mem-A",
            type="preference",
            title="测试",
            content="内容",
            scope_type="agent",
            scope_id="agent-1",
            actor_id="user-1",
            source="user",
        )
        memory.mark_superseded("mem-B")

        doc = memory.to_moorcheh_document()

        assert "superseded_at" in doc
        assert doc["superseded_by"] == "mem-B"

    def test_to_moorcheh_document_omits_superseded_at_when_none(self):
        """active memory 的 document 不应包含 superseded_at。"""
        memory = MemoryRecord(
            id="mem-A",
            type="preference",
            title="测试",
            content="内容",
            scope_type="agent",
            scope_id="agent-1",
            actor_id="user-1",
            source="user",
        )
        doc = memory.to_moorcheh_document()
        assert "superseded_at" not in doc
