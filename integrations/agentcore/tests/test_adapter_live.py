"""Live smoke test — real Moorcheh API, simulates two AgentCore runtime sessions."""

import asyncio
import os
import uuid

import pytest
from memanto_agentcore import MemantoRuntimeAdapter, TurnContext

from memanto.app.config import settings
from memanto.cli.client.sdk_client import SdkClient


def _live_key_configured() -> bool:
    key = (
        os.environ.get("MOORCHEH_API_KEY") or settings.MOORCHEH_API_KEY or ""
    ).strip()
    return bool(key) and key != "test-api-key"


pytestmark = pytest.mark.skipif(
    not _live_key_configured(),
    reason="MOORCHEH_API_KEY required for live AgentCore adapter smoke test",
)


@pytest.mark.asyncio
async def test_memory_survives_runtime_session_churn():
    suffix = uuid.uuid4().hex[:8]
    marker = f"agentcore-live-{suffix}"
    user_id = f"live-user-{suffix}"

    client = SdkClient(
        api_key=os.environ.get("MOORCHEH_API_KEY") or settings.MOORCHEH_API_KEY
    )
    adapter = MemantoRuntimeAdapter(
        client,
        agent_name="agentcore-smoke",
        retain_async=False,
        retain_memory_type="preference",
    )

    session_a = TurnContext(
        runtime_session_id=f"runtime-{suffix}-A",
        user_id=user_id,
        agent_name="agentcore-smoke",
        tenant_id="test",
    )

    await adapter.after_turn(
        session_a,
        result=f"Noted: {marker} prefers async email",
        query=f"Remember {marker} prefers async email",
    )

    session_b = TurnContext(
        runtime_session_id=f"runtime-{suffix}-B",
        user_id=user_id,
        agent_name="agentcore-smoke",
        tenant_id="test",
    )

    recall_query = f"What does {marker} prefer?"
    context = ""
    for attempt in range(1, 6):
        context = await adapter.before_turn(session_b, query=recall_query)
        lowered = context.lower()
        if marker in lowered or "async email" in lowered:
            break
        if attempt < 5:
            await asyncio.sleep(2)

    assert marker in context.lower() or "async email" in context.lower(), (
        "recall empty after retain — indexing may still be in progress; re-run the test"
    )
