from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from memanto.cli.client.sdk_client import SdkClient

AGENT_ID = "langgraph-memanto-permanent-brain"
sdk = SdkClient()

@tool
def store_memory(fact: str):
    """Store a piece of information for long-term recall across sessions."""
    return sdk.create_memory(agent_id=AGENT_ID, content=fact)

@tool
def retrieve_memory(query: str):
    """Retrieve relevant long-term memories based on a query."""
    return sdk.search_memories(agent_id=AGENT_ID, query=query)

tools = [store_memory, retrieve_memory]
model = ChatOpenAI(model="gpt-4o").bind_tools(tools)

class State(TypedDict):
    messages: Annotated[list, add_messages]

def call_model(state: State):
    response = model.invoke(state["messages"])
    return {"messages": [response]}

workflow = StateGraph(State)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools))
workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent", 
    lambda x: "tools" if x["messages"][-1].tool_calls else END
)
workflow.add_edge("tools", "agent")
app = workflow.compile()
