import operator
from typing import Annotated, TypedDict, Union
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from integrations.langgraph.memanto_manager import MemantoMemoryManager, MemorySyncSchema

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    user_id: str
    memories: list

class MemantoBrain:
    def __init__(self, api_key: str, agent_id: str):
        self.llm = ChatOpenAI(model="gpt-4-turbo-preview", temperature=0)
        self.memory_manager = MemantoMemoryManager(agent_id, api_key)
        self.structured_llm = self.llm.with_structured_output(MemorySyncSchema)

    async def call_model(self, state: AgentState):
        # Recall relevant memories for the current context
        # In a production system, this would use a semantic search over keys
        context = await self.memory_manager.recall("user_profile") or "No prior knowledge."
        
        system_prompt = f"Long-term Memory: {context}\n\nAssist the user based on state and memory."
        messages = [{"role": "system", "content": system_prompt}] + state["messages"]
        
        response = await self.llm.ainvoke(messages)
        return {"messages": [response]}

    async def memory_sync_node(self, state: AgentState):
        last_message = state["messages"][-1].content
        # Autonomous determination of fact-worthiness
        decision = await self.structured_llm.ainvoke(
            f"Analyze this message for permanent facts about the user: {last_message}"
        )
        
        if decision.should_store and decision.key and decision.value:
            await self.memory_manager.remember(decision.key, decision.value)
            
        return {"messages": []}

def create_graph(brain: MemantoBrain):
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", brain.call_model)
    workflow.add_node("memory_sync", brain.memory_sync_node)
    
    workflow.set_entry_point("agent")
    workflow.add_edge("agent", "memory_sync")
    workflow.add_edge("memory_sync", END)
    
    return workflow.compile()
