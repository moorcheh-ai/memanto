from __future__ import annotations

import tempfile
from pathlib import Path

from run_demo import run_two_session_demo


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_two_session_demo(
            backend="local",
            agent_id="validate-langgraph-recruiting-memory",
            local_db=Path(tmp) / "memories.json",
            reset_local=True,
        )

    session_one = result["session_one"]
    session_two = result["session_two"]
    recalled_text = " ".join(
        item["content"] for item in session_two.get("recalled_memories", [])
    )
    answer = session_two["answer"]

    assert session_one["thread_id"] != session_two["thread_id"]
    assert "Maya Chen" not in session_two["user_message"]
    assert "Maya Chen" in recalled_text
    assert "Staff AI Platform" in recalled_text
    assert "14:00 UTC" in recalled_text
    assert "take-home" in recalled_text
    assert "Memanto recalled" in answer

    print("offline validation passed")
    print(f"stored memories: {len(session_one.get('stored_memories', []))}")
    print(f"recalled memories: {len(session_two.get('recalled_memories', []))}")


if __name__ == "__main__":
    main()
