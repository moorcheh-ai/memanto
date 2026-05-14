import os
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, TypedDict

# Add integration path to sys.path for local testing
integration_path = str(Path(__file__).parent.parent / "langgraph")
if integration_path not in sys.path:
    sys.path.append(integration_path)

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from memanto_langgraph import MemantoSaver, create_memanto_tools

from memanto.cli.client.sdk_client import SdkClient

# 1. Setup Memanto Client
# Ensure you have MOORCHEH_API_KEY in your environment
api_key = os.getenv("MOORCHEH_API_KEY")
if not api_key:
    print("Warning: MOORCHEH_API_KEY not set. Using a dummy key for demonstration.")
    api_key = "mk_dummy_key"

client = SdkClient(api_key=api_key)
agent_id = "research-assistant-demo"


# 2. Define State
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]


# 3. Setup Tools
# Memanto tools allow the agent to explicitly store/recall long-term memories
memanto_tools = create_memanto_tools(client, agent_id)


# 4. Define the Graph
def call_model(state: AgentState):
    messages = state["messages"]
    # We provide a system message that encourages using Memanto for long-term storage
    system_message = SystemMessage(
        content=(
            "You are a Research Assistant with a 'Permanent Brain' powered by Memanto. "
            "When you learn something important about the user (preferences, facts, goals), "
            "use the 'memanto_remember' tool to save it for future sessions. "
            "At the start of a conversation, use 'memanto_recall' to see if you remember anything relevant about the user."
        )
    )
    llm = ChatOpenAI(model="gpt-4o")
    llm_with_tools = llm.bind_tools(memanto_tools)
    response = llm_with_tools.invoke([system_message] + messages)
    return {"messages": [response]}


# Define Tool Node
tool_node = ToolNode(memanto_tools)


# Define logic to decide whether to continue or end
def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


# Build the graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

# 5. Setup Memanto Checkpointer
# This gives the graph itself a persistent state in Memanto
checkpointer = MemantoSaver(client, agent_id)

# Compile the graph
app = workflow.compile(checkpointer=checkpointer)

# 6. Demonstration
if __name__ == "__main__":
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print(f"--- Starting session with thread_id: {thread_id} ---")

    # Day 1: Storing a memory
    inputs = {
        "messages": [
            HumanMessage(
                content="My name is Alice and I'm researching autonomous agent architectures. I prefer technical, dense explanations."
            )
        ]
    }
    for event in app.stream(inputs, config):
        for value in event.values():
            print(f"Agent: {value['messages'][-1].content}")

    print(
        "\n--- Session 1 Complete. The agent has stored Alice's name and preference in its 'Permanent Brain'. ---\n"
    )

    # Day 2: New Session, different thread, same Agent ID
    new_thread_id = str(uuid.uuid4())
    new_config = {"configurable": {"thread_id": new_thread_id}}

    print(f"--- Starting NEW session with thread_id: {new_thread_id} ---")
    inputs = {
        "messages": [
            HumanMessage(
                content="Hey there! Do you remember who I am and what I'm working on?"
            )
        ]
    }

    # The agent will use memanto_recall to find Alice's info across threads
    for event in app.stream(inputs, new_config):
        for value in event.values():
            if value["messages"][-1].content:
                print(f"Agent: {value['messages'][-1].content}")
