from __future__ import annotations

import importlib.util
from pathlib import Path


EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "langgraph-memanto"


def load_example_module(name: str):
    module_path = EXAMPLE_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeMemantoClient:
    def __init__(self) -> None:
        self.remember_calls: list[dict[str, object]] = []
        self.recall_response = {
            "memories": [
                {"content": "Customer prefers concise replies."},
                {"memory": {"content": "Customer is on the startup plan."}},
                {"text": "Escalate billing questions to account owner."},
            ]
        }

    def remember(self, **kwargs):
        self.remember_calls.append(kwargs)
        return {"memory_id": "mem_123", "status": "stored"}

    def recall(self, **kwargs):
        return self.recall_response


def test_adapter_stores_customer_preference_with_tags():
    adapter_module = load_example_module("memory_adapter")
    client = FakeMemantoClient()
    adapter = adapter_module.MemantoMemoryAdapter(client, "support-agent")

    result = adapter.store_customer_preference(
        customer_id="cust-42",
        preference="Customer prefers concise replies.",
        source_ticket="ticket-1001",
    )

    assert result["memory_id"] == "mem_123"
    assert client.remember_calls == [
        {
            "agent_id": "support-agent",
            "memory_type": "preference",
            "title": "Preference for cust-42",
            "content": "Customer prefers concise replies.",
            "confidence": 0.9,
            "tags": ["langgraph-demo", "customer:cust-42", "ticket:ticket-1001"],
            "source": "langgraph-support-demo",
            "provenance": "explicit_statement",
        }
    ]


def test_adapter_recalls_and_normalizes_context():
    adapter_module = load_example_module("memory_adapter")
    adapter = adapter_module.MemantoMemoryAdapter(
        FakeMemantoClient(), "support-agent"
    )

    memories = adapter.recall_customer_context("cust-42")

    assert memories == [
        "Customer prefers concise replies.",
        "Customer is on the startup plan.",
        "Escalate billing questions to account owner.",
    ]
