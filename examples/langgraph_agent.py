"""
Example: LangGraph Agent with Memanto Long-Term Memory

This example demonstrates how to use Memanto as the persistent
memory layer for a LangGraph agent, enabling cross-session memory.
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, MessagesState
from memanto_langgraph import MemantoLangGraphMemory

# Initialize memory
memory = MemantoLangGraphMemory(
    api_key="your-memanto-api-key",
    base_url="http://localhost:8000",
)

# Initialize LLM
llm = ChatOpenAI(model="gpt-4")


def chat_node(state: MessagesState):
    """Chat node with memory-augmented context."""
    last_msg = state["messages"][-1].content
    context = memory.get_context_for_prompt(last_msg, top_k=3)

    system_prompt = f"""You are a helpful assistant.
{context}

Use the past context above to provide informed, consistent responses."""

    response = llm.invoke(
        [HumanMessage(content=f"{system_prompt}\n\nUser: {last_msg}")]
    )

    # Save to long-term memory
    memory.save_conversation(
        session_id=state.get("session_id", "default"),
        messages=[
            HumanMessage(content=last_msg),
            response,
        ],
    )

    return {"messages": [response]}


# Build graph
graph = StateGraph(MessagesState)
graph.add_node("chat", chat_node)
graph.set_entry_point("chat")
graph.set_finish_point("chat")
agent = graph.compile()


# Interactive loop
if __name__ == "__main__":
    session_id = "demo-session"
    print("Chat with memory-enabled agent (Ctrl+C to exit)")
    print("=" * 50)

    while True:
        user_input = input("You: ")
        result = agent.invoke({
            "messages": [HumanMessage(content=user_input)],
            "session_id": session_id,
        })
        print(f"Agent: {result['messages'][-1].content}")
