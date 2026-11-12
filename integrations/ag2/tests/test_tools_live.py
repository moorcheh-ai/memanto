"""Live smoke — real Moorcheh API, AG2 tool functions."""

import os
import time
import uuid

import pytest
from memanto_ag2.tools import create_memanto_tools

from memanto.app.config import settings
from memanto.cli.client.sdk_client import SdkClient


def _live_key_configured() -> bool:
    key = (
        os.environ.get("MOORCHEH_API_KEY") or settings.MOORCHEH_API_KEY or ""
    ).strip()
    return bool(key) and key != "test-api-key"


pytestmark = pytest.mark.skipif(
    not _live_key_configured(),
    reason="MOORCHEH_API_KEY required for live AG2 smoke test",
)


def test_remember_recall_survives_tool_calls():
    suffix = uuid.uuid4().hex[:8]
    marker = f"ag2-live-{suffix}-teal"
    agent_id = f"ag2-live-{suffix}"

    client = SdkClient(
        api_key=os.environ.get("MOORCHEH_API_KEY") or settings.MOORCHEH_API_KEY
    )
    tools = create_memanto_tools(client, agent_id, source="ag2-live-test")
    remember = next(t for t in tools if t.__name__ == "memanto_remember")
    recall = next(t for t in tools if t.__name__ == "memanto_recall")

    remember(
        memory_type="preference",
        title="Smoke",
        content=f"Marker {marker} for pytest live smoke.",
        confidence=1.0,
        tags="ag2,live",
    )

    out = ""
    for attempt in range(1, 6):
        out = recall(query=f"What is {marker}?", limit=10)
        if marker.lower() in out.lower() or "teal" in out.lower():
            break
        if attempt < 5:
            time.sleep(2)

    assert marker.lower() in out.lower() or "teal" in out.lower(), (
        "recall empty after remember — indexing may lag; re-run"
    )
