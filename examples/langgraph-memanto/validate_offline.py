from __future__ import annotations

from langgraph_memanto import LocalJsonMemoryBackend, run_two_session_demo


def main() -> None:
    backend = LocalJsonMemoryBackend()
    backend.reset()

    result = run_two_session_demo(backend)
    recalled = "\n".join(
        memory.content for memory in result["session_2"].get("recalled_memories", [])
    )

    required = [
        "AR-8841",
        "concise answers",
        "manager approval",
    ]
    missing = [needle for needle in required if needle not in recalled]
    if missing:
        raise SystemExit(f"offline validation failed, missing: {missing}")

    print("offline validation passed")


if __name__ == "__main__":
    main()
