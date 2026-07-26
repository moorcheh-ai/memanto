"""Tests for the Hindsight to OKF migration example."""

from __future__ import annotations

import importlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from examples.migrations.hindsight import adapter, run_demo, run_roundtrip
from examples.migrations.hindsight.scenario import retain_items
from examples.migrations.hindsight.validation import (
    build_parity_report,
    memanto_retriever,
    score_answer,
)
from examples.migrations.hindsight.verify_artifacts import (
    DEFAULT_ARTIFACTS,
    verify,
)
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

yaml = importlib.import_module("yaml")


def _record(record_id: str, fact_type: str = "world", **extra):
    """Create a representative Hindsight API record."""
    record = {
        "id": record_id,
        "text": f"Memory text for {record_id}",
        "context": "A real retained conversation",
        "date": "2026-07-20T09:30:00+00:00",
        "fact_type": fact_type,
        "document_id": "session-01",
        "mentioned_at": "2026-07-20T09:30:00+00:00",
        "occurred_start": None,
        "occurred_end": None,
        "entities": "Project Atlas, Dana",
        "chunk_id": "chunk-01",
        "proof_count": 1,
        "tags": ["project:atlas"],
        "metadata": {"source": "demo"},
        "consolidated_at": None,
        "consolidation_failed_at": None,
        "state": "valid",
        "invalidation_reason": None,
        "invalidated_at": None,
        "edited_at": None,
    }
    record.update(extra)
    return record


def _snapshot(items):
    """Wrap records in a deterministic captured snapshot."""
    return {
        "schema": adapter.SNAPSHOT_SCHEMA,
        "source": {
            "provider": "hindsight",
            "bank_id": "incident-agent",
            "base_url": "http://localhost:8888",
            "captured_at": "2026-07-25T08:00:00Z",
            "included_states": ["valid", "invalidated"],
        },
        "items": items,
    }


def _frontmatter(path: Path):
    """Parse the YAML frontmatter from one generated concept."""
    content = path.read_text(encoding="utf-8")
    raw = content.split("\n---\n", 1)[0].removeprefix("---\n")
    return yaml.safe_load(raw)


def test_bundle_maps_types_and_preserves_source_fields(tmp_path):
    """The bundle maps all Hindsight classes and survives Memanto dry mapping."""
    records = [
        _record("world-1", "world"),
        _record(
            "experience-1",
            "experience",
            occurred_start="2026-07-19T12:00:00+00:00",
        ),
        _record("observation-1", "observation", proof_count=4),
    ]
    output = tmp_path / "hindsight-okf"
    manifest = adapter.build_bundle(_snapshot(records), output)

    assert manifest["migration"]["type_counts"] == {
        "event": 1,
        "fact": 1,
        "learning": 1,
    }
    rows = map_okf(load_okf_bundle(output))
    assert len(rows) == 3
    assert {row["type"] for row in rows} == {"fact", "event", "learning"}
    assert {row["source"] for row in rows} == {"hindsight"}
    assert all(row["source_ref"].startswith("http://localhost:8888/") for row in rows)
    assert all("Memory text" in row["content"] for row in rows)

    learning_file = next((output / "memories" / "learning").glob("*.md"))
    frontmatter = _frontmatter(learning_file)
    assert frontmatter["x_memanto"]["confidence"] == 0.89
    assert frontmatter["x_hindsight"]["proof_count"] == 4
    assert frontmatter["sources"][0]["author"] == "process:hindsight"
    assert frontmatter["generated"]["by"] == "memanto-hindsight-okf/1.0.0"


def test_missing_fact_type_uses_conservative_unknown_mapping(tmp_path):
    """Missing source classes remain visible and never become world facts."""
    record = _record("unknown-1")
    record["fact_type"] = None
    output = tmp_path / "hindsight-okf"
    manifest = adapter.build_bundle(_snapshot([record]), output)

    assert manifest["migration"]["type_counts"] == {"observation": 1}
    concept = next((output / "memories" / "observation").glob("*.md"))
    frontmatter = _frontmatter(concept)
    assert frontmatter["type"] == "observation"
    assert frontmatter["x_memanto"]["confidence"] == 0.75
    assert frontmatter["x_hindsight"]["fact_type"] == "unknown"
    assert "hindsight:unknown" in frontmatter["tags"]


def test_invalidated_memories_are_archived_not_reactivated(tmp_path):
    """Invalidated source records remain inspectable but outside import scope."""
    invalidated = _record(
        "old-1",
        state="invalidated",
        invalidation_reason="Superseded by corrected incident owner",
        invalidated_at="2026-07-24T10:00:00+00:00",
    )
    output = tmp_path / "hindsight-okf"
    manifest = adapter.build_bundle(
        _snapshot([_record("current-1"), invalidated]),
        output,
    )

    assert manifest["migration"]["importable_records"] == 1
    assert manifest["migration"]["archived_records"] == 1
    assert len(load_okf_bundle(output)["memories"]) == 1

    archived_file = next((output / "archive" / "invalidated" / "fact").glob("*.md"))
    archived_frontmatter = _frontmatter(archived_file)
    assert archived_frontmatter["status"] == "deprecated"
    assert archived_frontmatter["x_hindsight"]["invalidation_reason"].startswith(
        "Superseded"
    )


