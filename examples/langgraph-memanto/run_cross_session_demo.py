"""Run the full two-session demo without external LLM calls."""

from pathlib import Path

from support_agent import run_support_turn


if __name__ == "__main__":
    store = Path(".memanto-demo-store.json")
    if store.exists():
        store.unlink()

    first = run_support_turn(
        user_id="customer_42",
        message=(
            "My replacement orders are urgent. Please send updates by SMS and keep "
            "the replies brief."
        ),
    )
    print("=== Session 1 ===")
    print(first["reply"])

    second = run_support_turn(
        user_id="customer_42",
        message="The replacement package is delayed again. What happens next?",
    )
    print("\n=== Session 2 ===")
    print(second["reply"])
