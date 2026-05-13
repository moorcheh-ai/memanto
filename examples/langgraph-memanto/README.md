# Memanto + LangGraph: Give Your Graph a Permanent Brain 🧠

This example demonstrates how to integrate **Memanto** as the long-term memory layer for a **LangGraph** agent.

While LangGraph excels at managing state within a single thread or session, Memanto provides a persistent, semantic memory database that allows agents to remember information across disjointed sessions, different agents, and long periods of time.

## 🚀 Why Memanto for LangGraph?

1.  **Cross-Session Recall**: Your agent remembers a preference or a fact from "yesterday" even if the LangGraph state was cleared.
2.  **Semantic RAG**: Use the `memanto_answer` tool to get AI-generated answers grounded in the agent's entire memory history.
3.  **Typed Memories**: Store structured information like `decisions`, `goals`, and `preferences` for more precise retrieval.

## 🛠️ Setup

1.  **Install dependencies**:
    