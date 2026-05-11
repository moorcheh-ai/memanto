from support_memory_agent import (
    CUSTOMER_ID,
    TODAY_MESSAGE,
    YESTERDAY_MESSAGE,
    JsonLongTermMemory,
    build_support_graph,
    run_support_session,
)


def test_cross_session_recall_with_local_backend(tmp_path):
    memory = JsonLongTermMemory(tmp_path / "memories.json")
    graph = build_support_graph(memory)

    first = run_support_session(
        graph,
        session_name="yesterday",
        customer_id=CUSTOMER_ID,
        message=YESTERDAY_MESSAGE,
    )
    assert len(first["stored_memories"]) >= 2

    second = run_support_session(
        graph,
        session_name="today",
        customer_id=CUSTOMER_ID,
        message=TODAY_MESSAGE,
    )

    response = second["response"].lower()
    assert "sms" in response
    assert "enterprise" in response
    assert second["recalled_memories"]
