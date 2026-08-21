"""
test_notion_adapter.py
======================
Focused tests for the Notion → Memanto migration adapter.

Tests cover:
  - Type mapping from Notion "Type" property
  - Type inference from database name
  - Tag extraction and database-name tagging
  - Timestamp parsing (ISO 8601 with/without Z)
  - Confidence mapping from Priority
  - Supporting data footer construction
  - Blank/empty/archived page handling
  - Duplicate page deduplication
  - Content truncation at _MAX_CONTENT_CHARS
  - Round-trip field fidelity (title, source_ref, provenance)
  - Source count helper

Run:
    pytest tests/test_notion_adapter.py -v
    (no API keys, no network required)
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the adapter is importable without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))
from notion_adapter import (
    NOTION_TYPE_MAP,
    _coerce_type,
    _parse_dt,
    _title_from,
    map_notion,
    source_count,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _page(
    *,
    id: str = "page-001",
    database: str = "Research Notes",
    title: str = "Test page",
    content: str = "Some content about the test topic.",
    created_time: str = "2025-10-01T09:00:00Z",
    last_edited_time: str = "2025-10-02T12:00:00Z",
    props: dict | None = None,
    url: str = "https://notion.so/test",
) -> dict:
    return {
        "id": id,
        "database": database,
        "title": title,
        "created_time": created_time,
        "last_edited_time": last_edited_time,
        "properties": props or {"Type": "fact", "Tags": ["test"], "Priority": "Medium"},
        "content": content,
        "url": url,
    }


def _export(*pages) -> dict:
    return {"pages": list(pages)}


# ── _coerce_type ──────────────────────────────────────────────────────────────


class TestCoerceType:
    def test_known_types_map_correctly(self):
        for notion_val, expected in NOTION_TYPE_MAP.items():
            assert _coerce_type(notion_val) == expected

    def test_case_insensitive(self):
        assert _coerce_type("DECISION") == "decision"
        assert _coerce_type("Preference") == "preference"

    def test_task_maps_to_commitment(self):
        assert _coerce_type("task") == "commitment"

    def test_meeting_maps_to_event(self):
        assert _coerce_type("meeting") == "event"

    def test_unknown_returns_none(self):
        assert _coerce_type("random_notion_type") is None

    def test_none_returns_none(self):
        assert _coerce_type(None) is None

    def test_empty_string_returns_none(self):
        assert _coerce_type("") is None


# ── _parse_dt ─────────────────────────────────────────────────────────────────


class TestParseDt:
    def test_iso_with_z_suffix(self):
        dt = _parse_dt("2025-10-01T09:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.year == 2025

    def test_iso_with_offset(self):
        dt = _parse_dt("2025-10-01T09:00:00+00:00")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_naive_iso_gets_utc(self):
        dt = _parse_dt("2025-10-01T09:00:00")
        assert dt is not None
        assert dt.tzinfo == timezone.utc

    def test_none_returns_none(self):
        assert _parse_dt(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_dt("") is None

    def test_invalid_string_returns_none(self):
        assert _parse_dt("not-a-date") is None

    def test_already_datetime_preserved(self):
        now = datetime.now(timezone.utc)
        assert _parse_dt(now) is now

    def test_naive_datetime_gets_utc(self):
        naive = datetime(2025, 1, 1, 0, 0, 0)
        result = _parse_dt(naive)
        assert result.tzinfo == timezone.utc


# ── _title_from ───────────────────────────────────────────────────────────────


class TestTitleFrom:
    def test_short_content_unchanged(self):
        assert _title_from("Short title") == "Short title"

    def test_long_content_truncated(self):
        long = "A" * 100
        result = _title_from(long)
        assert result.endswith("...")
        assert len(result) == 80

    def test_newlines_replaced(self):
        result = _title_from("Line one\nLine two")
        assert "\n" not in result


# ── map_notion — core mapping ─────────────────────────────────────────────────


class TestMapNotion:
    def test_basic_page_maps_correctly(self):
        rows = map_notion(_export(_page()))
        assert len(rows) == 1
        row = rows[0]
        assert row["title"] == "Test page"
        assert "Some content" in row["content"]
        assert row["source"] == "notion"
        assert row["source_ref"] == "page-001"
        assert row["provenance"] == "imported"

    def test_type_from_property(self):
        p = _page(props={"Type": "decision", "Tags": [], "Priority": "High"})
        rows = map_notion(_export(p))
        assert rows[0]["type"] == "decision"

    def test_type_inference_from_decisions_database(self):
        p = _page(database="Project Decisions", props={"Tags": []})
        rows = map_notion(_export(p))
        assert rows[0]["type"] == "decision"

    def test_type_inference_from_meeting_database(self):
        p = _page(database="Meeting Notes", props={"Tags": []})
        rows = map_notion(_export(p))
        assert rows[0]["type"] == "event"

    def test_tags_extracted(self):
        p = _page(props={"Type": "fact", "Tags": ["AI", "research"], "Priority": "Low"})
        rows = map_notion(_export(p))
        tags = rows[0]["tags"]
        assert "AI" in tags
        assert "research" in tags

    def test_database_name_added_as_tag(self):
        p = _page(database="Research Notes")
        rows = map_notion(_export(p))
        tags = rows[0]["tags"]
        assert any("research-notes" in t for t in tags)

    def test_high_priority_confidence(self):
        p = _page(props={"Type": "fact", "Tags": [], "Priority": "High"})
        rows = map_notion(_export(p))
        assert rows[0]["confidence"] == 0.9

    def test_critical_priority_confidence(self):
        p = _page(props={"Type": "fact", "Tags": [], "Priority": "Critical"})
        rows = map_notion(_export(p))
        assert rows[0]["confidence"] == 0.95

    def test_low_priority_confidence(self):
        p = _page(props={"Type": "fact", "Tags": [], "Priority": "Low"})
        rows = map_notion(_export(p))
        assert rows[0]["confidence"] == 0.7

    def test_created_at_parsed(self):
        rows = map_notion(_export(_page(created_time="2025-10-01T09:00:00Z")))
        dt = rows[0]["created_at"]
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None
        assert dt.year == 2025

    def test_updated_at_is_now(self):
        rows = map_notion(_export(_page()))
        dt = rows[0]["updated_at"]
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None

    def test_footer_contains_source_id(self):
        rows = map_notion(_export(_page(id="abc-123")))
        assert "notion:abc-123" in rows[0]["content"]

    def test_footer_contains_url(self):
        rows = map_notion(_export(_page(url="https://notion.so/mypage")))
        assert "https://notion.so/mypage" in rows[0]["content"]

    def test_footer_contains_database(self):
        rows = map_notion(_export(_page(database="Research Notes")))
        assert "Research Notes" in rows[0]["content"]


# ── map_notion — edge cases ───────────────────────────────────────────────────


class TestMapNotionEdgeCases:
    def test_empty_pages_list(self):
        assert map_notion({"pages": []}) == []

    def test_missing_pages_key(self):
        assert map_notion({}) == []

    def test_page_with_no_content_uses_title(self):
        p = _page(content="", title="Only a title")
        rows = map_notion(_export(p))
        assert len(rows) == 1
        assert "Only a title" in rows[0]["content"]

    def test_completely_blank_page_skipped(self):
        p = _page(content="", title="")
        rows = map_notion(_export(p))
        assert len(rows) == 0

    def test_archived_page_skipped(self):
        p = _page(props={"Status": "Archived", "Tags": [], "Type": "fact"})
        rows = map_notion(_export(p))
        assert len(rows) == 0

    def test_cancelled_page_skipped(self):
        p = _page(props={"Status": "Cancelled", "Tags": [], "Type": "fact"})
        rows = map_notion(_export(p))
        assert len(rows) == 0

    def test_duplicate_page_ids_deduplicated(self):
        p1 = _page(id="dup-001", title="First")
        p2 = _page(id="dup-001", title="Second")  # same ID
        rows = map_notion(_export(p1, p2))
        assert len(rows) == 1
        assert rows[0]["title"] == "First"

    def test_multiple_pages_all_mapped(self):
        pages = [_page(id=f"page-{i:03d}", title=f"Page {i}") for i in range(5)]
        rows = map_notion({"pages": pages})
        assert len(rows) == 5

    def test_content_truncated_at_limit(self):
        long_content = "x" * 12000
        p = _page(content=long_content)
        rows = map_notion(_export(p))
        assert len(rows[0]["content"]) <= 10000

    def test_unknown_type_results_in_none(self):
        p = _page(props={"Type": "unknownnotiontype", "Tags": [], "Priority": "Low"})
        rows = map_notion(_export(p))
        assert rows[0]["type"] is None

    def test_missing_tags_property_ok(self):
        p = _page(props={"Type": "fact", "Priority": "Low"})
        rows = map_notion(_export(p))
        assert isinstance(rows[0]["tags"], list)

    def test_missing_priority_defaults_to_0_8(self):
        p = _page(props={"Type": "fact", "Tags": []})
        rows = map_notion(_export(p))
        assert rows[0]["confidence"] == 0.8

    def test_null_created_time_ok(self):
        p = dict(_page())
        p["created_time"] = None
        rows = map_notion(_export(p))
        assert len(rows) == 1
        assert rows[0]["created_at"] is None


# ── source_count ──────────────────────────────────────────────────────────────


class TestSourceCount:
    def test_counts_pages(self):
        export = {"pages": [_page(id=f"p{i}") for i in range(7)]}
        assert source_count(export) == 7

    def test_empty(self):
        assert source_count({"pages": []}) == 0

    def test_missing_key(self):
        assert source_count({}) == 0


# ── Full export round-trip (integration-level, no API) ────────────────────────


class TestFullExportRoundTrip:
    """Tests the complete mapping from the sample dataset."""

    def test_sample_dataset_maps_all_pages(self):
        import json

        sample = Path(__file__).parent.parent / "data" / "notion_export.json"
        assert sample.exists(), "Sample dataset missing — run from repo root"
        export = json.loads(sample.read_text(encoding="utf-8"))
        rows = map_notion(export)
        assert len(rows) == len(export["pages"]), (
            "All pages should map (none are archived)"
        )

    def test_decision_type_assigned_correctly(self):
        import json

        sample = Path(__file__).parent.parent / "data" / "notion_export.json"
        export = json.loads(sample.read_text(encoding="utf-8"))
        rows = map_notion(export)
        decisions = [r for r in rows if r.get("type") == "decision"]
        assert len(decisions) >= 2, "At least 2 decision pages in sample"

    def test_all_rows_have_required_fields(self):
        import json

        sample = Path(__file__).parent.parent / "data" / "notion_export.json"
        export = json.loads(sample.read_text(encoding="utf-8"))
        rows = map_notion(export)
        required = {
            "title",
            "content",
            "source",
            "source_ref",
            "provenance",
            "tags",
            "confidence",
        }
        for row in rows:
            missing = required - row.keys()
            assert not missing, f"Row missing fields: {missing}"

    def test_all_source_refs_are_notion_page_ids(self):
        import json

        sample = Path(__file__).parent.parent / "data" / "notion_export.json"
        export = json.loads(sample.read_text(encoding="utf-8"))
        rows = map_notion(export)
        page_ids = {p["id"] for p in export["pages"]}
        for row in rows:
            assert row["source_ref"] in page_ids

    def test_provenance_is_imported(self):
        import json

        sample = Path(__file__).parent.parent / "data" / "notion_export.json"
        export = json.loads(sample.read_text(encoding="utf-8"))
        rows = map_notion(export)
        for row in rows:
            assert row["provenance"] == "imported"
