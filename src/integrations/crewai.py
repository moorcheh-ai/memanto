

"""
CrewAI Integration for Memanto Agentic Memory

This module provides integration between CrewAI agents and Memanto's agentic memory system.
It allows CrewAI agents to store, retrieve, and utilize memories through Memanto's API.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from crewai import Agent, Crew, Task
from pydantic import BaseModel, Field

from memanto.app.core import MemoryRecord, MemoryScope
from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.utils.errors import MemoryError

logger = logging.getLogger(__name__)

class CrewAIMemoryConfig(BaseModel):
    """
    Configuration for CrewAI-Memanto integration.

    Attributes:
        agent_id: Unique identifier for the CrewAI agent
        scope_type: Type of scope for memory isolation (default: "agent")
        scope_id: ID for scope isolation (default: agent_id)
        actor_id: Identifier for the actor creating memories (default: agent_id)
        source: Source type for memories (default: "agent")
    """
    agent_id: str
    scope_type: str = "agent"
    scope_id: Optional[str] = None
    actor_id: Optional[str] = None
    source: str = "agent"

    def __init__(self, **data):
        super().__init__(**data)
        # Set defaults if not provided
        if self.scope_id is None:
            self.scope_id = self.agent_id
        if self.actor_id is None:
            self.actor_id = self.agent_id

class CrewAIMemoryManager:
    """
    Memory manager for CrewAI agents that integrates with Memanto's agentic memory system.

    This class provides methods for CrewAI agents to:
    - Store memories
    - Retrieve memories
    - Search memories
    - Update memories
    - Delete memories
    """

    def __init__(self, config: CrewAIMemoryConfig, moorcheh_api_key: str):
        """
        Initialize the CrewAI memory manager.

        Args:
            config: Configuration for the memory manager
            moorcheh_api_key: API key for Moorcheh (Memanto's backend)
        """
        self.config = config
        self.moorcheh_api_key = moorcheh_api_key

        # Initialize services
        from memanto.app.clients.moorcheh import MoorchehClient

        self.client = MoorchehClient(moorcheh_api_key)
        self.write_service = MemoryWriteService(self.client)
        self.read_service = MemoryReadService(self.client)

        # Create memory scope
        self.scope = MemoryScope(
            scope_type=self.config.scope_type,
            scope_id=self.config.scope_id
        )
        self.namespace = self.scope.to_namespace()

        logger.info(f"Initialized CrewAI memory manager for agent {self.config.agent_id}")

    def store_memory(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: Optional[List[str]] = None,
        source_ref: Optional[str] = None,
        **extra_fields
    ) -> Dict[str, Any]:
        """
        Store a memory in Memanto.

        Args:
            memory_type: Type of memory (fact, preference, goal, etc.)
            title: Title of the memory
            content: Content of the memory
            confidence: Confidence score (0.0-1.0)
            tags: List of tags for the memory
            source_ref: Reference to the source of this memory
            extra_fields: Additional fields to include in the memory

        Returns:
            Dictionary with storage result
        """
        try:
            # Create memory record
            memory = MemoryRecord(
                type=memory_type,
                title=title,
                content=content,
                scope_type=self.config.scope_type,
                scope_id=self.config.scope_id,
                actor_id=self.config.actor_id,
                source=self.config.source,
                source_ref=source_ref,
                confidence=confidence,
                tags=tags or [],
                **extra_fields
            )

            # Store memory
            result = self.write_service.store_memory(memory)

            logger.info(f"Stored memory {result['id']} for agent {self.config.agent_id}")
            return result

        except MemoryError as e:
            logger.error(f"Failed to store memory: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error storing memory: {str(e)}")
            raise MemoryError(f"Failed to store memory: {str(e)}")

    def retrieve_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific memory by ID.

        Args:
            memory_id: ID of the memory to retrieve

        Returns:
            Memory data or None if not found
        """
        try:
            memory = self.read_service.get_memory(memory_id, self.namespace)
            if memory:
                logger.info(f"Retrieved memory {memory_id} for agent {self.config.agent_id}")
            return memory
        except Exception as e:
            logger.error(f"Failed to retrieve memory {memory_id}: {str(e)}")
            raise MemoryError(f"Failed to retrieve memory: {str(e)}")

    def search_memories(
        self,
        query: str,
        limit: int = 10,
        memory_types: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        min_confidence: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Search for memories matching the query.

        Args:
            query: Search query
            limit: Maximum number of results to return
            memory_types: Filter by memory types
            tags: Filter by tags
            min_confidence: Minimum confidence score

        Returns:
            List of matching memories
        """
        try:
            # Build filter query
            filters = []

            # Add memory type filter if specified
            if memory_types:
                type_filters = " OR ".join([f"#memory_type:{t}" for t in memory_types])
                filters.append(f"({type_filters})")

            # Add tag filter if specified
            if tags:
                tag_filters = " OR ".join([f"#{t}" for t in tags])
                filters.append(f"({tag_filters})")

            # Add confidence filter
            filters.append(f"#confidence>={min_confidence}")

            # Combine filters
            filter_query = " AND ".join(filters) if filters else None

            # Search memories
            results = self.read_service.search_memories(
                query=query,
                namespace=self.namespace,
                limit=limit,
                filter_query=filter_query
            )

            logger.info(f"Found {len(results)} memories for query '{query}'")
            return results

        except Exception as e:
            logger.error(f"Failed to search memories: {str(e)}")
            raise MemoryError(f"Failed to search memories: {str(e)}")

    def update_memory(
        self,
        memory_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update an existing memory.

        Args:
            memory_id: ID of the memory to update
            updates: Dictionary of fields to update

        Returns:
            Dictionary with update result
        """
        try:
            result = self.write_service.update_memory(
                memory_id=memory_id,
                namespace=self.namespace,
                updates=updates
            )

            logger.info(f"Updated memory {memory_id} for agent {self.config.agent_id}")
            return result

        except MemoryError as e:
            logger.error(f"Failed to update memory {memory_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error updating memory {memory_id}: {str(e)}")
            raise MemoryError(f"Failed to update memory: {str(e)}")

    def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a memory.

        Args:
            memory_id: ID of the memory to delete

        Returns:
            True if deletion was successful
        """
        try:
            success = self.write_service.delete_memory(memory_id, self.namespace)

            if success:
                logger.info(f"Deleted memory {memory_id} for agent {self.config.agent_id}")
            return success

        except MemoryError as e:
            logger.error(f"Failed to delete memory {memory_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting memory {memory_id}: {str(e)}")
            raise MemoryError(f"Failed to delete memory: {str(e)}")

    def get_agent_context(self) -> Dict[str, Any]:
        """
        Get context about the agent's memories.

        Returns:
            Dictionary with agent context information
        """
        try:
            # Get memory count
            memory_count = self.read_service.count_memories(self.namespace)

            # Get recent memories
            recent_memories = self.read_service.search_memories(
                query="*",
                namespace=self.namespace,
                limit=5,
                sort_by="updated_at",
                sort_order="desc"
            )

            return {
                "agent_id": self.config.agent_id,
                "memory_count": memory_count,
                "recent_memories": recent_memories,
                "namespace": self.namespace
            }

        except Exception as e:
            logger.error(f"Failed to get agent context: {str(e)}")
            raise MemoryError(f"Failed to get agent context: {str(e)}")

