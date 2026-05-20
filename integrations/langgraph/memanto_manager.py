import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from memanto.cli.client.sdk_client import SdkClient

class MemoryEntry(BaseModel):
    timestamp: str
    content: str
    metadata: Dict[str, Any]

class MemantoMemoryManager:
    def __init__(self, agent_id: str, api_key: str):
        self.client = SdkClient(api_key=api_key)
        self.agent_id = agent_id
        self._lock = asyncio.Lock()

    async def remember(self, key: str, value: str, metadata: Optional[Dict] = None) -> bool:
        async with self._lock:
            timestamp = datetime.utcnow().isoformat()
            meta = metadata or {}
            # Versioned Append Strategy: Store as a time-series log to prevent Last-Write-Wins race conditions
            entry = MemoryEntry(
                timestamp=timestamp,
                content=value,
                metadata=meta
            ).model_dump_json()
            
            existing = await self.client.recall(self.agent_id, key)
            if existing:
                # Append to existing log rather than overwriting
                updated_log = f"{existing}\n{entry}"
                return await self.client.remember(self.agent_id, key, updated_log)
            
            return await self.client.remember(self.agent_id, key, entry)

    async def recall(self, key: str) -> Optional[str]:
        raw_data = await self.client.recall(self.agent_id, key)
        if not raw_data:
            return None
        
        # Return only the most recent entry from the versioned log
        entries = raw_data.strip().split("\n")
        if not entries:
            return None
            
        try:
            last_entry = MemoryEntry.model_validate_json(entries[-1])
            return last_entry.content
        except Exception:
            return raw_data

class MemorySyncSchema(BaseModel):
    should_store: bool = Field(description="Whether the conversation contains a fact worth permanent storage")
    key: Optional[str] = Field(None, description="The semantic key for the memory")
    value: Optional[str] = Field(None, description="The factual content to remember")
