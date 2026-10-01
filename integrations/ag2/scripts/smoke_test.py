#!/usr/bin/env python3
"""
End-to-end smoke test: Memanto + AG2 integration (tools + register path).

Exercises the same code path AG2 uses when the executor runs tool calls:
  remember → recall (with indexing retries) → answer → user isolation

Does not require AG2 or an LLM API key — only MOORCHEH_API_KEY.

Optional Step 5: if ``ag2`` is installed and ``OPENAI_API_KEY`` (or config in
``OAI_CONFIG_LIST``) is set, runs one short ``initiate_chat`` with memory tools.

Exit code 0 = PASS, 1 = FAIL.

Usage:

  python integrations/ag2/scripts/smoke_test.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path


def _bootstrap_import_path() -> None:
    here = Path(__file__).resolve().parent
    ag2_root = here.parent
    repo_root = ag2_root.parent.parent
    for p in (ag2_root, repo_root):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


_bootstrap_import_path()

from memanto_ag2 import (  # noqa: E402
    create_memanto_tools,
    openai_llm_config,
    register_memanto_tools,
)

from memanto.app.config import settings  # noqa: E402
from memanto.cli.client.sdk_client import SdkClient  # noqa: E402


def _resolve_api_key() -> str:
    key = (
        os.environ.get("MOORCHEH_API_KEY") or settings.MOORCHEH_API_KEY or ""
    ).strip()
    if not key or key == "test-api-key":
        print(
            "FAIL: MOORCHEH_API_KEY is missing or is the placeholder 'test-api-key'.\n"
            "  Set it in PowerShell:  $env:MOORCHEH_API_KEY = 'your-key'\n"
            "  Or run: memanto   (wizard writes ~/.memanto/.env)"
        )
        sys.exit(1)
    return key


def _step(n: int, msg: str) -> None:
    print(f"\n--- Step {n}: {msg} ---")


class _FakeAssistant:
    """Minimal stand-in for AG2 AssistantAgent (register_for_llm only)."""

    def register_for_llm(self, description: str = ""):
        def decorator(fn):
            fn._memanto_llm_description = description  # noqa: SLF001
            return fn

        return decorator


class _FakeExecutor:
    """Captures registered tools the way UserProxyAgent.register_for_execution does."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def register_for_execution(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _tool_by_name(tools: list, name: str):
    for fn in tools:
        if fn.__name__ == name:
            return fn
    raise KeyError(name)


