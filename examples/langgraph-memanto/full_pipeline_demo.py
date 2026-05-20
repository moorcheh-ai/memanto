import asyncio
import os
from agent import MemantoBrain, create_graph

async def run_session(session_id: str, user_input: str, api_key: str, agent_id: str):
    print(f"--- Starting Session {session_id} ---")
    brain = MemantoBrain(api_key, agent_id)
    graph = create_graph(brain)
    
    inputs = {"messages": [{"role": "user", "content": user_input}], "user_id": "user_123", "memories": []}
    result = await graph.ainvoke(inputs)
    print(f"Response: {result['messages'][-1].content}\n")

async def main():
    api_key = os.getenv("MEMANTO_API_KEY")
    agent_id = "architect_demo_agent_001"
    
    if not api_key:
        print("Missing MEMANTO_API_KEY")
        return

    # Session 1: Ingest a fact
    await run_session("1", "My favorite color is Obsidian Blue.", api_key, agent_id)
    
    print("!!! SIMULATING PROCESS KILL / SESSION RESET !!!\n")
    
    # Session 2: Recall the fact in a fresh environment
    await run_session("2", "Do you remember my favorite color?", api_key, agent_id)

if __name__ == "__main__":
    asyncio.run(main())
