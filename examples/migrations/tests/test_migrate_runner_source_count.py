import pytest

from runner import source_count
from mappers import map_chatgpt

ALL_PROVIDERS = [
    "mem0", "letta", "supermemory", "okf", "chatgpt", "claude",
    "gemini", "zep", "hindsight", "langgraph", "notion", "obsidian", "chroma",
]


@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_empty_dict_returns_zero(provider):
    assert source_count(provider, {}) == 0


@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_missing_array_key_does_not_raise(provider):
    assert source_count(provider, {"unrelated": "data"}) == 0


def test_letta_counts_passages():
    assert source_count("letta", {"passages": ["a", "b", "c"]}) == 3


def test_langgraph_counts_items():
    assert source_count("langgraph", {"items": [1, 2]}) == 2


def test_chatgpt_current_node_traversal():
    root, user_id, ctx_id, asst_id = "root", "user", "ctx", "asst"
    export = {
        "memories": [
            {
                "current_node": asst_id,
                "mapping": {
                    root:    {"id": root,    "message": None, "parent": None},
                    user_id: {"id": user_id, "parent": root,    "message": {"author": {"role": "user"},      "content": {"content_type": "text",                 "parts": ["hello"]}}},
                    ctx_id:  {"id": ctx_id,  "parent": user_id, "message": {"author": {"role": "user"},      "content": {"content_type": "user_editable_context", "parts": ["ctx"]}}},
                    asst_id: {"id": asst_id, "parent": ctx_id,  "message": {"author": {"role": "assistant"}, "content": {"content_type": "text",                 "parts": ["hi"]}}},
                },
            }
        ]
    }
    # user_editable_context excluded; only the plain user node counts
    assert source_count("chatgpt", export) == 1
    # source_count must agree with map_chatgpt
    assert len(map_chatgpt(export)) == source_count("chatgpt", export)


def test_chatgpt_fallback_count_without_current_node():
    export = {
        "memories": [
            {
                "mapping": {
                    "n1": {"message": {"author": {"role": "user"},      "content": "hi"}},
                    "n2": {"message": {"author": {"role": "assistant"}, "content": "hey"}},
                    "n3": {"message": {"author": {"role": "user"},      "content": "ok"}},
                }
            },
            {
                "mapping": {
                    "n4": {"message": {"author": {"role": "user"}, "content": "more"}},
                }
            },
        ]
    }
    assert source_count("chatgpt", export) == 3


def test_claude_counts_human_messages():
    export = {
        "memories": [
            {"chat_messages": [
                {"sender": "human",     "text": "hello"},
                {"sender": "assistant", "text": "hi"},
                {"sender": "human",     "text": "bye"},
            ]},
            {"chat_messages": [
                {"sender": "human", "text": "again"},
            ]},
        ]
    }
    assert source_count("claude", export) == 3


def test_gemini_counts_user_messages():
    export = {
        "memories": [
            {"messages": [
                {"role": "user",  "text": "q1"},
                {"role": "model", "text": "a1"},
                {"role": "user",  "text": "q2"},
            ]}
        ]
    }
    assert source_count("gemini", export) == 2


@pytest.mark.parametrize("provider", ["zep", "hindsight", "notion", "obsidian", "chroma", "mem0", "okf"])
def test_generic_providers_count_memories(provider):
    assert source_count(provider, {"memories": ["x", "y", "z"]}) == 3


def test_supermemory_falls_back_to_chunks_when_no_memories():
    export = {
        "documents": [
            {"chunks": ["a", "b"]},
            {"chunks": ["c"]},
        ]
    }
    assert source_count("supermemory", export) == 3


def test_supermemory_uses_memories_when_present():
    export = {
        "memories":  ["m1", "m2"],
        "documents": [{"chunks": ["a", "b", "c"]}],
    }
    assert source_count("supermemory", export) == 2
