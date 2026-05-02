from memanto.app.services.memory_parsing_service import MemoryParsingService
from memanto.app.core import MemoryRecord

#1 Rule-based detection
def test_detect_preference():
    parser = MemoryParsingService()

    memory = MemoryRecord(
        content="I like Python",
        type="fact",
        title="test",
        actor_id="user",
        source="test",
        scope_type="agent",
        scope_id="test",
    )
    memory.type = None

    parser.parse_memory(memory)

    assert memory.type == "preference"

#2 Do NOT override existing type
def test_no_override_existing_type():
    parser = MemoryParsingService()

    memory = MemoryRecord(
        content="I like Python",
        type="fact",
        title="test",
        actor_id="user",
        source="test",
        scope_type="agent",
        scope_id="test",
    )

    parser.parse_memory(memory)

    assert memory.type == "fact"

from memanto.app.config import settings

#3. Config disabled
def test_auto_parse_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AUTO_PARSE_ENABLED", False)

    parser = MemoryParsingService()

    memory = MemoryRecord(
        content="I like Python",
        type="fact",
        title="test",
        actor_id="user",
        source="test",
        scope_type="agent",
        scope_id="test",
    )
    memory.type = None

    parser.parse_memory(memory)

    assert memory.type is None

#4. Fallback to fact
def test_fallback_to_fact():
    parser = MemoryParsingService()

    memory = MemoryRecord(
        content="Earth is round",
        type="fact",
        title="test",
        actor_id="user",
        source="test",
        scope_type="agent",
        scope_id="test",
    )
    memory.type = None

    parser.parse_memory(memory)

    assert memory.type == "fact"
    
#5. LLM fallback is triggered
def test_llm_fallback_triggered(monkeypatch):
    from memanto.app.config import settings

    monkeypatch.setattr(settings, "USE_LLM_FALLBACK", True)

    parser = MemoryParsingService()

    # mock fallback method
    def mock_llm(text):
        return "context"

    monkeypatch.setattr(parser, "_llm_fallback", mock_llm)

    memory = MemoryRecord(
        content="random unrelated words here",
        type="fact",
        title="test",
        actor_id="user",
        source="test",
        scope_type="agent",
        scope_id="test",
    )
    memory.type = None

    parser.parse_memory(memory)

    assert memory.type == "context"