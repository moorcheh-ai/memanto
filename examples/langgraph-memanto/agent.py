from typing import Annotated, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph import MemantoSaver

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str

# --- Semantic Memory Toolkit ---
class MemantoToolkit:
    def __init__(self, agent_id: str):
        self.client = SdkClient()
        self.agent_id = agent_id

    def get_tools(self):
        @tool
        def store_user_preference(preference: str):
            """Store a permanent fact or preference about the user."""
            self.client.save_memory(self.agent_id, "user_prefs", preference)
            return "Preference saved to permanent brain."

        @tool
        def retrieve_user_preference(query: str):
            """Retrieve a permanent fact or preference about the user."""
            result = self.client.get_memory(self.agent_id, "user_prefs")
            return f"Found in memory: {result}" if result else "No relevant preference found."

        return [store_user_preference, retrieve_user_preference]

def create_graph(agent_id: str):
    llm = ChatOpenAI(model="gpt-4o")
    toolkit = MemantoToolkit(agent_id)
    tools = toolkit.get_tools()
    
    llm_with_tools = llm.bind_tools(tools)
    
    def call_model(state: AgentState):
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tools))
    
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", lambda x: "tools" if x["messages"][-1].tool_calls else END)
    workflow.add_edge("tools", "agent")
    
    # NATIVE PERSISTENCE: Memanto as the checkpointer
    memanto_saver = MemantoSaver(agent_id=agent_id)
    return workflow.compile(checkpointer=memanto_saver)
