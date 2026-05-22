#!/usr/bin/env python3
"""
ReAct Agent Demo: Use Memanto tools with a LangGraph ReAct agent.

This demonstrates using Memanto tools as regular LangChain tools
in a LangGraph prebuilt ReAct agent, where the LLM decides which
tool to call based on the user query.

Usage:
    python run_react_agent.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph_memanto import MemantoSetup, create_memanto_tools


def main():
    print("
" + "=" * 60)
    print("  LangGraph ReAct Agent with Memanto Memory")
    print("=" * 60 + "
")

    # Setup
    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    if not api_key:
        print("ERROR: MOORCHEH_API_KEY not set")
        return

    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(agent_id="react-agent-demo", pattern="tool")
    tools = create_memanto_tools(client, agent_id="react-agent-demo")

    # Create ReAct agent with Memanto tools
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    agent = create_react_agent(llm, list(tools.values()))

    print("ReAct agent ready! Type queries (Ctrl+C to exit):
")

    while True:
        try:
            query = input("> ").strip()
            if not query:
                continue

            result = agent.invoke({"messages": [{"role": "user", "content": query}]})

            # Extract the final AI message
            messages = result.get("messages", [])
            if messages:
                final = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
                print(f"
{final}
")

        except (KeyboardInterrupt, EOFError):
            print("
Goodbye!")
            break

    setup.teardown("react-agent-demo")


if __name__ == "__main__":
    main()
