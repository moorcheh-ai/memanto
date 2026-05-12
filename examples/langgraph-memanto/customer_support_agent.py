"""Customer Support Agent with Memanto Long-Term Memory.

This agent demonstrates how LangGraph + Memanto enables
persistent customer context across disjointed support sessions.
"""

from __future__ import annotations

import os
from typing import TypedDict, Annotated, Sequence

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from memanto_memory import LangGraphMemantoMemory


class SupportState(TypedDict):
    """LangGraph state with Memanto integration."""
    messages: Annotated[Sequence, "Chat history"]
    user_id: str
    context: str
    action: str


def create_support_agent():
    """Create a customer support agent with persistent memory."""
    
    # Initialize Memanto memory layer
    memory = LangGraphMemantoMemory(agent_id="customer-support")
    
    # Initialize LLM (works with any OpenAI-compatible provider)
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY", "dummy-key"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    
    def retrieve_context(state: SupportState) -> SupportState:
        """Node 1: Retrieve relevant memories from Memanto."""
        user_id = state["user_id"]
        last_message = ""
        for msg in reversed(state["messages"]):
            if msg.get("role") == "user":
                last_message = msg.get("content", "")
                break
        
        # Query Memanto for user context
        query = f"User {user_id}: {last_message}"
        context = memory.get_context_for_llm(query, top_k=5)
        
        # Store this interaction as observation
        if last_message:
            memory.remember(
                content=f"User {user_id} said: {last_message}",
                memory_type="event",
                tags=["interaction", user_id]
            )
        
        return {**state, "context": context}
    
    def generate_response(state: SupportState) -> SupportState:
        """Node 2: Generate response using LLM + Memanto context."""
        
        system_prompt = """You are a helpful customer support agent with perfect memory.
        
CRITICAL INSTRUCTIONS:
1. Use the provided MEMORIES to personalize your response
2. If the user has reported an issue before, acknowledge it
3. If they have preferences, respect them
4. Be concise but warm"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": state["context"]},
            *[
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in state["messages"]
            ]
        ]
        
        response = llm.invoke(messages)
        
        # Store agent decision
        memory.remember(
            content=f"Agent responded to {state['user_id']}: {response.content}",
            memory_type="decision",
            tags=["response", state["user_id"]]
        )
        
        return {
            **state,
            "messages": list(state["messages"]) + [
                {"role": "assistant", "content": response.content}
            ]
        }
    
    def extract_and_store(state: SupportState) -> SupportState:
        """Node 3: Extract key facts and store them."""
        
        last_user_msg = ""
        for msg in reversed(state["messages"]):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break
        
        # Store preferences
        if any(w in last_user_msg.lower() for w in ["prefer", "like", "want", "need"]):
            memory.remember(
                content=f"User {state['user_id']} preference: {last_user_msg}",
                memory_type="decision",
                confidence=0.85,
                tags=["preference", state["user_id"]]
            )
        
        # Store issues
        if any(w in last_user_msg.lower() for w in ["bug", "error", "issue", "problem", "broken", "not working"]):
            memory.remember(
                content=f"User {state['user_id']} issue: {last_user_msg}",
                memory_type="fact",
                confidence=0.95,
                tags=["issue", state["user_id"]]
            )
        
        return state
    
    # Build graph
    workflow = StateGraph(SupportState)
    workflow.add_node("retrieve", retrieve_context)
    workflow.add_node("respond", generate_response)
    workflow.add_node("extract", extract_and_store)
    
    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "respond")
    workflow.add_edge("respond", "extract")
    workflow.add_edge("extract", END)
    
    return workflow.compile(checkpointer=MemorySaver())


def demo():
    """Run interactive demo."""
    print("=" * 60)
    print("🧠 LangGraph + Memanto: Persistent Customer Support Agent")
    print("=" * 60)
    print()
    print("This agent remembers your preferences and past issues")
    print("across sessions using Memanto's long-term memory.")
    print()
    
    agent = create_support_agent()
    user_id = "demo-user-001"
    
    # Simulate conversation
    test_inputs = [
        "Hi, I'm having trouble logging in. I prefer email notifications.",
        "It's still not working. I tried resetting my password.",
        "Yes, I use the Pro plan.",
    ]
    
    for i, user_input in enumerate(test_inputs, 1):
        print(f"\n--- Turn {i} ---")
        print(f"User: {user_input}")
        
        result = agent.invoke(
            {
                "messages": [{"role": "user", "content": user_input}],
                "user_id": user_id,
                "context": "",
                "action": ""
            },
            config={"configurable": {"thread_id": f"session-{i}"}}
        )
        
        assistant_msg = result["messages"][-1]["content"]
        print(f"Agent: {assistant_msg}")
    
    print("\n" + "=" * 60)
    print("✅ Demo complete! Memories persisted in Memanto.")
    print("   Run again with same user_id to see memory recall.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
