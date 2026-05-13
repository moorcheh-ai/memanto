import os
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from memanto import Memanto

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str
    context: str

llm = ChatOpenAI(model="gpt-4o")
memory = Memanto()

def retrieve_memory(state: AgentState):
    user_id = state["user_id"]
    query = state["messages"][-1].content
    memories = memory.retrieve(user_id, query)
    context = "\n".join(memories) if memories else "No prior memories found."
    return {"context": context}

def call_model(state: AgentState):
    system_prompt = f"You are a helpful assistant. Use the provided context to personalize your response.\n\nContext:\n{state['context']}"
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}

def store_memory(state: AgentState):
    user_id = state["user_id"]
    last_message = state["messages"][-1].content
    
    extraction_prompt = f"Extract a concise fact about the user from this message: '{last_message}'. If no fact is present, reply 'NONE'."
    fact = llm.invoke(extraction_prompt).content
    
    if "NONE" not in fact.upper():
        memory.store(user_id, fact)
    
    return state

workflow = StateGraph(AgentState)
workflow.add_node("retrieve", retrieve_memory)
workflow.add_node("model", call_model)
workflow.add_node("store", store_memory)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "model")
workflow.add_edge("model", "store")
workflow.add_edge("store", END)

app = workflow.compile()
