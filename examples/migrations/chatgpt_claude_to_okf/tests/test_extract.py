"""Tests for the extraction layer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.extract import extract_memories, _classify, _is_junk  # noqa: E402

TURNS = [
    {"role": "user", "text": "I prefer Postgres over MySQL. We decided to migrate to Postgres 16 this quarter.", "ts": 1},
    {"role": "user", "text": "Remember: never run migrations during peak hours.", "ts": 2},
    {"role": "user", "text": "My wife and I are planning a trip to Da Nang in October.", "ts": 3},
    {"role": "user", "text": "Can you help me with a quick question?", "ts": 4},
    {"role": "user", "text": "Hi there, thanks!", "ts": 5},
    {"role": "assistant", "text": "That sounds great, let me know how it goes.", "ts": 6},
    {"role": "user", "text": "I'm building a Telegram bot in Python, my goal is to launch it this month.", "ts": 7},
    {"role": "user", "text": "I made a mistake last week with the credit card payment.", "ts": 8},
    {"role": "assistant", "text": "Noted — Tuesday/Thursday runs, coffee limit, Monday check-up. I'll add all of that to your profile.", "ts": 9},
]

CONV = [{"id": "c1", "title": "test", "source": "chatgpt", "turns": TURNS}]


def test_classify_types():
    assert _classify("I prefer Postgres over MySQL.")[0] == "preference"
    assert _classify("We decided to migrate to Postgres.")[0] == "decision"
    assert _classify("Remember: never run migrations at peak.")[0] == "instruction"
    assert _classify("My wife and I are planning a trip.")[0] == "relationship"
    assert _classify("I'm building a Telegram bot, my goal is to launch it.")[0] == "goal"
    assert _classify("I made a mistake last week.")[0] == "learning"


def test_junk_filtered():
    assert _is_junk("Can you help me with a quick question?")
    assert _is_junk("Hi there, thanks!")
    assert _is_junk("That sounds great, let me know how it goes.")


def test_extraction_counts():
    result = extract_memories(CONV)
    memories = result["memories"]
    types = {m["type"] for m in memories}
    assert "preference" in types
    assert "decision" in types
    assert "instruction" in types
    assert "relationship" in types
    assert "goal" in types
    assert "learning" in types
    # junk turns must not produce memories
    texts = [m["content"].lower() for m in memories]
    assert not any("can you help me" in t for t in texts)
    assert not any("hi there" in t for t in texts)


def test_assistant_turns_not_extracted():
    """Assistant replies are confirmations, not memories — never extract them."""
    result = extract_memories(CONV)
    texts = [m["content"].lower() for m in result["memories"]]
    assert not any("noted" in t for t in texts), "assistant turn leaked into memories"
    assert not any("coffee limit" in t for t in texts)


def test_dedupe():
    turns = [
        {"role": "user", "text": "I prefer Postgres over MySQL.", "ts": 1},
        {"role": "user", "text": "I prefer Postgres over MySQL!", "ts": 2},
    ]
    result = extract_memories([{"id": "c", "title": "t", "source": "chatgpt", "turns": turns}])
    assert len(result["memories"]) == 1


def test_metadata_shape():
    result = extract_memories(CONV)
    m = result["memories"][0]
    assert set(m) >= {"type", "title", "description", "content", "tags", "timestamp", "resource", "x_memanto"}
    assert set(m["x_memanto"]) == {"confidence", "provenance", "source", "type"}
    assert 0 < m["x_memanto"]["confidence"] <= 1
