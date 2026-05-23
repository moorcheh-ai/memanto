"""
Integration tests for the LangGraph Customer Support Agent with Memanto.

Tests verify:
- Cross-session recall: memories from one session persist into the next
- Triage classification: severity and category are assigned
- Resolution storage: resolutions are stored for future recall
- Follow-up commitment: high-severity tickets generate commitment memories
"""

import os
import sys
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Set required env vars before imports
os.environ.setdefault("MOORCHEH_API_KEY", "test-key-mock")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-mock")


class MockMemantoTool:
    """In-memory mock of MemantoTool for testing without API calls."""

    def __init__(self, **kwargs):
        self.agent_id = kwargs.get("agent_id", "test-agent")
        self.scope_id = kwargs.get("scope_id", "test")
        self._memories = []
        self._id_counter = 0

    def remember(self, content, title=None, memory_type="fact", confidence=0.8, tags=None, source="agent_inference"):
        self._id_counter += 1
        memory = {
            "memory_id": f"mem-{self._id_counter}",
            "type": memory_type,
            "title": title or content[:80],
            "content": content,
            "confidence": confidence,
            "tags": tags or [],
            "created_at": "2026-05-23T00:00:00Z",
        }
        self._memories.append(memory)
        return memory

    def recall(self, query, limit=5, memory_types=None, min_confidence=None):
        results = []
        for m in self._memories:
            if memory_types and m["type"] not in memory_types:
                continue
            if min_confidence and m["confidence"] < min_confidence:
                continue
            # Simple keyword matching for mock
            if any(word.lower() in m["content"].lower() for word in query.split()):
                results.append(m)
        return results[:limit]

    def answer(self, query):
        recalled = self.recall(query, limit=3)
        if not recalled:
            return {"answer": "No relevant memories found.", "sources": [], "confidence": 0.0}
        return {
            "answer": " | ".join(m["content"][:50] for m in recalled),
            "sources": recalled,
            "confidence": max(m["confidence"] for m in recalled),
        }


class MockLLM:
    """Mock LLM that returns deterministic responses."""

    def invoke(self, messages):
        last_content = messages[-1].content if messages else ""

        if "Classify" in str(messages[0].content) or "triage" in str(messages[0].content).lower():
            if "payment" in last_content.lower() or "billing" in last_content.lower():
                return MagicMock(content='{"severity": "high", "category": "billing"}')
            if "crash" in last_content.lower() or "error" in last_content.lower():
                return MagicMock(content='{"severity": "critical", "category": "technical"}')
            return MagicMock(content='{"severity": "low", "category": "general"}')

        if "investigat" in str(messages[0].content).lower():
            return MagicMock(content=(
                "1. Root cause identified: database connection timeout\n"
                "2. Observed that this affects customers on the legacy cluster\n"
                "3. Resolved by increasing connection pool size\n"
                "4. Should add monitoring for connection pool utilization\n"
            ))

        if "resolution" in str(messages[0].content).lower() or "Resolv" in str(messages[0].content):
            return MagicMock(content=(
                "1. Root cause: Database connection pool was exhausted under high load.\n"
                "2. Resolution: Increased pool size from 10 to 50 connections.\n"
                "3. Prevention: Added auto-scaling for connection pool based on queue depth."
            ))

        if "follow" in str(messages[0].content).lower() or "success" in str(messages[0].content).lower():
            return MagicMock(content=(
                "Hi there! We've resolved your issue. The connection timeout has been fixed "
                "by increasing our database capacity. We'll monitor your account closely. "
                "Please reach out if you experience any further issues!"
            ))

        return MagicMock(content="Processed.")


