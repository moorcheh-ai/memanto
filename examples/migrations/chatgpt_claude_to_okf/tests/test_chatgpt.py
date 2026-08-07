"""Tests for the ChatGPT export loader (active-path traversal)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.chatgpt import load_chatgpt  # noqa: E402


def _write_export(tmp_path, conversations):
    export = tmp_path / "chatgpt"
    (export / "chatgpt").mkdir(parents=True, exist_ok=True)
    (export / "chatgpt" / "conversations.json").write_text(
        json.dumps(conversations), encoding="utf-8")
    return export


def _node(node_id, role, text, ts, parent):
    return {
        "id": node_id,
        "message": {
            "id": node_id,
            "author": {"role": role, "name": None, "metadata": {}},
            "create_time": ts,
            "content": {"content_type": "text", "parts": [text]},
        },
        "parent": parent,
        "children": [],
    }


def test_active_path_excludes_abandoned_branch(tmp_path):
    """Only the current_node -> parent chain is extracted; abandoned branches
    from regenerated replies must not leak into the conversation."""
    root = _node("r", "user", "I prefer Postgres over MySQL.", 1.0, None)
    # branch A: abandoned attempt (has its own user statement)
    abandoned = _node("ab", "user", "I made a mistake with the abandoned config.", 2.0, "r")
    # branch B: the active reply chain
    active = _node("ac", "assistant", "Noted.", 3.0, "r")
    leaf = _node("l", "user", "We decided to migrate to Postgres 16.", 4.0, "ac")
    conv = {
        "id": "c1", "title": "Migration", "create_time": 1.0,
        "current_node": "l",
        "mapping": {"r": root, "ab": abandoned, "ac": active, "l": leaf},
    }
    export = _write_export(tmp_path, [conv])
    result = load_chatgpt(export)[0]
    texts = [t["text"] for t in result["turns"]]
    assert texts == ["I prefer Postgres over MySQL.", "Noted.", "We decided to migrate to Postgres 16."]
    assert not any("abandoned config" in t for t in texts), "abandoned branch leaked into turns"


def test_no_current_node_falls_back_to_all_nodes(tmp_path):
    """Exports without a usable current_node still parse (all nodes)."""
    root = _node("r", "user", "I prefer Postgres.", 1.0, None)
    n2 = _node("n2", "user", "I prefer offline docs.", 2.0, "r")
    conv = {
        "id": "c2", "title": "No current", "create_time": 1.0,
        "mapping": {"r": root, "n2": n2},
    }
    export = _write_export(tmp_path, [conv])
    result = load_chatgpt(export)[0]
    texts = [t["text"] for t in result["turns"]]
    assert texts == ["I prefer Postgres.", "I prefer offline docs."]
