from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from long_horizon.dataset import Event, Probe
from long_horizon.runner import BenchmarkConfig, run_benchmark
from long_horizon.scoring import RetrievedItem


class CurrentOnlyAdapter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.current: dict[str, Event] = {}

    def add(self, event: Event) -> None:
        self.current[event.fact_key] = event

    def search(self, probe: Probe, *, limit: int) -> list[RetrievedItem]:
        event = self.current[probe.fact_key]
        return [RetrievedItem(text=event.content, rank=1)][:limit]

    def close(self) -> None:
        return None


class AppendOnlyAdapter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.events: list[Event] = []

    def add(self, event: Event) -> None:
        self.events.append(event)

    def search(self, probe: Probe, *, limit: int) -> list[RetrievedItem]:
        matching = [event for event in self.events if event.fact_key == probe.fact_key]
        return [
            RetrievedItem(text=event.content, rank=index)
            for index, event in enumerate(matching[:limit], start=1)
        ]

    def close(self) -> None:
        return None


def fake_factory(name: str, **_: object) -> CurrentOnlyAdapter | AppendOnlyAdapter:
    if name == "current":
        return CurrentOnlyAdapter(name)
    if name == "append":
        return AppendOnlyAdapter(name)
    raise ValueError(name)


class RunnerTests(unittest.TestCase):
    def test_runner_rejects_empty_or_ambiguous_dimensions(self) -> None:
        invalid_configs = (
            BenchmarkConfig(backends=()),
            BenchmarkConfig(backends=("mem0", "mem0")),
            BenchmarkConfig(seeds=()),
            BenchmarkConfig(checkpoints=()),
        )
        for config in invalid_configs:
            with self.subTest(config=config), self.assertRaises(ValueError):
                run_benchmark(
                    config,
                    adapter_factory=fake_factory,
                    token_counter=lambda text: len(text.split()),
                )

    def test_runner_writes_auditable_paired_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = BenchmarkConfig(
                backends=("current", "append"),
                seeds=(7,),
                sessions=16,
                checkpoints=(8, 16),
                top_k=5,
                output_dir=Path(temp_dir),
            )
            output = run_benchmark(
                config,
                adapter_factory=fake_factory,
                token_counter=lambda text: len(text.split()),
                run_id="test-run",
            )
            summary = json.loads((output / "summary.json").read_text())
            by_name = {backend["backend"]: backend for backend in summary["backends"]}
            self.assertEqual(by_name["current"]["top1_accuracy"], 1.0)
            self.assertLess(by_name["append"]["top1_accuracy"], 1.0)
            self.assertEqual(by_name["current"]["strict_accuracy"], 1.0)
            self.assertLess(by_name["append"]["strict_accuracy"], 1.0)
            self.assertEqual(
                summary["paired_comparison"]["metric"],
                "paired_top1_accuracy_difference",
            )
            self.assertEqual(summary["paired_comparison"]["n_pairs"], 16)
            self.assertGreater(
                summary["paired_comparison"]["mean_difference"],
                0.0,
            )

            raw_rows = (output / "raw_traces.jsonl").read_text().splitlines()
            self.assertEqual(len(raw_rows), 32)
            first = json.loads(raw_rows[0])
            self.assertIn("retrieved", first)
            self.assertIn("latency_ms", first)
            self.assertNotIn("\r", (output / "summary.csv").read_text())
            self.assertTrue((output / "report.md").exists())
            environment = json.loads((output / "environment.json").read_text())
            self.assertIn("git_commit", environment["source"])
            self.assertIn("git_tracked_files_dirty", environment["source"])


if __name__ == "__main__":
    unittest.main()
