import os
from memanto import Memanto
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from typing import List, Dict, TypedDict

from langgraph.graph import StateGraph, END

# --- Memanto Setup ---
# Initializes Memanto to store agent memories persistently.
# The unique collection name ensures memories are specific to this agent
# and are saved to the specified local database path.
MEMANTO_DB_PATH = "./memanto_langgraph_db"
memanto = Memanto(db_path=MEMANTO_DB_PATH, collection_name="langgraph_agent_memories")

# --- LangChain/LangGraph Setup ---
# Ensure OPENAI_API_KEY is set as an environment variable.
# For local testing, you might use `export OPENAI_API_KEY="your_key_here"`
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable not set. Please set it to your OpenAI API key.")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# --- Graph State Definition ---
# Defines the structure of the state that flows through the LangGraph.
class AgentState(TypedDict):
    messages: List[BaseMessage]  # Stores the conversation history for the current session.
    retrieved_memories: List[str]  # Stores memories retrieved from Memanto for the current turn.

# --- Graph Nodes ---

def retrieve_memories(state: AgentState) -> Dict:
    """
    Queries Memanto for relevant past information based on the latest user message.
    This helps provide context from previous interactions that isn't in the current session's state.
    """
    messages = state["messages"]
    # Identify the latest human message to use as a query for Memanto.
    latest_user_message = messages[-1].content if messages and isinstance(messages[-1], HumanMessage) else ""

    if not latest_user_message:
        return {"retrieved_memories": []}

    # Retrieve top 3 most relevant facts from Memanto.
    relevant_facts = memanto.query(latest_user_message, top_k=3)
    retrieved_memory_texts = [fact.text for fact in relevant_facts]

    print(f"\n--- Retrieved Memories from Memanto: {retrieved_memory_texts} ---")
    return {"retrieved_memories": retrieved_memory_texts}

def generate_response(state: AgentState) -> Dict:
    """
    Generates an AI response using the LLM, incorporating retrieved memories
    and the ongoing conversation history.
    """
    messages = state["messages"]
    retrieved_memories = state["retrieved_memories"]

    # Format retrieved memories into a context string for the LLM.
    memory_context_str = ""
    if retrieved_memories:
        memory_context_str = "\nRelevant past memories:\n" + "\n".join([f"- {m}" for m in retrieved_memories])

    # Construct the full system instruction that integrates the retrieved memories.
    system_instruction_content = (
        "You are a helpful assistant. Use the provided context and conversation history to answer questions. "
        "If you don't know the answer based on the given information, state that you don't know. "
        "Keep your responses concise and directly address the user's query."
        f"{memory_context_str}"
    )

    # All messages are passed to the ChatPromptTemplate, starting with the system instruction.
    full_llm_messages = [SystemMessage(content=system_instruction_content)] + messages

    # Invoke the LLM with the full conversation history and system instruction.
    chain = ChatPromptTemplate.from_messages(full_llm_messages) | llm
    response = chain.invoke({})  # Input is not needed as all context is in `full_llm_messages`

    print(f"--- Generated AI Response: {response.content} ---")
    # Add the AI's response to the conversation history.
    return {"messages": messages + [AIMessage(content=response.content)]}

def store_memories(state: AgentState) -> Dict:
    """
    Analyzes the entire conversation history to extract and store new, important facts
    into Memanto. This node is critical for achieving cross-session recall.
    """
    messages = state["messages"]
    # Convert BaseMessage objects to a readable string format for fact extraction by LLM.
    conversation_history = "\n".join([f"{type(msg).__name__}: {msg.content}" for msg in messages])

    # Use an LLM to identify self-contained facts that should be remembered long-term.
    fact_extraction_prompt = ChatPromptTemplate.from_messages(
        [
            ("system",
             "You are an expert at identifying and extracting important, self-contained facts "
             "from a conversation that an AI assistant should remember long-term about the user or their preferences. "
             "Output each distinct fact on a new line, prefixed with a hyphen. "
             "If no new, important facts are present, output 'No new facts.' "
             "Examples of facts: '- User's name is John.', '- User lives in New York.', '- User's favorite color is blue.'\n\n"
             "Conversation history:\n{conversation}"
            ),
            ("human", "Extract any new, important facts from the above conversation that should be stored for long-term memory.")
        ]
    )

    extraction_chain = fact_extraction_prompt | llm
    extracted_facts_raw = extraction_chain.invoke({"conversation": conversation_history}).content

    if extracted_facts_raw and extracted_facts_raw.strip().lower() != "no new facts.":
        # Parse the extracted facts, ensuring they start with a hyphen.
        facts_to_store = [
            fact.strip() for fact in extracted_facts_raw.split('\n')
            if fact.strip().startswith('-') and len(fact.strip()) > 1
        ]
        for fact_text in facts_to_store:
            clean_fact = fact_text[1:].strip()  # Remove the hyphen prefix.
            memanto.add_fact(clean_fact, metadata={"source": "llm_extracted_fact"})
            print(f"--- Stored memory: {clean_fact} ---")
    else:
        print("--- No new facts extracted for long-term storage. ---")

    # The messages state remains unchanged in this node.
    return {"messages": messages}

