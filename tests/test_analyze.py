"""
Unit tests for memanto analyze pipeline (no API keys or network).

Covers deterministic metrics, ingestion cost math, LLM prompts, and report
markdown builders for Supermemory, Mem0, and Letta exports.
"""

from memanto.cli.analyze.ingestion_cost import (
    DEFAULT_INPUT_USD_PER_1M,
    DEFAULT_OUTPUT_USD_PER_1M,
    estimate_ingestion_cost,
)
from memanto.cli.analyze.letta_compare import (
    build_llm_prompt as build_letta_llm_prompt,
)
from memanto.cli.analyze.letta_compare import (
    build_report_markdown as build_letta_report,
)
from memanto.cli.analyze.letta_compare import (
    compute_metrics as compute_letta_metrics,
)
from memanto.cli.analyze.mem0_compare import (
    build_llm_prompt as build_mem0_llm_prompt,
)
from memanto.cli.analyze.mem0_compare import (
    build_report_markdown as build_mem0_report,
)
from memanto.cli.analyze.mem0_compare import (
    compute_metrics as compute_mem0_metrics,
)
from memanto.cli.analyze.supermemory_compare import (
    build_llm_prompt as build_supermemory_llm_prompt,
)
from memanto.cli.analyze.supermemory_compare import (
    build_report_markdown as build_supermemory_report,
)
from memanto.cli.analyze.supermemory_compare import (
    compute_metrics as compute_supermemory_metrics,
)

ASSUMPTIONS = {
    "extraction_usd_per_1m_input_tokens": DEFAULT_INPUT_USD_PER_1M,
    "extraction_usd_per_1m_output_tokens": DEFAULT_OUTPUT_USD_PER_1M,
}


class TestIngestionCost:
    def test_estimate_ingestion_cost(self):
        result = estimate_ingestion_cost(
            input_tokens=1_000_000,
            output_tokens=500_000,
            assumptions=ASSUMPTIONS,
        )

        assert result["input_tokens"] == 1_000_000
        assert result["output_tokens"] == 500_000
        assert result["total_extraction_tokens"] == 1_500_000
        assert result["input_cost_usd"] == 0.15
        assert result["output_cost_usd"] == 0.5
        assert result["total_cost_usd"] == 0.65
        assert result["tokens_saved"] == 1_500_000

    def test_zero_tokens(self):
        result = estimate_ingestion_cost(
            input_tokens=0,
            output_tokens=0,
            assumptions=ASSUMPTIONS,
        )

        assert result["total_cost_usd"] == 0.0
        assert result["tokens_saved"] == 0


