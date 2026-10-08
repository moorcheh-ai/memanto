"""Credential- and deployment-bound cache paths for automatic memory sync."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from memanto.app.clients.backend import Backend, parse_backend
from memanto.app.config import get_data_dir, settings
from memanto.app.utils.validation import validate_safe_id


# Bump the automatic-sync cache namespace when the rendered sync format changes.
_SYNC_CACHE_VERSION = 2


def memory_sync_cache_path(
    agent_id: str, api_key: str, *, backend_client: Any = None
) -> Path:
    """Bind a sync cache to the backend identity that supplies its memories.

    Agent names are caller-selected and do not establish cache ownership. Cloud
    caches include the credential and API endpoint; on-prem caches include the
    endpoint only because that backend ignores the Moorcheh API key. Prefer an
    already-created transport's settings over environment values changed since
    it was initialized. Only a digest of this context reaches the filesystem.

    Old unscoped exports are deliberately not adopted: their owner is unknown.
    Explicit user exports keep their existing paths and are not fallback caches.
    """
    validate_safe_id(agent_id, "agent_id")
    backend = parse_backend(settings.MEMANTO_BACKEND)
    if backend == Backend.ON_PREM:
        credential = ""
        endpoint = settings.MOORCHEH_ONPREM_URL or "http://localhost:8080"
        transport = getattr(backend_client, "_raw", None)
    else:
        credential = api_key
        endpoint = os.environ.get("MOORCHEH_BASE_URL") or "https://api.moorcheh.ai/v1"
        transport = backend_client
        transport_key = getattr(transport, "api_key", None)
        if isinstance(transport_key, str):
            credential = transport_key

    transport_url = getattr(transport, "base_url", None)
    if isinstance(transport_url, str) and transport_url:
        endpoint = transport_url

    context = json.dumps(
        {
            "version": _SYNC_CACHE_VERSION,
            "backend": backend.value,
            "endpoint": endpoint.rstrip("/"),
            "credential": credential,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    scope = hashlib.sha256(context.encode("utf-8")).hexdigest()
    return get_data_dir() / "exports" / "sync-cache" / scope / f"{agent_id}_memory.md"
