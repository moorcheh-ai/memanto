"""
LangGraph + Memanto: Agente con memoria persistente entre sesiones.
"""
import os
from langgraph.graph import StateGraph, MessagesState, END
from langchain_core.messages import HumanMessage, AIMessage
from memanto.cli.client.sdk_client import SdkClient

MOORCHEH_API_KEY = os.getenv("MOORCHEH_API_KEY")
AGENT_ID = "langgraph-demo-agent"

client = SdkClient(api_key=MOORCHEH_API_KEY)

def remember_node(state: MessagesState):
    last_msg = state["messages"][-1]
    if isinstance(last_msg, HumanMessage):
        client.remember(
            agent_id=AGENT_ID,
            content=last_msg.content,
            memory_type="fact"
        )
    return state

def recall_node(state: MessagesState):
    last_msg = state["messages"][-1]
    query = last_msg.content if isinstance(last_msg, HumanMessage) else ""
    memories = client.recall(agent_id=AGENT_ID, query=query, limit=3)
    context = "\n".join([m["content"] for m in memories]) if memories else "Sin memoria previa."
    response = f"Memoria recuperada: {context}"
    return {"messages": state["messages"] + [AIMessage(content=response)]}

builder = StateGraph(MessagesState)
builder.add_node("remember", remember_node)
builder.add_node("recall", recall_node)
builder.set_entry_point("remember")
builder.add_edge("remember", "recall")
builder.add_edge("recall", END)
graph = builder.compile()

if __name__ == "__main__":
    print("=== Sesion 1: guardando ===")
    graph.invoke({"messages": [HumanMessage(content="Mi color favorito es el azul.")]})
    print("=== Sesion 2: recordando ===")
    result = graph.invoke({"messages": [HumanMessage(content="Cual es mi color favorito?")]})
    print(result["messages"][-1].content)
