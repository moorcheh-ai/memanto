"""Small Memanto helper used by the LangGraph example scripts."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from memanto.cli.client.sdk_client import SdkClient

DEFAULT_AGENT_ID = "langgraph-support-demo"


def get_agent_id() -> str:
    return os.environ.get("MEMANTO_AGENT_ID", DEFAULT_AGENT_ID)


def build_client() -> SdkClient:
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MOORCHEH_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return SdkClient(api_key)


def ensure_active_agent(
    client: SdkClient,
    agent_id: str,
    description: str,
) -> None:
    try:
        client.create_agent(
            agent_id=agent_id,
            pattern="support",
            description=description,
        )
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            raise

    client.activate_agent(agent_id)


def format_recalled_memories(memories: Iterable[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for memory in memories:
        content = (
            memory.get("content")
            or memory.get("text")
            or memory.get("memory")
            or memory.get("title")
        )
        if content:
            lines.append(str(content))
    return lines
