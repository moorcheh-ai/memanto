import time
from typing import Optional, Dict, Any
from memanto.cli.client.sdk_client import SdkClient
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

class MemantoSemanticManager:
    def __init__(self, agent_id: str, api_key: str):
        self.client = SdkClient(api_key=api_key)
        self.agent_id = agent_id
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self._setup_gate()

    def _setup_gate(self):
        prompt = ChatPromptTemplate.from_template(
            "Analyze the following exchange. If it contains a specific fact, user preference, "
            "or long-term goal, return 'STORE' and the extracted insight. Otherwise, return 'IGNORE'.\n\n"
            "Exchange: {content}"
        )
        self.gate_chain = prompt | self.llm | StrOutputParser()

    def process_and_store(self, content: str) -> bool:
        decision = self.gate_chain.invoke({"content": content})
        if decision.startswith("STORE"):
            insight = decision.replace("STORE", "").strip()
            self.safe_remember(insight)
            return True
        return False

    def safe_remember(self, content: str):
        # Optimistic Locking implementation
        # We retrieve the existing memory to check for a version/timestamp before updating
        existing_memories = self.client.recall(self.agent_id, query=content)
        
        current_timestamp = time.time()
        # Prevent overwriting if a newer update happened within the same semantic window
        if existing_memories and "timestamp" in existing_memories[0]:
            last_update = existing_memories[0]["timestamp"]
            if current_timestamp - last_update < 1.0:
                return # Prevent rapid-fire duplicate writes

        self.client.remember(self.agent_id, content)

    def recall_semantic(self, query: str) -> str:
        memories = self.client.recall(self.agent_id, query=query)
        return "\n".join([m["content"] for m in memories]) if memories else ""