# --- Build the LangGraph ---
workflow = StateGraph(AgentState)

# Add nodes to the graph representing different steps in the agent's process.
workflow.add_node("retrieve_memories", retrieve_memories)
workflow.add_node("generate_response", generate_response)
workflow.add_node("store_memories", store_memories)

# Set the starting point for the graph.
workflow.set_entry_point("retrieve_memories")

# Define the flow of execution between nodes.
workflow.add_edge("retrieve_memories", "generate_response")
workflow.add_edge("generate_response", "store_memories")
workflow.add_edge("store_memories", END)  # End of a single turn after storing memories.

app = workflow.compile()

# --- Example Usage to Demonstrate Cross-Session Recall ---
if __name__ == "__main__":
    print("--- Welcome to the Memanto-powered LangGraph Agent! ---")
    print("This agent stores and retrieves facts across different conversation sessions.")
    print("The Memanto database is saved locally at './memanto_langgraph_db'.")

    # Optional: Clear previous memories for a clean run if desired.
    # Uncomment the following lines to start with a fresh memory database each time.
    # from shutil import rmtree
    # if os.path.exists(MEMANTO_DB_PATH):
    #     rmtree(MEMANTO_DB_PATH)
    #     print(f"--- Cleared existing Memanto database at {MEMANTO_DB_PATH} ---")
    #     # Re-initialize memanto after deleting the directory
    #     memanto = Memanto(db_path=MEMANTO_DB_PATH, collection_name="langgraph_agent_memories")

    print("\n--- Session 1: Introducing new facts ---")
    # User introduces personal information. These facts should be stored by `store_memories`.
    inputs1 = {"messages": [HumanMessage(content="Hello, my name is Alice. I love hiking in the mountains and my favorite animal is a cat.")]}
    final_state1 = {}
    for s in app.stream(inputs1):
        if "__end__" in s:
            final_state1 = s["__end__"]
    if final_state1 and final_state1.get('messages') and len(final_state1['messages']) > 0:
        print(f"Agent's final response in Session 1: {final_state1['messages'][-1].content}")
    else:
        print("Agent's final response in Session 1: No response generated or error occurred.")


    print("\n--- Session 2: Asking a question within the same logical run ---")
    # Agent should recall from the previous turn *within the current LangGraph execution*.
    inputs2 = {"messages": [HumanMessage(content="What is my name?")]}
    final_state2 = {}
    for s in app.stream(inputs2):
        if "__end__" in s:
            final_state2 = s["__end__"]
    if final_state2 and final_state2.get('messages') and len(final_state2['messages']) > 0:
        print(f"Agent's final response in Session 2: {final_state2['messages'][-1].content}")
    else:
        print("Agent's final response in Session 2: No response generated or error occurred.")


    print("\n--- Simulating a NEW, disjointed session (e.g., agent restarted, days later) ---")
    print("The agent should now recall facts from Session 1 via Memanto, despite starting with a fresh LangGraph state.")

    # Ask questions that rely on previously stored memories.
    # The LangGraph `AgentState` starts fresh, but Memanto provides the long-term memory.
    inputs_new_session_1 = {"messages": [HumanMessage(content="What is my favorite animal?")]}
    print("Querying agent for favorite animal...")
    final_state_ns1 = {}
    for s in app.stream(inputs_new_session_1):
        if "__end__" in s:
            final_state_ns1 = s["__end__"]
    if final_state_ns1 and final_state_ns1.get('messages') and len(final_state_ns1['messages']) > 0:
        print(f"Agent's final response in New Session 1: {final_state_ns1['messages'][-1].content}")
    else:
        print("Agent's final response in New Session 1: No response generated or error occurred.")


    inputs_new_session_2 = {"messages": [HumanMessage(content="What do I love doing?")]}
    print("Querying agent for hobby...")
    final_state_ns2 = {}
    for s in app.stream(inputs_new_session_2):
        if "__end__" in s:
            final_state_ns2 = s["__end__"]
    if final_state_ns2 and final_state_ns2.get('messages') and len(final_state_ns2['messages']) > 0:
        print(f"Agent's final response in New Session 2: {final_state_ns2['messages'][-1].content}")
    else:
        print("Agent's final response in New Session 2: No response generated or error occurred.")

    inputs_new_session_3 = {"messages": [HumanMessage(content="Remind me, what is my name?")]}
    print("Querying agent for name again...")
    final_state_ns3 = {}
    for s in app.stream(inputs_new_session_3):
        if "__end__" in s:
            final_state_ns3 = s["__end__"]
    if final_state_ns3 and final_state_ns3.get('messages') and len(final_state_ns3['messages']) > 0:
        print(f"Agent's final response in New Session 3: {final_state_ns3['messages'][-1].content}")
    else:
        print("Agent's final response in New Session 3: No response generated or error occurred.")

    print("\n--- End of Demonstration ---")
    print("You can inspect the './memanto_langgraph_db' directory to see the persistent memory storage.")
