import os
import subprocess
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

# ==========================================
# Memanto Tools for Long-Term Memory
# ==========================================

@tool
def remember(memory_type: str, content: str) -> str:
    """
    Store a piece of information into the agent's long-term memory.
    Use this when the user tells you a fact, preference, or goal that should be remembered for future sessions.
    Valid memory types: fact, preference, goal, instruction.
    """
    try:
        # We use the CLI to seamlessly integrate with the configured Memanto session
        result = subprocess.run(
            ["memanto", "remember", content, "--type", memory_type],
            capture_output=True,
            text=True,
            check=True
        )
        return f"Successfully remembered: {content}"
    except subprocess.CalledProcessError as e:
        return f"Failed to remember. Error: {e.stderr}"

@tool
def recall(query: str) -> str:
    """
    Search the agent's long-term memory for information relevant to the user's query.
    Use this to retrieve past context, preferences, or facts from previous sessions before answering.
    """
    try:
        result = subprocess.run(
            ["memanto", "recall", query],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Failed to recall. Error: {e.stderr}"

tools = [remember, recall]
tool_node = ToolNode(tools)

# ==========================================
# LangGraph Agent Setup
# ==========================================

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda a, b: a + b]

# Initialize the LLM with tools
# Ensure OPENAI_API_KEY is set in your environment
llm = ChatOpenAI(model="gpt-4o", temperature=0)
llm_with_tools = llm.bind_tools(tools)

def agent_node(state: AgentState):
    """The main reasoning node of the agent."""
    messages = state["messages"]
    
    # Inject a system prompt if it's the start of the conversation
    if not any(isinstance(m, SystemMessage) for m in messages):
        sys_msg = SystemMessage(content=(
            "You are a helpful AI assistant equipped with a permanent memory (Memanto). "
            "If the user asks you something about their past or preferences, use the `recall` tool. "
            "If the user shares new facts, preferences, or instructions, use the `remember` tool to store it permanently."
        ))
        messages = [sys_msg] + list(messages)
        
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState) -> str:
    """Determine if we need to call tools or finish."""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

# Build the graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")

app = workflow.compile()

# ==========================================
# Demonstration: Cross-Session Recall
# ==========================================

if __name__ == "__main__":
    print("\n=== Memanto + LangGraph Integration Demo ===\n")
    print("Initializing agent... (Make sure you have run `memanto agent create demo-agent` and activated it)")
    
    # Session 1: The user tells the agent a preference
    print("\n--- Session 1: Storing a Memory ---")
    session1_input = "Hi! I just wanted to let you know that my favorite color is crimson red and I prefer very short answers."
    print(f"User: {session1_input}")
    
    state1 = {"messages": [HumanMessage(content=session1_input)]}
    for event in app.stream(state1):
        for key, value in event.items():
            if key == "agent" and not value["messages"][-1].tool_calls:
                print(f"Agent: {value['messages'][-1].content}")
                
    # Simulate a completely new session (LangGraph state is reset)
    print("\n--- Session 2: Cross-Session Recall ---")
    print("(LangGraph state has been completely cleared)")
    session2_input = "What is my favorite color? And please answer according to my preferences."
    print(f"User: {session2_input}")
    
    state2 = {"messages": [HumanMessage(content=session2_input)]}
    for event in app.stream(state2):
        for key, value in event.items():
            if key == "agent" and not value["messages"][-1].tool_calls:
                print(f"Agent: {value['messages'][-1].content}")
