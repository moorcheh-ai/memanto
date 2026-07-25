import json
from pathlib import Path

import pytest

from examples.migrations.open_webui.adapter import (
    ExportError,
    convert_export,
    current_branch,
)
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


def _export(history, **extra):
    return [
        {
            "id": "chat-1",
            "created_at": 1_700_000_000,
            "meta": {"tags": ["project"]},
            "chat": {"title": "Release plan", "history": history},
            **extra,
        }
    ]


def test_selected_branch_excludes_abandoned_response(tmp_path):
    history = {
        "currentId": "current",
        "messages": {
            "root": {
                "role": "user",
                "content": "Release on Friday",
                "parentId": None,
                "childrenIds": ["abandoned", "current"],
                "timestamp": 1,
            },
            "abandoned": {
                "role": "assistant",
                "content": "Release on Thursday",
                "parentId": "root",
                "childrenIds": [],
                "timestamp": 2,
            },
            "current": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Release on Friday confirmed"}],
                "parentId": "root",
                "childrenIds": [],
                "timestamp": 3,
                "model": "qwen3",
            },
        },
    }
    output = tmp_path / "bundle"
    manifest = convert_export(_export(history), output)

    assert manifest["conversations"] == 1
    assert manifest["messages"] == 2
    rows = map_okf(load_okf_bundle(output))
    assert len(rows) == 1
    assert rows[0]["type"] == "artifact"
    assert rows[0]["source"] == "open-webui"
    assert "Release on Friday confirmed" in rows[0]["content"]
    assert "Release on Thursday" not in rows[0]["content"]
    assert set(rows[0]["tags"]) == {"open-webui", "conversation", "project"}


def test_missing_current_id_chooses_newest_leaf():
    history = {
        "messages": {
            "root": {
                "role": "user",
                "content": "x",
                "parentId": None,
                "childrenIds": ["a", "b"],
            },
            "a": {
                "role": "assistant",
                "content": "old",
                "parentId": "root",
                "childrenIds": [],
                "timestamp": 10,
            },
            "b": {
                "role": "assistant",
                "content": "new",
                "parentId": "root",
                "childrenIds": [],
                "timestamp": 20,
            },
        }
    }
    assert [message["id"] for message in current_branch(history)] == ["root", "b"]


def test_cycle_and_missing_parent_fail_closed():
    with pytest.raises(ExportError, match="cycle"):
        current_branch({"currentId": "a", "messages": {"a": {"parentId": "a"}}})
    with pytest.raises(ExportError, match="missing parent"):
        current_branch({"currentId": "a", "messages": {"a": {"parentId": "gone"}}})


def test_legacy_envelope_and_empty_chat_count(tmp_path):
    data = {
        "chats": [
            {
                "title": "Legacy",
                "history": {
                    "currentId": "u",
                    "messages": {
                        "u": {"role": "user", "content": "", "parentId": None}
                    },
                },
            }
        ]
    }
    manifest = convert_export(data, tmp_path / "bundle")
    assert manifest["conversations"] == 0
    assert manifest["skipped_empty"] == 1
    assert (
        json.loads((tmp_path / "bundle" / "migration-manifest.json").read_text())[
            "messages"
        ]
        == 0
    )


def test_repeated_conversion_replaces_stale_files(tmp_path):
    history = {
        "currentId": "u",
        "messages": {"u": {"role": "user", "content": "kept", "parentId": None}},
    }
    output = tmp_path / "bundle"
    convert_export(_export(history), output)
    stale = output / "memories" / "artifact" / "stale.md"
    stale.write_text("stale", encoding="utf-8")
    convert_export(_export(history), output)
    assert not stale.exists()
    assert len(load_okf_bundle(output)["memories"]) == 1


def test_committed_sample_bundle_matches_adapter(tmp_path):
    root = Path(__file__).parents[1] / "examples" / "migrations" / "open_webui"
    data = json.loads((root / "sample-export.json").read_text(encoding="utf-8"))
    generated = tmp_path / "sample-okf"
    convert_export(data, generated, "sample-export.json")

    def files(directory):
        return {
            path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*")
            if path.is_file()
        }

    assert files(generated) == files(root / "sample-okf")
