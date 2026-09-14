import pytest

from mappers import map_chatgpt, map_claude, map_gemini


def _chatgpt_export(*user_texts, conv_id="conv-1", title="Test Conv"):
    nodes = {}
    prev = None
    for i, text in enumerate(user_texts):
        nid = f"node-{i}"
        nodes[nid] = {
            "id": nid,
            "parent": prev,
            "message": {
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": [text]},
                "create_time": 1700000000 + i,
            },
        }
        prev = nid
    return {
        "memories": [
            {
                "id": conv_id,
                "title": title,
                "create_time": 1700000000,
                "mapping": nodes,
                "current_node": prev,
            }
        ]
    }


def _claude_export(*texts, conv_id="c-1", name="My Conv"):
    messages = [
        {
            "uuid": f"msg-{i}",
            "sender": "human",
            "text": t,
            "created_at": "2024-01-01T00:00:00Z",
        }
        for i, t in enumerate(texts)
    ]
    return {"memories": [{"uuid": conv_id, "name": name, "chat_messages": messages}]}


def _gemini_export(*texts, conv_id="g-1"):
    return {
        "memories": [
            {
                "id": conv_id,
                "createdTime": "2024-01-01T00:00:00Z",
                "messages": [{"role": "user", "text": t} for t in texts],
            }
        ]
    }


class TestMapChatgpt:
    def test_basic_fields(self):
        rows = map_chatgpt(_chatgpt_export("Hello world"))
        assert len(rows) == 1
        r = rows[0]
        assert r["source"] == "chatgpt"
        assert r["provenance"] == "imported"
        assert r["type"] is None
        assert "Hello world" in r["content"]

    def test_chronological_order(self):
        rows = map_chatgpt(_chatgpt_export("first", "second", "third"))
        contents = [r["content"] for r in rows]
        first_idx = next(i for i, c in enumerate(contents) if "first" in c)
        third_idx = next(i for i, c in enumerate(contents) if "third" in c)
        assert first_idx < third_idx

    def test_skips_assistant_nodes(self):
        mapping = {
            "u1": {
                "id": "u1",
                "parent": None,
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["user msg"]},
                    "create_time": 1700000001,
                },
            },
            "a1": {
                "id": "a1",
                "parent": "u1",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["assistant reply"]},
                    "create_time": 1700000002,
                },
            },
        }
        export = {"memories": [{"id": "c1", "title": "t", "mapping": mapping, "current_node": "a1"}]}
        rows = map_chatgpt(export)
        assert len(rows) == 1
        assert "assistant reply" not in rows[0]["content"]

    def test_skips_user_editable_context(self):
        mapping = {
            "n1": {
                "id": "n1",
                "parent": None,
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "user_editable_context", "parts": ["system context"]},
                    "create_time": 1700000001,
                },
            },
            "n2": {
                "id": "n2",
                "parent": "n1",
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["real question"]},
                    "create_time": 1700000002,
                },
            },
        }
        export = {"memories": [{"id": "c1", "title": "t", "mapping": mapping, "current_node": "n2"}]}
        rows = map_chatgpt(export)
        assert len(rows) == 1
        assert "system context" not in rows[0]["content"]
        assert "real question" in rows[0]["content"]

    def test_skips_empty_conversations(self):
        export = {"memories": [{"id": "c1", "title": "empty", "mapping": {}, "current_node": None}]}
        assert map_chatgpt(export) == []

    def test_cycle_guard(self):
        mapping = {
            "n1": {
                "id": "n1",
                "parent": "n2",
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["msg a"]},
                    "create_time": 1700000001,
                },
            },
            "n2": {
                "id": "n2",
                "parent": "n1",
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["msg b"]},
                    "create_time": 1700000002,
                },
            },
        }
        export = {"memories": [{"id": "c1", "title": "cycle", "mapping": mapping, "current_node": "n1"}]}
        assert len(map_chatgpt(export)) == 2

    def test_empty_memories(self):
        assert map_chatgpt({"memories": []}) == []
        assert map_chatgpt({}) == []

    def test_title_used_when_present(self):
        rows = map_chatgpt(_chatgpt_export("some text", title="My Title"))
        assert rows[0]["title"] == "My Title"

    def test_timestamp_parsed(self):
        rows = map_chatgpt(_chatgpt_export("hello"))
        assert rows[0]["created_at"] is not None

    def test_source_ref_is_node_id(self):
        rows = map_chatgpt(_chatgpt_export("hello"))
        assert rows[0]["source_ref"] == "node-0"

    def test_skips_malformed_conv(self):
        good_conv = _chatgpt_export("valid message")["memories"][0]
        export = {"memories": ["not a dict", None, 42, good_conv]}
        rows = map_chatgpt(export)
        assert len(rows) == 1
        assert "valid message" in rows[0]["content"]


