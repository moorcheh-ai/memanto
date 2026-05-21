import os
from typing import Annotated, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from memanto.cli.client.sdk_client import SdkClient

# Global Config
AGENT_ID = os.getenv("MEMANTO_AGENT_ID", "langgraph-permanent-brain-001")
sdk = SdkClient()

@tool
def recall_memory(query: str):
    """Recall specific historical facts about the user or previous interactions."""
    results = sdk.search(agent_id=AGENT_ID, query=query)
    return results

@tool
def remember_fact(fact: str):
    """Persist a new fact or preference to long-term memory."""
    sdk.store(agent_id=AGENT_ID, key=f"fact_{hash(fact)}", value=fact)
    return "Fact stored in permanent memory."

class AgentState(TypedDict):
    messages: Annotated[list, "The conversation history"]
    memory_extracted: bool

tools = [recall_memory, remember_fact]
tool_node = ToolNode(tools)
model = ChatOpenAI(model="gpt-4-turbo").bind_tools(tools)

def call_model(state: AgentState):
    response = model.invoke(state["messages"])
    return {"messages": [response]}

def memory_classifier(state: AgentState):
    # Determine if the last message contains a fact worth persisting
    last_msg = state["messages"][-1].content
    if "remember" in last_msg.lower() or "I like" in last_msg:
        return "tools"
    return END

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.set_entry_point("agent")
workflow.add_edge("agent", "tools")
workflow.add_edge("tools", "agent")

# This allows the LLM to decide if we loop back or end
# based on the memory classification logic
# In a full pipeline, this would be a conditional edge
