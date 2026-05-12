import json
import os
from typing import List, Dict, Optional, TypedDict, Any
from uuid import uuid4

from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

# --- Mock Memanto Client for Demonstration ---
# In a real scenario, you would replace this with the actual Memanto client library.
# This mock client persists memories to a local JSON file to demonstrate
# cross-session recall without requiring a running Memanto service.
class PersistentMemantoClient:
    def __init__(self, storage_file="memanto_data.json"):
        self.storage_file = storage_file
        self.memories: Dict[str, Any] = self._load_memories()
        print(f"MemantoClient initialized. Memories loaded from {self.storage_file}.")

    def _load_memories(self) -> Dict[str, Any]:
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"WARNING: Could not decode {self.storage_file}. Starting with empty memories.")
                return {"memories": []}
        return {"memories": []}

    def _save_memories(self):
        with open(self.storage_file, 'w') as f:
            json.dump(self.memories, f, indent=2)

    def add_memory(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        memory_id = str(uuid4())
        memory = {"id": memory_id, "content": content, "metadata": metadata or {}}
        self.memories["memories"].append(memory)
        self._save_memories()
        print(f"[Memanto] Stored memory (ID: {memory_id}): '{content}'")
        return memory_id

    def retrieve_memory(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        retrieved = []
        query_lower = query.lower()
        # Simple keyword-based retrieval. Real Memanto would use embeddings and vector search.
        for mem in self.memories["memories"]:
            if query_lower in mem["content"].lower():
                retrieved.append(mem)
        
        # Limit to top_k, returning just the content for simplicity in the agent response.
        retrieved_contents = [mem["content"] for mem in retrieved[:top_k]]
        print(f"[Memanto] Retrieved {len(retrieved_contents)} memories for query '{query}': {retrieved_contents}")
        return retrieved_contents

    def clear_all_memories(self):
        self.memories = {"memories": []}
        self._save_memories()
        print("[Memanto] All memories cleared.")


# --- LangGraph State Definition ---
class AgentState(TypedDict):
    """
    Represents the state of our graph.
    """
    input_message: str  # The current input from the user
    memories_retrieved: List[str]  # Relevant memories retrieved from Memanto
    new_fact_to_store: Optional[str] # A fact identified to be stored in Memanto
    response: str # The agent's final response
    action: str # Determines the next step: "store_fact" or "answer_question"


# --- Graph Nodes ---

def retrieve_memories_node(state: AgentState, memanto_client: PersistentMemantoClient) -> AgentState:
    """
    Retrieves relevant memories from Memanto based on the current input message.
    This provides context from long-term memory to the current session.
    """
    print("---NODE: retrieve_memories_node---")
    query = state["input_message"]
    memories = memanto_client.retrieve_memory(query)
    return {"memories_retrieved": memories}

def decide_action_node(state: AgentState) -> AgentState:
    """
    Analyzes the input message to decide if the agent should store a new fact
    or answer a question. This is a routing decision based on user intent.
    """
    print("---NODE: decide_action_node---")
    input_msg = state["input_message"]
    new_fact = None
    action = "answer_question" # Default action

    if input_msg.lower().startswith("remember:"):
        new_fact = input_msg[len("remember:"):].strip()
        action = "store_fact"
        print(f"Decided action: STORE FACT. New fact: '{new_fact}'")
    else:
        print("Decided action: ANSWER QUESTION.")

    return {"new_fact_to_store": new_fact, "action": action}

def store_fact_node(state: AgentState, memanto_client: PersistentMemantoClient) -> AgentState:
    """
    Stores the identified new fact into Memanto's long-term memory.
    """
    print("---NODE: store_fact_node---")
    fact = state["new_fact_to_store"]
    if fact:
        memanto_client.add_memory(fact, metadata={"source": "user_input"})
        response = f"Okay, I've remembered: '{fact}'."
    else:
        response = "I was supposed to store a fact, but no fact was provided." # This path should generally not be taken.
    return {"response": response, "new_fact_to_store": None} # Clear fact after storing

def answer_question_node(state: AgentState) -> AgentState:
    """
    Generates a response to a question, incorporating retrieved memories
    to provide an informed answer. In a real application, an LLM would
    process these memories and the query to generate a more sophisticated response.
    """
    print("---NODE: answer_question_node---")
    query = state["input_message"]
    memories = state["memories_retrieved"]

    response_parts = []
    if memories:
        response_parts.append("Based on what I recall:")
        for i, mem in enumerate(memories):
            response_parts.append(f"- {mem}")
        response_parts.append(f"Regarding your question: '{query}'")
        response_parts.append("I can try to use these memories to help.")
    else:
        response_parts.append(f"I don't recall anything specific related to '{query}'.")
        response_parts.append("Is there something you'd like me to remember?")

    response = "\n".join(response_parts)
    return {"response": response}

# --- Graph Builder ---

def create_memanto_langgraph_agent(memanto_client: PersistentMemantoClient):
    workflow = StateGraph(AgentState)

    # Define the nodes for our agent's workflow
    workflow.add_node("retrieve_memories", lambda state: retrieve_memories_node(state, memanto_client))
    workflow.add_node("decide_action", decide_action_node)
    workflow.add_node("store_fact", lambda state: store_fact_node(state, memanto_client))
    workflow.add_node("answer_question", answer_question_node)

    # Set the starting point of the graph
    workflow.set_entry_point("retrieve_memories")

    # Connect the nodes. After retrieving memories, decide what action to take.
    workflow.add_edge("retrieve_memories", "decide_action")

    # Use a conditional edge to route based on the 'action' determined by 'decide_action_node'
    workflow.add_conditional_edges(
        "decide_action",
        lambda state: state["action"], # This function determines the next node based on the 'action' key in the state
        {
            "store_fact": "store_fact", # If action is "store_fact", go to 'store_fact' node
            "answer_question": "answer_question", # If action is "answer_question", go to 'answer_question' node
        },
    )

    # Both 'store_fact' and 'answer_question' nodes are terminal points for this graph run
    workflow.add_edge("store_fact", END)
    workflow.add_edge("answer_question", END)

    return workflow.compile()

# --- Main Execution ---
if __name__ == "__main__":
    # Initialize the mock Memanto client. This client will save/load memories
    # from 'memanto_data.json' in the current directory.
    memanto_client = PersistentMemantoClient(storage_file="memanto_data.json")

    # Uncomment the line below during development if you want to clear all
    # previously stored memories for a fresh start.
    # memanto_client.clear_all_memories()

    # Create and compile the agent graph
    agent_executor = create_memanto_langgraph_agent(memanto_client)

    print("\n--- LangGraph + Memanto Agent Demo ---")
    print("Type 'Remember: <fact>' to store a memory.")
    print("Type any question to retrieve related memories and get a response.")
    print("Type 'exit' to quit.\n")

    while True:
        user_input = input("You: ")
        if user_input.lower() == 'exit':
            break

        # Define the initial state for each new interaction with the agent
        initial_state = {
            "input_message": user_input,
            "memories_retrieved": [],
            "new_fact_to_store": None,
            "response": "",
            "action": "" # Will be set by decide_action_node
        }

        # Invoke the agent graph with the initial state
        # The stream method can also be used for step-by-step execution.
        final_state = agent_executor.invoke(initial_state)

        # Print the agent's final response
        print(f"Agent: {final_state['response']}\n")

    print("Demo ended. Current memories are saved in memanto_data.json.")