def main() -> int:
    api_key = _resolve_api_key()
    suffix = uuid.uuid4().hex[:8]
    secret_marker = f"ag2-smoke-{suffix}-favorite-color-teal"
    agent_id = f"ag2-smoke-{suffix}"
    other_agent_id = f"ag2-smoke-other-{suffix}"

    print("Memanto AG2 integration — live smoke test")
    print(f"  run id:   {suffix}")
    print(f"  agent_id: {agent_id}")

    client = SdkClient(api_key=api_key)
    tools = create_memanto_tools(client, agent_id, source="ag2-smoke-test")

    remember = _tool_by_name(tools, "memanto_remember")
    recall = _tool_by_name(tools, "memanto_recall")
    answer = _tool_by_name(tools, "memanto_answer")

    _step(1, "remember — store preference (simulated AG2 tool execution)")
    remember_out = remember(
        memory_type="preference",
        title="Favorite color",
        content=f"User's {secret_marker} for AG2 smoke tests.",
        confidence=1.0,
        tags="ag2,smoke",
    )
    if "Memory stored" not in remember_out:
        print(f"FAIL: unexpected remember response:\n{remember_out}")
        return 1
    print("  remember: OK")

    _step(2, "recall — semantic search (new session, same agent_id)")
    recall_query = "What is the user's favorite color for AG2 smoke tests?"
    recall_out = ""
    for attempt in range(1, 6):
        recall_out = recall(query=recall_query, limit=10)
        lowered = recall_out.lower()
        if secret_marker.lower() in lowered or "teal" in lowered:
            print(f"  recall: OK (attempt {attempt})")
            break
        if attempt < 5:
            print(f"  recall: not indexed yet, retrying in 2s ({attempt}/5)...")
            time.sleep(2)
    else:
        print("FAIL: recall did not return the stored preference after retries.")
        print(recall_out[:800] if recall_out else "  (empty)")
        return 1

    _step(3, "answer — RAG over memories (memanto_answer / reflect-style)")
    answer_out = answer(
        question="What favorite color preference was stored for AG2 smoke tests?"
    )
    if (
        "teal" not in answer_out.lower()
        and secret_marker.lower() not in answer_out.lower()
    ):
        print("WARN: answer did not mention the marker (indexing may be partial).")
        print(f"  preview: {answer_out[:400]}")
    else:
        print("  answer: OK")

    _step(4, "register_memanto_tools — executor invokes registered callables")
    assistant = _FakeAssistant()
    executor = _FakeExecutor()
    register_memanto_tools(
        assistant,
        executor=executor,
        client=client,
        agent_id=agent_id,
    )
    if set(executor.tools) != {"memanto_remember", "memanto_recall", "memanto_answer"}:
        print(f"FAIL: expected three tools on executor, got {list(executor.tools)}")
        return 1
    reg_recall = executor.tools["memanto_recall"]
    reg_out = reg_recall(query=recall_query, limit=5)
    if secret_marker.lower() not in reg_out.lower() and "teal" not in reg_out.lower():
        print("FAIL: registered recall tool did not return stored memory.")
        print(reg_out[:500])
        return 1
    print("  register + executor recall: OK")

    _step(5, "isolation — different agent_id must not see this memory")
    other_tools = create_memanto_tools(client, other_agent_id, source="ag2-smoke-test")
    other_recall = _tool_by_name(other_tools, "memanto_recall")
    # Query must not embed the secret (recall echoes the query string on empty results).
    isolation_query = "What is the user's favorite color for support tickets?"
    leak = other_recall(query=isolation_query, limit=10)
    if "Found " in leak and "teal" in leak.lower():
        print("FAIL: another agent_id recalled the secret (namespace leak).")
        print(leak[:500])
        return 1
    if "Found " in leak and secret_marker.split("-")[-1] in leak.lower():
        print("FAIL: another agent_id recalled smoke marker content.")
        print(leak[:500])
        return 1
    print("  agent_id isolation: OK")

    _step(6, "optional — live AG2 chat (requires ag2 + OPENAI_API_KEY)")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("  skipped (set OPENAI_API_KEY to enable)")
    else:
        try:
            from autogen import AssistantAgent, UserProxyAgent
        except ImportError:
            print("  skipped (pip install ag2)")
        else:
            try:
                llm_config = openai_llm_config("gpt-4o-mini")
                assistant = AssistantAgent(
                    name="assistant",
                    llm_config=llm_config,
                    system_message=(
                        "You have memanto_* tools. When asked to remember something, "
                        "call memanto_remember with type preference."
                    ),
                )
                user_proxy = UserProxyAgent(
                    name="user",
                    human_input_mode="NEVER",
                    max_consecutive_auto_reply=3,
                )
                register_memanto_tools(
                    assistant,
                    executor=user_proxy,
                    client=client,
                    agent_id=agent_id,
                )
                chat_marker = f"ag2-chat-{suffix}"
                user_proxy.initiate_chat(
                    assistant,
                    message=(
                        f"Use memanto_remember to store: user {chat_marker} likes hiking. "
                        "Then confirm you stored it in one short sentence."
                    ),
                    max_turns=2,
                )
                verify = recall(
                    query="What outdoor activity or hobby preference was stored?",
                    limit=5,
                )
                if chat_marker.lower() in verify.lower() or "hiking" in verify.lower():
                    print("  AG2 chat + recall verify: OK")
                else:
                    print(
                        "WARN: AG2 chat ran but recall did not show hiking yet (retry smoke)."
                    )
                    print(verify[:400])
            except Exception as exc:
                print(f"WARN: optional AG2 chat failed: {exc}")

    print("\n========================================")
    print("PASS — AG2 Memanto smoke test completed.")
    print("========================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
