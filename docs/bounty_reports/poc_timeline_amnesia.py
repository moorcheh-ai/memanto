"""
独立 PoC：验证 search_as_of 的 Timeline Amnesia bug (issue #770)

不依赖 pytest，可直接 `python docs/bounty_reports/poc_timeline_amnesia.py` 运行。

bug 描述：
    MemoryReadService.search_as_of 用 memory['updated_at'] 判断 supersession
    发生的时间。但 updated_at 会被 validate() / detect_contradiction() /
    update_memory() 等多种操作刷新，导致 supersession 时间被错误判定为更晚，
    进而让 point-in-time 查询返回已经被 supersede 的记忆。

正确行为：
    as_of_date 之前已被 supersede 的记忆不应出现在 search_as_of 结果中。

运行方式：
    cd <memanto repo root>
    python docs/bounty_reports/poc_timeline_amnesia.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

# 确保 memanto 包可被导入
sys.path.insert(0, ".")

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_read_service import MemoryReadService


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def make_memory(
    memory_id: str,
    created_at: datetime,
    updated_at: datetime,
    *,
    superseded_by: str | None = None,
    status: str = "active",
    title: str = "memory",
    content: str = "content",
) -> dict:
    """构造 _format_memory_item 格式的 memory dict。"""
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
        "created_at": iso(created_at),
        "updated_at": iso(updated_at),
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


def main() -> int:
    print("=" * 70)
    print("PoC: Timeline Amnesia in search_as_of (issue #770)")
    print("=" * 70)

    # ── 场景 1：BUG 复现（无 superseded_at 字段，fallback 到被污染的 updated_at）──
    #
    # 时间线：
    #   2026-01-01  A 创建（"用户喜欢咖啡"）
    #   2026-02-01  A 被 B supersede（mark_superseded 刷新 updated_at=2026-02-01）
    #   2026-03-01  A 被错误地 validate()，updated_at 被刷新为 2026-03-01
    #   查询 as_of = 2026-02-15
    #
    # 期望：A 不应出现（2026-02-15 时 A 已被 supersede）
    # 旧数据（无 superseded_at）：fallback 到 updated_at，A 错误出现

    memory_a_legacy = make_memory(
        "mem-A-legacy",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),  # 被 validate 污染
        superseded_by="mem-B-legacy",
        status="superseded",
        title="用户喜欢咖啡(旧数据)",
        content="用户偏好：咖啡",
    )
    memory_b_legacy = make_memory(
        "mem-B-legacy",
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        status="active",
        title="用户喜欢茶(旧数据)",
        content="用户偏好：茶",
    )

    client = MagicMock()
    read_service = MemoryReadService(client)
    read_service._fetch_all_memories = lambda namespaces, **kw: [
        memory_a_legacy,
        memory_b_legacy,
    ]

    result = read_service.search_as_of(
        as_of_date="2026-02-15T00:00:00Z",
        agent_id="agent-1",
    )
    result_ids = [m["id"] for m in result["results"]]

    print(f"\n[场景 1] 旧数据（无 superseded_at 字段）—— 验证向后兼容 fallback")
    print(f"  时间线：2026-01-01 A创建 → 2026-02-01 A被supersede → 2026-03-01 updated_at被污染")
    print(f"  查询 as_of = 2026-02-15")
    print(f"  search_as_of 返回: {result_ids}")
    print(f"  说明：旧数据没有 superseded_at，fallback 到 updated_at（被污染），A 仍错误出现。")
    print(f"  这是已知限制 —— 修复是 forward-looking 的，新 supersede 的 memory 会有 superseded_at。")

    # ── 场景 2：修复后行为（有 superseded_at，正确排除）──
    #
    # 同样时间线，但 A 有 superseded_at=2026-02-01（mark_superseded 设置）
    # 即使 updated_at=2026-03-01（被污染），search_as_of 用 superseded_at 判断

    memory_a_fixed = make_memory(
        "mem-A-fixed",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),  # 被 validate 污染
        superseded_by="mem-B-fixed",
        status="superseded",
        title="用户喜欢咖啡(修复后)",
        content="用户偏好：咖啡",
    )
    # 关键：superseded_at 记录真正的 supersession 时间
    memory_a_fixed["superseded_at"] = iso(datetime(2026, 2, 1, tzinfo=timezone.utc))

    memory_b_fixed = make_memory(
        "mem-B-fixed",
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        status="active",
        title="用户喜欢茶(修复后)",
        content="用户偏好：茶",
    )

    read_service._fetch_all_memories = lambda namespaces, **kw: [
        memory_a_fixed,
        memory_b_fixed,
    ]

    result_fixed = read_service.search_as_of(
        as_of_date="2026-02-15T00:00:00Z",
        agent_id="agent-1",
    )
    result_ids_fixed = [m["id"] for m in result_fixed["results"]]

    print(f"\n[场景 2] 修复后（有 superseded_at=2026-02-01）—— 验证 bug 已修复")
    print(f"  时间线同上，但 A.superseded_at = 2026-02-01（mark_superseded 设置）")
    print(f"  查询 as_of = 2026-02-15")
    print(f"  search_as_of 返回: {result_ids_fixed}")

    bug_fixed = "mem-A-fixed" not in result_ids_fixed
    if bug_fixed:
        print(f"  [OK] 记忆 A 被正确排除！superseded_at=2026-02-01 <= as_of=2026-02-15")
        print(f"  即使 updated_at=2026-03-01 被污染，search_as_of 仍用 superseded_at 判断。")
    else:
        print(f"  [FAIL] 记忆 A 仍错误出现，修复未生效！")
        return 1

    # ── 场景 3：mark_superseded 正确设置 superseded_at ──
    print(f"\n[场景 3] 验证 MemoryRecord.mark_superseded 正确设置 superseded_at")
    memory = MemoryRecord(
        id="mem-X",
        type="preference",
        title="测试",
        content="测试内容",
        scope_type="agent",
        scope_id="agent-1",
        actor_id="user-1",
        source="user",
    )
    memory.mark_superseded("mem-Y")
    has_field = hasattr(memory, "superseded_at") and memory.superseded_at is not None
    print(f"  mark_superseded 后：superseded_at = {memory.superseded_at}")
    if has_field:
        print(f"  [OK] superseded_at 字段已正确设置")
    else:
        print(f"  [FAIL] superseded_at 字段未设置")
        return 1

    # ── 场景 4：validate/detect_contradiction 不污染 superseded memory ──
    print(f"\n[场景 4] 验证 validate/detect_contradiction 不操作 superseded memory")
    memory2 = MemoryRecord(
        id="mem-X2",
        type="preference",
        title="测试2",
        content="测试内容2",
        scope_type="agent",
        scope_id="agent-1",
        actor_id="user-1",
        source="user",
    )
    memory2.mark_superseded("mem-Y2")
    updated_at_before = memory2.updated_at
    memory2.validate()  # 应该被跳过
    memory2.detect_contradiction()  # 应该被跳过
    no_pollution = memory2.updated_at == updated_at_before
    print(f"  supersede 后 updated_at = {updated_at_before}")
    print(f"  调用 validate() + detect_contradiction() 后 updated_at = {memory2.updated_at}")
    if no_pollution:
        print(f"  [OK] updated_at 未被污染（validate/detect_contradiction 被正确跳过）")
    else:
        print(f"  [FAIL] updated_at 被污染")
        return 1

    print(f"\n{'=' * 70}")
    print(f"总结：所有修复场景验证通过")
    print(f"  - 场景 2: search_as_of 用 superseded_at 正确排除已 supersede 的记忆")
    print(f"  - 场景 3: mark_superseded 正确设置 superseded_at")
    print(f"  - 场景 4: validate/detect_contradiction 不再污染 superseded memory 的 updated_at")
    print(f"{'=' * 70}")
    return 0


def demo_root_cause_on_memory_record() -> None:
    """直接在 MemoryRecord 上演示 updated_at 被污染。"""
    print("\n" + "=" * 70)
    print("根因演示：MemoryRecord.updated_at 被多种操作污染")
    print("=" * 70)

    memory = MemoryRecord(
        id="mem-A",
        type="preference",
        title="用户喜欢咖啡",
        content="用户偏好：咖啡",
        scope_type="agent",
        scope_id="agent-1",
        actor_id="user-1",
        source="user",
    )

    # 模拟 supersede
    memory.mark_superseded("mem-B")
    supersede_time = memory.updated_at
    print(f"\nmark_superseded 后：")
    print(f"  status        = {memory.status}")
    print(f"  superseded_by = {memory.superseded_by}")
    print(f"  updated_at    = {supersede_time}")
    print(f"  superseded_at = {getattr(memory, 'superseded_at', '<字段不存在>')}")

    # 模拟 30 天后调用 validate()（错误操作，但没有被阻止）
    later = supersede_time + timedelta(days=30)
    memory.validated_at = later
    memory.updated_at = later
    memory.validation_count += 1
    print(f"\n30 天后调用 validate() 后：")
    print(f"  status        = {memory.status}")
    print(f"  updated_at    = {memory.updated_at}  (被污染！远晚于 supersede 时间)")
    print(f"  supersede 时间信息已丢失 — search_as_of 无法判断真正的 supersession 时间")


if __name__ == "__main__":
    exit_code = main()
    demo_root_cause_on_memory_record()
    print(f"\nPoC 退出码: {exit_code} (1=bug存在, 0=bug已修复)")
    sys.exit(exit_code)
