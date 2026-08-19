"""Tests for the Claude.ai / ChatGPT conversation-memory mappers.

These verify: (1) both export shapes are accepted, (2) user signal turns are
distilled into typed memory rows, (3) non-signal assistant chatter is dropped
so the migration doesn't echo noise, (4) rows carry the correct source /
source_ref / provenance so they round-trip through OKF, and (5) the MAPPERS
registry exposes both providers end-to-end.
"""



from memanto.cli.migrate.mappers import (
    MAPPERS,
    map_chatgpt,
    map_claude,
)
from memanto.cli.migrate.runner import source_count

CLAUDE_EXPORT = {
    "conversations": [
        {
            "name": "setup",
            "chat_messages": [
                {
                    "sender": "human",
                    "text": "I prefer dark themes and use a Dell XPS for work.",
                    "created_at": "2026-08-01T10:00:00Z",
                    "uuid": "m1",
                },
                {
                    "sender": "assistant",
                    "text": "Got it. Remember to always pin npm dependency versions.",
                    "created_at": "2026-08-01T10:01:00Z",
                    "uuid": "m2",
                },
                {
                    "sender": "human",
                    "text": "My goal is to ship the CLI by Friday.",
                    "created_at": "2026-08-01T10:02:00Z",
                    "uuid": "m3",
                },
            ],
        }
    ]
}

CHATGPT_EXPORT = {
    "conversations": [
        {
            "title": "fastapi backend",
            "mapping": {
                "a": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {
                            "content_type": "text",
                            "parts": ["I decided to use FastAPI for the backend."],
                        },
                        "create_time": 1722500000,
                    },
                    "parent": None,
                },
                "b": {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "text",
                            "parts": ["Good call. Always add tests before you merge."],
                        },
                        "create_time": 1722500100,
                    },
                    "parent": "a",
                },
            },
        }
    ]
}


class TestProviderRegistration:
    def test_both_providers_registered(self):
        assert "claude" in MAPPERS
        assert "chatgpt" in MAPPERS

    def test_map_export_uses_registry(self):
        # map_export dispatches via MAPPERS; ensure it routes to our fns.
        from memanto.cli.migrate.runner import map_export

        claude_rows = map_export("claude", CLAUDE_EXPORT)
        chatgpt_rows = map_export("chatgpt", CHATGPT_EXPORT)
        assert claude_rows
        assert chatgpt_rows


class TestMapClaude:
    def test_distills_signal_turns(self):
        rows = map_claude(CLAUDE_EXPORT)
        titles = [r["title"] for r in rows]
        assert any("dark themes" in t for t in titles)
        assert any("ship the CLI" in t for t in titles)

    def test_classifies_types(self):
        rows = {r["title"]: r for r in map_claude(CLAUDE_EXPORT)}
        pref = next(r for r in rows.values() if "dark themes" in r["title"])
        goal = next(r for r in rows.values() if "ship the CLI" in r["title"])
        # assistant "remember to ..." -> instruction
        inst = next(r for r in rows.values() if "pin npm" in r["title"])
        assert pref["type"] == "preference"
        assert goal["type"] == "goal"
        assert inst["type"] == "instruction"

    def test_source_and_provenance(self):
        rows = map_claude(CLAUDE_EXPORT)
        for r in rows:
            assert r["source"] == "claude"
            assert r["provenance"] == "imported"
            assert r["updated_at"] is not None

    def test_created_at_parsed(self):
        row = next(r for r in map_claude(CLAUDE_EXPORT) if "dark themes" in r["title"])
        assert row["created_at"] is not None
        assert row["created_at"].tzinfo is not None

    def test_assistant_non_signal_dropped(self):
        # A purely conversational assistant turn with no durable signal should
        # not become a memory row.
        export = {
            "conversations": [
                {
                    "chat_messages": [
                        {"sender": "human", "text": "hi", "created_at": "2026-01-01T00:00:00Z", "uuid": "x"},
                        {"sender": "assistant", "text": "Hey! How can I help today?", "created_at": "2026-01-01T00:00:01Z", "uuid": "y"},
                    ]
                }
            ]
        }
        rows = map_claude(export)
        # "hi" is too short to be a durable memory and assistant greeting is
        # non-signal, so we expect no artifacts here.
        titles = [r["title"] for r in rows]
        assert not any("how can i help" in t.lower() for t in titles)


class TestMapChatgpt:
    def test_extracts_parts(self):
        rows = map_chatgpt(CHATGPT_EXPORT)
        assert any("FastAPI" in r["title"] for r in rows)

    def test_classifies_decision(self):
        row = next(r for r in map_chatgpt(CHATGPT_EXPORT) if "FastAPI" in r["title"])
        assert row["type"] == "decision"
        assert row["source_ref"] == "a"

    def test_invalid_roles_skipped(self):
        export = {
            "conversations": [
                {
                    "mapping": {
                        "a": {"message": {"author": {"role": "system"}, "content": "be concise", "create_time": 1}},
                        "b": {"message": {"author": {"role": "user"}, "content": "I like coffee.", "create_time": 2}},
                    }
                }
            ]
        }
        rows = map_chatgpt(export)
        assert len(rows) == 1
        assert "coffee" in rows[0]["title"]


class TestSourceCount:
    def test_claude_counts_nonempty_messages(self):
        assert source_count("claude", CLAUDE_EXPORT) == 3

    def test_claude_skips_empty_text(self):
        export = {
            "conversations": [
                {"chat_messages": [
                    {"sender": "human", "text": "about me note", "uuid": "a"},
                    {"sender": "assistant", "text": "   ", "uuid": "b"},
                ]}
            ]
        }
        assert source_count("claude", export) == 1

    def test_chatgpt_counts_parts(self):
        assert source_count("chatgpt", CHATGPT_EXPORT) == 2
