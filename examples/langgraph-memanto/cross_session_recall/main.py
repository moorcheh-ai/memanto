import os

from cross_session_recall.graph import create_research_graph
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph_memanto import create_memanto_tools

from memanto.cli.client.sdk_client import SdkClient


def run_session(agent_id, user_id, task, thread_id):
    load_dotenv()

    api_key = os.getenv("MOORCHEH_API_KEY")
    if not api_key:
        print("Please set MOORCHEH_API_KEY in .env")
        return

    client = SdkClient(api_key=api_key)

    tools = create_memanto_tools(client, agent_id)
    app = create_research_graph("poolside/laguna-xs.2:free", tools)

    config = {"configurable": {"thread_id": thread_id}}

    print(f"\n--- Session for {user_id} (Thread: {thread_id}) ---")
    print(f"Task: {task}")

    events = app.stream(
        {"messages": [HumanMessage(content=task)]}, config, stream_mode="values"
    )

    for event in events:
        if "messages" in event:
            event["messages"][-1].pretty_print()


def main():
    agent_id = "langgraph-researcher-001"
    user_id = "user-123"

    task1 = (
        "Research the top 3 benefits of using Memanto for AI agents. "
        "Store each benefit as a 'fact' in your memory with tags 'memanto,benefits'. "
        "Be specific and concise."
    )

    # Note: Each run_session call creates a completely fresh in-memory MemorySaver
    # using a distinct thread_id. LangGraph's checkpointer carries nothing between
    # the two sessions. The cross-session recall demonstrated here works because
    # the Memanto tools query a shared global store based on the agent_id.
    run_session(agent_id, user_id, task1, thread_id="session-1")

    task2 = (
        "I'm writing a report about Memanto. What were those 3 benefits you found earlier? "
        "Use your memory to recall them."
    )

    run_session(agent_id, user_id, task2, thread_id="session-2")


if __name__ == "__main__":
    main()
