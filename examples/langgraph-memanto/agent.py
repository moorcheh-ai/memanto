import os
from typing import Annotated, TypedDict, List
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage
from memanto.cli.client import MemantoClient

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_id: str
    session_id: str
    memories: str

client = MemantoClient()
llm = ChatOpenAI(model="gpt-4o")

def retrieve_memories(state: AgentState):
    user_id = state["user_id"]
    last_message = state["messages"][-1].content
    memories = client.search_memories(user_id=user_id, query=last_message)
    return {"memories": memories}

def call_model(state: AgentState):
    messages = state["messages"]
    memories = state["memories"]
    
    system_prompt = (
        "You are a personalized research assistant. "
        "Use the provided long-term memories to personalize your response. "
        f"Relevant Memories: {memories}"
    )
    
    prompt = [("system", system_prompt)]
    for m in messages:
        role = "user" if isinstance(m, HumanMessage) else "assistant"
        prompt.append((role, m.content))
    
    response = llm.invoke(prompt)
    return {"messages": [response]}

def store_memory(state: AgentState):
    user_id = state["user_id"]
    last_user_msg = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)
    if last_user_msg:
        client.store_memory(user_id=user_id, content=last_user_msg.content)
    return {"messages": []}

workflow = StateGraph(AgentState)
workflow.add_node("retrieve", retrieve_memories)
workflow.add_node("model", call_model)
workflow.add_node("store", store_memory)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "model")
workflow.add_edge("model", "store")
workflow.add_edge("store", END)

app = workflow.compile()
