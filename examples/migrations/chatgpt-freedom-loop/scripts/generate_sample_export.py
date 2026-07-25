#!/usr/bin/env python3
"""Generate a ChatGPT-shaped conversations.json sample (tree mapping + branches)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "conversations.json"


def node(nid, parent, children, message=None):
    return {"id": nid, "parent": parent, "children": children, "message": message}


def msg(mid, role, parts, t, content_type="text"):
    return {
        "id": mid,
        "author": {"role": role},
        "create_time": t,
        "content": {"content_type": content_type, "parts": parts},
        "metadata": {},
    }


def main() -> None:
    # Lived-in style threads: preferences, decisions, multimodal, branching edit
    conv_prefs = {
        "title": "Coding Preferences Over Time",
        "conversation_id": "chatgpt-export-prefs-001",
        "create_time": 1710000000.0,
        "update_time": 1710003600.0,
        "mapping": {
            "root": node("root", None, ["u1"]),
            "u1": node(
                "u1",
                "root",
                ["a1"],
                msg("u1", "user", ["I prefer dark mode and vim keybindings in every editor."], 1710000100.0),
            ),
            "a1": node(
                "a1",
                "u1",
                ["u2"],
                msg(
                    "a1",
                    "assistant",
                    ["Got it — I'll remember dark mode + vim bindings as your defaults."],
                    1710000105.0,
                ),
            ),
            "u2": node(
                "u2",
                "a1",
                ["a2"],
                msg(
                    "u2",
                    "user",
                    ["Also never suggest tabs — always spaces, width 4."],
                    1710000200.0,
                ),
            ),
            "a2": node(
                "a2",
                "u2",
                [],
                msg("a2", "assistant", ["Locked in: 4-space indentation, no tabs."], 1710000205.0),
            ),
        },
    }

    conv_decision = {
        "title": "Database Choice for Memanto Side Project",
        "conversation_id": "chatgpt-export-decision-002",
        "create_time": 1711000000.0,
        "update_time": 1711001800.0,
        "mapping": {
            "root": node("root", None, ["u1"]),
            "u1": node(
                "u1",
                "root",
                ["a1"],
                msg(
                    "u1",
                    "user",
                    ["I decided to use PostgreSQL + pgvector for the retrieval layer."],
                    1711000100.0,
                ),
            ),
            "a1": node(
                "a1",
                "u1",
                [],
                msg(
                    "a1",
                    "assistant",
                    ["Solid decision — Postgres + pgvector keeps ops simple for agent memory."],
                    1711000105.0,
                ),
            ),
        },
    }

    # Branching: user edited a prompt; current_node marks the kept answer
    conv_branch = {
        "title": "Branching Edit Example",
        "conversation_id": "chatgpt-export-branch-003",
        "create_time": 1712000000.0,
        "update_time": 1712000900.0,
        "current_node": "a_keep",
        "mapping": {
            "root": node("root", None, ["u1"]),
            "u1": node(
                "u1",
                "root",
                ["a_keep", "a_sibling"],
                msg("u1", "user", ["Explain OKF in one sentence."], 1712000100.0),
            ),
            "a_keep": node(
                "a_keep",
                "u1",
                [],
                msg(
                    "a_keep",
                    "assistant",
                    ["OKF is a vendor-neutral markdown bundle for portable agent knowledge."],
                    1712000105.0,
                ),
            ),
            "a_sibling": node(
                "a_sibling",
                "u1",
                [],
                msg(
                    "a_sibling",
                    "assistant",
                    ["(discarded sibling from an edit) OKF is just YAML files."],
                    1712000110.0,
                ),
            ),
        },
    }

    conv_mm = {
        "title": "Multimodal Diagram Review",
        "conversation_id": "chatgpt-export-mm-004",
        "create_time": 1713000000.0,
        "update_time": 1713000600.0,
        "mapping": {
            "root": node("root", None, ["u1"]),
            "u1": node(
                "u1",
                "root",
                ["a1"],
                msg(
                    "u1",
                    "user",
                    [
                        "I realized our migration pipeline needs a freedom-loop diagram.",
                        {"content_type": "image_asset_pointer", "asset_pointer": "file-service://diagram"},
                    ],
                    1713000100.0,
                    content_type="multimodal_text",
                ),
            ),
            "a1": node(
                "a1",
                "u1",
                [],
                msg(
                    "a1",
                    "assistant",
                    ["Diagram shows ChatGPT → Memanto migrate → OKF export → round-trip."],
                    1713000105.0,
                ),
            ),
        },
    }

    conversations = [conv_prefs, conv_decision, conv_branch, conv_mm]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(conversations, indent=2), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT).as_posix()} ({len(conversations)} conversations)")


if __name__ == "__main__":
    main()
