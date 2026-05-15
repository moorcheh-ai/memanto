"""Session one: store memories through the LangGraph agent."""

from support_agent import run_support_turn


if __name__ == "__main__":
    result = run_support_turn(
        user_id="customer_42",
        message=(
            "My replacement orders are urgent. Please send updates by SMS and keep "
            "the replies brief."
        ),
    )
    print("Session 1 reply:")
    print(result["reply"])
    print("\nStored memories:")
    for memory in result["memories_to_store"]:
        print(f"- {memory.content}")
