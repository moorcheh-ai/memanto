from datetime import datetime, timezone

import pytest

from mappers import map_chroma, map_hindsight, map_zep


def _zep_export(*edges):
    return {"memories": list(edges)}


def _hindsight_export(*items):
    return {"memories": list(items)}


def _chroma_export(*items):
    return {"memories": list(items)}


class TestMapZep:
    def test_fact_field_becomes_content(self):
        export = _zep_export({"fact": "User prefers dark mode", "uuid": "abc"})
        assert map_zep(export)[0]["content"].startswith("User prefers dark mode")

    def test_type_is_always_fact(self):
        assert map_zep(_zep_export({"fact": "Some fact"}))[0]["type"] == "fact"

    def test_valid_at_maps_to_created_at(self):
        export = _zep_export({"fact": "x", "valid_at": "2024-01-15T12:00:00Z"})
        assert map_zep(export)[0]["created_at"] == datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_created_at_fallback_when_no_valid_at(self):
        export = _zep_export({"fact": "x", "created_at": "2024-03-01T00:00:00Z"})
        assert map_zep(export)[0]["created_at"] == datetime(2024, 3, 1, tzinfo=timezone.utc)

    def test_source_and_provenance(self):
        r = map_zep(_zep_export({"fact": "x"}))[0]
        assert r["source"] == "zep"
        assert r["provenance"] == "imported"

    def test_uuid_becomes_source_ref(self):
        export = _zep_export({"fact": "x", "uuid": "edge-uuid-123"})
        assert map_zep(export)[0]["source_ref"] == "edge-uuid-123"

    @pytest.mark.parametrize("field,value,expected", [
        ("score",     0.6,  0.6),
        ("relevance", 0.9,  0.9),
        ("score",     1.5,  1.0),
        ("score",    -0.2,  0.0),
        ("score",     0.0,  0.0),   # 0.0 must not fall back to 0.8
    ])
    def test_confidence_from_score_or_relevance(self, field, value, expected):
        export = _zep_export({"fact": "x", field: value})
        assert map_zep(export)[0]["confidence"] == pytest.approx(expected)

    def test_score_takes_precedence_over_relevance(self):
        # both present — score wins
        export = _zep_export({"fact": "x", "score": 0.3, "relevance": 0.9})
        assert map_zep(export)[0]["confidence"] == pytest.approx(0.3)

    def test_confidence_defaults_to_0_8_when_absent(self):
        assert map_zep(_zep_export({"fact": "x"}))[0]["confidence"] == pytest.approx(0.8)

    def test_empty_memories_returns_empty(self):
        assert map_zep({"memories": []}) == []

    def test_missing_fact_field_skipped(self):
        export = _zep_export({"fact": ""}, {"fact": "valid"})
        result = map_zep(export)
        assert len(result) == 1
        assert result[0]["content"].startswith("valid")

    def test_multiple_edges_all_mapped(self):
        export = _zep_export(
            {"fact": "fact one", "uuid": "u1"},
            {"fact": "fact two", "uuid": "u2"},
        )
        result = map_zep(export)
        assert len(result) == 2
        assert result[0]["source_ref"] == "u1"
        assert result[1]["source_ref"] == "u2"


class TestMapHindsight:
    def test_text_field_becomes_content(self):
        export = _hindsight_export({"text": "I visited Paris", "fact_type": "experience"})
        assert map_hindsight(export)[0]["content"].startswith("I visited Paris")

    def test_content_fallback_when_no_text(self):
        export = _hindsight_export({"content": "fallback text", "fact_type": "world"})
        assert map_hindsight(export)[0]["content"].startswith("fallback text")

    @pytest.mark.parametrize("fact_type,expected_type", [
        ("world",       "fact"),
        ("experience",  "event"),
        ("observation", "observation"),
    ])
    def test_hindsight_type_map(self, fact_type, expected_type):
        export = _hindsight_export({"text": "x", "fact_type": fact_type})
        assert map_hindsight(export)[0]["type"] == expected_type

    def test_unknown_fact_type_returns_none(self):
        export = _hindsight_export({"text": "x", "fact_type": "totally_unknown_type"})
        assert map_hindsight(export)[0]["type"] is None

    def test_source_and_provenance(self):
        r = map_hindsight(_hindsight_export({"text": "x"}))[0]
        assert r["source"] == "hindsight"
        assert r["provenance"] == "imported"

    def test_date_maps_to_created_at(self):
        export = _hindsight_export({"text": "x", "date": "2024-05-10T08:00:00Z"})
        assert map_hindsight(export)[0]["created_at"] == datetime(2024, 5, 10, 8, 0, 0, tzinfo=timezone.utc)

    def test_mentioned_at_fallback(self):
        export = _hindsight_export({"text": "x", "mentioned_at": "2024-06-01T00:00:00Z"})
        assert map_hindsight(export)[0]["created_at"] == datetime(2024, 6, 1, tzinfo=timezone.utc)

    def test_tags_preserved(self):
        export = _hindsight_export({"text": "x", "tags": ["travel", "personal"]})
        assert map_hindsight(export)[0]["tags"] == ["travel", "personal"]

    def test_empty_tags_when_absent(self):
        assert map_hindsight(_hindsight_export({"text": "x"}))[0]["tags"] == []

    def test_empty_memories_returns_empty(self):
        assert map_hindsight({"memories": []}) == []


class TestMapChroma:
    def test_document_field_becomes_content(self):
        export = _chroma_export({"document": "some vector doc", "id": "c1", "metadata": {}})
        assert "some vector doc" in map_chroma(export)[0]["content"]

    def test_payload_source_is_chroma(self):
        export = _chroma_export({"document": "x", "id": "c1", "metadata": {}})
        assert map_chroma(export)[0]["source"] == "chroma"

    def test_metadata_source_goes_into_footer(self):
        export = _chroma_export({
            "document": "doc text",
            "id": "c1",
            "metadata": {"source": "https://example.com/article"},
        })
        r = map_chroma(export)[0]
        assert r["source"] == "chroma"
        assert "[Supporting data]" in r["content"]
        assert "https://example.com/article" in r["content"]

    def test_id_becomes_source_ref(self):
        export = _chroma_export({"document": "x", "id": "chroma-id-99", "metadata": {}})
        assert map_chroma(export)[0]["source_ref"] == "chroma-id-99"

    def test_type_is_none(self):
        assert map_chroma(_chroma_export({"document": "x", "id": "c1", "metadata": {}}))[0]["type"] is None

    def test_provenance_is_imported(self):
        assert map_chroma(_chroma_export({"document": "x", "id": "c1", "metadata": {}}))[0]["provenance"] == "imported"

    def test_supporting_data_footer_format(self):
        export = _chroma_export({
            "document": "content",
            "id": "c1",
            "metadata": {"source": "wiki"},
        })
        content = map_chroma(export)[0]["content"]
        assert "\n\n---\n[Supporting data]" in content
        assert "- source: wiki" in content

    def test_empty_memories_returns_empty(self):
        assert map_chroma({"memories": []}) == []

    def test_no_metadata_no_footer(self):
        export = _chroma_export({"document": "plain doc", "id": "c1", "metadata": {}})
        assert map_chroma(export)[0]["content"] == "plain doc"

    def test_multiple_items_all_mapped(self):
        export = _chroma_export(
            {"document": "doc a", "id": "ca", "metadata": {}},
            {"document": "doc b", "id": "cb", "metadata": {}},
        )
        result = map_chroma(export)
        assert len(result) == 2
        assert result[0]["source_ref"] == "ca"
        assert result[1]["source_ref"] == "cb"
