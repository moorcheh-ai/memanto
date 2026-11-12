#!/usr/bin/env python3
"""
End-to-end smoke test: Memanto + AgentCore-style adapter (two ephemeral runtime sessions).

Simulates:
  Session A — user states a preference → after_turn (retain)
  Session B — new runtimeSessionId, same userId → before_turn (recall) → fake Bedrock agent

Exit code 0 = PASS, 1 = FAIL.

Usage (from repo root or integrations/agentcore):

  python integrations/agentcore/scripts/smoke_test.py

Requires MOORCHEH_API_KEY in the environment or ~/.memanto/.env (same as `memanto` CLI).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path


def _bootstrap_import_path() -> None:
    """Allow imports without manually setting PYTHONPATH."""
    here = Path(__file__).resolve().parent
    agentcore_root = here.parent  # contains memanto_agentcore/ package
    repo_root = agentcore_root.parent.parent
    for p in (agentcore_root, repo_root):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


_bootstrap_import_path()

from memanto_agentcore import MemantoRuntimeAdapter, TurnContext  # noqa: E402

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


async def _fake_bedrock_agent(payload: dict, memory_context: str) -> dict:
    """Stand-in for your AgentCore agent + Bedrock call."""
    prompt = payload.get("prompt", "")
    if memory_context:
        reply = (
            f"Based on past context, I see prior memories.\n"
            f"Memory block length: {len(memory_context)} chars.\n"
            f"Answering: {prompt}"
        )
    else:
        reply = f"No prior memory context. Answering: {prompt}"
    return {"output": reply}


async def main() -> int:
    api_key = _resolve_api_key()
    suffix = uuid.uuid4().hex[:8]
    secret_fact = f"smoke-{suffix}-favorite-color-is-teal"
    user_id = f"smoke-user-{suffix}"
    tenant_id = "smoke-tenant"
    agent_name = "agentcore-smoke"

    print("Memanto AgentCore adapter — live smoke test")
    print(f"  run id:     {suffix}")
    print(f"  user_id:    {user_id}")
    print(f"  agent_name: {agent_name}")

    client = SdkClient(api_key=api_key)
    adapter = MemantoRuntimeAdapter(
        client,
        agent_name=agent_name,
        retain_async=False,
        retain_memory_type="preference",
        recall_limit=10,
    )

    agent_id = adapter.resolve_agent_id(
        TurnContext(
            runtime_session_id="unused",
            user_id=user_id,
            agent_name=agent_name,
            tenant_id=tenant_id,
        )
    )
    print(f"  memanto agent_id: {agent_id}")

    # --- Turn 1: ephemeral runtime session A ---
    _step(1, "Runtime session A — retain user preference (after_turn)")
    session_a = TurnContext(
        runtime_session_id=f"rt-{suffix}-SESSION-A",
        user_id=user_id,
        agent_name=agent_name,
        tenant_id=tenant_id,
        request_id=f"req-{suffix}-1",
    )
    user_message_a = f"Please remember my {secret_fact} for support tickets."
    await adapter.after_turn(
        session_a,
        result=f"Stored preference: user's {secret_fact}.",
        query=user_message_a,
    )
    print("  retain: OK")

    # Moorcheh indexing can lag briefly; retry recall a few times.
    _step(2, "Runtime session B — recall before turn (before_turn)")
    session_b = TurnContext(
        runtime_session_id=f"rt-{suffix}-SESSION-B",
        user_id=user_id,
        agent_name=agent_name,
        tenant_id=tenant_id,
        request_id=f"req-{suffix}-2",
    )
    recall_query = f"What is the user's {secret_fact}?"

    memory_context = ""
    for attempt in range(1, 6):
        memory_context = await adapter.before_turn(session_b, query=recall_query)
        if secret_fact in memory_context.lower() or "teal" in memory_context.lower():
            print(f"  recall: OK (attempt {attempt})")
            break
        if attempt < 5:
            print(f"  recall: empty or missing marker, retrying in 2s ({attempt}/5)...")
            await asyncio.sleep(2)
    else:
        print("FAIL: recall did not return the retained preference after retries.")
        print("  Last memory_context preview:")
        print(memory_context[:500] if memory_context else "  (empty)")
        return 1

    # --- Turn 2: full run_turn like a real handler ---
    _step(3, "Full handler path — run_turn with fake Bedrock agent")
    event = {
        "sessionId": session_b.runtime_session_id,
        "userId": user_id,
        "tenantId": tenant_id,
        "requestId": session_b.request_id,
        "prompt": recall_query,
    }
    context = TurnContext(
        runtime_session_id=event["sessionId"],
        user_id=event["userId"],
        agent_name=agent_name,
        tenant_id=event.get("tenantId"),
        request_id=event.get("requestId"),
    )
    handler_result = await adapter.run_turn(
        context=context,
        payload={"prompt": event["prompt"]},
        agent_callable=_fake_bedrock_agent,
    )
    output = handler_result.get("output", "")
    if "prior memory" not in output.lower() and "memory block" not in output.lower():
        print("FAIL: fake agent did not receive memory context via run_turn.")
        print(f"  output: {output[:300]}")
        return 1
    print("  run_turn: OK")
    print(f"  agent output (truncated): {output[:200]}...")

    _step(4, "Negative check — different user must not see this memory")
    other_user = TurnContext(
        runtime_session_id=f"rt-{suffix}-OTHER",
        user_id=f"other-user-{suffix}",
        agent_name=agent_name,
        tenant_id=tenant_id,
    )
    other_context = await adapter.before_turn(other_user, query=recall_query)
    if secret_fact in other_context.lower():
        print("FAIL: another user's recall leaked the secret fact (isolation broken).")
        return 1
    print("  user isolation: OK")

    print("\n========================================")
    print("PASS — AgentCore-style smoke test completed.")
    print("========================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
