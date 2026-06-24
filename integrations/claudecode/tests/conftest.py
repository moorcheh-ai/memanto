"""Shared test fixtures: a fake SdkClient so tests need no network or API key."""

from __future__ import annotations

import json
from typing import Any

import pytest
from memanto.app.utils.errors import AgentNotFoundError

from claudecode_memanto.config import SkillsConfig


class FakeSdkClient:
    """Records calls and returns canned responses, mimicking SdkClient.

    ``agent_exists=False`` simulates a first run: ``activate_agent`` raises
    ``AgentNotFoundError`` until ``create_agent`` is called, matching the real
    SDK's behaviour (verified against the live API).
    """

    def __init__(
        self,
        recall_memories: list[dict[str, Any]] | None = None,
        answer_text: str = "[]",
        agent_exists: bool = True,
    ) -> None:
        self.recall_memories = recall_memories or []
        self.answer_text = answer_text
        self.agent_exists = agent_exists
        self.created: list[str] = []
        self.activated: list[str] = []
        self.remembered: list[dict[str, Any]] = []
        self.batch_calls: list[list[dict[str, Any]]] = []
        self.answer_calls: list[dict[str, Any]] = []
        self.recall_calls: list[dict[str, Any]] = []

    # lifecycle
    def create_agent(self, agent_id: str, pattern: str = "tool", **_: Any) -> dict:
        self.created.append(agent_id)
        self.agent_exists = True
        return {"agent_id": agent_id}

    def activate_agent(self, agent_id: str, duration_hours: int | None = None) -> dict:
        if not self.agent_exists:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
        self.activated.append(agent_id)
        return {"agent_id": agent_id}

    # recall family
    def recall(self, agent_id: str, query: str, **kwargs: Any) -> dict:
        self.recall_calls.append({"query": query, **kwargs})
        return {"memories": list(self.recall_memories)}

    def recall_recent(self, agent_id: str, **kwargs: Any) -> dict:
        return {"memories": list(self.recall_memories)}

    # extraction + persistence
    def answer(self, agent_id: str, question: str, **kwargs: Any) -> dict:
        self.answer_calls.append({"question": question, **kwargs})
        return {"answer": self.answer_text, "sources": []}

    def batch_remember(self, agent_id: str, memories: list[dict[str, Any]]) -> dict:
        self.batch_calls.append(memories)
        return {"successful": len(memories), "failed": 0, "results": []}

    def remember(self, agent_id: str, **kwargs: Any) -> dict:
        self.remembered.append(kwargs)
        return {"memory_id": f"mem-{len(self.remembered)}"}


@pytest.fixture
def config() -> SkillsConfig:
    return SkillsConfig(
        api_key="mch_test_key",
        agent_id="test-agent",
        recall_limit=5,
        min_similarity=None,
    )


@pytest.fixture
def sample_memories() -> list[dict[str, Any]]:
    return [
        {
            "type": "instruction",
            "title": "Always Vitest",
            "content": "Always use Vitest for tests, never Jest.",
            "confidence": 0.95,
            "score": 0.9,
        },
        {
            "type": "decision",
            "title": "CQRS for orders",
            "content": "Use CQRS for the Order domain.",
            "confidence": 0.9,
            "score": 0.8,
        },
        {
            "type": "preference",
            "title": "AAA tests",
            "content": "Structure tests with Arrange-Act-Assert.",
            "confidence": 0.4,
            "score": 0.5,
        },
    ]


@pytest.fixture
def llm_answer_json() -> str:
    return json.dumps(
        [
            {
                "type": "decision",
                "title": "Use CQRS",
                "content": "Use CQRS for the Order domain.",
                "confidence": 0.9,
            },
            {
                "type": "instruction",
                "title": "Cart != Order",
                "content": "Never conflate Cart and Order terminology.",
                "confidence": 0.95,
            },
        ]
    )
