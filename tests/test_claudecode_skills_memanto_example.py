"""Regression tests for the Claude Code skills + Memanto example."""

from __future__ import annotations

import os
import subprocess
import sys
from types import ModuleType
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "claudecode-skills-memanto"
sys.path.insert(0, str(EXAMPLE_DIR))

from skill_memory import (  # noqa: E402
    LocalPreviewMemoryStore,
    MemantoSdkMemoryStore,
    SkillMemoryHook,
    build_memory_store,
)


def test_local_preview_reuses_cross_skill_memory(tmp_path: Path) -> None:
    memory_path = tmp_path / "skills-memory.jsonl"
    first_hook = SkillMemoryHook(LocalPreviewMemoryStore(memory_path))
    first_hook.after_skill(
        "/grill-with-docs",
        "Review billing retry architecture",
        """
Decision: Keep retry scheduling in billing/retry.py.
Preference: Use fake clock fixtures for retry tests.
""",
        ["billing/retry.py"],
    )

    second_hook = SkillMemoryHook(LocalPreviewMemoryStore(memory_path))
    context = second_hook.before_skill(
        "/tdd",
        "Write retry tests for billing/retry.py",
        ["tests/billing/test_retry.py", "billing/retry.py"],
    )

    assert "billing/retry.py" in context
    assert "fake clock" in context


def test_build_memory_store_selects_sdk_backend(monkeypatch) -> None:
    monkeypatch.setenv("MEMANTO_SKILLS_BACKEND", "memanto-sdk")
    created = {}

    class FakeSdkStore:
        def __init__(self) -> None:
            created["called"] = True

    monkeypatch.setattr("skill_memory.MemantoSdkMemoryStore", FakeSdkStore)

    assert isinstance(build_memory_store(), FakeSdkStore)
    assert created["called"] is True


def test_sdk_backend_uses_repository_python_package(monkeypatch) -> None:
    calls = {}

    class FakeConfigManager:
        def get_api_key(self) -> str:
            return "test-key"

        def get_active_session(self) -> tuple[str, str]:
            return ("agent-1", "session-token")

    class FakeSdkClient:
        def __init__(self, api_key: str) -> None:
            calls["api_key"] = api_key
            self.agent_id = None
            self.session_token = None

        def remember(self, **kwargs) -> None:
            calls["remember"] = kwargs

        def recall(self, **kwargs) -> dict[str, object]:
            calls["recall"] = kwargs
            return {
                "memories": [
                    {
                        "content": "Use service-layer retry scheduling.",
                        "source": "/grill-with-docs",
                        "created_at": "2026-05-20T00:00:00+00:00",
                    }
                ]
            }

    config_module = ModuleType("memanto.cli.config.manager")
    config_module.ConfigManager = FakeConfigManager
    sdk_module = ModuleType("memanto.cli.client.sdk_client")
    sdk_module.SdkClient = FakeSdkClient
    monkeypatch.setitem(sys.modules, "memanto.cli.config.manager", config_module)
    monkeypatch.setitem(sys.modules, "memanto.cli.client.sdk_client", sdk_module)

    store = MemantoSdkMemoryStore()
    hook = SkillMemoryHook(store)
    hook.after_skill(
        "/grill-with-docs",
        "Review retry architecture",
        "Decision: Keep retry logic in a service layer.",
    )
    context = hook.before_skill("/tdd", "Write retry tests")

    assert calls["api_key"] == "test-key"
    assert calls["remember"]["agent_id"] == "agent-1"
    assert calls["remember"]["memory_type"] == "decision"
    assert calls["recall"]["type"] == [
        "decision",
        "preference",
        "instruction",
        "context",
    ]
    assert "service-layer retry" in context


def test_runner_wraps_command_with_local_memory(tmp_path: Path) -> None:
    memory_path = tmp_path / "memories.jsonl"
    env = os.environ.copy()
    env["MEMANTO_SKILLS_MEMORY"] = str(memory_path)
    env["MEMANTO_SKILLS_BACKEND"] = "local-preview"

    seed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from skill_memory import LocalPreviewMemoryStore, SkillMemoryHook;"
                f"h=SkillMemoryHook(LocalPreviewMemoryStore(r'{memory_path}'));"
                "h.after_skill('/handoff','Seed notes',"
                "'Decision: Keep retry logic in billing/retry.py.',"
                "['billing/retry.py'])"
            ),
        ],
        cwd=EXAMPLE_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert seed.returncode == 0

    result = subprocess.run(
        [
            sys.executable,
            "run_skill_with_memory.py",
            "--skill",
            "/tdd",
            "--task",
            "Write retry tests",
            "--file",
            "billing/retry.py",
            "--",
            sys.executable,
            "-c",
            "print('wrapped command ran')",
        ],
        cwd=EXAMPLE_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Relevant prior engineering memory from Memanto" in result.stdout
    assert "billing/retry.py" in result.stdout
    assert "wrapped command ran" in result.stdout
