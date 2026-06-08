"""
Memanto memory tools for Claude Code skills integration.

Provides remember/recall/answer wrappers around the Moorcheh SDK,
scoped to a project namespace so memories persist across sessions.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from moorcheh_sdk import MoorchehClient


def _project_namespace(project_path: str | None = None) -> str:
    """
    Derive a stable Moorcheh namespace from the current project directory.
    Format: memanto_project_{short_hash} so each project gets isolated memory.
    """
    path = project_path or os.getcwd()
    slug = hashlib.md5(path.encode()).hexdigest()[:8]
    # Strip non-alphanumeric chars from the dir name for a readable prefix
    name = Path(path).name
    safe_name = "".join(c if c.isalnum() else "_" for c in name)[:20]
    return f"memanto_project_{safe_name}_{slug}"


def get_client(api_key: str | None = None) -> MoorchehClient:
    key = api_key or os.environ.get("MOORCHEH_API_KEY", "")
    if not key:
        raise RuntimeError(
            "MOORCHEH_API_KEY not set. "
            "Get a free key at https://console.moorcheh.ai/api-keys"
        )
    return MoorchehClient(api_key=key)


def remember(
    title: str,
    content: str,
    memory_type: str = "preference",
    tags: list[str] | None = None,
    *,
    project_path: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Store a developer preference or engineering decision in Memanto.

    Args:
        title:        Short label (< 100 chars)
        content:      Full content of the memory (< 10 000 chars)
        memory_type:  One of: preference, decision, fact, pattern, constraint
        tags:         Optional list of tags for filtering
        project_path: Override for project directory (defaults to cwd)
        api_key:      Override MOORCHEH_API_KEY env var

    Returns:
        Dict with 'id' and 'namespace' of the stored document.
    """
    client = get_client(api_key)
    namespace = _project_namespace(project_path)
    tags = tags or []

    # Formatted text that semantic search will index
    text = (
        f"[{memory_type.upper()}] {title}\n\n"
        f"{content}"
    )
    if tags:
        text += f"\n\nTags: {', '.join(tags)}"

    result = client.documents.upsert(
        namespace=namespace,
        documents=[{
            "text": text,
            "metadata": {
                "title": title,
                "memory_type": memory_type,
                "tags": ",".join(tags),
            },
        }],
    )
    return {"namespace": namespace, "result": result}


def recall(
    query: str,
    top_k: int = 5,
    *,
    project_path: str | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve the most relevant memories for a query.

    Args:
        query:        Natural-language query
        top_k:        Number of results to return
        project_path: Override for project directory
        api_key:      Override MOORCHEH_API_KEY env var

    Returns:
        List of matching memory dicts with 'text' and 'score'.
    """
    client = get_client(api_key)
    namespace = _project_namespace(project_path)

    results = client.similarity_search(
        namespace=namespace,
        query=query,
        top_k=top_k,
    )
    return results if isinstance(results, list) else []


def answer(
    question: str,
    *,
    project_path: str | None = None,
    api_key: str | None = None,
) -> str:
    """
    Ask a question against the project memory — Moorcheh synthesises an answer
    from the stored documents rather than just returning raw chunks.

    Args:
        question:     Natural-language question
        project_path: Override for project directory
        api_key:      Override MOORCHEH_API_KEY env var

    Returns:
        Synthesised answer string.
    """
    client = get_client(api_key)
    namespace = _project_namespace(project_path)

    result = client.answer(
        namespace=namespace,
        query=question,
    )
    # SDK returns various shapes; normalise to string
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result.get("answer") or result.get("text") or str(result)
    return str(result)


def list_memories(
    *,
    project_path: str | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """List all stored memories for the current project namespace."""
    client = get_client(api_key)
    namespace = _project_namespace(project_path)
    result = client.documents.list(namespace=namespace)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("documents", [])
    return []