class TestSupermemoryCompare:
    @staticmethod
    def _sample_export() -> dict:
        return {
            "exported_at": "2026-06-04T12:00:00Z",
            "summary": {
                "document_count": 1,
                "chunk_count": 2,
                "memory_entry_count": 1,
                "container_tag_count": 1,
                "connection_count": 0,
            },
            "documents": [
                {
                    "chunks": [
                        {"content": "a" * 40},
                        {"content": "b" * 40},
                    ]
                }
            ],
            "memories": [{"content": "c" * 20}],
        }

    def test_compute_metrics(self):
        metrics = compute_supermemory_metrics(self._sample_export())
        volume = metrics["volume"]

        assert volume["documents"] == 1
        assert volume["chunks"] == 2
        assert volume["memories"] == 1
        assert volume["container_tags"] == 1
        assert volume["estimated_input_tokens"] == 20
        assert volume["estimated_output_tokens"] == 5
        assert volume["estimated_content_tokens"] == 25
        assert volume["vector_count"] == 2

        ingestion = metrics["ingestion_tax"]
        assert ingestion["supermemory_input_tokens"] == 20
        assert ingestion["supermemory_output_tokens"] == 5
        assert ingestion["memanto_extraction_tokens"] == 0
        assert ingestion["tokens_saved"] == 25

        storage = metrics["storage"]
        assert storage["supermemory_bytes"] == 2 * 4096
        assert storage["memanto_bytes"] == 2 * 128
        assert storage["compression_ratio"] == 32

        latency = metrics["latency"]
        assert latency["supermemory_read_ms"] == 300
        assert latency["memanto_read_ms"] == 90
        assert latency["speedup_x"] == 3.3
        assert latency["ms_saved_per_query"] == 210

    def test_build_llm_prompt_uses_measured_numbers(self):
        metrics = compute_supermemory_metrics(self._sample_export())
        prompt = build_supermemory_llm_prompt(metrics)

        assert "MEASURED SUPERMEMORY FOOTPRINT" in prompt
        assert "Documents: 1" in prompt
        assert "RAG chunks (vectors): 2" in prompt
        assert "Memory entries: 1" in prompt
        assert "Estimated content tokens: 25" in prompt
        assert "PROJECTED MEMANTO IMPACT" in prompt
        assert "Executive summary" in prompt
        assert "Do NOT invent benchmark scores" in prompt

    def test_build_report_markdown(self):
        metrics = compute_supermemory_metrics(self._sample_export())
        report = build_supermemory_report(
            metrics=metrics,
            narrative="## Executive summary\nTest narrative.",
            export_path="/tmp/supermemory_export.json",
            llm_model="test-model",
            llm_method="Moorcheh answer (kiosk)",
            exported_at="2026-06-04T12:00:00Z",
        )

        assert "# Memanto vs. Supermemory" in report
        assert "Your Supermemory footprint (measured)" in report
        assert "| Documents | 1 |" in report
        assert "Test narrative." in report
        assert "Method & assumptions" in report
        assert "test-model" in report
        assert "/tmp/supermemory_export.json" in report


class TestMem0Compare:
    @staticmethod
    def _sample_export() -> dict:
        return {
            "exported_at": "2026-06-04T12:00:00Z",
            "summary": {
                "entity_count": 2,
                "scope_count": 2,
                "memory_count": 2,
            },
            "entities": [
                {"id": "user:alice", "name": "alice", "type": "user"},
                {"id": "agent:bot", "name": "bot", "type": "agent"},
            ],
            "memories": [
                {"id": "m1", "memory": "a" * 40},
                {"id": "m2", "memory": "b" * 40},
            ],
        }

    def test_compute_metrics(self):
        metrics = compute_mem0_metrics(self._sample_export())
        volume = metrics["volume"]

        assert volume["entities"] == 2
        assert volume["scopes"] == 2
        assert volume["memories"] == 2
        assert volume["entity_types"] == {"user": 1, "agent": 1}
        assert volume["estimated_content_tokens"] == 20
        assert volume["estimated_output_tokens"] == 20
        assert volume["estimated_input_tokens"] == 50
        assert volume["vector_count"] == 2

        ingestion = metrics["ingestion_tax"]
        assert ingestion["mem0_input_tokens"] == 50
        assert ingestion["mem0_output_tokens"] == 20
        assert ingestion["tokens_saved"] == 70

        storage = metrics["storage"]
        assert storage["mem0_bytes"] == 2 * 4096
        assert storage["memanto_bytes"] == 2 * 128

        latency = metrics["latency"]
        assert latency["mem0_read_ms"] == 499
        assert latency["speedup_x"] == 5.5
        assert latency["ms_saved_per_query"] == 409

    def test_build_llm_prompt_uses_measured_numbers(self):
        metrics = compute_mem0_metrics(self._sample_export())
        prompt = build_mem0_llm_prompt(metrics)

        assert "MEASURED MEM0 FOOTPRINT" in prompt
        assert "Entities: 2" in prompt
        assert "Memories: 2" in prompt
        assert "agent: 1" in prompt
        assert "user: 1" in prompt
        assert "Estimated content tokens: 20" in prompt
        assert "PROJECTED MEMANTO IMPACT" in prompt
        assert "Migration considerations" in prompt

    def test_build_report_markdown(self):
        metrics = compute_mem0_metrics(self._sample_export())
        report = build_mem0_report(
            metrics=metrics,
            narrative="## Executive summary\nMem0 migration brief.",
            export_path="/tmp/mem0_export.json",
            llm_model="test-model",
            llm_method="Moorcheh answer (kiosk)",
            exported_at="2026-06-04T12:00:00Z",
        )

        assert "# Memanto vs. Mem0" in report
        assert "Your Mem0 footprint (measured)" in report
        assert "| Entities | 2 |" in report
        assert "agent: 1, user: 1" in report
        assert "Mem0 migration brief." in report
        assert "Method & assumptions" in report


