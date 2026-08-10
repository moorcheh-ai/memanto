from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

EXAMPLE_DIR = Path(__file__).parents[1] / "examples" / "migrations" / "codex-to-okf"


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, EXAMPLE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load_module("codex_to_okf", "codex_to_okf.py")
validator = _load_module("validate_roundtrip", "validate_roundtrip.py")
portability = _load_module("validate_portability", "validate_portability.py")


def _workdir(name: str) -> Path:
    path = EXAMPLE_DIR / "sample_output" / "test-work" / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _record(record_type: str, payload: dict, index: int) -> dict:
    return {
        "timestamp": f"2026-08-10T12:00:{index:02d}Z",
        "type": record_type,
        "payload": payload,
    }


def test_adapter_exports_only_visible_messages_and_redacts():
    tmp_path = _workdir("privacy")
    source = tmp_path / "rollout.jsonl"
    records = [
        _record("session_meta", {"session_id": "session-1"}, 0),
        _record(
            "response_item",
            {
                "type": "message",
                "id": "dev-1",
                "role": "developer",
                "content": [{"type": "input_text", "text": "private policy"}],
            },
            1,
        ),
        _record(
            "response_item",
            {
                "type": "message",
                "id": "user-1",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "My goal is to migrate memory. Do not expose "
                            "sk-1234567890abcdefghijkl or C:\\Users\\alice\\private.txt."
                        ),
                    }
                ],
            },
            2,
        ),
        _record(
            "response_item",
            {
                "type": "reasoning",
                "encrypted_content": "ciphertext",
            },
            3,
        ),
        _record(
            "response_item",
            {
                "type": "custom_tool_call",
                "name": "shell_command",
                "input": {"secret": "never export me"},
            },
            4,
        ),
        _record(
            "response_item",
            {
                "type": "message",
                "id": "assistant-1",
                "role": "assistant",
                "phase": "commentary",
                "content": [
                    {
                        "type": "output_text",
                        "text": "I confirmed the portable route works.",
                    }
                ],
            },
            5,
        ),
    ]
    source.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )

    session_meta, messages, audit = adapter.read_rollout(source)
    memories = adapter.build_memories(messages)
    output = tmp_path / "okf"
    report = adapter.write_bundle(
        source=source,
        output=output,
        session_meta=session_meta,
        messages=messages,
        memories=memories,
        audit=audit,
        title="Test bundle",
    )

    rendered = "\n".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*.md")
    )
    assert "private policy" not in rendered
    assert "never export me" not in rendered
    assert "sk-1234567890abcdefghijkl" not in rendered
    assert "C:\\Users\\alice" not in rendered
    assert "<REDACTED>" in rendered
    assert "<REDACTED_PATH>" in rendered
    assert report["summary"]["messages_included"] == 2
    assert audit["skip_counts"]["role:developer"] == 1

    imported = map_okf(load_okf_bundle(output))
    assert len(imported) == len(memories)
    assert all(row["source"] == "codex" for row in imported)
    assert {row["type"] for row in imported} >= {"goal", "instruction"}


def test_golden_retrieval_validation():
    tmp_path = _workdir("golden")
    bundle = tmp_path / "bundle"
    memory_dir = bundle / "memories" / "goal"
    memory_dir.mkdir(parents=True)
    (memory_dir / "goal.md").write_text(
        """---
type: goal
title: Earn two hundred dollars
resource: urn:codex:test:goal
timestamp: '2026-08-10T12:00:00Z'
x_memanto:
  source: codex
---

The objective is to earn $200.
""",
        encoding="utf-8",
    )
    golden = tmp_path / "golden.json"
    golden.write_text(
        json.dumps(
            [
                {
                    "question": "What is the objective to earn?",
                    "expected_type": "goal",
                    "expected_terms": ["objective", "$200"],
                }
            ]
        ),
        encoding="utf-8",
    )
    result = validator.validate(bundle, golden)
    assert result["structural_errors"] == []
    assert result["recall_parity_percent"] == 100.0


def test_official_memanto_mapper_exporter_roundtrip():
    tmp_path = _workdir("official-roundtrip")
    source_bundle = EXAMPLE_DIR / "sample_output" / "okf-bundle"
    output_bundle = tmp_path / "reexported-okf"

    report = portability.validate_portability(source_bundle, output_bundle)

    assert report["source_memories"] == 17
    assert report["mapped_memories"] == 17
    assert report["reexported_memories"] == 17
    assert report["parity_percent"] == 100.0
    assert all(case["passed"] for case in report["cases"])