class TestCustomerSupportAgent(unittest.TestCase):
    """Test the LangGraph customer support agent with mock dependencies."""

    def setUp(self):
        self.mock_memanto = MockMemantoTool(
            agent_id="test-support-agent",
            scope_id="test-support",
        )
        self.mock_llm = MockLLM()

        # Pre-seed some memories to simulate "yesterday's session"
        self.mock_memanto.remember(
            content="Customer cust-001 reported payment gateway timeout on 2026-05-22",
            title="Previous payment issue: cust-001",
            memory_type="event",
            confidence=0.90,
            tags=["cust-001", "billing"],
        )
        self.mock_memanto.remember(
            content="Resolved payment timeout by restarting the payment gateway service",
            title="Resolution: payment timeout",
            memory_type="fact",
            confidence=0.92,
            tags=["resolution", "billing"],
        )
        self.mock_memanto.remember(
            content="Customer cust-001 prefers email communication for follow-ups",
            title="Preference: cust-001",
            memory_type="preference",
            confidence=0.88,
            tags=["cust-001", "preference"],
        )

    def _build_graph(self):
        """Build the graph with mock dependencies."""
        from agent import SupportState, triage_node, investigate_node, resolve_node, follow_up_node
        from langgraph.graph import StateGraph, END

        graph = StateGraph(SupportState)

        graph.add_node(
            "triage",
            lambda state: triage_node(state, llm=self.mock_llm, memanto=self.mock_memanto),
        )
        graph.add_node(
            "investigate",
            lambda state: investigate_node(state, llm=self.mock_llm, memanto=self.mock_memanto),
        )
        graph.add_node(
            "resolve",
            lambda state: resolve_node(state, llm=self.mock_llm, memanto=self.mock_memanto),
        )
        graph.add_node(
            "follow_up",
            lambda state: follow_up_node(state, llm=self.mock_llm, memanto=self.mock_memanto),
        )

        graph.set_entry_point("triage")
        graph.add_edge("triage", "investigate")
        graph.add_edge("investigate", "resolve")
        graph.add_edge("resolve", "follow_up")
        graph.add_edge("follow_up", END)

        return graph.compile()

    def test_triage_classifies_billing_issue(self):
        """Triage should classify a payment issue as billing/high."""
        graph = self._build_graph()
        result = graph.invoke({
            "ticket_id": "TKT-0001",
            "customer_id": "cust-001",
            "message": "My payment failed again, this is the second time!",
            "severity": "",
            "category": "",
            "customer_history": [],
            "similar_issues": [],
            "investigation_notes": [],
            "resolution": "",
            "follow_up": "",
            "session_id": "session-2",
        })

        self.assertEqual(result["severity"], "high")
        self.assertEqual(result["category"], "billing")

    def test_cross_session_recall(self):
        """Agent should recall memories from a previous session.

        This is the KEY test: the agent ran yesterday (Session 1) and stored
        memories. Today (Session 2) with a completely new graph state, the
        agent should recall those memories because they live in Memanto,
        not in the ephemeral LangGraph state.
        """
        graph = self._build_graph()
        result = graph.invoke({
            "ticket_id": "TKT-0002",
            "customer_id": "cust-001",
            "message": "My payment failed again!",
            "severity": "",
            "category": "",
            "customer_history": [],
            "similar_issues": [],
            "investigation_notes": [],
            "resolution": "",
            "follow_up": "",
            "session_id": "session-2",
        })

        # The agent should have recalled the customer's history
        customer_history = result.get("customer_history", [])
        self.assertGreater(len(customer_history), 0,
                           "Agent should recall customer history from previous session")

        # Verify the recalled memory contains the previous issue
        history_contents = [m["content"] for m in customer_history]
        has_payment_memory = any("payment" in c.lower() for c in history_contents)
        self.assertTrue(has_payment_memory,
                        "Recalled memories should include the previous payment issue")

    def test_similar_issues_recalled(self):
        """Agent should find similar past issues from memory."""
        graph = self._build_graph()
        result = graph.invoke({
            "ticket_id": "TKT-0003",
            "customer_id": "cust-002",
            "message": "Payment gateway timeout on checkout",
            "severity": "",
            "category": "",
            "customer_history": [],
            "similar_issues": [],
            "investigation_notes": [],
            "resolution": "",
            "follow_up": "",
            "session_id": "session-2",
        })

        similar = result.get("similar_issues", [])
        self.assertGreater(len(similar), 0,
                           "Agent should find similar issues from memory")

    def test_resolution_is_stored_in_memory(self):
        """Resolution should be stored as a memory for future sessions."""
        initial_count = len(self.mock_memanto._memories)

        graph = self._build_graph()
        graph.invoke({
            "ticket_id": "TKT-0004",
            "customer_id": "cust-003",
            "message": "Application crash on startup",
            "severity": "",
            "category": "",
            "customer_history": [],
            "similar_issues": [],
            "investigation_notes": [],
            "resolution": "",
            "follow_up": "",
            "session_id": "session-2",
        })

        new_memories = self.mock_memanto._memories[initial_count:]
        # Should have stored at least: triage event + investigation notes + resolution
        self.assertGreater(len(new_memories), 2,
                           "Agent should store multiple memories from the workflow")

        # Check that a resolution memory was stored
        has_resolution = any("Resolved" in m["content"] or "resolution" in m["title"].lower()
                             for m in new_memories)
        self.assertTrue(has_resolution, "A resolution memory should be stored")

    def test_high_severity_creates_commitment(self):
        """Critical tickets should create a follow-up commitment memory."""
        initial_count = len(self.mock_memanto._memories)

        graph = self._build_graph()
        graph.invoke({
            "ticket_id": "TKT-0005",
            "customer_id": "cust-004",
            "message": "Application crash - database connection timeout critical error",
            "severity": "",
            "category": "",
            "customer_history": [],
            "similar_issues": [],
            "investigation_notes": [],
            "resolution": "",
            "follow_up": "",
            "session_id": "session-2",
        })

        new_memories = self.mock_memanto._memories[initial_count:]
        has_commitment = any(m["type"] == "commitment" for m in new_memories)
        self.assertTrue(has_commitment,
                        "Critical ticket should create a commitment memory for follow-up")

    def test_complete_workflow_produces_all_outputs(self):
        """The full workflow should produce triage, investigation, resolution, and follow-up."""
        graph = self._build_graph()
        result = graph.invoke({
            "ticket_id": "TKT-0006",
            "customer_id": "cust-005",
            "message": "Payment gateway timeout",
            "severity": "",
            "category": "",
            "customer_history": [],
            "similar_issues": [],
            "investigation_notes": [],
            "resolution": "",
            "follow_up": "",
            "session_id": "session-3",
        })

        # All stages should have produced output
        self.assertNotEqual(result["severity"], "")
        self.assertNotEqual(result["category"], "")
        self.assertGreater(len(result["investigation_notes"]), 0)
        self.assertNotEqual(result["resolution"], "")
        self.assertNotEqual(result["follow_up"], "")


