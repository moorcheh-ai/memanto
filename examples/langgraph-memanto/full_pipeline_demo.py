from agent import app
from langchain_core.messages import HumanMessage
import os

def test_cross_session_recall():
    # Session 1: Ingesting information
    print("--- Session 1: Learning User Preferences ---")
    input_1 = "My name is Alice and I love hiking in the Swiss Alps."
    res_1 = app.invoke({"messages": [HumanMessage(content=input_1)]})
    print(f"Session 1 Response: {res_1['messages'][-1].content}")

    # Session 2: Recalling information in a fresh state
    print("\n--- Session 2: Recalling from Long-Term Memory ---")
    input_2 = "Where do I love hiking?"
    res_2 = app.invoke({"messages": [HumanMessage(content=input_2)]})
    print(f"Session 2 Response: {res_2['messages'][-1].content}")

    if "Swiss Alps" in res_2['messages'][-1].content:
        print("\n✅ Success: Cross-session recall verified via Memanto.")
    else:
        print("\n❌ Failure: Agent failed to recall the memory.")

if __name__ == "__main__":
    test_cross_session_recall()
