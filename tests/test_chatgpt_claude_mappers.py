"""Unit tests for ChatGPT and Claude migration mappers.

Covers tree-walking, flat fallback, content extraction, edge cases,
and schema contract compliance.
"""

from memanto.cli.migrate.mappers import map_chatgpt, map_claude


# ---------------------------------------------------------------------------
# ChatGPT mappers
# ---------------------------------------------------------------------------

def _chatgpt_tree_convo():
    """Minimal ChatGPT conversation with tree mapping."""
    return {
        "title": "Test Conversation",
        "conversation_id": "conv-123",
        "create_time": 1700000000.0,
        "current_node": "node_a1",
        "mapping": {
            "node_root": {"id": "node_root", "message": None, "parent": None, "children": ["node_u1"]},
            "node_u1": {
                "id": "node_u1",
                "message": {
                    "id": "msg_u1",
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Hello world"]},
                    "create_time": 1700000000.0,
                },
                "parent": "node_root",
                "children": ["node_a1"],
            },
            "node_a1": {
                "id": "node_a1",
                "message": {
                    "id": "msg_a1",
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["Hi there!"]},
                    "create_time": 1700000100.0,
                },
                "parent": "node_u1",
                "children": [],
            },
        },
    }


def test_chatgpt_tree_basic():
    """Tree-structured conversation produces correct memories."""
    rows = map_chatgpt({"conversations": [_chatgpt_tree_convo()]})
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Test Conversation"
    assert row["source"] == "chatgpt"
    assert row["source_ref"] == "conv-123"
    assert "Hello world" in row["content"]
    assert "Hi there!" in row["content"]
    assert row["tags"] == ["chatgpt", "ai-conversation"]


def test_chatgpt_tree_preserves_both_roles():
    """Both user and assistant messages appear in content."""
    rows = map_chatgpt({"conversations": [_chatgpt_tree_convo()]})
    content = rows[0]["content"]
    assert "[User message" in content
    assert "[Assistant message" in content


def test_chatgpt_flat_fallback():
    """Flat messages array works when no mapping is present."""
    convo = {
        "title": "Flat Chat",
        "messages": [
            {"author": {"role": "user"}, "content": {"parts": ["Question?"]}},
            {"author": {"role": "assistant"}, "content": {"parts": ["Answer."]}},
        ],
    }
    rows = map_chatgpt({"conversations": [convo]})
    assert len(rows) == 1
    assert "Question?" in rows[0]["content"]
    assert "Answer." in rows[0]["content"]


def test_chatgpt_flat_string_content():
    """Flat fallback handles string content (not dict with parts)."""
    convo = {
        "title": "String Content",
        "messages": [
            {"author": {"role": "user"}, "content": "Plain text message"},
        ],
    }
    rows = map_chatgpt({"conversations": [convo]})
    assert len(rows) == 1
    assert "Plain text message" in rows[0]["content"]


def test_chatgpt_empty_conversation_skipped():
    """Empty conversations are skipped."""
    rows = map_chatgpt({"conversations": [{"title": "Empty"}]})
    assert len(rows) == 0


def test_chatgpt_conversation_id_used_as_source_ref():
    """conversation_id maps to source_ref."""
    convo = _chatgpt_tree_convo()
    convo["conversation_id"] = "abc-456"
    rows = map_chatgpt({"conversations": [convo]})
    assert rows[0]["source_ref"] == "abc-456"


def test_chatgpt_fallback_to_id_when_no_conversation_id():
    """Falls back to 'id' field when conversation_id is absent."""
    convo = _chatgpt_tree_convo()
    del convo["conversation_id"]
    convo["id"] = "fallback-id"
    rows = map_chatgpt({"conversations": [convo]})
    assert rows[0]["source_ref"] == "fallback-id"


def test_chatgpt_flat_retains_assistant_messages():
    """Flat fallback retains assistant messages, not just user."""
    convo = {
        "title": "Multi-role",
        "messages": [
            {"author": {"role": "user"}, "content": {"parts": ["Q1"]}},
            {"author": {"role": "assistant"}, "content": {"parts": ["A1"]}},
            {"author": {"role": "system"}, "content": {"parts": ["System msg"]}},
        ],
    }
    rows = map_chatgpt({"conversations": [convo]})
    content = rows[0]["content"]
    assert "Q1" in content
    assert "A1" in content
    assert "System msg" in content


def test_chatgpt_handles_dict_content_with_null_parts():
    """Dict content with null parts doesn't crash."""
    convo = {
        "title": "Null parts",
        "messages": [
            {"author": {"role": "user"}, "content": {"parts": None}},
        ],
    }
    rows = map_chatgpt({"conversations": [convo]})
    # Should skip empty content, not crash
    assert isinstance(rows, list)


def test_chatgpt_schema_contract():
    """Every row has required keys."""
    rows = map_chatgpt({"conversations": [_chatgpt_tree_convo()]})
    required = {"title", "content", "type", "tags", "confidence", "source", "source_ref", "provenance", "created_at", "updated_at"}
    for row in rows:
        assert required.issubset(row.keys()), f"Missing keys: {required - row.keys()}"


# ---------------------------------------------------------------------------
# Claude mappers
# ---------------------------------------------------------------------------

def _claude_convo():
    """Minimal Claude conversation."""
    return {
        "name": "Claude Chat",
        "uuid": "uuid-789",
        "created_at": "2024-01-15T10:00:00Z",
        "chat_messages": [
            {"sender": "human", "text": "What is 2+2?", "created_at": "2024-01-15T10:00:00Z"},
            {"sender": "assistant", "text": "4", "created_at": "2024-01-15T10:00:01Z"},
        ],
    }


def test_claude_basic():
    """Claude conversation produces correct memory."""
    rows = map_claude({"conversations": [_claude_convo()]})
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Claude Chat"
    assert row["source"] == "claude"
    assert row["source_ref"] == "uuid-789"
    assert "2+2" in row["content"]


def test_claude_retains_assistant_messages():
    """Claude mapper retains assistant messages."""
    rows = map_claude({"conversations": [_claude_convo()]})
    content = rows[0]["content"]
    assert "4" in content


def test_claude_flat_messages_fallback():
    """Falls back to 'messages' key when chat_messages absent."""
    convo = {
        "name": "Alt Claude",
        "uuid": "uuid-alt",
        "messages": [
            {"sender": "human", "text": "Hello"},
            {"sender": "assistant", "text": "Hi!"},
        ],
    }
    rows = map_claude({"conversations": [convo]})
    assert len(rows) == 1
    assert "Hello" in rows[0]["content"]


def test_claude_empty_skipped():
    """Conversations with no human messages are skipped."""
    rows = map_claude({"conversations": [{"name": "Empty", "chat_messages": []}]})
    assert len(rows) == 0


def test_claude_dict_content():
    """Claude mapper handles dict content with parts."""
    convo = {
        "name": "Dict Content",
        "uuid": "uuid-dict",
        "chat_messages": [
            {"sender": "human", "content": {"parts": ["Question"]}},
        ],
    }
    rows = map_claude({"conversations": [convo]})
    assert len(rows) == 1
    assert "Question" in rows[0]["content"]


def test_claude_schema_contract():
    """Every row has required keys."""
    rows = map_claude({"conversations": [_claude_convo()]})
    required = {"title", "content", "type", "tags", "confidence", "source", "source_ref", "provenance", "created_at", "updated_at"}
    for row in rows:
        assert required.issubset(row.keys()), f"Missing keys: {required - row.keys()}"
