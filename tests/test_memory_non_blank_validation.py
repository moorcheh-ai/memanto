import pytest
from pydantic import ValidationError

from memanto.app.core import MemoryRecord
from memanto.app.models import BatchRememberItem, MemoryBatchItem, MemoryStoreRequest


def test_memory_record_rejects_blank_content() -> None:
    with pytest.raises(ValidationError):
        MemoryRecord(
            type="fact",
            title="valid title",
            content="   \n\t",
            agent_id="agent-1",
            actor_id="agent-1",
            source="agent",
        )


def test_memory_record_rejects_blank_title() -> None:
    with pytest.raises(ValidationError):
        MemoryRecord(
            type="fact",
            title="   ",
            content="User prefers concise answers",
            agent_id="agent-1",
            actor_id="agent-1",
            source="agent",
        )


@pytest.mark.parametrize(
    "model,kwargs",
    [
        (
            MemoryStoreRequest,
            {
                "type": "fact",
                "title": "valid title",
                "content": "\t\n ",
                "agent_id": "agent-1",
                "actor_id": "agent-1",
                "source": "agent",
            },
        ),
        (
            MemoryStoreRequest,
            {
                "type": "fact",
                "title": "\t\n ",
                "content": "valid content",
                "agent_id": "agent-1",
                "actor_id": "agent-1",
                "source": "agent",
            },
        ),
        (
            MemoryBatchItem,
            {
                "type": "fact",
                "title": "valid title",
                "content": "\t\n ",
                "source": "agent",
            },
        ),
        (
            MemoryBatchItem,
            {
                "type": "fact",
                "title": "\t\n ",
                "content": "valid content",
                "source": "agent",
            },
        ),
        (
            BatchRememberItem,
            {
                "content": "\t\n ",
                "source": "agent",
            },
        ),
    ],
)
def test_api_memory_models_reject_blank_content(model, kwargs) -> None:
    with pytest.raises(ValidationError):
        model(**kwargs)


def test_memory_record_accepts_non_blank_text() -> None:
    record = MemoryRecord(
        type="preference",
        title="Communication style",
        content="User prefers concise answers",
        agent_id="agent-1",
        actor_id="agent-1",
        source="agent",
    )

    assert record.content == "User prefers concise answers"
