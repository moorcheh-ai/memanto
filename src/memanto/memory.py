

"""
Enhanced Agentic Memory System for Memanto

This module extends Memanto's core memory system to provide better integration
with external AI frameworks like CrewAI.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from memanto.app.core import MemoryRecord, MemoryScope, ValidationPolicy
from memanto.app.constants import MemoryType, ScopeType, SourceType, StatusType, ProvenanceType

logger = logging.getLogger(__name__)

class EnhancedMemoryRecord(MemoryRecord):
    """
    Enhanced Memory Record with additional fields and methods for better AI framework integration.
    """

    # Additional fields for enhanced memory system
    priority: float = Field(default=0.5, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    last_accessed: datetime | None = None
    access_count: int = 0
    related_memories: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_moorcheh_document(self) -> Dict[str, Any]:
        """
        Convert to Moorcheh document format with enhanced metadata fields.
        """
        # Get base document
        document = super().to_moorcheh_document()

        # Add enhanced fields
        document.update({
            "priority": self.priority,
            "importance": self.importance,
            "relevance_score": self.relevance_score,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "access_count": self.access_count,
            "related_memories": ",".join(self.related_memories) if self.related_memories else None,
            "metadata": str(self.metadata) if self.metadata else None,
        })

        return document

    def mark_accessed(self):
        """Mark memory as accessed and update access count."""
        self.access_count += 1
        self.last_accessed = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def add_related_memory(self, memory_id: str):
        """Add a related memory ID."""
        if memory_id not in self.related_memories:
            self.related_memories.append(memory_id)

    def set_relevance(self, score: float):
        """Set relevance score for this memory."""
        self.relevance_score = max(0.0, min(1.0, score))

    def set_priority(self, priority: float):
        """Set priority score for this memory."""
        self.priority = max(0.0, min(1.0, priority))

    def set_importance(self, importance: float):
        """Set importance score for this memory."""
        self.importance = max(0.0, min(1.0, importance))

    def update_metadata(self, key: str, value: Any):
        """Update metadata field."""
        self.metadata[key] = value

class MemoryContext(BaseModel):
    """
    Context for memory operations, including validation and enrichment.
    """
    user_confirmed: bool = False
    repetition_count: int = 0
    conversation_history: List[str] = Field(default_factory=list)
    current_task: str = ""
    agent_state: Dict[str, Any] = Field(default_factory=dict)

class EnhancedMemoryValidationPolicy(ValidationPolicy):
    """
    Enhanced memory validation policy with additional checks and enrichment.
    """

    @staticmethod
    def validate_memory(
        memory: EnhancedMemoryRecord,
        context: MemoryContext | None = None
    ) -> Dict[str, Any]:
        """
        Enhanced validation with additional checks and enrichment.

        Returns: {"valid": bool, "action": str, "reason": str, "memory": EnhancedMemoryRecord}
        """
        context = context or MemoryContext()

        # Base validation
        result = super().validate_memory(memory, context)

        # Enhanced validation for critical memory types
        if memory.type in ["fact", "preference", "goal"]:
            # Check for consistency with existing memories
            consistency_check = EnhancedMemoryValidationPolicy._check_memory_consistency(
                memory, context
            )
            if not consistency_check["valid"]:
                return {
                    "valid": False,
                    "action": "reject",
                    "reason": f"Memory rejected due to inconsistency: {consistency_check['reason']}",
                    "memory": memory
                }

            # Check for importance/priority conflicts
            priority_check = EnhancedMemoryValidationPolicy._check_priority_conflicts(
                memory, context
            )
            if not priority_check["valid"]:
                return {
                    "valid": False,
                    "action": "reject",
                    "reason": f"Memory rejected due to priority conflict: {priority_check['reason']}",
                    "memory": memory
                }

        # Enrich memory with context
        enriched_memory = EnhancedMemoryValidationPolicy._enrich_memory_with_context(
            memory, context
        )

        # Update result with enriched memory
        result["memory"] = enriched_memory
        return result

    @staticmethod
    def _check_memory_consistency(
        memory: EnhancedMemoryRecord,
        context: MemoryContext
    ) -> Dict[str, Any]:
        """
        Check if new memory is consistent with existing memories.
        """
        # In a real implementation, this would query existing memories
        # For now, we'll just do a simple check
        if "contradicts" in context.agent_state:
            for existing_memory in context.agent_state["contradicts"]:
                if existing_memory.get("type") == memory.type and \
                   existing_memory.get("title") == memory.title:
                    return {
                        "valid": False,
                        "reason": f"Memory contradicts existing memory: {existing_memory.get('id')}"
                    }

        return {"valid": True, "reason": "No contradictions detected"}

    @staticmethod
    def _check_priority_conflicts(
        memory: EnhancedMemoryRecord,
        context: MemoryContext
    ) -> Dict[str, Any]:
        """
        Check if new memory conflicts with existing memories in terms of priority/importance.
        """
        # In a real implementation, this would query existing memories
        # For now, we'll just do a simple check
        if "high_priority_memories" in context.agent_state:
            for existing_memory in context.agent_state["high_priority_memories"]:
                if existing_memory.get("importance", 0) > 0.8 and \
                   memory.importance > 0.8 and \
                   existing_memory.get("type") == memory.type:
                    return {
                        "valid": False,
                        "reason": "High importance memory already exists for this type"
                    }

        return {"valid": True, "reason": "No priority conflicts detected"}

    @staticmethod
    def _enrich_memory_with_context(
        memory: EnhancedMemoryRecord,
        context: MemoryContext
    ) -> EnhancedMemoryRecord:
        """
        Enrich memory with context information.
        """
        # Set relevance based on context
        if context.current_task:
            # Simple relevance scoring based on task matching
            task_words = context.current_task.lower().split()
            content_words = memory.content.lower().split()
            common_words = set(task_words) & set(content_words)
            relevance = min(1.0, len(common_words) / max(1, len(task_words)))
            memory.set_relevance(relevance)

        # Set priority based on context
        if "priority_rules" in context.agent_state:
            for rule in context.agent_state["priority_rules"]:
                if rule.get("type") == memory.type:
                    memory.set_priority(rule.get("priority", 0.5))

        # Add metadata from context
        if context.agent_state:
            memory.update_metadata("agent_state", context.agent_state)

        return memory

class MemoryEnrichmentService:
    """
    Service for enriching memories with additional context and metadata.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def enrich_memory(
        self,
        memory: EnhancedMemoryRecord,
        context: MemoryContext
    ) -> EnhancedMemoryRecord:
        """
        Enrich a memory with additional context and metadata.

        Args:
            memory: Memory to enrich
            context: Context information

        Returns:
            Enriched memory
        """
        try:
            # Apply validation and enrichment
            validation_result = EnhancedMemoryValidationPolicy.validate_memory(
                memory, context
            )

            if not validation_result["valid"]:
                self.logger.warning(
                    f"Memory validation failed: {validation_result['reason']}"
                )
                return memory

            enriched_memory = validation_result["memory"]

            # Additional enrichment steps
            enriched_memory = self._add_temporal_context(enriched_memory, context)
            enriched_memory = self._add_relationship_context(enriched_memory, context)

            self.logger.info(f"Enriched memory {enriched_memory.id}")
            return enriched_memory

        except Exception as e:
            self.logger.error(f"Failed to enrich memory: {str(e)}")
            raise

    def _add_temporal_context(
        self,
        memory: EnhancedMemoryRecord,
        context: MemoryContext
    ) -> EnhancedMemoryRecord:
        """
        Add temporal context to memory based on conversation history.
        """
        if context.conversation_history:
            # Simple temporal analysis - in a real implementation this would be more sophisticated
            recent_messages = context.conversation_history[-3:]  # Last 3 messages
            time_refs = sum(1 for msg in recent_messages if any(
                word in msg.lower() for word in ["yesterday", "today", "tomorrow", "last", "next"]
            ))

            if time_refs > 0:
                memory.set_importance(min(1.0, memory.importance + 0.2))
                memory.update_metadata("temporal_relevance", "high")

        return memory

    def _add_relationship_context(
        self,
        memory: EnhancedMemoryRecord,
        context: MemoryContext
    ) -> EnhancedMemoryRecord:
        """
        Add relationship context to memory based on existing memories.
        """
        # In a real implementation, this would query existing memories
        # For now, we'll just add some example relationships
        if memory.type == "fact" and "user_preferences" in context.agent_state:
            memory.add_related_memory("user_preference_123")
            memory.update_metadata("related_to_preferences", True)

        return memory

