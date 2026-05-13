import os
import sys
import uuid
import time
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

# Add integrations/langgraph to path so we can import memanto_langgraph
# This allows the example to run without needing to install the package first
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../integrations/langgraph")))

# Now we can import the agent factory
from agent import create_memanto_agent

load_dotenv()

def run_session(agent_id: str, query: str, session_num: int):
    """Run a single interaction with a brand new agent instance."""
    print(f"\n{'='*60}")
    print(f" SESSION {session_num}")
    print(f" User Query: {query}")
    print(f"{'='*60}")
    
    # We create a FRESH agent instance here. 
    # It has NO local history or memory of previous sessions.
    agent = create_memanto_agent(agent_id)
    
    # Standard LangGraph config
    config = {"configurable": {"thread_id": f"session-{session_num}"}}
    inputs = {"messages": [HumanMessage(content=query)]}
    
    last_response = ""
    
    # Stream the graph execution
    for event in agent.stream(inputs, config=config, stream_mode="values"):
        for message in event.get("messages", []):
            if message.content and hasattr(message, 'tool_calls') and not message.tool_calls:
                # This is a final response from the agent node
                last_response = message.content
            elif message.content and not hasattr(message, 'tool_calls'):
                # This is likely the user message or tool result message
                pass
    
    print(f"\nAssistant: {last_response}")
    return last_response

def main():
    # Use a unique agent ID for this demo to avoid collisions with other runs
    # In a real app, this would be your User ID or a persistent Agent ID
    agent_id = f"langgraph-demo-{uuid.uuid4().hex[:8]}"
    
    print("🚀 Starting Memanto + LangGraph Cross-Session Recall Demo")
    print(f"Agent ID: {agent_id}")
    
    # SESSION 1: The agent learns something new
    print("\n--- Phase 1: Storage ---")
    run_session(
        agent_id, 
        "Hi! My name is Alex. I'm a software engineer from Berlin. "
        "Please remember that I prefer Python and I'm currently working on a LangGraph integration. "
        "Store these as my permanent preferences.",
        session_num=1
    )
    
    print("\n" + "-"*60)
    print("WAITING... Simulating time passing between sessions.")
    print("In a real scenario, this could be hours, days, or weeks later.")
    print("-"*60)
    time.sleep(2)
    
    # SESSION 2: The agent recalls what it learned, despite being a brand new instance
    print("\n--- Phase 2: Cross-Session Recall ---")
    run_session(
        agent_id,
        "Hi again! Do you remember who I am and what I'm working on?",
        session_num=2
    )
    
    print("\n" + "="*60)
    print("✅ DEMO COMPLETE")
    print("Even though Session 2 used a completely new Agent instance with no")
    print("local history, it was able to retrieve Alex's identity and project")
    print("from Memanto's persistent memory layer.")
    print("="*60)

if __name__ == "__main__":
    # Check for API keys
    if not os.getenv("MOORCHEH_API_KEY"):
        print("❌ Error: MOORCHEH_API_KEY not found in .env")
        sys.exit(1)
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY not found in .env")
        sys.exit(1)
        
    main()
