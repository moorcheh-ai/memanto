import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import adapters  # noqa: F401
from adapters.chatgpt import ChatGPTAdapter
from core.adapters import ADAPTERS


class TestChatGPTTitleNormalization:
    def _adapter(self) -> ChatGPTAdapter:
        return ADAPTERS["chatgpt"]()

    def _conversation(self, title, text="hello"):
        return {
            "id": "abc12345",
            "title": title,
            "messages": [
                {
                    "author": {"role": "user"},
                    "content": {"parts": [text]},
                    "role": "user",
                },
                {
                    "author": {"role": "assistant"},
                    "content": {"parts": ["hi there"]},
                    "role": "assistant",
                },
            ],
        }

    def test_conversation_list_normalizes_none_title(self):
        adapter = self._adapter()
        conv = self._conversation(None)
        listed = adapter.get_conversation_list({"conversations": [conv]})
        assert listed[0]["title"] == "ChatGPT abc12345"

    def test_conversation_list_normalizes_non_string_title(self):
        adapter = self._adapter()
        conv = self._conversation(12345)
        listed = adapter.get_conversation_list({"conversations": [conv]})
        assert listed[0]["title"] == "ChatGPT abc12345"

    def test_conversation_list_keeps_string_title(self):
        adapter = self._adapter()
        conv = self._conversation("My real title")
        listed = adapter.get_conversation_list({"conversations": [conv]})
        assert listed[0]["title"] == "My real title"

    def test_extract_normalizes_none_title(self):
        adapter = self._adapter()
        entities = adapter.extract({"conversations": [self._conversation(None)]})
        assert entities[0].title == "ChatGPT abc12345"

    def test_extract_title_lower_without_crash(self):
        adapter = self._adapter()
        conv = self._conversation(None, text="pipeline")
        entities = adapter.extract(
            {"conversations": [conv]},
            filters={"keyword": "pipeline"},
        )
        assert entities[0].title == "ChatGPT abc12345"


def _mapping_fixture():
    """user -> tool -> assistant interleaved sequence per CodeRabbit."""
    mapping = {
        "root": {
            "parent": None,
            "message": {
                "id": "root",
                "author": {"role": "assistant"},
                "content": {"parts": ["welcome"]},
                "create_time": 1000.0,
            },
        },
        "n1": {
            "parent": "root",
            "message": {
                "id": "n1",
                "author": {"role": "user"},
                "content": {"parts": ["what is X?"]},
                "create_time": 1001.0,
            },
        },
        "n2": {
            "parent": "n1",
            "message": {
                "id": "n2",
                "author": {"role": "tool"},
                "content": {"parts": ["tool result"]},
                "create_time": 1002.0,
            },
        },
        "n3": {
            "parent": "n2",
            "message": {
                "id": "n3",
                "author": {"role": "assistant"},
                "content": {"parts": ["X is the answer"]},
                "create_time": 1003.0,
            },
        },
        "n4": {
            "parent": "n3",
            "message": {
                "id": "n4",
                "author": {"role": "user"},
                "content": {"parts": ["next question"]},
                "create_time": 1004.0,
            },
        },
        "n5": {
            "parent": "n4",
            "message": {
                "id": "n5",
                "author": {"role": "assistant"},
                "content": {"parts": ["next answer"]},
                "create_time": 1005.0,
            },
        },
    }
    return {"mapping": mapping}


class TestChatGPTMappingPairs:
    def test_user_tool_assistant_preserves_assistant_reply(self):
        adapter = ADAPTERS["chatgpt"]()
        entities = adapter.extract(_mapping_fixture())
        assert len(entities) == 1
        content = entities[0].content
        assert "**User:** what is X?" in content
        assert "**Assistant:** X is the answer" in content
        assert "tool result" not in content

    def test_pairing_continues_after_interleaved(self):
        adapter = ADAPTERS["chatgpt"]()
        entities = adapter.extract(_mapping_fixture())
        content = entities[0].content
        assert "**User:** next question" in content
        assert "**Assistant:** next answer" in content