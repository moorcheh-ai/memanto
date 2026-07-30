"""Coverage for the n8n execution-history -> OKF migration example."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from examples.migrations.n8n_executions.adapter import (
    MappingError,
    convert_n8n_executions,
    load_executions,
    validate_round_trip,
)
from examples.migrations.n8n_executions.recall_validation import (
    validate_recall_parity,
)
from memanto.app.core import MemoryRecord
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

NODE = "Normalize, Score & Route"
WORKFLOW = "LeadOps — Intake, Scoring & Follow-up"


def _lead(
    company: str = "Acme",
    *,
    score: int = 82,
    route: str = "hot",
    email: str = "private@example.test",
) -> dict:
    return {
        "idempotencyKey": f"key-{company.lower()}",
        "processedAt": "2026-07-30T12:00:01.000Z",
        "followUpAt": "2026-07-30T12:15:01.000Z",
        "lead": {
            "company": company,
            "email": email,
            "useCase": "Automate inbound qualification",
        },
        "qualification": {
            "score": score,
            "route": route,
            "reasons": ["Budget above threshold", "Urgent timeline"],
            "nextAction": "Send priority response",
        },
    }


def _execution(
    execution_id: str = "101",
    *,
    items: list[dict] | None = None,
    node: str = NODE,
) -> dict:
    return {
        "id": execution_id,
        "workflowId": "leadops-demo",
        "status": "success",
        "startedAt": "2026-07-30T12:00:00.000Z",
        "stoppedAt": "2026-07-30T12:00:02.000Z",
        "workflowData": {"id": "leadops-demo", "name": WORKFLOW},
        "data": {
            "resultData": {
                "runData": {
                    node: [
                        {
                            "data": {
                                "main": [
                                    [{"json": item} for item in (items or [_lead()])]
                                ]
                            }
                        }
                    ]
                }
            }
        },
    }


def _mapping(path: Path) -> Path:
    value = {
        "version": 1,
        "source": {
            "workflow_name": WORKFLOW,
            "execution_base_url": "http://localhost:5679",
        },
        "mappings": [
            {
                "node": NODE,
                "memory_type": "decision",
                "title": (
                    "Lead {lead.company}: {qualification.route} ({qualification.score})"
                ),
                "confidence": 1.0,
                "tags": ["n8n", "route:{qualification.route}"],
                "fields": [
                    {"label": "Company", "path": "lead.company"},
                    {"label": "Route", "path": "qualification.route"},
                    {"label": "Score", "path": "qualification.score"},
                    {"label": "Reasons", "path": "qualification.reasons"},
                ],
            }
        ],
    }
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_converts_public_api_envelope_and_preserves_provenance(tmp_path):
    source = _write_json(
        tmp_path / "executions.json",
        {"data": [_execution(items=[_lead("Acme"), _lead("Globex", score=61)])]},
    )
    output = tmp_path / "okf"

    result = convert_n8n_executions(source, _mapping(tmp_path / "map.yaml"), output)

    assert result["memory_count"] == 2
    assert result["memory_counts_by_type"] == {"decision": 2}
    assert result["round_trip"]["valid"] is True

    entries = load_okf_bundle(output)["memories"]
    assert {entry["title"] for entry in entries} == {
        "Lead Acme: hot (82)",
        "Lead Globex: hot (61)",
    }
    acme = next(entry for entry in entries if "Acme" in entry["title"])
    assert acme["x_memanto"]["source"] == "tool"
    assert acme["x_memanto"]["provenance"] == "n8n_execution"
    assert acme["resource"].endswith("/workflow/leadops-demo/executions/101")


def test_allow_list_does_not_copy_unselected_email(tmp_path):
    secret = "do-not-store@example.test"
    source = _write_json(
        tmp_path / "execution.json",
        _execution(items=[_lead(email=secret)]),
    )
    output = tmp_path / "okf"

    convert_n8n_executions(source, _mapping(tmp_path / "map.yaml"), output)

    all_text = "\n".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file()
    )
    assert secret not in all_text


def test_directory_input_is_sorted_and_hashed(tmp_path):
    source_dir = tmp_path / "input"
    source_dir.mkdir()
    _write_json(source_dir / "b.json", [_execution("2")])
    _write_json(source_dir / "a.json", {"data": [_execution("1")]})

    executions, hashes = load_executions(source_dir)

    assert [execution["id"] for execution in executions] == ["1", "2"]
    assert [row["file"] for row in hashes] == ["a.json", "b.json"]
    assert all(len(row["sha256"]) == 64 for row in hashes)


def test_output_is_byte_deterministic(tmp_path):
    source = _write_json(tmp_path / "execution.json", [_execution()])
    mapping = _mapping(tmp_path / "map.yaml")
    first = tmp_path / "first"
    second = tmp_path / "second"

    convert_n8n_executions(source, mapping, first)
    convert_n8n_executions(source, mapping, second)

    first_files = {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    assert (
        b"Visualizations generated from source snapshot "
        b"2026-07-30T12:00:02.000Z" in first_files[Path("metrics/overview.md")]
    )


def test_atomically_replaces_stale_output(tmp_path):
    source = _write_json(tmp_path / "execution.json", [_execution()])
    output = tmp_path / "okf"
    output.mkdir()
    stale = output / "stale.txt"
    stale.write_text("old", encoding="utf-8")

    convert_n8n_executions(source, _mapping(tmp_path / "map.yaml"), output)

    assert not stale.exists()
    assert (output / "migration-manifest.json").exists()


def test_round_trip_maps_back_to_memanto_without_loss(tmp_path):
    source = _write_json(tmp_path / "execution.json", [_execution()])
    output = tmp_path / "okf"
    convert_n8n_executions(source, _mapping(tmp_path / "map.yaml"), output)

    report = validate_round_trip(output)
    rows = map_okf(load_okf_bundle(output))

    assert report == {
        "valid": True,
        "source_count": 1,
        "okf_count": 1,
        "memanto_count": 1,
        "stable_ids_preserved": True,
        "issues": [],
    }
    assert rows[0]["type"] == "decision"
    assert rows[0]["confidence"] == pytest.approx(1.0)
    assert rows[0]["source"] == "tool"
    assert "Budget above threshold" in rows[0]["content"]
    MemoryRecord(agent_id="n8n-operations", actor_id="migration", **rows[0])


def test_missing_required_field_fails_with_source_coordinate(tmp_path):
    broken = _lead()
    del broken["qualification"]["score"]
    source = _write_json(tmp_path / "execution.json", [_execution(items=[broken])])

    with pytest.raises(MappingError, match="execution 101"):
        convert_n8n_executions(
            source,
            _mapping(tmp_path / "map.yaml"),
            tmp_path / "okf",
        )


def test_workflow_and_missing_node_are_reported_as_no_memories(tmp_path):
    source = _write_json(
        tmp_path / "execution.json",
        [_execution(node="Some other node")],
    )

    with pytest.raises(MappingError, match="No memories"):
        convert_n8n_executions(
            source,
            _mapping(tmp_path / "map.yaml"),
            tmp_path / "okf",
        )


def test_golden_questions_score_source_and_round_trip_parity(tmp_path):
    source = _write_json(tmp_path / "execution.json", [_execution()])
    mapping = _mapping(tmp_path / "map.yaml")
    output = tmp_path / "okf"
    questions = tmp_path / "questions.yaml"
    questions.write_text(
        yaml.safe_dump(
            {
                "questions": [
                    {
                        "id": "acme-route",
                        "question": "Where was the Acme lead routed?",
                        "memory_title": "Lead Acme: hot (82)",
                        "must_contain": ["**Route**: hot", "**Score**: 82"],
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    convert_n8n_executions(source, mapping, output)

    report = validate_recall_parity(source, mapping, output, questions)

    assert report["valid"] is True
    assert report["recall_parity_score"] == 1.0
    assert report["passed"] == report["questions"] == 1
