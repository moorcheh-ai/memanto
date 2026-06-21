from pathlib import Path

from adversarial_memory.dataset import Event, Probe
from adversarial_memory.runner import (
    BenchmarkConfig,
    Trace,
    _run_one,
    compare_backends,
    summarize,
)


class FakeAdapter:
    name = "fake"

    def __init__(self):
        self.memories = {}
        self.closed = False

    def add(self, event: Event):
        self.memories.setdefault(event.tenant, []).append(event.content)

    def search(self, probe: Probe, *, limit: int):
        matching = [
            text
            for text in reversed(self.memories[probe.tenant])
            if f"Incident {probe.probe_id.split('-incident-')[1].split('-')[0]} "
            in text
        ]
        return matching[:limit]

    def close(self):
        self.closed = True


def test_run_one_interleaves_writes_and_temporal_probes(tmp_path: Path):
    adapter = FakeAdapter()

    def factory(*args, **kwargs):
        return adapter

    config = BenchmarkConfig(
        backends=("fake", "other"),
        seeds=(2,),
        tenants=2,
        incidents=1,
        revisions=2,
        top_k=1,
    )
    traces, writes, tokens = _run_one(
        config=config,
        backend="fake",
        seed=2,
        work_dir=tmp_path,
        adapter_factory=factory,
    )

    assert len(traces) == 4
    assert all(trace.hit for trace in traces)
    assert len(writes) == 16
    assert tokens > 0
    assert adapter.closed is True


def test_summary_includes_required_and_resilience_metrics():
    config = BenchmarkConfig(
        backends=("fake", "other"),
        seeds=(2,),
        tenants=2,
        incidents=1,
        revisions=2,
        top_k=1,
    )
    traces, writes, tokens = _run_one(
        config=config,
        backend="fake",
        seed=2,
        work_dir=Path("unused"),
        adapter_factory=lambda *args, **kwargs: FakeAdapter(),
    )
    row = summarize(traces, {"fake": writes}, {"fake": tokens})[0]

    assert row["retrieval_accuracy"] == 1.0
    assert row["foreign_exposure_rate"] == 0.0
    assert row["tokens_ingested"] == tokens
    assert row["p95_retrieval_latency_seconds"] >= 0


def test_paired_comparison_aligns_by_seed_and_probe():
    common = {
        "seed": 1,
        "probe_id": "p",
        "latency_seconds": 0.1,
        "reciprocal_rank": 1.0,
        "stale_exposure": False,
        "poison_exposure": False,
        "foreign_exposure": False,
        "retrieved_tokens": 10,
    }
    traces = [
        Trace(backend="memanto", hit=True, **common),
        Trace(backend="mem0", hit=False, **common),
    ]

    comparison = compare_backends(traces, left="memanto", right="mem0")

    assert comparison["hit"]["mean_delta_left_minus_right"] == 1.0
    assert comparison["retrieved_tokens"]["mean_delta_left_minus_right"] == 0.0
    assert (
        comparison["mean_retrieval_latency_seconds"]["mean_delta_left_minus_right"]
        == 0.0
    )
    assert "latency_seconds" not in comparison
