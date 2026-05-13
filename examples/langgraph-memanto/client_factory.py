from __future__ import annotations

import os
from typing import Any

from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is in requirements.txt
    load_dotenv = None


def build_memanto_client(
    agent_id: str,
    *,
    description: str = "LangGraph support workflow memory",
) -> SdkClient:
    if load_dotenv:
        load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MOORCHEH_API_KEY is required. Create a Moorcheh key, then set it "
            "before running the LangGraph example."
        )

    client = SdkClient(api_key)
    try:
        client.create_agent(agent_id, pattern="support", description=description)
    except AgentAlreadyExistsError:
        pass

    client.activate_agent(agent_id)
    return client


def deactivate_client(client: Any, agent_id: str) -> None:
    try:
        client.deactivate_agent(agent_id)
    except Exception:
        pass
