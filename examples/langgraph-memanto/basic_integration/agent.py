from typing import Annotated

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict


class State(TypedDict):
    messages: Annotated[list, add_messages]


def build_graph(tools: list[callable]):
    """
    Builds the LangGraph state graph for the agent.
    """
    # Using a fast and capable model
    import os

    llm = ChatOpenAI(
        model=os.environ.get("LLM_MODEL", "openai/gpt-4o-mini"),
        temperature=0,
        api_key=os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_API_BASE", "https://openrouter.ai/api/v1"),
    )
    llm_with_tools = llm.bind_tools(tools)

    def chatbot(state: State):
        sys_msg = SystemMessage(
            content=(
                "You are an intelligent personal assistant equipped with a persistent memory. "
                "You have two special tools: memanto_remember and memanto_recall. "
                "1. When the user tells you personal facts, preferences, or important instructions, ALWAYS use 'memanto_remember' to save them. "
                "2. When the user asks you a question that might require past context, ALWAYS use 'memanto_recall' to search your memory first. "
                "Do not hallucinate facts about the user. Rely on your long-term memory."
            )
        )
        messages = [sys_msg] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    graph_builder = StateGraph(State)
    graph_builder.add_node("chatbot", chatbot)

    tool_node = ToolNode(tools=tools)
    graph_builder.add_node("tools", tool_node)

    graph_builder.add_conditional_edges("chatbot", tools_condition)
    graph_builder.add_edge("tools", "chatbot")
    graph_builder.add_edge(START, "chatbot")

    return graph_builder.compile()
