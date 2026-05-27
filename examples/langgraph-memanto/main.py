from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointer
from memanto.cli.client.sdk_client import SdkClient

# Define a type-safe state
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str

def call_model(state: AgentState):
    # Logic for model call would go here
    return {"messages": [("assistant", "I have remembered your state via Memanto.")]}

# Setup Memanto Integration
AGENT_ID = "type_safe_agent_001"
sdk_client = SdkClient()
checkpointer = MemantoCheckpointer(agent_id=AGENT_ID, sdk_client=sdk_client)

# Build Graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_edge(START, "agent")
workflow.add_edge("agent", END)

# Compile with checkpointer for persistence
app = workflow.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    config = {"configurable": {"thread_id": "user_session_1"}}
    inputs = {"messages": [("user", "Hello Memanto")], "user_id": "user_123"}
    
    for event in app.stream(inputs, config=config):
        print(event)