class MemoryQueryService:
    """
    Service for querying and retrieving memories with advanced filtering and ranking.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def search_memories(
        self,
        query: str,
        memories: List[EnhancedMemoryRecord],
        limit: int = 10,
        min_confidence: float = 0.5,
        min_relevance: float = 0.3,
        sort_by: str = "relevance",
        sort_order: str = "desc"
    ) -> List[EnhancedMemoryRecord]:
        """
        Search and rank memories based on the query.

        Args:
            query: Search query
            memories: List of memories to search
            limit: Maximum number of results
            min_confidence: Minimum confidence score
            min_relevance: Minimum relevance score
            sort_by: Field to sort by (relevance, confidence, importance, priority)
            sort_order: Sort order (asc, desc)

        Returns:
            List of ranked memories
        """
        try:
            # Filter memories
            filtered_memories = [
                m for m in memories
                if m.confidence >= min_confidence and
                m.relevance_score >= min_relevance
            ]

            # Rank memories
            ranked_memories = self._rank_memories(query, filtered_memories, sort_by)

            # Apply limit
            result = ranked_memories[:limit]

            self.logger.info(f"Found {len(result)} memories for query '{query}'")
            return result

        except Exception as e:
            self.logger.error(f"Failed to search memories: {str(e)}")
            raise

    def _rank_memories(
        self,
        query: str,
        memories: List[EnhancedMemoryRecord],
        sort_by: str
    ) -> List[EnhancedMemoryRecord]:
        """
        Rank memories based on query relevance and other factors.
        """
        # Simple ranking based on relevance score and other factors
        # In a real implementation, this would use semantic search and more sophisticated ranking

        def get_sort_key(memory: EnhancedMemoryRecord) -> float:
            """Get sort key based on sort_by parameter."""
            if sort_by == "confidence":
                return memory.confidence
            elif sort_by == "importance":
                return memory.importance
            elif sort_by == "priority":
                return memory.priority
            else:  # default to relevance
                return memory.relevance_score

        # Sort memories
        sorted_memories = sorted(
            memories,
            key=get_sort_key,
            reverse=sort_order.lower() == "desc"
        )

        return sorted_memories

    def get_memory_context(
        self,
        memory_id: str,
        memories: List[EnhancedMemoryRecord]
    ) -> Dict[str, Any]:
        """
        Get context for a specific memory, including related memories.

        Args:
            memory_id: ID of the memory
            memories: List of all memories

        Returns:
            Dictionary with memory context
        """
        try:
            # Find the memory
            memory = next((m for m in memories if m.id == memory_id), None)
            if not memory:
                raise ValueError(f"Memory {memory_id} not found")

            # Find related memories
            related_memories = []
            for mid in memory.related_memories:
                related = next((m for m in memories if m.id == mid), None)
                if related:
                    related_memories.append(related)

            # Build context
            context = {
                "memory": memory,
                "related_memories": related_memories,
                "total_related": len(related_memories),
                "memory_count": len(memories)
            }

            self.logger.info(f"Retrieved context for memory {memory_id}")
            return context

        except Exception as e:
            self.logger.error(f"Failed to get memory context: {str(e)}")
            raise

def create_enhanced_memory(
    memory_type: MemoryType,
    title: str,
    content: str,
    scope: MemoryScope,
    actor_id: str,
    source: SourceType = "agent",
    confidence: float = 0.8,
    **extra_fields
) -> EnhancedMemoryRecord:
    """
    Create an enhanced memory record.

    Args:
        memory_type: Type of memory
        title: Title of the memory
        content: Content of the memory
        scope: Memory scope
        actor_id: ID of the actor creating the memory
        source: Source of the memory
        confidence: Confidence score
        extra_fields: Additional fields

    Returns:
        EnhancedMemoryRecord
    """
    memory = EnhancedMemoryRecord(
        type=memory_type,
        title=title,
        content=content,
        scope_type=scope.scope_type,
        scope_id=scope.scope_id,
        actor_id=actor_id,
        source=source,
        confidence=confidence,
        **extra_fields
    )

    return memory

def create_memory_context(
    user_confirmed: bool = False,
    conversation_history: Optional[List[str]] = None,
    current_task: str = "",
    agent_state: Optional[Dict[str, Any]] = None
) -> MemoryContext:
    """
    Create a memory context.

    Args:
        user_confirmed: Whether the user confirmed the memory
        conversation_history: Conversation history
        current_task: Current task description
        agent_state: Agent state

    Returns:
        MemoryContext
    """
    return MemoryContext(
        user_confirmed=user_confirmed,
        conversation_history=conversation_history or [],
        current_task=current_task,
        agent_state=agent_state or {}
    )

