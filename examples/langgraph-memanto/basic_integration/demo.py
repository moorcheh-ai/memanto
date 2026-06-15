import os
import sys
import time
import uuid
import warnings

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph_memanto import create_memanto_tools

from basic_integration.agent import build_graph
from memanto.cli.client.sdk_client import SdkClient

warnings.filterwarnings("ignore", module="langgraph")


def main():
    load_dotenv()

    print("\n" + "=" * 60)
    print("🚀 Initializing Memanto + LangGraph Integration Demo...")
    print("=" * 60 + "\n")

    if not os.getenv("MOORCHEH_API_KEY"):
        print("❌ Error: MOORCHEH_API_KEY environment variable is missing.")
        print("Please set it: export MOORCHEH_API_KEY='your_key'")
        sys.exit(1)

    if not os.getenv("OPENAI_API_KEY") and not os.getenv("OPENROUTER_API_KEY"):
        print(
            "❌ Error: OPENAI_API_KEY or OPENROUTER_API_KEY environment variable is missing."
        )
        print("Please set one: export OPENROUTER_API_KEY='your_key'")
        sys.exit(1)

    # Initialize Memanto Client
    client = SdkClient(api_key=os.environ["MOORCHEH_API_KEY"])
    agent_id = f"langgraph-demo-{uuid.uuid4().hex[:6]}"

    tools = create_memanto_tools(client, agent_id)
    graph = build_graph(tools)

    # ---------------------------------------------------------
    # SESSION 1
    # ---------------------------------------------------------
    print("\n" + "-" * 50)
    print(" 🌙 SESSION 1: The User Provides Information")
    print("-" * 50)

    session1_input = "Hi! I'm Alice. I'm a big fan of cyberpunk aesthetics and my favorite framework is LangGraph."
    print(f"User: {session1_input}\n")

    state1 = {"messages": [HumanMessage(content=session1_input)]}
    for event in graph.stream(state1, stream_mode="values"):
        message = event["messages"][-1]
        if message.type == "ai" and message.content:
            print(f"🤖 Agent (Session 1): {message.content}")

    print("\n[The LangGraph state is completely cleared. Simulating a new day...]")
    time.sleep(2)

    # ---------------------------------------------------------
    # SESSION 2
    # ---------------------------------------------------------
    print("\n" + "-" * 50)
    print(" ☀️ SESSION 2: Cross-Session Recall")
    print("-" * 50)

    session2_input = (
        "Hi again! What is my name and what kind of UI theme should you build for me?"
    )
    print(f"User: {session2_input}\n")

    # Completely new state! No memory in LangGraph messages.
    state2 = {"messages": [HumanMessage(content=session2_input)]}
    for event in graph.stream(state2, stream_mode="values"):
        message = event["messages"][-1]
        if message.type == "ai" and message.content:
            print(f"🤖 Agent (Session 2): {message.content}")

    print("\n" + "=" * 60)
    print(
        "✅ Demo complete. The agent successfully recalled cross-session memory using Memanto!"
    )
    print("=" * 60 + "\n")

    # Cleanup
    try:
        client.delete_agent(agent_id=agent_id)
        print("[*] Cleaned up temporary agent.")
    except Exception:
        pass


if __name__ == "__main__":
    main()
