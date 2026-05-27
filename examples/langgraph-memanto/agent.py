from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from integrations.langgraph.memanto_manager import MemantoGraphManager

# Type-safe state definition
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str
    context_summary: str

# Define bound tools using SdkClient
def create_memanto_tools(sdk_client):
    @tool
    def store_user_preference(preference: str, user_id: str):
        """Store a specific user preference in long-term memory."""
        sdk_client.write_memory(
            agent_id="USER_PROFILES",
            session_id=user_id,
            content=preference
        )
        return f"Preference stored for {user_id}"

    @tool
    def recall_user_preference(user_id: str):
        """Recall user preferences from long-term memory."""
        memories = sdk_client.read_memory(
            agent_id="USER_PROFILES",
            session_id=user_id
        )
        return memories[0].content if memories else "No preferences found."

    return [store_user_preference, recall_user_preference]

def call_model(state: AgentState, config):
    # Mock model logic to demonstrate state transition
    last_message = state["messages"][-1]
    return {"messages": [("assistant", f"Processed: {last_message.content}")]}

def create_graph(manager: MemantoGraphManager):
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", call_model)
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)
    
    # Integrate the type-safe checkpointer
    return workflow.compile(checkpointer=manager.get_checkpointer())
