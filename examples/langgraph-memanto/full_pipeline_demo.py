import os
import uuid
from typing import Annotated, TypedDict, Literal
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_checkpoint import MemantoCheckpointSaver

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], "The conversation history"]
    next_step: str

class MemoryFact(BaseModel):
    fact: str = Field(description="The specific factual information to remember")
    category: str = Field(description="The category for the memory")

@tool
def remember_fact(fact_details: MemoryFact):
    """Saves a factual piece of information to long-term semantic memory."""
    client = SdkClient()
    agent_id = "global_brain_v1"
    client.save_memory(
        namespace=agent_id,
        key=str(uuid.uuid4()),
        value=fact_details.model_dump_json()
    )
    return "Information committed to permanent brain."

@tool
def recall_facts(query: str):
    """Retrieves relevant factual information from long-term semantic memory."""
    client = SdkClient()
    agent_id = "global_brain_v1"
    memories = client.list_memories(namespace=agent_id)
    
    relevant = [m["value"] for m in memories if query.lower() in m["value"].lower()]
    if not relevant:
        return "No relevant memories found."
    return f"Recalled information: {relevant}"

def supervisor_node(state: AgentState):
    llm = ChatOpenAI(model="gpt-4-turbo").bind_tools([remember_fact, recall_facts])
    response = llm.invoke([SystemMessage(content="You are the supervisor. Use tools to remember or recall facts."), *state["messages"]])
    
    if response.tool_calls:
        return {"messages": [response], "next_step": "tools"}
    return {"messages": [response], "next_step": END}

def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("tools", ToolNode([remember_fact, recall_facts]))
    
    builder.set_entry_point("supervisor")
    builder.add_edge("tools", "supervisor")
    builder.add_conditional_edges("supervisor", lambda x: x["next_step"])
    
    client = SdkClient()
    checkpoint_saver = MemantoCheckpointSaver(sdk_client=client)
    return builder.compile(checkpointer=checkpoint_saver)

def run_session(thread_id: str, user_input: str):
    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"\n--- Session Start (Thread: {thread_id}) ---")
    print(f"Input: {user_input}")
    
    for event in graph.stream({"messages": [HumanMessage(content=user_input)]}, config):
        for value in event.values():
            if "messages" in value:
                last_msg = value["messages"][-1]
                if hasattr(last_msg, "content") and last_msg.content:
                    print(f"Agent: {last_msg.content}")

if __name__ == "__main__":
    shared_thread_id = "user_123_persistent_session"
    
    print("SCENARIO: Yesterday vs Today")
    
    print("\n[DAY 1: Teaching the agent]")
    run_session(shared_thread_id, "My favorite color is Obsidian Blue and I live in Neo-Tokyo.")
    
    print("\n[DAY 2: New Process, Same Thread, Different Interaction]")
    # We simulate a new process by calling run_session again with the same thread_id
    # The BaseCheckpointSaver will restore the graph state, 
    # while remember_fact tool provides the semantic layer.
    run_session(shared_thread_id, "Do you remember my favorite color and where I live?")
