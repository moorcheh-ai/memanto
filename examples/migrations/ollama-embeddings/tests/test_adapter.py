"""
Tests for the Ollama Embeddings Migration Adapter.

Covers:
- Model discovery
- Embedding verification
- Memory export (with mock Ollama API)
- Mapper (ollama → Memanto)
- OKF bundle building
- Full migration pipeline
- Error handling and edge cases
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

from adapter.ollama_adapter import (
    DEFAULT_OLLAMA_BASE,
    DEFAULT_EMBEDDING_DIM,
    _now_utc,
    _slugify,
    _title_from,
    build_okf_bundle,
    discover_models,
    export_ollama_memories,
    map_ollama,
    run_full_migration,
    verify_embedding_compatibility,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ollama_client():
    """Returns a MagicMock httpx.Client for Ollama API mocking."""
    with patch("adapter.ollama_adapter._make_client") as mock_make:
        mock_client = MagicMock()
        mock_make.return_value.__enter__.return_value = mock_client
        mock_make.return_value.__exit__.return_value = False
        yield mock_client


@pytest.fixture
def sample_export():
    """A realistic Ollama export dict for testing."""
    return {
        "exported_at": "2026-07-26T12:00:00+00:00",
        "provider": "ollama",
        "model": "nomic-embed-text",
        "chat_model": "llama3.2",
        "api_base": DEFAULT_OLLAMA_BASE,
        "summary": {
            "model_count": 1,
            "memory_count": 4,
            "context_count": 3,
        },
        "memories": [
            {
                "title": "User prefers dark mode",
                "content": "The user has indicated a strong preference for dark mode across all applications, especially when coding late at night.",
                "type": "preference",
                "tags": ["ui", "dark-mode", "accessibility"],
                "confidence": 0.95,
                "source": "ollama",
                "source_ref": "ollama-0-0",
                "export_scope": {"agent_id": "ollama-agent"},
            },
            {
                "title": "PostgreSQL is the primary database",
                "content": "The team decided to use PostgreSQL 16 as the primary production database for all new services. MySQL legacy instances are being phased out by Q4 2026.",
                "type": "fact",
                "tags": ["infra", "database", "postgres"],
                "confidence": 0.90,
                "source": "ollama",
                "source_ref": "ollama-1-1",
                "export_scope": {"agent_id": "ollama-agent"},
            },
            {
                "title": "Project Alpha deadline",
                "content": "Project Alpha has a hard deadline of August 15, 2026. The client (Acme Corp) requires weekly progress reports every Friday.",
                "type": "commitment",
                "tags": ["project-alpha", "deadline", "acme-corp"],
                "confidence": 0.85,
                "source": "ollama",
                "source_ref": "ollama-2-2",
                "export_scope": {"agent_id": "ollama-agent"},
            },
            {
                "title": "Redis cache migration successful",
                "content": "The Redis cache migration from v6 to v7 completed successfully on July 20, 2026. Performance improved by 35%.",
                "type": "event",
                "tags": ["infra", "redis", "migration"],
                "confidence": 0.88,
                "source": "ollama",
                "source_ref": "ollama-2-3",
                "export_scope": {"agent_id": "ollama-agent"},
            },
        ],
        "notes": {
            "extraction": "Memories extracted from Ollama conversations.",
        },
    }


@pytest.fixture
def tmp_output_dir(tmp_path):
    """A temporary output directory for tests."""
    out = tmp_path / "output"
    out.mkdir()
    return out


# ---------------------------------------------------------------------------
# Unit: helpers
# ---------------------------------------------------------------------------

class TestTitleFrom:
    def test_short_content(self):
        assert _title_from("Hello") == "Hello"

    def test_long_content(self):
        long = "A" * 200
        result = _title_from(long, max_chars=80)
        assert len(result) <= 80
        assert result.endswith("...")

    def test_newlines_removed(self):
        assert _title_from("Hello\nWorld") == "Hello World"

    def test_empty_strips(self):
        assert _title_from("   trimmed   ") == "trimmed"


class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert _slugify("User's Dark Mode (2026)") == "user-s-dark-mode-2026"

    def test_multiple_dashes(self):
        assert _slugify("foo---bar___baz") == "foo-bar-baz"

    def test_truncates_long_slugs(self):
        long = "a" * 200
        result = _slugify(long)
        assert len(result) <= 100


class TestNowUtc:
    def test_returns_datetime_with_tz(self):
        dt = _now_utc()
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# Model Discovery
# ---------------------------------------------------------------------------

class TestDiscoverModels:
    def test_empty_response(self, mock_ollama_client):
        mock_ollama_client.get.return_value.status_code = 200
        mock_ollama_client.get.return_value.json.return_value = {}
        mock_ollama_client.get.return_value.content = b"{}"

        result = discover_models()
        assert result["count"] == 0
        assert result["all_models"] == []
        assert result["embedding_models"] == []
        assert result["chat_models"] == []

    def test_embedding_models_identified(self, mock_ollama_client):
        mock_ollama_client.get.return_value.status_code = 200
        mock_ollama_client.get.return_value.json.return_value = {
            "models": [
                {"name": "nomic-embed-text:latest", "details": {}},
                {"name": "llama3.2:latest", "details": {"family": "llama"}},
                {"name": "bge-large-en-v1.5", "details": {}},
                {"name": "all-minilm:latest", "details": {}},
            ]
        }
        mock_ollama_client.get.return_value.content = b"{}"

        result = discover_models()
        assert result["count"] == 4
        assert len(result["embedding_models"]) == 3  # nomic, bge, all-minilm
        assert len(result["chat_models"]) == 1  # llama3.2

        emb_names = {m["name"] for m in result["embedding_models"]}
        assert "nomic-embed-text:latest" in emb_names
        assert "bge-large-en-v1.5" in emb_names
        assert "all-minilm:latest" in emb_names

    def test_all_non_embedding(self, mock_ollama_client):
        mock_ollama_client.get.return_value.status_code = 200
        mock_ollama_client.get.return_value.json.return_value = {
            "models": [
                {"name": "llama3.2:latest", "details": {"family": "llama"}},
                {"name": "mistral:latest", "details": {"family": "llama"}},
            ]
        }
        mock_ollama_client.get.return_value.content = b"{}"

        result = discover_models()
        assert len(result["embedding_models"]) == 0
        assert len(result["chat_models"]) == 2

    def test_api_error(self, mock_ollama_client):
        mock_ollama_client.get.return_value.status_code = 500
        mock_ollama_client.get.return_value.text = "Internal error"

        with pytest.raises(RuntimeError, match="Ollama /api/tags failed"):
            discover_models()


# ---------------------------------------------------------------------------
# Embedding Verification
# ---------------------------------------------------------------------------

class TestVerifyEmbeddingCompatibility:
    def test_successful_verification(self, mock_ollama_client):
        mock_ollama_client.post.return_value.status_code = 200
        mock_ollama_client.post.return_value.json.return_value = {
            "embedding": [0.1] * 768
        }
        mock_ollama_client.post.return_value.content = b"{}"

        result = verify_embedding_compatibility("nomic-embed-text")
        assert result["compatible"] is True
        assert result["dimensions"] == 768
        assert result["raw_length"] == 768
        assert "error" not in result

    def test_dimension_mismatch(self, mock_ollama_client):
        mock_ollama_client.post.return_value.status_code = 200
        mock_ollama_client.post.return_value.json.return_value = {
            "embedding": [0.1] * 384
        }
        mock_ollama_client.post.return_value.content = b"{}"

        result = verify_embedding_compatibility(
            "nomic-embed-text", dimensions=768
        )
        assert result["compatible"] is False
        assert result["raw_length"] == 384

    def test_http_error(self, mock_ollama_client):
        mock_ollama_client.post.return_value.status_code = 502
        mock_ollama_client.post.return_value.text = "Bad Gateway"

        result = verify_embedding_compatibility("unknown-model")
        assert result["compatible"] is False
        assert "error" in result

    def test_exception_handled(self, mock_ollama_client):
        mock_ollama_client.post.side_effect = Exception("Connection refused")

        result = verify_embedding_compatibility("nomic-embed-text")
        assert result["compatible"] is False
        assert "Connection refused" in result["error"]


# ---------------------------------------------------------------------------
# Memory Export (with mocked Ollama chat API)
# ---------------------------------------------------------------------------

class TestExportOllamaMemories:
    def test_structured_json_extraction(self, mock_ollama_client):
        extracted_memories = [
            {
                "type": "preference",
                "title": "Dark mode UI",
                "content": "User prefers dark mode.",
                "tags": ["ui"],
                "confidence": 0.95,
            }
        ]

        mock_ollama_client.post.return_value.status_code = 200
        mock_ollama_client.post.return_value.json.return_value = {
            "message": {"content": json.dumps(extracted_memories)}
        }
        mock_ollama_client.post.return_value.content = b"{}"

        result = export_ollama_memories(
            "nomic-embed-text", ["User likes dark mode."]
        )

        assert result["provider"] == "ollama"
        assert result["model"] == "nomic-embed-text"
        assert result["summary"]["context_count"] == 1
        assert result["summary"]["memory_count"] == 1
        assert result["memories"][0]["title"] == "Dark mode UI"
        assert result["memories"][0]["confidence"] == 0.95

    def test_raw_fallback_on_parse_failure(self, mock_ollama_client):
        mock_ollama_client.post.return_value.status_code = 200
        mock_ollama_client.post.return_value.json.return_value = {
            "message": {"content": "Just some plain text, not valid JSON."}
        }
        mock_ollama_client.post.return_value.content = b"{}"

        result = export_ollama_memories(
            "nomic-embed-text", ["Some context here."]
        )

        assert len(result["memories"]) == 1
        mem = result["memories"][0]
        assert mem["type"] == "artifact"
        assert mem["confidence"] == 0.7
        assert "Just some plain text" in mem["content"]

    def test_empty_json_fallback(self, mock_ollama_client):
        """Valid-but-empty JSON (empty array/object/null) should fall back to raw context."""
        for empty_json in ("[]", "{}", "null"):
            mock_ollama_client.post.return_value.status_code = 200
            mock_ollama_client.post.return_value.json.return_value = {
                "message": {"content": empty_json}
            }
            mock_ollama_client.post.return_value.content = b"{}"

            result = export_ollama_memories(
                "nomic-embed-text", [f"Context for {empty_json}"]
            )

            assert len(result["memories"]) >= 1, f"Empty JSON {empty_json!r} should produce a fallback memory"

    def test_http_error_preserves_raw_context(self, mock_ollama_client):
        mock_ollama_client.post.return_value.status_code = 500
        mock_ollama_client.post.return_value.text = "Server error"

        result = export_ollama_memories(
            "nomic-embed-text", ["Important context data."]
        )

        assert len(result["memories"]) == 1
        mem = result["memories"][0]
        assert mem["type"] == "artifact"
        assert "Important context data" in mem["content"]
        assert mem["confidence"] == 0.5

    def test_empty_contexts(self, mock_ollama_client):
        result = export_ollama_memories("nomic-embed-text", [])
        assert result["summary"]["memory_count"] == 0
        assert result["memories"] == []

    def test_multiple_contexts(self, mock_ollama_client):
        extracted = [{
            "type": "fact",
            "title": "Test",
            "content": "Test content",
            "tags": [],
            "confidence": 0.9,
        }]
        mock_ollama_client.post.return_value.status_code = 200
        mock_ollama_client.post.return_value.json.return_value = {
            "message": {"content": json.dumps(extracted)}
        }
        mock_ollama_client.post.return_value.content = b"{}"

        result = export_ollama_memories(
            "nomic-embed-text",
            ["Context A", "Context B", "Context C"],
        )
        assert result["summary"]["context_count"] == 3
        assert result["summary"]["memory_count"] == 3

    def test_exception_preserves_context(self, mock_ollama_client):
        mock_ollama_client.post.side_effect = Exception("Connection lost")

        result = export_ollama_memories(
            "nomic-embed-text", ["Critical data here."]
        )

        assert len(result["memories"]) == 1
        assert "Critical data here" in result["memories"][0]["content"]
        assert result["memories"][0]["confidence"] == 0.3


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------

class TestMapOllama:
    def test_maps_all_memories(self, sample_export):
        rows = map_ollama(sample_export)
        assert len(rows) == 4

    def test_preserves_types(self, sample_export):
        rows = map_ollama(sample_export)
        types = {r["type"] for r in rows}
        assert "preference" in types
        assert "fact" in types
        assert "commitment" in types
        assert "event" in types

    def test_invalid_type_nullified(self):
        export = {
            "memories": [
                {
                    "title": "Test",
                    "content": "Test content.",
                    "type": "invalid-type-xyz",
                    "tags": [],
                    "confidence": 0.8,
                }
            ]
        }
        rows = map_ollama(export)
        assert rows[0]["type"] is None  # Let Memanto auto-classify

    def test_empty_memories(self):
        rows = map_ollama({"memories": []})
        assert rows == []

    def test_missing_memories_key(self):
        rows = map_ollama({})
        assert rows == []

    def test_empty_content_skipped(self):
        export = {
            "memories": [
                {"title": "Empty", "content": "", "tags": [], "confidence": 0.8}
            ]
        }
        rows = map_ollama(export)
        assert rows == []

    def test_confidence_bounds(self):
        export = {
            "memories": [
                {
                    "title": "High",
                    "content": "x",
                    "confidence": 999.0,
                    "tags": [],
                },
                {
                    "title": "Low",
                    "content": "x",
                    "confidence": -5.0,
                    "tags": [],
                },
                {
                    "title": "None",
                    "content": "x",
                    "confidence": None,
                    "tags": [],
                },
            ]
        }
        rows = map_ollama(export)
        assert rows[0]["confidence"] == 1.0
        assert rows[1]["confidence"] == 0.0
        assert rows[2]["confidence"] == 0.8  # default

    def test_returns_required_fields(self, sample_export):
        rows = map_ollama(sample_export)
        for row in rows:
            assert "title" in row
            assert "content" in row
            assert "type" in row or row["type"] is None
            assert "tags" in row
            assert isinstance(row["tags"], list)
            assert "confidence" in row
            assert row["confidence"] >= 0.0
            assert row["confidence"] <= 1.0
            assert row["source"] == "ollama"
            assert row["provenance"] == "imported"
            assert "updated_at" in row


# ---------------------------------------------------------------------------
# OKF Bundle Building
# ---------------------------------------------------------------------------

class TestBuildOkfBundle:
    def test_creates_bundle_structure(self, sample_export, tmp_output_dir):
        result = build_okf_bundle(sample_export, tmp_output_dir / "okf_bundle")
        assert result["total_memories"] == 4
        assert result["per_type_counts"] == {
            "commitment": 1,
            "event": 1,
            "fact": 1,
            "preference": 1,
        }
        assert set(result["sections"]) == {"memories", "metrics"}

        bundle_dir = Path(result["output_path"])
        assert bundle_dir.is_dir()
        assert (bundle_dir / "index.md").exists()
        assert (bundle_dir / "memories" / "index.md").exists()
        assert (bundle_dir / "metrics" / "overview.md").exists()

    def test_file_per_memory_layout(self, sample_export, tmp_output_dir):
        result = build_okf_bundle(
            sample_export, tmp_output_dir / "okf_file", split="file"
        )
        bundle_dir = Path(result["output_path"])

        # Each memory should have its own .md file
        pref_dir = bundle_dir / "memories" / "preference"
        assert pref_dir.is_dir()
        pref_files = list(pref_dir.glob("*.md"))
        # One index + one memory file
        assert len(pref_files) == 2
        assert any(f.name != "index.md" for f in pref_files)

    def test_stacked_layout(self, sample_export, tmp_output_dir):
        result = build_okf_bundle(
            sample_export, tmp_output_dir / "okf_type", split="type"
        )
        bundle_dir = Path(result["output_path"])

        pref_dir = bundle_dir / "memories" / "preference"
        assert pref_dir.is_dir()
        assert (pref_dir / "preference.md").exists()

    def test_auto_split_switches_to_stacked(self, sample_export, tmp_output_dir):
        # threshold = 2 → no type exceeds it (each has 1 memory), stays file-per-memory
        result = build_okf_bundle(
            sample_export, tmp_output_dir / "okf_auto", split="auto", threshold=2
        )
        assert result["total_memories"] == 4
        # With threshold=0 all types are larger than threshold → stacked
        result2 = build_okf_bundle(
            sample_export, tmp_output_dir / "okf_auto2", split="auto", threshold=0
        )
        bundle_dir = Path(result2["output_path"])
        # With threshold=0 all types are larger than threshold
        for mtype in ["preference", "fact", "commitment", "event"]:
            type_dir = bundle_dir / "memories" / mtype
            assert (type_dir / f"{mtype}.md").exists()

    def test_empty_export(self, tmp_output_dir):
        empty = {
            "exported_at": "2026-01-01T00:00:00+00:00",
            "model": "test",
            "chat_model": "test",
            "summary": {"memory_count": 0, "context_count": 0},
            "memories": [],
        }
        result = build_okf_bundle(empty, tmp_output_dir / "empty_bundle")
        assert result["total_memories"] == 0
        assert result["per_type_counts"] == {}

    def test_okf_frontmatter_valid(self, sample_export, tmp_output_dir):
        import yaml

        result = build_okf_bundle(
            sample_export, tmp_output_dir / "okf_frontmatter", split="file"
        )
        bundle_dir = Path(result["output_path"])

        # Check a memory file has valid YAML frontmatter
        pref_dir = bundle_dir / "memories" / "preference"
        md_files = [f for f in pref_dir.glob("*.md") if f.name != "index.md"]
        assert len(md_files) > 0

        content = md_files[0].read_text(encoding="utf-8")
        assert content.startswith("---")
        parts = content.split("---", 2)
        assert len(parts) >= 3

        fm = yaml.safe_load(parts[1])
        assert "type" in fm
        assert "title" in fm
        assert "x_memanto" in fm

    def test_metrics_file_has_summary(self, sample_export, tmp_output_dir):
        result = build_okf_bundle(sample_export, tmp_output_dir / "okf_metrics")
        bundle_dir = Path(result["output_path"])

        metrics = (bundle_dir / "metrics" / "overview.md").read_text(encoding="utf-8")
        assert "Migration Metrics" in metrics
        assert "Total Memories Exported" in metrics
        assert "4" in metrics


# ---------------------------------------------------------------------------
# Full Migration Pipeline
# ---------------------------------------------------------------------------

class TestRunFullMigration:
    def test_produces_export_and_okf(self, mock_ollama_client, tmp_output_dir):
        # Mock model discovery
        mock_ollama_client.get.return_value.status_code = 200
        mock_ollama_client.get.return_value.json.return_value = {
            "models": [
                {"name": "nomic-embed-text:latest", "details": {}},
            ]
        }
        mock_ollama_client.get.return_value.content = b"{}"

        # Mock embedding verification
        mock_ollama_client.post.return_value.status_code = 200
        mock_ollama_client.post.return_value.json.side_effect = [
            # First call: embeddings verify
            {"embedding": [0.1] * 768},
            # Second call: chat extraction
            {
                "message": {
                    "content": json.dumps([{
                        "type": "preference",
                        "title": "Dark mode",
                        "content": "User prefers dark mode.",
                        "tags": ["ui"],
                        "confidence": 0.95,
                    }])
                }
            },
        ]
        mock_ollama_client.post.return_value.content = b"{}"

        result = run_full_migration(
            model="nomic-embed-text",
            contexts=["User likes dark mode."],
            output_dir=tmp_output_dir,
            verify_embedding=True,
        )

        assert "export" in result
        assert "okf_bundle" in result
        assert "model_info" in result
        assert "embedding_verify" in result
        assert "export_path" in result

        export_path = Path(result["export_path"])
        assert export_path.exists()
        assert export_path.name == "ollama_export.json"

        okf_dir = Path(result["okf_bundle"]["output_path"])
        assert okf_dir.is_dir()
        assert (okf_dir / "index.md").exists()

    def test_skip_verify(self, mock_ollama_client, tmp_output_dir):
        mock_ollama_client.get.return_value.status_code = 200
        mock_ollama_client.get.return_value.json.return_value = {
            "models": [{"name": "nomic-embed-text:latest", "details": {}}]
        }
        mock_ollama_client.get.return_value.content = b"{}"

        # Only chat extraction (no embedding verify)
        mock_ollama_client.post.return_value.status_code = 200
        mock_ollama_client.post.return_value.json.return_value = {
            "message": {"content": json.dumps([{"type": "fact", "title": "T", "content": "C", "tags": [], "confidence": 0.9}])}
        }
        mock_ollama_client.post.return_value.content = b"{}"

        result = run_full_migration(
            model="nomic-embed-text",
            contexts=["Test."],
            output_dir=tmp_output_dir,
            verify_embedding=False,
        )

        assert "embedding_verify" not in result


# ---------------------------------------------------------------------------
# Integration: export JSON → memanto migrate compatibility
# ---------------------------------------------------------------------------

class TestMemantoMigrateCompatibility:
    """Verify the export JSON is compatible with memanto migrate --file."""

    def test_export_has_required_top_level_fields(self, sample_export):
        required = {"exported_at", "provider", "model", "summary", "memories"}
        assert required.issubset(sample_export.keys())

    def test_summary_has_counts(self, sample_export):
        summary = sample_export["summary"]
        assert "memory_count" in summary
        assert isinstance(summary["memory_count"], int)
        assert summary["memory_count"] > 0

    def test_each_memory_has_content(self, sample_export):
        for mem in sample_export["memories"]:
            assert "content" in mem
            assert mem["content"].strip()

    def test_mapper_output_is_batch_remember_shape(self, sample_export):
        from memanto.cli.migrate.mappers import MAPPERS

        # Register the ollama mapper (simulating what would happen in production)
        with patch.dict(MAPPERS, {"ollama": map_ollama}):
            rows = MAPPERS["ollama"](sample_export)
            assert len(rows) == 4
            for row in rows:
                assert "title" in row
                assert "content" in row
                assert "type" in row or row["type"] is None
                assert isinstance(row["confidence"], float)
                assert row["confidence"] >= 0 and row["confidence"] <= 1
                assert row["provenance"] == "imported"

    def test_can_load_export_json(self, sample_export, tmp_output_dir):
        """Write export to JSON, read it back — simulate --file workflow."""
        export_path = tmp_output_dir / "ollama_export.json"
        export_path.write_text(
            json.dumps(sample_export, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        # Simulate memanto migrate loading
        loaded = json.loads(export_path.read_text(encoding="utf-8"))
        assert loaded["provider"] == "ollama"
        assert len(loaded["memories"]) == 4


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_none_memories_in_export(self):
        export = {"memories": None}
        rows = map_ollama(export)
        assert rows == []

    def test_malformed_memory_entries(self):
        export = {
            "memories": [
                "not a dict",
                123,
                None,
                {},
            ]
        }
        rows = map_ollama(export)
        # Only iterate dict entries, skip non-dicts gracefully
        assert rows == []

    def test_very_long_content(self):
        long_content = "A" * 20000
        export = {
            "memories": [
                {
                    "title": "Long",
                    "content": long_content,
                    "tags": [],
                    "confidence": 0.8,
                }
            ]
        }
        rows = map_ollama(export)
        assert len(rows) == 1
        assert len(rows[0]["content"]) == len(long_content)  # No truncation at mapper level

    def test_unicode_and_special_chars(self, tmp_output_dir):
        export = {
            "exported_at": "2026-01-01T00:00:00+00:00",
            "model": "test",
            "chat_model": "test",
            "summary": {"memory_count": 1, "context_count": 0},
            "memories": [
                {
                    "title": "ユーザー設定",
                    "content": "日本語のテキストを含むメモリです。🎉🚀",
                    "type": "preference",
                    "tags": ["日本語", "emoji"],
                    "confidence": 0.9,
                }
            ],
        }
        result = build_okf_bundle(export, tmp_output_dir / "unicode_bundle")
        assert result["total_memories"] == 1

        # Verify the markdown file can be read back
        bundle_dir = Path(result["output_path"])
        pref_dir = bundle_dir / "memories" / "preference"
        md_files = [f for f in pref_dir.glob("*.md") if f.name != "index.md"]
        assert len(md_files) > 0
        content = md_files[0].read_text(encoding="utf-8")
        assert "日本語" in content
        assert "🎉" in content

    def test_mixed_null_and_valid_memories(self):
        export = {
            "memories": [
                None,
                {"title": "Valid", "content": "OK", "tags": [], "confidence": 0.8},
                None,
                {"title": "", "content": "", "tags": [], "confidence": 0.8},
                {"title": "Also valid", "content": "Yes", "tags": [], "confidence": 0.9},
            ]
        }
        rows = map_ollama(export)
        assert len(rows) == 2  # Only the two with non-empty content
