import operator
from typing import Annotated, Dict, List, Optional, Sequence, TypedDict
from langgraph.graph import Graph
from memanto import MemantoClient

class AgentState(TypedDict):
    # Define the agent state
    messages: Annotated[Sequence[Dict], "The messages in the conversation"]
    next: str

class Agent:
    def __init__(self, client: MemantoClient):
        self.client = client
        self.state = AgentState(messages=[])

    def remember(self, info: str) -> str:
        # Remember information using Memanto
        return self.client.remember(info)

    def recall(self, query: str) -> List[Dict]:
        # Recall information from Memanto
        return self.client.recall(query)

    def answer(self, query: str) -> str:
        # Get an answer from Memanto
        return self.client.answer(query)

def run_agent():
    # Initialize the agent
    agent = Agent(MemantoClient())

    # Start the agent
    while True:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit"]:
            break

        # Recall context from memory
        context = agent.recall(user_input)
        
        # Generate response using context
        response = agent.answer(user_input)
        print(f"Agent: {response}")
        
        # Remember the new interaction
        agent.remember(f"User: {user_input}\nAgent: {response}")
        
        print("Agent: ", response)

if __name__ == "__main__":
    run_agent()
