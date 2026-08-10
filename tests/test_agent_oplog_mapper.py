"""Tests for the agent operational-log migration adapter.

The adapter's job is not format translation. An oplog's defining property is
that later records overturn earlier ones on the same channel, and a plain
content dump loses that: the stale belief and the finding that killed it arrive
as two equally-confident memories. These tests pin the correction structure.
"""

from __future__ import annotations

from datetime import timezone

from memanto.cli.migrate.mappers import MAPPERS, map_agent_oplog
from memanto.cli.migrate.runner import source_count


def _export(records):
    return {"provider": "agent_oplog", "records": records}


def _tags(row):
    return set(row.get("tags") or [])


def test_registered_in_mappers():
    assert MAPPERS["agent_oplog"] is map_agent_oplog


def test_source_count_uses_records():
    exp = _export([{"at": "2026-07-24T08:00:00Z", "channel": "c", "result": "r"}])
    assert source_count("agent_oplog", exp) == 1


def test_source_count_of_other_providers_unaffected():
    # A provider without a `records` key must not start counting oplog records.
    assert source_count("mem0", {"memories": [{"memory": "x"}]}) == 1


def test_maps_action_and_result_into_content():
    rows = map_agent_oplog(
        _export(
            [
                {
                    "id": "a",
                    "at": "2026-07-24T08:00:00Z",
                    "channel": "vercel-analytics",
                    "action": "enable web analytics",
                    "result": "script returns 404",
                }
            ]
        )
    )
    assert len(rows) == 1
    content = rows[0]["content"]
    assert "Channel: vercel-analytics" in content
    assert "What I tried: enable web analytics" in content
    assert "What actually happened: script returns 404" in content


def test_original_timestamp_is_preserved():
    """A migration that loses `created_at` makes --as-of queries meaningless."""
    rows = map_agent_oplog(
        _export([{"at": "2026-07-24T08:35:56Z", "channel": "c", "result": "r"}])
    )
    created = rows[0]["created_at"]
    assert created is not None
    assert created.year == 2026 and created.month == 7 and created.day == 24
    assert created.hour == 8 and created.minute == 35
    assert created.tzinfo is not None
    assert created.astimezone(timezone.utc).isoformat().startswith("2026-07-24T08:35:56")


def test_later_record_supersedes_earlier_on_same_channel():
    rows = map_agent_oplog(
        _export(
            [
                {
                    "id": "old",
                    "at": "2026-07-24T08:35:00Z",
                    "channel": "vercel-analytics",
                    "result": "404, integration only partial",
                },
                {
                    "id": "new",
                    "at": "2026-07-24T08:43:00Z",
                    "channel": "vercel-analytics",
                    "result": "WORKING now: returns 200",
                },
            ]
        )
    )
    by_ref = {r["source_ref"]: r for r in rows}

    old, new = by_ref["old"], by_ref["new"]
    assert "oplog-superseded" in _tags(old)
    assert "oplog-current" not in _tags(old)
    assert "oplog-current" in _tags(new)
    assert "oplog-superseded" not in _tags(new)

    # The stale memory must carry a pointer to what replaced it, so a reader
    # that retrieves it still learns it is stale.
    assert "SUPERSEDED" in old["content"]
    assert "WORKING now: returns 200" in old["content"]

    # And it must not outrank the correction on confidence.
    assert old["confidence"] < new["confidence"]
    assert old["type"] == "error"
    assert new["type"] == "learning"


def test_out_of_order_input_still_resolves_newest():
    """Supersession follows the timestamp, not the position in the file."""
    rows = map_agent_oplog(
        _export(
            [
                {"id": "new", "at": "2026-07-25T10:00:00Z", "channel": "c", "result": "second"},
                {"id": "old", "at": "2026-07-24T10:00:00Z", "channel": "c", "result": "first"},
            ]
        )
    )
    by_ref = {r["source_ref"]: r for r in rows}
    assert "oplog-current" in _tags(by_ref["new"])
    assert "oplog-superseded" in _tags(by_ref["old"])


def test_distinct_channels_do_not_supersede_each_other():
    rows = map_agent_oplog(
        _export(
            [
                {"id": "a", "at": "2026-07-24T10:00:00Z", "channel": "one", "result": "x"},
                {"id": "b", "at": "2026-07-25T10:00:00Z", "channel": "two", "result": "y"},
            ]
        )
    )
    assert all("oplog-current" in _tags(r) for r in rows)
    assert not any("oplog-superseded" in _tags(r) for r in rows)


def test_single_record_channel_is_current():
    rows = map_agent_oplog(
        _export([{"id": "a", "at": "2026-07-24T10:00:00Z", "channel": "solo", "result": "x"}])
    )
    assert "oplog-current" in _tags(rows[0])
    assert rows[0]["type"] == "learning"


def test_records_without_action_or_result_are_skipped():
    rows = map_agent_oplog(
        _export(
            [
                {"id": "empty", "at": "2026-07-24T10:00:00Z", "channel": "c"},
                {"id": "ok", "at": "2026-07-24T11:00:00Z", "channel": "c", "result": "r"},
            ]
        )
    )
    assert [r["source_ref"] for r in rows] == ["ok"]


def test_missing_timestamps_do_not_crash():
    rows = map_agent_oplog(
        _export(
            [
                {"id": "a", "channel": "c", "result": "no timestamp"},
                {"id": "b", "at": "2026-07-24T10:00:00Z", "channel": "c", "result": "dated"},
            ]
        )
    )
    assert len(rows) == 2
    assert all(r["source"] == "agent_oplog" for r in rows)
    assert all(r["provenance"] == "imported" for r in rows)


def test_evidence_is_preserved_in_footer():
    rows = map_agent_oplog(
        _export(
            [
                {
                    "id": "a",
                    "at": "2026-07-24T10:00:00Z",
                    "channel": "c",
                    "result": "r",
                    "evidence": "iter-173; 495-project pull",
                }
            ]
        )
    )
    assert "iter-173; 495-project pull" in rows[0]["content"]


def test_channel_becomes_a_stable_tag():
    rows = map_agent_oplog(
        _export(
            [
                {
                    "id": "a",
                    "at": "2026-07-24T10:00:00Z",
                    "channel": "sizing a market with a keyword filter I wrote myself",
                    "result": "r",
                }
            ]
        )
    )
    tags = _tags(rows[0])
    assert "oplog" in tags
    assert any(t.startswith("sizing-a-market-with-a-keyword-filter") for t in tags)