class TestMapClaude:
    def test_basic_fields(self):
        rows = map_claude(_claude_export("Hello Claude"))
        assert len(rows) == 1
        r = rows[0]
        assert r["source"] == "claude"
        assert r["provenance"] == "imported"
        assert r["type"] is None
        assert "Hello Claude" in r["content"]

    def test_skips_non_human_senders(self):
        export = {
            "memories": [
                {
                    "uuid": "c1",
                    "name": "conv",
                    "chat_messages": [
                        {"uuid": "m1", "sender": "assistant", "text": "AI reply", "created_at": "2024-01-01T00:00:00Z"},
                        {"uuid": "m2", "sender": "human", "text": "human msg", "created_at": "2024-01-01T00:00:01Z"},
                    ],
                }
            ]
        }
        rows = map_claude(export)
        assert len(rows) == 1
        assert "AI reply" not in rows[0]["content"]

    def test_skips_empty_text(self):
        export = {
            "memories": [
                {
                    "uuid": "c1",
                    "name": "conv",
                    "chat_messages": [
                        {"uuid": "m1", "sender": "human", "text": "", "created_at": "2024-01-01T00:00:00Z"},
                        {"uuid": "m2", "sender": "human", "text": "real text", "created_at": "2024-01-01T00:00:01Z"},
                    ],
                }
            ]
        }
        rows = map_claude(export)
        assert len(rows) == 1
        assert "real text" in rows[0]["content"]

    def test_fallback_to_content_parts(self):
        export = {
            "memories": [
                {
                    "uuid": "c1",
                    "name": "conv",
                    "chat_messages": [
                        {
                            "uuid": "m1",
                            "sender": "human",
                            "text": "",
                            "content": [{"type": "text", "text": "from parts"}],
                            "created_at": "2024-01-01T00:00:00Z",
                        }
                    ],
                }
            ]
        }
        rows = map_claude(export)
        assert len(rows) == 1
        assert "from parts" in rows[0]["content"]

    def test_empty_memories(self):
        assert map_claude({"memories": []}) == []
        assert map_claude({}) == []

    def test_conv_title_used(self):
        rows = map_claude(_claude_export("hi", name="My Conversation"))
        assert rows[0]["title"] == "My Conversation"

    def test_timestamp_parsed(self):
        assert map_claude(_claude_export("hello"))[0]["created_at"] is not None

    def test_source_ref_is_message_uuid(self):
        assert map_claude(_claude_export("hello"))[0]["source_ref"] == "msg-0"

    def test_multiple_messages(self):
        assert len(map_claude(_claude_export("first", "second", "third"))) == 3

    def test_skips_malformed_conv(self):
        export = {"memories": [
            "not a dict",
            None,
            {"uuid": "c1", "name": "ok", "chat_messages": [{"uuid": "m1", "sender": "human", "text": "valid"}]},
        ]}
        rows = map_claude(export)
        assert len(rows) == 1
        assert "valid" in rows[0]["content"]


class TestMapGemini:
    def test_basic_fields(self):
        rows = map_gemini(_gemini_export("Hello Gemini"))
        assert len(rows) == 1
        r = rows[0]
        assert r["source"] == "gemini"
        assert r["provenance"] == "imported"
        assert r["type"] is None
        assert "Hello Gemini" in r["content"]

    def test_skips_non_user_roles(self):
        export = {
            "memories": [
                {
                    "id": "g1",
                    "createdTime": "2024-01-01T00:00:00Z",
                    "messages": [
                        {"role": "model", "text": "AI response"},
                        {"role": "user", "text": "user msg"},
                    ],
                }
            ]
        }
        rows = map_gemini(export)
        assert len(rows) == 1
        assert "AI response" not in rows[0]["content"]

    def test_skips_empty_text(self):
        export = {
            "memories": [
                {
                    "id": "g1",
                    "createdTime": "2024-01-01T00:00:00Z",
                    "messages": [
                        {"role": "user", "text": ""},
                        {"role": "user", "text": "real text"},
                    ],
                }
            ]
        }
        rows = map_gemini(export)
        assert len(rows) == 1
        assert "real text" in rows[0]["content"]

    def test_skips_malformed_conv(self):
        export = {"memories": [
            "not a dict",
            None,
            {"id": "g1", "createdTime": None, "messages": [{"role": "user", "text": "ok"}]},
        ]}
        rows = map_gemini(export)
        assert len(rows) == 1
        assert "ok" in rows[0]["content"]

    def test_empty_memories(self):
        assert map_gemini({"memories": []}) == []
        assert map_gemini({}) == []

    def test_timestamp_parsed(self):
        assert map_gemini(_gemini_export("hello"))[0]["created_at"] is not None

    def test_source_ref_is_unique_per_message(self):
        rows = map_gemini(_gemini_export("hello", conv_id="gemini-conv-42"))
        assert rows[0]["source_ref"] == "gemini-conv-42:0"

    def test_multiple_user_messages_same_conv(self):
        assert len(map_gemini(_gemini_export("first", "second"))) == 2

    def test_native_conversation_format(self):
        export = {
            "memories": [
                {
                    "id": "native-1",
                    "createdTime": "2024-06-01T10:00:00Z",
                    "messages": [
                        {"role": "user", "text": "Hello"},
                        {"role": "model", "text": "Hi there"},
                        {"role": "user", "text": "How are you"},
                    ],
                }
            ]
        }
        rows = map_gemini(export)
        assert len(rows) == 2
        texts = [r["content"] for r in rows]
        assert any("Hello" in t for t in texts)
        assert any("How are you" in t for t in texts)
