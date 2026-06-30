from unittest.mock import MagicMock

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_write_service import MemoryWriteService


def make_memory(**overrides):
    data = {
        "type": "fact",
        "title": "User location",
        "content": "The user lives in Can Tho.",
        "scope_type": "agent",
        "scope_id": "agent-1",
        "actor_id": "agent-1",
        "source": "agent",
        "confidence": 0.9,
    }
    data.update(overrides)
    return MemoryRecord(**data)


def make_service(validation_result):
    client = MagicMock()
    client.documents.upload.return_value = {"status": "success"}
    service = MemoryWriteService(client)
    service._validation_service = MagicMock()
    service._validation_service.validate_memory.return_value = validation_result
    return service, client


def test_store_memory_preserves_validation_result_and_modified_memory():
    validated = make_memory(content="Validated content", confidence=0.4)
    validated.status = "provisional"
    service, client = make_service(
        {
            "valid": True,
            "action": "store_provisional",
            "reason": "Requires validation",
            "memory": validated,
        }
    )

    context = {"user_confirmed": False}
    memory = make_memory()
    result = service.store_memory(memory, context=context)

    service._validation_service.validate_memory.assert_called_once()
    _, validation_context = service._validation_service.validate_memory.call_args.args
    assert validation_context == context
    assert result["action"] == "store_provisional"
    assert result["reason"] == "Requires validation"
    assert result["memory_status"] == "provisional"
    uploaded = client.documents.upload.call_args.kwargs["documents"][0]
    assert uploaded["text"].endswith("Validated content")
    assert uploaded["status"] == "provisional"


def test_store_memory_reject_skips_upload_and_returns_validation_reason():
    service, client = make_service(
        {"valid": False, "action": "reject", "reason": "Untrusted source"}
    )

    result = service.store_memory(make_memory())

    client.documents.upload.assert_not_called()
    assert result["status"] == "rejected"
    assert result["action"] == "reject"
    assert result["reason"] == "Untrusted source"


def test_batch_store_memories_skips_rejected_items_but_uploads_allowed_items():
    client = MagicMock()
    client.documents.upload.return_value = {"status": "success"}
    service = MemoryWriteService(client)
    service._validation_service = MagicMock()
    service._validation_service.validate_memory.side_effect = [
        {"valid": False, "action": "reject", "reason": "Needs confirmation"},
        {"valid": True, "action": "store", "reason": "User confirmed"},
    ]

    contexts = [{"user_confirmed": False}, {"user_confirmed": True}]
    result = service.batch_store_memories(
        [make_memory(id="reject-me"), make_memory(id="store-me")],
        context=contexts,
    )

    assert service._validation_service.validate_memory.call_args_list[0].args[1] == contexts[0]
    assert service._validation_service.validate_memory.call_args_list[1].args[1] == contexts[1]
    assert result["total_submitted"] == 2
    assert result["successful"] == 1
    assert result["failed"] == 1
    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["action"] == "reject"
    assert result["results"][1]["status"] == "success"
    uploaded_docs = client.documents.upload.call_args.kwargs["documents"]
    assert len(uploaded_docs) == 1
    assert uploaded_docs[0]["id"] == "store-me"


def test_validation_service_computes_repetition_count_when_missing():
    service, _ = make_service({"valid": True, "action": "store", "reason": "Repeated content"})
    service._validation_service._check_repetition = MagicMock(return_value=2)

    service._validation_service.validate_memory.side_effect = None
    from memanto.app.services.memory_validation_service import MemoryValidationService

    validation_service = MemoryValidationService(MagicMock())
    validation_service._check_repetition = MagicMock(return_value=2)
    result = validation_service.validate_memory(make_memory(confidence=0.5), context={"user_confirmed": False})

    assert result["action"] == "store"
    assert result["reason"] == "Repeated content"
    validation_service._check_repetition.assert_called_once()
