"""Shared fixtures. Env isolation mirrors integrations/mcp/tests/conftest.py."""

from __future__ import annotations

import itertools
import os
import types
from unittest.mock import MagicMock

import pytest

_PREFIXES = ("MOORCHEH_", "MEMANTO_", "LANGFUSE_")


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """Keep a developer's real keys and .env out of the tests."""
    for name in list(os.environ):
        if name.upper().startswith(_PREFIXES):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def capture_dir(tmp_path, monkeypatch):
    """Point Memanto's migrate directory at a temp dir and return it."""
    from memanto.cli.config.manager import ConfigManager

    monkeypatch.setattr(
        ConfigManager, "get_migrate_dir", lambda self, provider: tmp_path
    )
    return tmp_path


@pytest.fixture
def errors_only(capture_dir):
    """Store an 'errors' capture profile, as `--save` would."""
    from memanto.cli.migrate.langfuse_config import (
        ProjectConfig,
        config_path,
        save_project,
    )

    save_project(
        config_path(capture_dir),
        "default",
        ProjectConfig(capture=frozenset({"errors"})),
    )
    return capture_dir


@pytest.fixture
def memanto_client():
    """A Memanto client double that hands back unique memory ids."""
    ids = itertools.count(1)
    client = MagicMock()
    client.batch_remember.side_effect = lambda agent_id, memories: {
        "successful": len(memories),
        "failed": 0,
        "results": [{"id": f"mem-{next(ids)}", "status": "queued"} for _ in memories],
    }
    client.update_memory.return_value = {"status": "updated"}
    return client


def make_span(
    name="generate",
    *,
    level="ERROR",
    status_message="Model returned malformed output",
    status_code="ERROR",
    trace_id=0x0123456789ABCDEF0123456789ABCDEF,
    span_id=0x0123456789ABCDEF,
    start_ns=1_786_000_000_000_000_000,
    end_ns=1_786_000_001_000_000_000,
    attributes=None,
    events=(),
):
    """A stand-in for an OpenTelemetry ReadableSpan.

    Field names and the ``langfuse.observation.*`` attribute keys were taken
    from a real span captured off langfuse 4.14.3.
    """
    attrs = {}
    if level is not None:
        attrs["langfuse.observation.level"] = level
    if status_message is not None:
        attrs["langfuse.observation.status_message"] = status_message
    attrs.update(attributes or {})

    return types.SimpleNamespace(
        name=name,
        context=types.SimpleNamespace(trace_id=trace_id, span_id=span_id),
        status=types.SimpleNamespace(
            status_code=types.SimpleNamespace(name=status_code),
            description=status_message,
        ),
        start_time=start_ns,
        end_time=end_ns,
        attributes=attrs,
        events=events,
    )
