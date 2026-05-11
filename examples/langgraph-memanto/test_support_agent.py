from support_agent import run_demo


def test_cross_session_recall_drives_response_plan():
    session_1, session_2 = run_demo()

    assert "preference: User prefers concise support answers." in session_1[
        "stored_memories"
    ]
    assert "preference: User prefers email follow-up." in session_1["stored_memories"]

    assert "User prefers concise support answers." in session_2["recalled_memories"]
    assert "User prefers email follow-up." in session_2["recalled_memories"]
    assert session_2["response_plan"] == (
        "Use a concise tone and send the follow-up over email."
    )
