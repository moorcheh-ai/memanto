"""
LangGraph Customer Support Agent with Memanto Long-Term Memory

This agent demonstrates cross-session memory:
- LangGraph manages conversation flow (stateful within session)
- Memanto stores long-term facts (persistent across sessions)
"""

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

# Import Memanto
try:
    from memanto import Memanto
except ImportError:
    print("Installing memanto...")
    import subprocess
    subprocess.check_call(["pip", "install", "memanto"])
    from memanto import Memanto

load_dotenv()


class AgentState(TypedDict):
    """LangGraph state - resets between sessions"""
    messages: Annotated[list, add_messages]
    user_id: str


class CustomerSupportAgent:
    """Customer support agent with Memanto long-term memory"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
        
        # Initialize Memanto for long-term memory
        self.memanto = Memanto(
            api_key=os.getenv("MOORCHEH_API_KEY"),
            agent_id=f"support-agent-{user_id}"
        )
        
        # Build LangGraph workflow
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build LangGraph workflow"""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("greet", self._greet_node)
        workflow.add_node("query_memory", self._query_memory_node)
        workflow.add_node("respond", self._respond_node)
        workflow.add_node("store_memory", self._store_memory_node)
        
        # Define edges
        workflow.set_entry_point("greet")
        workflow.add_edge("greet", "query_memory")
        workflow.add_edge("query_memory", "respond")
        workflow.add_edge("respond", "store_memory")
        workflow.add_edge("store_memory", END)
        
        return workflow.compile()
    
    def _greet_node(self, state: AgentState) -> AgentState:
        """Initial greeting"""
        if len(state["messages"]) == 1:
            greeting = AIMessage(content="Hello! I'm your customer support assistant. How can I help you today?")
            state["messages"].append(greeting)
        return state
    
    def _query_memory_node(self, state: AgentState) -> AgentState:
        """Query Memanto for relevant long-term memories"""
        last_message = state["messages"][-1]
        
        if isinstance(last_message, HumanMessage):
            # Recall relevant memories from Memanto
            try:
                memories = self.memanto.recall(
                    query=last_message.content,
                    limit=5
                )
                
                if memories:
                    memory_context = "\n".join([
                        f"- {m['content']} (type: {m.get('memory_type', 'unknown')}, confidence: {m.get('confidence', 0):.2f})"
                        for m in memories
                    ])
                    
                    # Add memory context as system message
                    system_msg = SystemMessage(
                        content=f"Relevant memories about this user:\n{memory_context}"
                    )
                    state["messages"].insert(-1, system_msg)
            except Exception as e:
                print(f"Memory recall error: {e}")
        
        return state
    
    def _respond_node(self, state: AgentState) -> AgentState:
        """Generate response using LLM"""
        response = self.llm.invoke(state["messages"])
        state["messages"].append(response)
        return state
    
    def _store_memory_node(self, state: AgentState) -> AgentState:
        """Extract and store important facts in Memanto"""
        last_human_msg = None
        last_ai_msg = None
        
        # Get last human and AI messages
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage) and last_ai_msg is None:
                last_ai_msg = msg
            elif isinstance(msg, HumanMessage) and last_human_msg is None:
                last_human_msg = msg
            
            if last_human_msg and last_ai_msg:
                break
        
        if last_human_msg:
            # Use LLM to extract memorable facts
            extraction_prompt = f"""
Extract any important facts, preferences, or decisions from this conversation that should be remembered long-term.

User: {last_human_msg.content}
Assistant: {last_ai_msg.content if last_ai_msg else ''}

Return ONLY facts worth remembering (preferences, decisions, important context).
Format: One fact per line, or "NONE" if nothing memorable.
"""
            
            try:
                extraction = self.llm.invoke([HumanMessage(content=extraction_prompt)])
                facts = extraction.content.strip()
                
                if facts and facts != "NONE":
                    for fact in facts.split("\n"):
                        fact = fact.strip()
                        if fact and not fact.startswith("#"):
                            # Determine memory type
                            memory_type = "fact"
                            if "prefer" in fact.lower():
                                memory_type = "preference"
                            elif "decided" in fact.lower() or "will" in fact.lower():
                                memory_type = "decision"
                            
                            # Store in Memanto
                            self.memanto.remember(
                                content=fact,
                                memory_type=memory_type,
                                confidence=0.9
                            )
                            print(f"[Stored in Memanto] {fact}")
            except Exception as e:
                print(f"Memory storage error: {e}")
        
        return state
    
    def chat(self, message: str) -> str:
        """Process a user message"""
        initial_state = {
            "messages": [HumanMessage(content=message)],
            "user_id": self.user_id
        }
        
        result = self.graph.invoke(initial_state)
        
        # Return last AI message
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage):
                return msg.content
        
        return "I'm sorry, I couldn't process that."


if __name__ == "__main__":
    # Quick test
    agent = CustomerSupportAgent(user_id="test-user-123")
    
    print("Agent: Hello! I'm your customer support assistant.")
    print("\nUser: I prefer dark mode for all interfaces")
    response = agent.chat("I prefer dark mode for all interfaces")
    print(f"Agent: {response}")
    
    print("\n--- New session (simulating next day) ---\n")
    
    # Create new agent instance (simulates new session)
    agent2 = CustomerSupportAgent(user_id="test-user-123")
    print("User: What theme do I prefer?")
    response2 = agent2.chat("What theme do I prefer?")
    print(f"Agent: {response2}")