class TestLettaCompare:
    @staticmethod
    def _sample_export() -> dict:
        return {
            "exported_at": "2026-06-04T12:00:00Z",
            "export_mode": "all_agents",
            "summary": {
                "agent_count": 2,
                "passage_count": 2,
                "passage_pages": 2,
            },
            "agents": [
                {"id": "agent-test-123", "name": "lette"},
                {"id": "agent-test-456", "name": "support-bot"},
            ],
            "passages": [
                {
                    "id": "p1",
                    "text": "a" * 40,
                    "export_agent_id": "agent-test-123",
                    "export_agent_name": "lette",
                },
                {
                    "id": "p2",
                    "text": "b" * 40,
                    "export_agent_id": "agent-test-456",
                    "export_agent_name": "support-bot",
                },
            ],
        }

    def test_compute_metrics(self):
        metrics = compute_letta_metrics(self._sample_export())
        volume = metrics["volume"]

        assert volume["agents"] == 2
        assert volume["passages"] == 2
        assert volume["estimated_content_tokens"] == 20
        assert volume["estimated_output_tokens"] == 20
        assert volume["estimated_input_tokens"] == 50
        assert volume["vector_count"] == 2

        ingestion = metrics["ingestion_tax"]
        assert ingestion["letta_input_tokens"] == 50
        assert ingestion["letta_output_tokens"] == 20
        assert ingestion["tokens_saved"] == 70

        storage = metrics["storage"]
        assert storage["letta_bytes"] == 2 * 4096
        assert storage["memanto_bytes"] == 2 * 128

        latency = metrics["latency"]
        assert latency["letta_read_ms"] == 450
        assert latency["speedup_x"] == 5.0
        assert latency["ms_saved_per_query"] == 360

    def test_build_llm_prompt_uses_measured_numbers(self):
        metrics = compute_letta_metrics(self._sample_export())
        prompt = build_letta_llm_prompt(metrics)

        assert "MEASURED LETTA FOOTPRINT" in prompt
        assert "Agents: 2" in prompt
        assert "Archival passages: 2" in prompt
        assert "Estimated content tokens: 20" in prompt
        assert "PROJECTED MEMANTO IMPACT" in prompt
        assert "Migration considerations" in prompt

    def test_build_report_markdown(self):
        metrics = compute_letta_metrics(self._sample_export())
        report = build_letta_report(
            metrics=metrics,
            narrative="## Executive summary\nLetta migration brief.",
            export_path="/tmp/letta_export.json",
            llm_model="test-model",
            llm_method="Moorcheh answer (kiosk)",
            exported_at="2026-06-04T12:00:00Z",
        )

        assert "# Memanto vs. Letta" in report
        assert "Your Letta footprint (measured)" in report
        assert "| Agents | 2 |" in report
        assert "| Archival passages | 2 |" in report
        assert "Letta migration brief." in report
        assert "Method & assumptions" in report

    def test_compute_metrics_single_agent_legacy_export(self):
        """Older single-agent exports still produce metrics."""
        export = {
            "exported_at": "2026-06-04T12:00:00Z",
            "agent_id": "agent-test-123",
            "agent_name": "lette",
            "summary": {"passage_count": 1},
            "passages": [{"id": "p1", "text": "a" * 40}],
        }
        metrics = compute_letta_metrics(export)
        assert metrics["volume"]["agents"] == 1
        assert metrics["volume"]["passages"] == 1
