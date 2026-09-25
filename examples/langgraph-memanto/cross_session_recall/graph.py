from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from orcarouter_llm import build_orcarouter_llm, orcarouter_configured


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def create_research_graph(model_name: str, tools: list):
    # When OrcaRouter is configured, its smart-routing model is used
    # regardless of the explicit OpenRouter model id passed by the caller.
    llm = build_orcarouter_llm(model=None if orcarouter_configured() else model_name)
    llm_with_tools = llm.bind_tools(tools)

    def chatbot(state: State):
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    workflow = StateGraph(State)
    workflow.add_node("chatbot", chatbot)

    tool_node = ToolNode(tools=tools)
    workflow.add_node("tools", tool_node)

    workflow.add_conditional_edges(
        "chatbot",
        tools_condition,
    )
    workflow.add_edge("tools", "chatbot")
    workflow.add_edge(START, "chatbot")

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
