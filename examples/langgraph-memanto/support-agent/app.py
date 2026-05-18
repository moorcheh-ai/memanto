import os
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
# Mock Memanto client
class MemantoClient:
    def __init__(self):
        self.memory = {}
    def store(self, user_id, key, value):
        if user_id not in self.memory:
            self.memory[user_id] = {}
        self.memory[user_id][key] = value
    def retrieve(self, user_id, key):
        return self.memory.get(user_id, {}).get(key, None)

memanto = MemantoClient()
llm = ChatOpenAI(model="gpt-3.5-turbo")

class State(TypedDict):
    messages: list
    user_id: str
    user_profile: dict

def recall_memory(state: State):
    profile = memanto.retrieve(state["user_id"], "profile")
    return {"user_profile": profile or {}}

def process_chat(state: State):
    context = f"User Profile: {state['user_profile']}\n"
    response = llm.invoke(context + state["messages"][-1].content)
    return {"messages": [response]}

def update_memory(state: State):
    # Logic to extract new preferences from the last message and store in Memanto
    # (Mocked for example)
    memanto.store(state["user_id"], "profile", {"tier": "premium", "issue": "billing"})
    return {}

builder = StateGraph(State)
builder.add_node("recall", recall_memory)
builder.add_node("chat", process_chat)
builder.add_node("store", update_memory)

builder.add_edge(START, "recall")
builder.add_edge("recall", "chat")
builder.add_edge("chat", "store")
builder.add_edge("store", END)
graph = builder.compile()
