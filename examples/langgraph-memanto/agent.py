"""
LangGraph + Memanto: Persistent Memory Research Assistant

A LangGraph workflow that uses Memanto for cross-session memory.
The agent remembers past conversations, user preferences, and key facts.
"""

from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import os
from dotenv import load_dotenv

from memanto_tools import remember, recall

load_dotenv()

# --- State ---

class AgentState(TypedDict):
    messages: list  # Conversation history
    user_input: str
    recalled_memories: str
    final_response: str


# --- Graph Nodes ---

def recall_memories(state: AgentState) -> dict:
    """Retrieve relevant memories from Memanto before responding."""
    query = state["user_input"]
    memories = recall(query, limit=5)
    return {"recalled_memories": memories}


def generate_response(state: AgentState) -> dict:
    """Generate response using LLM + recalled memories."""
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_api_base=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        temperature=0.7,
    )

    memories = state["recalled_memories"]
    user_input = state["user_input"]

    system = SystemMessage(
        content=f"""You are a research assistant with persistent memory.
Before answering, consider the following past memories:

{memories}

Use these memories to provide context-aware responses.
If the user mentions something they discussed before, acknowledge it.
If no relevant memories exist, answer normally."""
    )

    history = state.get("messages", [])
    messages = [system] + history + [HumanMessage(content=user_input)]

    response = llm.invoke(messages)
    return {"final_response": response.content, "messages": history + [
        HumanMessage(content=user_input),
        AIMessage(content=response.content),
    ]}


def store_memory(state: AgentState) -> dict:
    """Store the interaction as a memory in Memanto."""
    user_input = state["user_input"]
    response = state["final_response"]

    remember(
        content=f"User asked: {user_input[:100]}. I responded: {response[:150]}",
        memory_type="conversation",
        tags=["langgraph", "research-assistant"],
    )
    return {}


def should_continue(state: AgentState) -> Literal["store", END]:
    """Decide next step."""
    return "store"


# --- Build Graph ---

workflow = StateGraph(AgentState)

workflow.add_node("recall", recall_memories)
workflow.add_node("generate", generate_response)
workflow.add_node("store", store_memory)

workflow.set_entry_point("recall")
workflow.add_edge("recall", "generate")
workflow.add_conditional_edges("generate", should_continue)
workflow.add_edge("store", END)

app = workflow.compile()


def chat(user_input: str, messages: list | None = None) -> str:
    """Run the LangGraph agent with Memanto memory."""
    if messages is None:
        messages = []

    result = app.invoke({
        "user_input": user_input,
        "messages": messages,
        "recalled_memories": "",
        "final_response": "",
    })

    return result["final_response"], result["messages"]


# --- CLI Demo ---

def main():
    print("=" * 60)
    print("🧠 LangGraph + Memanto: Research Assistant")
    print("Memories persist across sessions! Try: 'what did we discuss last time?'")
    print("Type 'exit' to quit.")
    print("=" * 60)

    messages = []
    while True:
        user_input = input("\n👤 You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            print("👋 Bye! Memories saved in Memanto.")
            break

        response, messages = chat(user_input, messages)
        print(f"\n🤖 Assistant: {response}")


if __name__ == "__main__":
    main()
