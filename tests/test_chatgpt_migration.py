"""Tests for ChatGPT conversation export → Memanto migration adapter.

Covers: basic mapping, temporal preservation, source_ref tracking, edge cases
(empty conversations, Unicode, multimodal, large exports, branching trees).
"""

import pytest
from datetime import datetime, timezone

from memanto.cli.migrate.chatgpt_mapper import (
    map_chatgpt,
    load_chatgpt_export,
    _linearize_conversation,
    _extract_text,
    _parse_dt,
)


# -- Fixtures ----------------------------------------------------------------


def _make_message(msg_id, role, text, create_time=None, content_type="text"):
    """Helper to build a ChatGPT message node."""
    parts = [text] if isinstance(text, str) else text
    return {
        "id": msg_id,
        "author": {"role": role},
        "create_time": create_time,
        "content": {"content_type": content_type, "parts": parts},
        "metadata": {},
    }


def _make_conversation(title, conv_id, messages_data, create_time=1700000000.0):
    """Build a conversation dict from a list of (id, role, text, time) tuples."""
    mapping = {}
    prev_id = "root"
    mapping["root"] = {
        "id": "root",
        "message": None,
        "parent": None,
        "children": [messages_data[0][0]] if messages_data else [],
    }
    for i, (msg_id, role, text, time) in enumerate(messages_data):
        children = [messages_data[i + 1][0]] if i + 1 < len(messages_data) else []
        mapping[msg_id] = {
            "id": msg_id,
            "message": _make_message(msg_id, role, text, time),
            "parent": prev_id,
            "children": children,
        }
        prev_id = msg_id

    return {
        "title": title,
        "conversation_id": conv_id,
        "create_time": create_time,
        "update_time": create_time + 1000,
        "mapping": mapping,
    }


# -- Basic Mapping -----------------------------------------------------------


