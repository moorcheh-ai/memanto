import os
from agent import app

USER_ID = "user_1234"

def run_session(user_id, message, session_id):
    print(f"User: {message}")
    inputs = {"messages": [("user", message)], "user_id": user_id}
    config = {"configurable": {"thread_id": session_id}}
    result = app.invoke(inputs, config)
    print(f"Assistant: {result['messages'][-1].content}\n")

if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Please set OPENAI_API_KEY environment variable.")
        exit(1)

    print("--- Session 1: Establishing Memory ---")
    run_session(USER_ID, "Hi, I'm Alex. I prefer my coffee black and I live in Tokyo.", "session_1")

    print("--- Session 2: Recalling Memory (New Thread) ---")
    run_session(USER_ID, "Do you remember where I live and how I like my coffee?", "session_2")