def test_generation_is_deterministic_and_replaces_only_with_force(tmp_path):
    """Snapshot replay is byte-stable and replacement requires explicit force."""
    snapshot = _snapshot([_record("world-1"), _record("world-2")])
    first = tmp_path / "first"
    second = tmp_path / "second"
    adapter.build_bundle(snapshot, first)
    replayed = adapter.load_snapshot(
        first / "source" / "hindsight-memory-snapshot.json"
    )
    adapter.build_bundle(replayed, second)

    def tree(directory):
        return {
            path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*")
            if path.is_file()
        }

    assert tree(first) == tree(second)
    with pytest.raises(adapter.AdapterError, match="not empty"):
        adapter.build_bundle(snapshot, first)

    stale = first / "stale.txt"
    stale.write_text("must disappear", encoding="utf-8")
    adapter.build_bundle(snapshot, first, force=True)
    assert not stale.exists()
    assert tree(first) == tree(second)


def test_loader_accepts_raw_list_and_rejects_duplicate_ids(tmp_path):
    """Offline replay accepts raw API items and prevents ambiguous duplicates."""
    source = tmp_path / "source.json"
    source.write_text(json.dumps([_record("one")]), encoding="utf-8")
    snapshot = adapter.load_snapshot(source, bank_id_override="bank-from-cli")
    assert snapshot["source"]["bank_id"] == "bank-from-cli"
    assert snapshot["items"][0]["entities"] == ["Project Atlas", "Dana"]

    source.write_text(
        json.dumps([_record("same"), _record("same")]),
        encoding="utf-8",
    )
    with pytest.raises(adapter.AdapterError, match="duplicate valid memory"):
        adapter.load_snapshot(source, bank_id_override="bank-from-cli")


