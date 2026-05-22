from __future__ import annotations

import os

from dotenv import load_dotenv
from memanto.cli.client.direct_client import DirectClient


def build_client() -> tuple[DirectClient, str]:
    """Create and activate a Memanto client for the LangGraph demo."""
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MOORCHEH_API_KEY is required. Copy .env.example to .env and set it."
        )

    agent_id = os.environ.get("MEMANTO_AGENT_ID", "langgraph-support-agent")
    client = DirectClient(api_key=api_key)

    try:
        client.get_agent(agent_id)
    except Exception:
        client.create_agent(
            agent_id=agent_id,
            pattern="tool",
            description="LangGraph + Memanto cross-session memory demo",
        )

    client.activate_agent(agent_id)
    return client, agent_id
