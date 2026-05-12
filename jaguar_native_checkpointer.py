import os
from langgraph.graph import StateGraph, MessagesState
from memanto_saver import MemantoSaver
from langchain_core.messages import HumanMessage

# Configuración de Capa 0 bajo SHA-713
api_key = os.getenv("MOORCHEH_API_KEY")
# El agent_id hereda la soberanía de Isabella y Giulia
saver = MemantoSaver(api_key=api_key, agent_id="jaguar-sovereign-001")

def jaguar_logic(state: MessagesState):
    return {"messages": [HumanMessage(content="Memoria SHA-713 Certificada por Jaguar-256.")]}

builder = StateGraph(MessagesState)
builder.add_node("jaguar_node", jaguar_logic)
builder.set_entry_point("jaguar_node")

# Compilación con persistencia oficial para el Bounty #397
graph = builder.compile(checkpointer=saver)

print("--- [JAGUAR] Protocolo SHA-713 Iniciado en Nodo GIANKOOF ---")
config = {"configurable": {"thread_id": "root-nexus-alpha"}}
graph.invoke({"messages": [HumanMessage(content="Ingesta de soberanía digital.")]}, config)
print("--- [JAGUAR] Estado persistido exitosamente en Moorcheh ---")
