"""Tests for the revocation-memory benchmark."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("benchmark.py")
SPEC = importlib.util.spec_from_file_location("revocation_benchmark", MODULE_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    """Deterministic tests that do not require framework credentials."""

    def test_fixture_reaches_current_state_without_stale_leaks(self) -> None:
        dataset = benchmark.load_dataset(Path(__file__).with_name("dataset.json"))
        report = benchmark.run_backend(
            "fixture",
            dataset,
            limit=6,
            settle_seconds=0,
            run_id="fixture",
        )

        self.assertEqual(report["mode"], "smoke_fixture")
        self.assertEqual(report["run_id"], "fixture")
        self.assertEqual(report["summary"]["retrieval_accuracy"], 1.0)
        self.assertEqual(report["summary"]["stale_leak_rate"], 0.0)
        self.assertEqual(report["summary"]["write_latency_p95_ms"], 0.0)
        self.assertEqual(report["summary"]["read_latency_p95_ms"], 0.0)
        self.assertEqual(len(report["probes"]), 6)

    def test_score_probe_counts_required_and_forbidden_terms(self) -> None:
        probe = {
            "required_terms": ["current rule", "PagerDuty"],
            "forbidden_terms": ["SMS", "old rule"],
        }
        required, forbidden, accuracy = benchmark.score_probe(
            probe,
            "The current rule routes incidents to PagerDuty. SMS is obsolete.",
        )

        self.assertEqual(required, 2)
        self.assertEqual(forbidden, 1)
        self.assertEqual(accuracy, 1.0)

    def test_dataset_fact_keys_end_in_one_current_value(self) -> None:
        dataset = json.loads(Path(__file__).with_name("dataset.json").read_text())
        current = {}
        for session in dataset["sessions"]:
            for event in session["events"]:
                current[event["fact_key"]] = event["content"]

        self.assertIn("Beta staging cluster", current["deployment_access"])
        self.assertIn("deleted within 24 hours", current["customer_export"])
        self.assertIn("PagerDuty", current["incident_contact"])

    def test_percentile_interpolates(self) -> None:
        self.assertEqual(benchmark.percentile([10, 20, 30, 40], 0.95), 38.5)

    def test_mem0_adapter_uses_raw_import_and_normalizes_results(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        class FakeMemory:
            config = None

            def __init__(self) -> None:
                self.vector_store = types.SimpleNamespace(client=FakeClient())
                self.add_call = None
                self.search_call = None

            @classmethod
            def from_config(cls, config):
                cls.config = config
                return cls()

            def add(self, content, **kwargs):
                self.add_call = (content, kwargs)

            def search(self, query, **kwargs):
                self.search_call = (query, kwargs)
                return {"results": [{"memory": "current value"}]}

        fake_module = types.SimpleNamespace(Memory=FakeMemory)
        with patch.dict(sys.modules, {"mem0": fake_module}):
            adapter = benchmark.Mem0Adapter("unit-test")
            adapter.write(
                {
                    "content": "current value",
                    "fact_key": "scope",
                    "session_id": "session-1",
                }
            )
            results = adapter.search("what is current?", limit=3)

            self.assertEqual(results, [{"memory": "current value"}])
            self.assertFalse(adapter._memory.add_call[1]["infer"])
            self.assertEqual(adapter._memory.search_call[1]["limit"], 3)
            self.assertFalse(adapter._memory.search_call[1]["rerank"])
            self.assertEqual(
                FakeMemory.config["embedder"]["provider"],
                "fastembed",
            )
            adapter.close()
            self.assertTrue(adapter._memory.vector_store.client.closed)


if __name__ == "__main__":
    unittest.main()
