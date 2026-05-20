from __future__ import annotations

from run_demo import run_demo

EXPECTED_TERMS = [
    "Northstar",
    "Friday",
    "purchase order",
    "May 28",
    "Ada",
]


def main() -> None:
    result = run_demo(backend="local", reset_local=True)
    today = result["today"]
    response = today["response"]
    recalled = today.get("recalled_memories", [])

    missing = [term for term in EXPECTED_TERMS if term.lower() not in response.lower()]
    if missing:
        raise SystemExit(f"missing recalled terms: {', '.join(missing)}")

    leaked = [
        memory
        for memory in recalled
        if memory["source_session"] == today["session_id"]
    ]
    if leaked:
        raise SystemExit("memory boundary failed: current session supplied recall")

    if len(recalled) < 3:
        raise SystemExit(f"expected at least 3 recalled memories, got {len(recalled)}")

    print("offline validation passed")
    print(f"recalled_memories={len(recalled)}")
    print("state_boundary=passed")


if __name__ == "__main__":
    main()
