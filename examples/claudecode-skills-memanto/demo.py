from __future__ import annotations

from pathlib import Path

from skill_memory_bridge import LocalJsonlBackend, SkillMemoryBridge


def main() -> None:
    memory_path = Path(".memanto-demo/skills-memory.jsonl")
    if memory_path.exists():
        memory_path.unlink()

    bridge = SkillMemoryBridge(
        LocalJsonlBackend(memory_path),
        project_slug="checkout-service",
    )

    architecture = bridge.begin_skill(
        "/grill-with-docs",
        "Choose a retry policy for checkout payment capture.",
        cwd="/repo/checkout-service",
        files=["src/payments/capture.ts"],
    )
    print("=== First skill context ===")
    print(bridge.context_block(architecture))

    bridge.record_event(
        architecture,
        "decision",
        "Use idempotency keys around payment capture because retries can double-charge.",
        files=["src/payments/capture.ts"],
        tags=["payments", "retry-policy"],
        confidence=0.95,
    )
    bridge.record_event(
        architecture,
        "constraint",
        "Avoid retrying card_declined responses; only retry network and gateway timeout errors.",
        files=["src/payments/errors.ts"],
        tags=["payments", "error-handling"],
        confidence=0.9,
    )
    bridge.record_event(
        architecture,
        "tool_output",
        "Test runner failed once because the gateway mock reused the same request id.",
        files=["tests/payments/capture.test.ts"],
        tags=["test-gotcha"],
        confidence=0.85,
    )
    bridge.end_skill(
        architecture,
        "Selected a safe retry policy for payment capture and documented edge cases.",
    )

    tdd = bridge.begin_skill(
        "/tdd",
        "Write tests for payment capture retry behavior.",
        cwd="/repo/checkout-service",
        files=["tests/payments/capture.test.ts"],
    )
    print("\n=== Later skill context ===")
    print(bridge.context_block(tdd))


if __name__ == "__main__":
    main()
