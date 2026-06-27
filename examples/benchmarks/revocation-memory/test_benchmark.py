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
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(
            report["experiment_configuration"]["shared"]["extraction_llm"],
            "none",
        )
        self.assertIn(
            "smoke testing only",
            report["experiment_configuration"]["backend"]["purpose"],
        )

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

    def test_dataset_fingerprint_is_stable_and_sensitive(self) -> None:
        dataset = benchmark.load_dataset(Path(__file__).with_name("dataset.json"))
        first = benchmark.dataset_sha256(dataset)
        second = benchmark.dataset_sha256(
            json.loads(json.dumps(dataset, sort_keys=True))
        )
        changed = json.loads(json.dumps(dataset))
        changed["probes"][0]["query"] += " changed"

        self.assertEqual(first, second)
        self.assertNotEqual(first, benchmark.dataset_sha256(changed))

    def test_report_integrity_rejects_smoke_report_labeled_live(self) -> None:
        dataset = benchmark.load_dataset(Path(__file__).with_name("dataset.json"))
        report = benchmark.run_backend(
            "fixture",
            dataset,
            limit=6,
            settle_seconds=0,
            run_id="fixture",
        )
        self.assertEqual(benchmark.validate_report(report, dataset), [])

        report["mode"] = "live_framework"
        self.assertIn(
            "mode 'live_framework' does not match backend 'fixture'",
            benchmark.validate_report(report, dataset),
        )

    def test_report_integrity_requires_experiment_configuration(self) -> None:
        dataset = benchmark.load_dataset(Path(__file__).with_name("dataset.json"))
        report = benchmark.run_backend(
            "fixture",
            dataset,
            limit=6,
            settle_seconds=0,
            run_id="fixture",
        )
        del report["experiment_configuration"]

        self.assertIn(
            "experiment_configuration must be an object",
            benchmark.validate_report(report, dataset),
        )

    def test_report_integrity_recomputes_probe_and_summary_values(self) -> None:
        dataset = benchmark.load_dataset(Path(__file__).with_name("dataset.json"))
        report = benchmark.run_backend(
            "fixture",
            dataset,
            limit=6,
            settle_seconds=0,
            run_id="fixture",
        )

        report["probes"][0]["retrieved_tokens"] += 1
        report["summary"]["retrieval_accuracy"] = 0.25
        errors = benchmark.validate_report(report, dataset)

        self.assertIn(
            "probe current-deployment-scope has invalid retrieved_tokens",
            errors,
        )
        self.assertIn("summary retrieval_accuracy does not match probes", errors)

    def test_report_integrity_rejects_backend_configuration_drift(self) -> None:
        dataset = benchmark.load_dataset(Path(__file__).with_name("dataset.json"))
        report = benchmark.run_backend(
            "fixture",
            dataset,
            limit=6,
            settle_seconds=0,
            run_id="fixture",
        )
        report["experiment_configuration"]["backend"]["purpose"] = "live"

        self.assertIn(
            "experiment_configuration does not match the backend",
            benchmark.validate_report(report, dataset),
        )

    def test_mem0_configuration_discloses_all_retrieval_toggles(self) -> None:
        configuration = benchmark.experiment_configuration("mem0", limit=6)

        self.assertFalse(configuration["backend"]["infer"])
        self.assertFalse(configuration["backend"]["rerank"])
        self.assertEqual(configuration["backend"]["embedding_dimensions"], 384)
        self.assertEqual(configuration["shared"]["retrieval_limit"], 6)

    def test_dataset_validation_rejects_duplicate_probe_ids(self) -> None:
        dataset = json.loads(Path(__file__).with_name("dataset.json").read_text())
        dataset["probes"][1]["id"] = dataset["probes"][0]["id"]
        with patch("pathlib.Path.read_text", return_value=json.dumps(dataset)):
            with self.assertRaisesRegex(ValueError, "unique non-empty id"):
                benchmark.load_dataset(Path("ignored.json"))

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
            self.assertEqual(
                FakeMemory.config["llm"]["provider"],
                "ollama",
            )
            self.assertEqual(
                FakeMemory.config["llm"]["config"]["ollama_base_url"],
                "http://127.0.0.1:9",
            )
            adapter.close()
            self.assertTrue(adapter._memory.vector_store.client.closed)


if __name__ == "__main__":
    unittest.main()