class TestBasicMapping:
    def test_single_exchange(self):
        """A user question + assistant answer becomes one memory."""
        conv = _make_conversation("Test", "conv-1", [
            ("m1", "user", "What is Python?", 1700000100.0),
            ("m2", "assistant", "A programming language.", 1700000105.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert len(rows) == 1
        assert "Q: What is Python?" in rows[0]["content"]
        assert "A: A programming language." in rows[0]["content"]
        assert rows[0]["source"] == "chatgpt"
        assert rows[0]["provenance"] == "imported"

    def test_multiple_exchanges(self):
        """Multiple turns produce multiple memories."""
        conv = _make_conversation("Multi", "conv-2", [
            ("m1", "user", "First question", 1700000100.0),
            ("m2", "assistant", "First answer", 1700000105.0),
            ("m3", "user", "Second question", 1700000200.0),
            ("m4", "assistant", "Second answer", 1700000205.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert len(rows) == 2
        assert "First question" in rows[0]["content"]
        assert "Second question" in rows[1]["content"]

    def test_multiple_conversations(self):
        """Each conversation is processed independently."""
        convs = [
            _make_conversation("Conv A", "a", [
                ("m1", "user", "Hello", 1700000100.0),
                ("m2", "assistant", "Hi!", 1700000105.0),
            ]),
            _make_conversation("Conv B", "b", [
                ("m1", "user", "Bye", 1700000200.0),
                ("m2", "assistant", "Goodbye!", 1700000205.0),
            ]),
        ]
        rows = map_chatgpt({"conversations": convs})
        assert len(rows) == 2
        assert rows[0]["tags"][0] == "session:Conv A"
        assert rows[1]["tags"][0] == "session:Conv B"

    def test_user_message_without_response(self):
        """A user message with no assistant follow-up still becomes a memory."""
        conv = _make_conversation("Solo", "conv-3", [
            ("m1", "user", "Thinking out loud...", 1700000100.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert len(rows) == 1
        assert "Thinking out loud..." in rows[0]["content"]


# -- Temporal Metadata Preservation ------------------------------------------


class TestTemporalPreservation:
    def test_created_at_from_message(self):
        """created_at comes from the message timestamp, not conversation."""
        conv = _make_conversation("Time", "conv-t", [
            ("m1", "user", "Hi", 1700000500.0),
            ("m2", "assistant", "Hello", 1700000505.0),
        ], create_time=1700000000.0)
        rows = map_chatgpt({"conversations": [conv]})
        assert rows[0]["created_at"] == datetime(2023, 11, 14, 22, 21, 40, tzinfo=timezone.utc)

    def test_fallback_to_conversation_time(self):
        """When message has no timestamp, falls back to conversation create_time."""
        conv = _make_conversation("NoTime", "conv-nt", [
            ("m1", "user", "Hi", None),
            ("m2", "assistant", "Hello", None),
        ], create_time=1700000000.0)
        rows = map_chatgpt({"conversations": [conv]})
        assert rows[0]["created_at"] == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    def test_updated_at_is_migration_time(self):
        """updated_at is always set to the migration timestamp."""
        conv = _make_conversation("Up", "conv-u", [
            ("m1", "user", "Q", 1700000100.0),
            ("m2", "assistant", "A", 1700000105.0),
        ])
        before = datetime.now(timezone.utc)
        rows = map_chatgpt({"conversations": [conv]})
        after = datetime.now(timezone.utc)
        assert before <= rows[0]["updated_at"] <= after

    def test_turn_index_in_supporting_data(self):
        """Supporting data includes turn number for ordering."""
        conv = _make_conversation("Turns", "conv-turns", [
            ("m1", "user", "First", 1700000100.0),
            ("m2", "assistant", "Reply 1", 1700000105.0),
            ("m3", "user", "Second", 1700000200.0),
            ("m4", "assistant", "Reply 2", 1700000205.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert "Turn: 1" in rows[0]["content"]
        assert "Turn: 2" in rows[1]["content"]


# -- Source Ref Tracking -----------------------------------------------------


class TestSourceRef:
    def test_source_ref_format(self):
        """source_ref is conversation_id:message_id."""
        conv = _make_conversation("Ref", "conv-abc", [
            ("m1", "user", "Test", 1700000100.0),
            ("m2", "assistant", "OK", 1700000105.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert rows[0]["source_ref"] == "conv-abc:m1"

    def test_source_is_chatgpt(self):
        """source field is always 'chatgpt'."""
        conv = _make_conversation("Src", "conv-s", [
            ("m1", "user", "Hi", 1700000100.0),
            ("m2", "assistant", "Hey", 1700000105.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert rows[0]["source"] == "chatgpt"

    def test_conversation_id_in_supporting_data(self):
        """Full conversation_id preserved in supporting data."""
        conv = _make_conversation("ID", "uuid-1234-5678", [
            ("m1", "user", "Hi", 1700000100.0),
            ("m2", "assistant", "Hey", 1700000105.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert "uuid-1234-5678" in rows[0]["content"]


# -- Edge Cases --------------------------------------------------------------


class TestEdgeCases:
    def test_empty_conversations_list(self):
        """Empty export produces no memories."""
        rows = map_chatgpt({"conversations": []})
        assert rows == []

    def test_empty_mapping(self):
        """Conversation with empty mapping is skipped."""
        conv = {
            "title": "Empty",
            "conversation_id": "conv-e",
            "create_time": 1700000000.0,
            "mapping": {},
        }
        rows = map_chatgpt({"conversations": [conv]})
        assert rows == []

    def test_system_messages_skipped(self):
        """System messages are not turned into memories."""
        conv = _make_conversation("Sys", "conv-sys", [
            ("m0", "system", "You are a helpful assistant.", 1700000000.0),
            ("m1", "user", "Hi", 1700000100.0),
            ("m2", "assistant", "Hello!", 1700000105.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert len(rows) == 1
        assert "helpful assistant" not in rows[0]["content"]

    def test_tool_messages_skipped(self):
        """Tool-call messages are not turned into memories."""
        conv = _make_conversation("Tool", "conv-tool", [
            ("m1", "user", "Search for X", 1700000100.0),
            ("m2", "tool", "Results: ...", 1700000102.0),
            ("m3", "assistant", "I found X.", 1700000105.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        # tool message skipped; user gets paired with next non-tool (assistant)
        # user "Search for X" has no immediate assistant response (tool is between)
        # so it becomes standalone, then assistant is standalone
        assert all(r["source"] == "chatgpt" for r in rows)
        assert not any("Results: ..." in r["content"] for r in rows)

    def test_unicode_content(self):
        """Unicode characters are preserved."""
        conv = _make_conversation("Unicode", "conv-uni", [
            ("m1", "user", "什么是量子计算？🔬", 1700000100.0),
            ("m2", "assistant", "量子计算是利用量子力学原理的计算方式。✨", 1700000105.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert "什么是量子计算？🔬" in rows[0]["content"]
        assert "量子计算是利用量子力学原理" in rows[0]["content"]

    def test_empty_content_skipped(self):
        """Messages with empty content are skipped."""
        conv = _make_conversation("Empty", "conv-emp", [
            ("m1", "user", "", 1700000100.0),
            ("m2", "user", "Real question", 1700000200.0),
            ("m3", "assistant", "Real answer", 1700000205.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert len(rows) == 1
        assert "Real question" in rows[0]["content"]

    def test_very_long_content_truncated(self):
        """Content exceeding 10000 chars is truncated cleanly."""
        long_text = "x" * 12000
        conv = _make_conversation("Long", "conv-long", [
            ("m1", "user", long_text, 1700000100.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert len(rows[0]["content"]) <= 10000

    def test_untitled_conversation(self):
        """Conversations without titles default to 'Untitled'."""
        conv = _make_conversation(None, "conv-notitle", [
            ("m1", "user", "Hi", 1700000100.0),
            ("m2", "assistant", "Hey", 1700000105.0),
        ])
        conv["title"] = None
        rows = map_chatgpt({"conversations": [conv]})
        assert "session:Untitled" in rows[0]["tags"]


# -- Type Classification ----------------------------------------------------


class TestTypeClassification:
    def test_preference_detection(self):
        """Messages with preference signals get type='preference'."""
        conv = _make_conversation("Pref", "conv-p", [
            ("m1", "user", "I prefer dark mode always", 1700000100.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert rows[0]["type"] == "preference"

    def test_decision_detection(self):
        """Messages with decision signals get type='decision'."""
        conv = _make_conversation("Dec", "conv-d", [
            ("m1", "user", "I decided to use PostgreSQL for this project", 1700000100.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert rows[0]["type"] == "decision"

    def test_no_type_when_ambiguous(self):
        """Generic messages get type=None for auto-classification."""
        conv = _make_conversation("Gen", "conv-g", [
            ("m1", "user", "How do I sort a list?", 1700000100.0),
            ("m2", "assistant", "Use sorted() or .sort()", 1700000105.0),
        ])
        rows = map_chatgpt({"conversations": [conv]})
        assert rows[0]["type"] is None


# -- Loader ------------------------------------------------------------------


class TestLoader:
    def test_load_from_file(self, tmp_path):
        """Load directly from conversations.json."""
        data = [{"title": "T", "conversation_id": "c1", "create_time": 1700000000.0,
                 "mapping": {"r": {"id": "r", "message": None, "parent": None, "children": ["m1"]},
                             "m1": {"id": "m1", "message": _make_message("m1", "user", "Hi", 1700000100.0),
                                    "parent": "r", "children": []}}}]
        f = tmp_path / "conversations.json"
        import json
        f.write_text(json.dumps(data))
        export = load_chatgpt_export(f)
        assert len(export["conversations"]) == 1

    def test_load_from_directory(self, tmp_path):
        """Load from a directory containing conversations.json."""
        data = [{"title": "T", "conversation_id": "c1", "create_time": 1700000000.0, "mapping": {}}]
        (tmp_path / "conversations.json").write_text(__import__("json").dumps(data))
        export = load_chatgpt_export(tmp_path)
        assert len(export["conversations"]) == 1

    def test_missing_file_raises(self, tmp_path):
        """FileNotFoundError when no conversations.json exists."""
        with pytest.raises(FileNotFoundError):
            load_chatgpt_export(tmp_path / "nonexistent")

    def test_invalid_format_raises(self, tmp_path):
        """ValueError when JSON is not an array."""
        f = tmp_path / "conversations.json"
        f.write_text('{"not": "an array"}')
        with pytest.raises(ValueError, match="Expected a JSON array"):
            load_chatgpt_export(f)


# -- Branching / multimodal / robustness (CodeRabbit follow-ups) ------------


class TestBranchingAndRobustness:
    def test_first_child_path_on_branching_tree(self):
        """Edits create sibling branches — mapper follows the first-child path."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": {
                "id": "m1",
                "message": _make_message("m1", "user", "Original Q", 1700000100.0),
                "parent": "root",
                "children": ["m2a", "m2b"],  # branch: edit created sibling
            },
            "m2a": {
                "id": "m2a",
                "message": _make_message("m2a", "assistant", "First-child answer", 1700000105.0),
                "parent": "m1",
                "children": [],
            },
            "m2b": {
                "id": "m2b",
                "message": _make_message("m2b", "assistant", "Sibling branch answer", 1700000110.0),
                "parent": "m1",
                "children": [],
            },
        }
        conv = {
            "title": "Branched",
            "conversation_id": "conv-branch",
            "create_time": 1700000000.0,
            "mapping": mapping,
        }
        rows = map_chatgpt({"conversations": [conv]})
        assert len(rows) == 1
        assert "First-child answer" in rows[0]["content"]
        assert "Sibling branch answer" not in rows[0]["content"]

    def test_cyclic_parent_chain_does_not_hang(self):
        """Malformed cyclic parents must not infinite-loop in root finding."""
        mapping = {
            "a": {
                "id": "a",
                "message": _make_message("a", "user", "Ping", 1700000100.0),
                "parent": "b",
                "children": ["b"],
            },
            "b": {
                "id": "b",
                "message": _make_message("b", "assistant", "Pong", 1700000105.0),
                "parent": "a",
                "children": [],
            },
        }
        conv = {
            "title": "Cycle",
            "conversation_id": "conv-cycle",
            "create_time": 1700000000.0,
            "mapping": mapping,
        }
        rows = map_chatgpt({"conversations": [conv]})
        assert isinstance(rows, list)
        assert len(rows) >= 1

    def test_multimodal_parts_extracted(self):
        """Multimodal content parts contribute text / image markers."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": {
                "id": "m1",
                "message": {
                    "id": "m1",
                    "author": {"role": "user"},
                    "create_time": 1700000100.0,
                    "content": {
                        "content_type": "multimodal_text",
                        "parts": [
                            "Describe this diagram",
                            {"content_type": "image_asset_pointer", "asset_pointer": "file://x"},
                        ],
                    },
                },
                "parent": "root",
                "children": ["m2"],
            },
            "m2": {
                "id": "m2",
                "message": _make_message("m2", "assistant", "It shows a pipeline.", 1700000105.0),
                "parent": "m1",
                "children": [],
            },
        }
        conv = {
            "title": "Multimodal",
            "conversation_id": "conv-mm",
            "create_time": 1700000000.0,
            "mapping": mapping,
        }
        rows = map_chatgpt({"conversations": [conv]})
        assert len(rows) == 1
        assert "Describe this diagram" in rows[0]["content"]
        assert "[image]" in rows[0]["content"]

    def test_malformed_content_does_not_abort_run(self):
        """A string/list content shape on one message must not kill the migration."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["bad"]},
            "bad": {
                "id": "bad",
                "message": {
                    "id": "bad",
                    "author": {"role": "user"},
                    "create_time": 1700000100.0,
                    "content": "plain string content, not a dict",
                },
                "parent": "root",
                "children": ["good_u"],
            },
            "good_u": {
                "id": "good_u",
                "message": _make_message("good_u", "user", "Recovered question", 1700000200.0),
                "parent": "bad",
                "children": ["good_a"],
            },
            "good_a": {
                "id": "good_a",
                "message": _make_message("good_a", "assistant", "Recovered answer", 1700000205.0),
                "parent": "good_u",
                "children": [],
            },
        }
        conv = {
            "title": "Malformed",
            "conversation_id": "conv-mal",
            "create_time": 1700000000.0,
            "mapping": mapping,
        }
        rows = map_chatgpt({"conversations": [conv]})
        assert any("Recovered question" in r["content"] for r in rows)

    def test_large_export_many_conversations(self):
        """Many conversations map without dropping later ones."""
        convs = []
        for i in range(25):
            convs.append(
                _make_conversation(
                    f"Conv {i}",
                    f"c-{i}",
                    [
                        ("m1", "user", f"Question {i}", 1700000100.0 + i),
                        ("m2", "assistant", f"Answer {i}", 1700000105.0 + i),
                    ],
                )
            )
        rows = map_chatgpt({"conversations": convs})
        assert len(rows) == 25
        assert "Question 0" in rows[0]["content"]
        assert "Question 24" in rows[-1]["content"]
