import os
import sys

# Add root to path to import memanto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from langchain_core.messages import HumanMessage
from agent import app

def run_conversation(user_id, session_id, text):
    inputs = {
        "messages": [HumanMessage(content=text)],
        "user_id": user_id,
        "session_id": session_id,
        "memories": ""
    }
    config = {"configurable": {"thread_id": session_id}}
    result = app.invoke(inputs, config=config)
    return result["messages"][-1].content

if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("Please set OPENAI_API_KEY environment variable.")
        exit(1)

    user_id = "test_user_123"
    
    print("--- Session 1: Establishing Memory ---")
    print("User: I am researching sustainable architecture. I specifically care about mycelium bricks.")
    resp1 = run_conversation(user_id, "session_1", "I am researching sustainable architecture. I specifically care about mycelium bricks.")
    print(f"Agent: {resp1}\n")
    
    print("--- Session 2: Testing Cross-Session Recall ---")
    print("User: Based on my research interests, what should I look into next?")
    resp2 = run_conversation(user_id, "session_2", "Based on my research interests, what should I look into next?")
    print(f"Agent: {resp2}")
