"""Register Memanto tools on AG2 agents."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from memanto.app.utils.errors import AuthenticationError
from memanto.cli.client.sdk_client import SdkClient
from memanto_ag2.config import get_config
from memanto_ag2.tools import create_memanto_tools

_ORIG_SDK_CLIENT = SdkClient


def _build_memanto_client(api_key: str | None, cfg_key: str | None) -> SdkClient:
    from dotenv import dotenv_values

    from memanto.app.clients.backend import Backend
    from memanto.cli.client.factory import build_client
    from memanto.cli.client.hosted_client import HostedClient
    from memanto.cli.config.manager import ConfigManager

    def _make(key: str, *, cloud: bool) -> SdkClient:
        if SdkClient is not _ORIG_SDK_CLIENT or not (cloud or key.startswith("mk_")):
            return SdkClient(api_key=key)
        base_url = os.environ.get("MEMANTO_API_URL", "").strip()
        return HostedClient(key, base_url=base_url) if base_url else HostedClient(key)

    explicit = api_key or cfg_key
    if explicit is not None and explicit.strip():
        clean = explicit.strip()
        return _make(
            clean,
            cloud=clean == os.environ.get("MEMANTO_API_KEY", "").strip(),
        )

    memanto_key = os.environ.get("MEMANTO_API_KEY", "").strip()
    moorcheh_key = os.environ.get("MOORCHEH_API_KEY", "").strip()
    caller_url = os.environ.get("MEMANTO_API_URL", "").strip()
    cm = ConfigManager()
    if memanto_key:
        os.environ["MEMANTO_API_KEY"] = memanto_key
    if moorcheh_key:
        os.environ["MOORCHEH_API_KEY"] = moorcheh_key
    if caller_url:
        os.environ["MEMANTO_API_URL"] = caller_url
    backend = cm.get_backend()
    saved_cloud_key = (
        (dotenv_values(cm.env_file).get("MEMANTO_API_KEY") or "").strip()
        if cm.env_file.exists()
        else ""
    )
    is_dormant_saved_key = (
        cm.config_file.exists()
        and backend == Backend.ON_PREM
        and bool(saved_cloud_key)
        and memanto_key == saved_cloud_key
    )
    if memanto_key and not is_dormant_saved_key:
        return _make(memanto_key, cloud=True)
    if backend == Backend.MEMANTO_CLOUD:
        try:
            return build_client()
        except AuthenticationError:
            pass
    if backend == Backend.ON_PREM and cm.config_file.exists():
        return build_client()
    if moorcheh_key:
        return _make(moorcheh_key, cloud=False)
    try:
        return build_client()
    except AuthenticationError:
        raise ValueError(
            "Memanto API key required: pass api_key=, configure(), set MEMANTO_API_KEY "
            "(https://console.memanto.ai) or MOORCHEH_API_KEY, or run `memanto login`"
        )


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
    if client is None:
        client = _build_memanto_client(api_key, cfg.api_key)

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