def test_live_capture_follows_pagination_and_authenticates():
    """The live path fetches valid and invalidated pages with bearer auth."""
    valid = [_record(f"valid-{index}") for index in range(105)]
    invalidated = [
        _record(
            "invalidated-1",
            state="invalidated",
            invalidation_reason="Corrected",
        )
    ]
    requests = []

    class Handler(BaseHTTPRequestHandler):
        """Serve deterministic Hindsight-shaped pagination."""

        def do_GET(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            state = query["state"][0]
            offset = int(query["offset"][0])
            limit = int(query["limit"][0])
            source = valid if state == "valid" else invalidated
            requests.append(
                (
                    parsed.path,
                    state,
                    offset,
                    self.headers.get("Authorization"),
                )
            )
            payload = {
                "items": source[offset : offset + limit],
                "total": len(source),
                "limit": limit,
                "offset": offset,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            """Silence the test HTTP server log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        snapshot = adapter.capture_snapshot(
            base_url=base_url,
            bank_id="bank with spaces/slash",
            api_token="secret-token",
            timeout=2,
        )
        anonymous_snapshot = adapter.capture_snapshot(
            base_url=base_url,
            bank_id="bank with spaces/slash",
            api_token=None,
            timeout=2,
            include_invalidated=False,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert len(snapshot["items"]) == 106
    assert len(anonymous_snapshot["items"]) == 105
    expected_path = "/v1/default/banks/bank%20with%20spaces%2Fslash/memories/list"
    assert requests == [
        (expected_path, "valid", 0, "Bearer secret-token"),
        (expected_path, "valid", 100, "Bearer secret-token"),
        (expected_path, "invalidated", 0, "Bearer secret-token"),
        (expected_path, "valid", 0, None),
        (expected_path, "valid", 100, None),
    ]


def test_reset_bank_suppresses_only_missing_bank_errors():
    """Reset tolerates a 404 but keeps every other delete failure visible."""

    class DeleteError(Exception):
        def __init__(self, status):
            self.status = status

    class Banks:
        def __init__(self, status):
            self.status = status
            self.created = False

        def delete(self, **kwargs):
            raise DeleteError(self.status)

        def create(self, **kwargs):
            self.created = True

    class Client:
        def __init__(self, status):
            self.banks = Banks(status)

        def retain(self, **kwargs):
            return {"success": True}

    missing_client = Client(404)
    responses = run_demo.populate_bank(missing_client, "demo-bank", reset=True)
    assert missing_client.banks.created is True
    assert len(responses) == len(retain_items())

    failed_client = Client(503)
    with pytest.raises(adapter.AdapterError, match="Could not reset"):
        run_demo.populate_bank(failed_client, "demo-bank", reset=True)
    assert failed_client.banks.created is False


def test_invalidation_requires_truthy_success(monkeypatch):
    """A 200-shaped failure cannot be counted as a curated source fact."""

    class Memories:
        def list(self, **kwargs):
            return {
                "items": [
                    {
                        "id": "old-window",
                        "text": ("Tentative production window is Friday, July 31."),
                    }
                ]
            }

    class Client:
        memories = Memories()

    monkeypatch.setattr(
        run_demo,
        "request_json",
        lambda *args, **kwargs: {"success": False},
    )
    with pytest.raises(adapter.AdapterError, match="invalidate failed"):
        run_demo.curate_superseded_facts(
            Client(),
            base_url="http://localhost:8888",
            bank_id="demo-bank",
        )


def test_cli_reports_bad_input_without_traceback(tmp_path, capsys):
    """Malformed user input produces a concise nonzero CLI result."""
    source = tmp_path / "bad.json"
    source.write_text("{not-json", encoding="utf-8")
    status = adapter.run(
        [
            "--source-json",
            str(source),
            "--bank-id",
            "demo",
            "--output",
            str(tmp_path / "bundle"),
        ]
    )
    captured = capsys.readouterr()
    assert status == 2
    assert captured.err.startswith("error:")
    assert "Traceback" not in captured.err


def test_scenario_is_source_conversation_and_scoring_is_deterministic():
    """The demo feeds conversations to Hindsight and uses scoped fact scoring."""
    items = retain_items()
    assert len(items) == 8
    assert all("content" in item and "document_id" in item for item in items)
    assert all(
        item["metadata"]["source"] == "scripted-live-agent-run" for item in items
    )
    assert (
        score_answer(
            "The canary is 10% for 30 minutes.",
            [["10 percent", "10%"], ["30 minutes"]],
        )
        == 1.0
    )
    assert (
        score_answer(
            "The canary is 10%.",
            [["10 percent", "10%"], ["30 minutes"]],
        )
        == 0.5
    )


def test_memanto_retriever_and_parity_use_raw_destination_results():
    """Destination evidence stays raw and parity exposes any score loss."""

    class FakeClient:
        def recall(self, **kwargs):
            assert kwargs["agent_id"] == "beacon-agent"
            assert kwargs["limit"] == 10
            assert kwargs["min_similarity"] == 0.0
            return {
                "memories": [
                    {
                        "id": "memory-1",
                        "title": "Approved release window",
                        "content": "Tuesday, August 4 at 14:00 UTC",
                        "type": "fact",
                        "score": 0.91,
                        "namespace": "must-not-leak",
                    }
                ]
            }

    answer, evidence = memanto_retriever(
        FakeClient(),
        "beacon-agent",
    )("When is the release?")
    assert "Tuesday, August 4 at 14:00 UTC" in answer
    assert evidence[0]["score"] == 0.91
    assert "namespace" not in evidence[0]

    source = {
        "retriever": "hindsight",
        "passed": 1,
        "average_score": 1.0,
        "cases": [{"id": "release-date", "score": 1.0}],
    }
    destination = {
        "retriever": "memanto",
        "passed": 0,
        "average_score": 0.5,
        "cases": [{"id": "release-date", "score": 0.5}],
    }
    parity = build_parity_report(source, destination)
    assert parity["mean_score_retention"] == 0.5
    assert parity["cases"][0]["delta"] == -0.5
    assert parity["retained_or_improved"] == 0


def test_committed_showcase_artifacts_are_self_consistent():
    """Committed evidence replays exactly and agrees on every source count."""
    result = verify(DEFAULT_ARTIFACTS)
    assert result["source_records"] == 35
    assert result["importable_records"] == 32
    assert result["archived_records"] == 3
    assert result["source_passed"] == 8
    assert result["byte_identical_replay"] is True


def test_roundtrip_copies_staged_export_into_evidence(tmp_path):
    """Cloud exports are staged inside Memanto's safe data dir before copying."""
    staged = tmp_path / "staged"
    artifact = tmp_path / "artifact"
    concept = staged / "memories" / "fact" / "release.md"
    concept.parent.mkdir(parents=True)
    concept.write_text("release window", encoding="utf-8")

    run_roundtrip.copy_staged_export(staged, artifact)

    assert (artifact / "memories" / "fact" / "release.md").read_text(
        encoding="utf-8"
    ) == "release window"
    with pytest.raises(adapter.AdapterError, match="missing or empty"):
        run_roundtrip.copy_staged_export(tmp_path / "missing", artifact)


def test_roundtrip_transcripts_remove_paths_and_terminal_padding():
    """Captured CLI evidence is portable and clean without changing its text."""
    raw = f"$ memanto --data {Path.home() / '.memanto'}   \nresult   \n"

    transcript = run_roundtrip.normalize_transcript(raw)

    assert str(Path.home()) not in transcript
    assert transcript.endswith("result\n")
    assert all(line == line.rstrip() for line in transcript.splitlines())
