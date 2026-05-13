import os
from typing import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from memanto.cli.client.sdk_client import SdkClient
from memanto_langgraph.tools import create_memanto_tools

# State definition
class State(TypedDict):
    # The messages list will be updated by adding new messages
    messages: Annotated[list[BaseMessage], lambda x, y: x + y]

def create_memanto_agent(agent_id: str):
    """
    Creates a LangGraph agent equipped with Memanto long-term memory tools.
    
    Args:
        agent_id: The unique identifier for the Memanto agent. 
                 This ID is used to scope the persistent memory.
    """
    # 1. Initialize Memanto Client
    api_key = os.getenv("MOORCHEH_API_KEY")
    if not api_key:
        raise ValueError("MOORCHEH_API_KEY not found in environment")
    
    client = SdkClient(api_key=api_key)
    
    # Ensure agent exists and activate session
    # In a real app, you might do this once during user onboarding
    try:
        client.create_agent(
            agent_id=agent_id,
            pattern="tool",
            description="A LangGraph agent with long-term memory"
        )
    except Exception:
        # Agent likely already exists, which is fine
        pass
    
    # Activate the session for this agent
    client.activate_agent(agent_id)
    
    # 2. Setup Memanto Tools for LangChain
    # This helper creates MemantoRememberTool, MemantoRecallTool, and MemantoAnswerTool
    tools = create_memanto_tools(client, agent_id)
    tool_node = ToolNode(tools)
    
    # 3. Setup LLM with tools
    # Using GPT-4 for reliable tool calling
    llm = ChatOpenAI(model="gpt-4-turbo-preview").bind_tools(tools)
    
    # 4. Define Graph Nodes
    
    def call_model(state: State):
        """The primary node that calls the LLM."""
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: State):
        """Determines if the graph should go to tools or end."""
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    # 5. Build Graph
    workflow = StateGraph(State)
    
    # Add the two main nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    
    # Set the entry point
    workflow.set_entry_point("agent")
    
    # Add conditional edge: agent -> tools OR agent -> END
    workflow.add_conditional_edges("agent", should_continue)
    
    # Add edge: tools -> agent (to process tool output)
    workflow.add_edge("tools", "agent")
    
    # Compile the graph
    return workflow.compile()
