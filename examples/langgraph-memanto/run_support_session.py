"""Session two: recall yesterday's memories in a fresh process."""

from support_agent import run_support_turn


if __name__ == "__main__":
    result = run_support_turn(
        user_id="customer_42",
        message="The replacement package is delayed again. What happens next?",
    )
    print("Session 2 reply:")
    print(result["reply"])
