import pytest
from datetime import datetime, timezone
from memanto.cli.migrate.mappers import map_chatgpt
from memanto.cli.migrate.runner import source_count

@pytest.fixture
def sample_export():
    return {
        "conversations": [
            {
                "title": "Test Chat",
                "conversation_id": "c1",
                "create_time": 1700000000.0,
                "mapping": {
                    "m1": {
                        "message": {
                            "author": {"role": "user"},
                            "create_time": 1700000000.0,
                            "content": {"parts": ["Hello world!"]}
                        }
                    },
                    "m2": {
                        "message": {
                            "author": {"role": "assistant"},
                            "create_time": 1700000010.0,
                            "content": {"parts": ["Hi there!"]}
                        }
                    },
                    "m3": {
                        "message": {
                            "author": {"role": "system"},
                            "content": {"parts": ["System prompt"]}
                        }
                    }
                }
            }
        ]
    }

def test_chatgpt_source_count(sample_export):
    count = source_count("chatgpt", sample_export)
    assert count == 3  # All nodes in mapping

def test_chatgpt_mapper(sample_export):
    rows = map_chatgpt(sample_export)
    # Should skip the system message
    assert len(rows) == 2
    
    # Sort by created_at to ensure order
    rows.sort(key=lambda r: r["created_at"])
    
    user_mem = rows[0]
    assert user_mem["title"] == "Hello world!"
    assert "Hello world!" in user_mem["content"]
    assert "Conversation title: Test Chat" in user_mem["content"]
    assert "Role: user" in user_mem["content"]
    assert user_mem["type"] == "fact"
    assert "chatgpt" in user_mem["tags"]
    assert "conv_id=c1" in user_mem["tags"]
    assert user_mem["source"] == "chatgpt"
    
    assistant_mem = rows[1]
    assert assistant_mem["type"] == "observation"
    assert "Hi there!" in assistant_mem["content"]
    assert "Role: assistant" in assistant_mem["content"]
    
def test_chatgpt_mapper_empty():
    assert map_chatgpt({}) == []
    assert map_chatgpt({"conversations": None}) == []
    assert map_chatgpt({"conversations": [{"mapping": {}}]}) == []
