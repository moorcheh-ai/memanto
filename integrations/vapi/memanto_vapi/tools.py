"""Vapi function-tool definitions for the Memanto memory tools."""

from __future__ import annotations

from typing import Any

from memanto.app.constants import VALID_MEMORY_TYPES
from memanto_vapi.memory import RECALL_TOOL, REMEMBER_TOOL, SCOPES, Scope


def tool_definitions(
    server_url: str,
    *,
    scope: Scope = "shared",
    credential_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return request bodies for Vapi's ``POST /tool``.

    Args:
        server_url: Public URL of the memanto-vapi webhook.
        scope: Must match the ``scope`` the webhook runs with.
        credential_id: Vapi bearer credential holding the webhook secret.
    """
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}, got {scope!r}")
    server: dict[str, Any] = {"url": server_url}
    if credential_id:
        server["credentialId"] = credential_id

    remember_properties: dict[str, Any] = {
        "content": {
            "type": "string",
            "description": "The memory, as one self-contained sentence.",
        },
        "type": {
            "type": "string",
            "enum": sorted(VALID_MEMORY_TYPES),
            "description": (
                "Kind of memory: 'learning' or 'error' for lessons, 'instruction' "
                "for how to handle something, 'fact' if unsure."
            ),
        },
        "title": {"type": "string", "description": "Optional short label."},
    }

    if scope == "caller":
        recall_description = (
            "Search memory: knowledge and lessons shared across all calls, plus "
            "what is remembered about the current caller from earlier calls. Use "
            "it before asking the caller for details they may already have given."
        )
        remember_description = (
            "Save something about the current caller to remember on their future "
            "calls, such as a preference they state or a promise made to them. "
            "It stays private to this caller. Never save secrets, card numbers, "
            "or passwords."
        )
    else:
        recall_description = (
            "Search the agent's memory: organization knowledge and lessons learned "
            "on earlier calls. Use it when unsure how to answer or handle a request."
        )
        remember_description = (
            "Save a lesson that should apply on every future call: a mistake to "
            "avoid, a correction, a better way to answer, or a fact about the "
            "business. This memory is shared with all callers, so never save "
            "personal details about the caller, secrets, card numbers, or passwords."
        )

    return [
        {
            "type": "function",
            "function": {
                "name": RECALL_TOOL,
                "description": recall_description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "What to look up, in plain language.",
                        }
                    },
                    "required": ["query"],
                },
            },
            "server": server,
        },
        {
            "type": "function",
            "function": {
                "name": REMEMBER_TOOL,
                "description": remember_description,
                "parameters": {
                    "type": "object",
                    "properties": remember_properties,
                    "required": ["content"],
                },
            },
            "server": server,
        },
    ]