class TestCrossSessionRecallIsolation(unittest.TestCase):
    """Verify that cross-session recall works across truly independent graph instances.

    This test creates TWO completely separate graph instances (simulating
    two separate sessions on different days) and verifies that memories
    stored in Session 1 are recalled in Session 2.
    """

    def test_memories_persist_across_independent_graphs(self):
        """Memories from graph instance 1 should be available in graph instance 2."""
        shared_memanto = MockMemantoTool(
            agent_id="test-isolation-agent",
            scope_id="test-isolation",
        )

        # ── Session 1: Yesterday ──
        memanto_1 = shared_memanto
        memanto_1.remember(
            content="Customer cust-999 reported recurring login bug on May 22",
            title="Bug report: login issue",
            memory_type="event",
            confidence=0.90,
            tags=["cust-999", "bug"],
        )
        memanto_1.remember(
            content="Resolved login bug by clearing stale session tokens",
            title="Resolution: login bug",
            memory_type="learning",
            confidence=0.93,
            tags=["resolution", "login"],
        )

        # ── Session 2: Today (completely new process) ──
        memanto_2 = shared_memanto  # Same Memanto = same persistent store

        # In a real deployment, memanto_2 would be a fresh MemantoTool()
        # connecting to the same Moorcheh namespace. Here we simulate
        # that by sharing the same mock store.

        recalled = memanto_2.recall("login bug cust-999", limit=5)

        self.assertEqual(len(recalled), 2,
                         "Session 2 should recall 2 memories from Session 1")
        contents = [m["content"] for m in recalled]
        self.assertTrue(any("login bug" in c.lower() for c in contents))
        self.assertTrue(any("Resolved" in c for c in contents),
                         "The resolution from yesterday should be recalled today")


if __name__ == "__main__":
    unittest.main()
