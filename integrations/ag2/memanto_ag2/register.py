"""Register Memanto tools on AG2 agents."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from memanto.cli.client.sdk_client import SdkClient
from memanto_ag2.config import get_config
from memanto_ag2.tools import create_memanto_tools


def register_memanto_tools(
    *llm_agents: Any,
    executor: Any,
    agent_id: str,
    client: SdkClient | None = None,
    api_key: str | None = None,
    source: str | None = None,
    recall_limit: int | None = None,
    include_remember: bool = True,
    include_recall: bool = True,
    include_answer: bool = True,
) -> list[Callable[..., str]]:
    """
    Register ``memanto_remember``, ``memanto_recall``, and ``memanto_answer`` on AG2 agents.

    *llm_agents* receive ``register_for_llm``; *executor* receives ``register_for_execution``.
    Multiple assistants can share one *agent_id* memory namespace (GroupChat pattern).
    """
    if not agent_id or not agent_id.strip():
        raise ValueError("agent_id is required")

    cfg = get_config()
    resolved_key = api_key or cfg.api_key or os.environ.get("MOORCHEH_API_KEY")
    if client is None:
        if not resolved_key:
            raise ValueError(
                "Memanto API key required: pass api_key=, configure(), or set MOORCHEH_API_KEY"
            )
        client = SdkClient(api_key=resolved_key)

    tools = create_memanto_tools(
        client,
        agent_id.strip(),
        source=source or cfg.source,
        recall_limit=recall_limit if recall_limit is not None else cfg.recall_limit,
        include_remember=include_remember,
        include_recall=include_recall,
        include_answer=include_answer,
    )

    llm_registers: list[Any] = []
    for agent in llm_agents:
        register_llm = getattr(agent, "register_for_llm", None)
        if register_llm is None:
            raise TypeError(
                f"{type(agent).__name__} has no register_for_llm; pass AG2 AssistantAgent instances"
            )
        llm_registers.append(register_llm)

    register_exec = getattr(executor, "register_for_execution", None)
    if register_exec is None:
        raise TypeError(
            f"{type(executor).__name__} has no register_for_execution; pass a UserProxyAgent"
        )

    for register_llm in llm_registers:
        for tool_fn in tools:
            register_llm(description=(tool_fn.__doc__ or "").strip())(tool_fn)

    for tool_fn in tools:
        register_exec()(tool_fn)

    return tools
