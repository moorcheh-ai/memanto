"""
LangGraph Research Assistant with Memanto Persistent Memory

This module defines a stateful research assistant graph that uses Memanto
as its long-term memory layer. The graph demonstrates cross-session recall
where memories from previous runs persist and can be retrieved.

Key features:
- Cross-session recall: memories from previous sessions are available
- Typed semantic memory: stores memories with types like fact, observation, decision
- Persistent context: graph state can incorporate retrieved memories
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel

from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI

from tools import MemantoSetup, create_memanto_tools


# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------


class AgentState(BaseModel):
    """State passed between nodes in the research assistant graph."""

    messages: list[str] = []
    query: str = ""
    research_topic: str = ""
    findings: list[str] = []
    memories_retrieved: list[dict] = []
    final_answer: str = ""
    recall_performed: bool = False


# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------


def recall_memories(state: AgentState, tools: dict) -> AgentState:
    """
    First node: recall any relevant memories from previous sessions.

    This demonstrates the cross-session recall capability - the agent
    retrieves memories stored in previous runs (even days ago).
    """
    messages = []

    # Check for prior memories about this topic
    recall_result = tools["recall"]._run(
        query=f"research findings about {state.research_topic}",
        limit=5,
        memory_types="observation,fact,learning",
    )

    if "Found" in recall_result and "memories" in recall_result:
        messages.append(f"[Prior Memories Retrieved]\n{recall_result}")

    # Also check for any preferences or context from past sessions
    context_result = tools["recall"]._run(
        query=f"user preferences research style context",
        limit=3,
        memory_types="preference,context",
    )

    if "Found" in context_result and "memories" in context_result:
        messages.append(f"[User Context Retrieved]\n{context_result}")

    return state.model_copy(
        update={
            "messages": messages,
            "memories_retrieved": [{"recall": recall_result}, {"context": context_result}],
            "recall_performed": True,
        }
    )


def conduct_research(state: AgentState, tools: dict, llm) -> AgentState:
    """
    Second node: conduct research using the LLM.

    If memories were found, use them as context to avoid redundant work.
    """
    context = ""
    if state.recall_performed and state.memories_retrieved:
        context = "\n\n[Prior Research Context]\n"
        for mem_data in state.memories_retrieved:
            for key, value in mem_data.items():
                if "Found" in value and "memories" in value:
                    context += value + "\n"

    system_prompt = f"""You are a research assistant. Your task is to gather and synthesize
information about the topic: {state.research_topic}

{context}

Provide a concise summary of key findings. Structure your response as:
1. Main points discovered
2. Any gaps or areas needing more research
3. Confidence level in findings

Be thorough but concise. If prior context was provided, build upon it and avoid repeating what's already known."""

    response = llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Research the following topic: {state.research_topic}"},
        ]
    )

    findings = response.content if hasattr(response, "content") else str(response)

    return state.model_copy(
        update={
            "findings": [findings],
            "messages": state.messages + [f"[Research Findings]\n{findings}"],
        }
    )


def store_findings(state: AgentState, tools: dict) -> AgentState:
    """
    Third node: store the research findings in Memanto for future sessions.

    This is the key to cross-session persistence - findings are saved
    so future runs can retrieve them.
    """
    findings_text = "\n".join(state.findings) if state.findings else ""

    if findings_text:
        # Store as observation type (derived from research)
        store_result = tools["remember"]._run(
            memory_type="observation",
            title=f"Research findings: {state.research_topic[:80]}",
            content=findings_text[:500],
            confidence=0.75,
            tags=f"research,{state.research_topic.lower().replace(' ', '-')[:30]}",
        )

        # Also store a key fact if significant findings
        if len(findings_text) > 100:
            key_fact = f"Key insight from researching '{state.research_topic}': {findings_text[:200]}..."
            tools["remember"]._run(
                memory_type="fact",
                title=f"Key fact: {state.research_topic[:80]}",
                content=key_fact[:500],
                confidence=0.7,
                tags="research,key-finding",
            )

        return state.model_copy(
            update={
                "messages": state.messages
                + [f"[Memory Stored]\nResearch findings saved to Memanto for future sessions."],
            }
        )

    return state


def answer_query(state: AgentState, tools: dict, llm) -> AgentState:
    """
    Fourth node: answer the user's query using research and memories.

    This uses Memanto's RAG capability (answer tool) to synthesize
    a grounded response from stored memories.
    """
    # First try to get a RAG-grounded answer
    answer_result = tools["answer"]._run(question=state.query)

    # Build final answer incorporating research and prior memories
    research_context = "\n".join(state.findings) if state.findings else "No new research conducted."

    messages = state.messages + [
        f"[Answer from Memanto RAG]\n{answer_result}",
    ]

    return state.model_copy(
        update={
            "final_answer": answer_result,
            "messages": messages,
        }
    )


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------


def build_research_graph(
    client,
    agent_id: str,
    llm=None,
):
    """
    Build and compile the research assistant graph.

    Args:
        client: Memanto SdkClient instance
        agent_id: Memanto agent ID for memory namespace
        llm: Language model (defaults to GPT-4o-mini via OpenAI)

    Returns:
        Compiled LangGraph for the research assistant
    """
    if llm is None:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

    tools = create_memanto_tools(client, agent_id)

    # Create the graph
    graph = StateGraph(AgentState)

    # Add nodes - wrap with partial to pass tools and llm
    graph.add_node(
        "recall_memories",
        lambda state: recall_memories(state, tools),
    )
    graph.add_node(
        "conduct_research",
        lambda state: conduct_research(state, tools, llm),
    )
    graph.add_node(
        "store_findings",
        lambda state: store_findings(state, tools),
    )
    graph.add_node(
        "answer_query",
        lambda state: answer_query(state, tools, llm),
    )

    # Define edges
    graph.add_edge(START, "recall_memories")
    graph.add_edge("recall_memories", "conduct_research")
    graph.add_edge("conduct_research", "store_findings")
    graph.add_edge("store_findings", "answer_query")
    graph.add_edge("answer_query", END)

    return graph.compile()