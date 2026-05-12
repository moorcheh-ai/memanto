"""
Context Summarization Service

Leverages Moorcheh's AI answer generation to compress multiple memories
into concise summaries, reducing context window usage for agents.
"""

from datetime import datetime, timedelta
from typing import Any, cast

from moorcheh_sdk import MoorchehClient

from memanto.app.config import settings
from memanto.app.constants import ScopeType
from memanto.app.core import MemoryRecord
from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.utils.errors import MemoryError
from memanto.app.utils.ids import generate_memory_id


class ContextSummarizationService:
    """Service for summarizing and compressing agent memory context"""

    def __init__(self, moorcheh_client: MoorchehClient):
        self.client = moorcheh_client
        self.write_service = MemoryWriteService(moorcheh_client)
        self.read_service = MemoryReadService(moorcheh_client)

    def summarize_scope_context(
        self,
        scope_type: str,
        scope_id: str,
        actor_id: str,
        summary_title: str = "Context Summary",
        memory_types: list[str] | None = None,
        max_memories: int = 50,
        link_to_originals: bool = True,
    ) -> dict[str, Any]:
        """
        Summarize all memories in a scope into a compressed context summary

        Args:
            scope_type: Type of scope (user, workspace, agent, session)
            scope_id: Scope identifier
            actor_id: ID of actor requesting summarization
            summary_title: Title for the summary memory
            memory_types: Optional filter for memory types to include
            max_memories: Maximum number of memories to summarize
            link_to_originals: Whether to store references to original memories

        Returns:
            Dict with summary memory details
        """
        try:
            # Step 1: Retrieve memories from the scope
            search_result = self.read_service.search_memories(
                query="",  # Empty query to get all
                scope_type=scope_type,
                scope_id=scope_id,
                type=memory_types,
                limit=max_memories,
            )

            memories = search_result.get("results", [])

            if not memories:
                raise MemoryError("No memories found in scope to summarize")

            # Step 2: Build context for AI summarization
            memory_texts = []
            memory_ids = []

            for memory in memories:
                memory_ids.append(memory.get("id"))
                mem_type = memory.get("type", "unknown")
                text = memory.get("text", "")
                created = memory.get("created_at", "")

                # Format each memory for context
                formatted = f"[{mem_type.upper()}] {text}"
                if created:
                    formatted += f" (created: {created})"
                memory_texts.append(formatted)

            # Step 3: Generate AI summary using Moorcheh
            from memanto.app.constants import ScopeType
            from memanto.app.core import create_memory_scope

            scope = create_memory_scope(cast(ScopeType, scope_type), scope_id)
            namespace = scope.to_namespace()

            summary_prompt = f"""Summarize the following {len(memories)} memories into a concise context summary.
Focus on key facts, decisions, preferences, and important context. Preserve critical information while being concise.

Memories to summarize:
{chr(10).join(memory_texts)}

Provide a clear, organized summary that an AI agent could use to understand the context."""

            # Use Moorcheh's answer.generate for summarization
            answer_result = self.client.answer.generate(
                namespace=namespace,
                query=summary_prompt,
                ai_model=settings.ANSWER_MODEL,
                top_k=max_memories,
            )

            summary_text = answer_result.get("answer", "")

            if not summary_text:
                raise MemoryError("Failed to generate summary - empty response from AI")

            # Step 4: Create summary memory
            summary_metadata = {
                "summarized_count": len(memories),
                "summarized_types": list(
                    {m.get("type") for m in memories if m.get("type")}
                ),
                "summary_date": datetime.utcnow().isoformat(),
            }

            # Add links to original memories if requested
            if link_to_originals:
                summary_metadata["original_memory_ids"] = memory_ids

            resolved_scope_type = cast(
                ScopeType,
                scope_type
                if scope_type in {"user", "workspace", "agent", "session"}
                else "agent",
            )
            summary_memory = MemoryRecord(
                id=generate_memory_id(),
                type="context",  # Use 'context' type for summaries
                title=summary_title,
                content=summary_text[:500],  # Truncate to max content length
                scope_type=resolved_scope_type,
                scope_id=scope_id,
                actor_id=actor_id,
                source="system",
                source_ref="context_summarization",
                confidence=0.9,  # High confidence for AI-generated summaries
                tags=["summary", "ai-generated", "context-compression"],
            )

            # Store the summary
            result = self.write_service.store_memory(
                summary_memory,
                context={"user_confirmed": True},  # Auto-confirm system summaries
            )

            return {
                "summary_id": result["id"],
                "namespace": result["namespace"],
                "status": result["status"],
                "summarized_count": len(memories),
                "original_memory_ids": memory_ids if link_to_originals else [],
                "summary_preview": summary_text[:200] + "..."
                if len(summary_text) > 200
                else summary_text,
            }

        except Exception as e:
            raise MemoryError(f"Failed to summarize context: {e}")

    def summarize_by_memory_ids(
        self,
        memory_ids: list[str],
        namespace: str,
        scope_type: str,
        scope_id: str,
        actor_id: str,
        summary_title: str = "Custom Summary",
    ) -> dict[str, Any]:
        """
        Summarize specific memories by their IDs

        Args:
            memory_ids: List of memory IDs to summarize
            namespace: Namespace containing the memories
            scope_type: Type of scope
            scope_id: Scope identifier
            actor_id: ID of actor requesting summarization
            summary_title: Title for the summary

        Returns:
            Dict with summary memory details
        """
        try:
            # Retrieve all specified memories
            memories = []
            for mem_id in memory_ids:
                memory = self.read_service.get_memory(mem_id, namespace)
                if memory:
                    memories.append(memory)

            if not memories:
                raise MemoryError("No valid memories found to summarize")

            # Build summarization context
            memory_texts = [
                f"[{m.get('type', 'unknown').upper()}] {m.get('text', '')}"
                for m in memories
            ]

            summary_prompt = f"""Summarize these {len(memories)} related memories into a concise summary:

{chr(10).join(memory_texts)}

Create a clear, organized summary preserving key information."""

            # Generate summary
            answer_result = self.client.answer.generate(
                namespace=namespace,
                query=summary_prompt,
                ai_model=settings.ANSWER_MODEL,
                top_k=len(memories),
            )

            summary_text = answer_result.get("answer", "")

            if not summary_text:
                raise MemoryError("Failed to generate summary")

            resolved_scope_type = cast(
                ScopeType,
                scope_type
                if scope_type in {"user", "workspace", "agent", "session"}
                else "agent",
            )
            # Create and store summary memory
            summary_memory = MemoryRecord(
                id=generate_memory_id(),
                type="context",
                title=summary_title,
                content=summary_text[:500],
                scope_type=resolved_scope_type,
                scope_id=scope_id,
                actor_id=actor_id,
                source="system",
                source_ref="custom_summarization",
                confidence=0.9,
                tags=["summary", "ai-generated", "custom"],
            )

            result = self.write_service.store_memory(
                summary_memory, context={"user_confirmed": True}
            )

            return {
                "summary_id": result["id"],
                "namespace": result["namespace"],
                "status": result["status"],
                "summarized_count": len(memories),
                "original_memory_ids": memory_ids,
                "summary_text": summary_text,
            }

        except Exception as e:
            raise MemoryError(f"Failed to summarize specified memories: {e}")

    def compress_conversation_history(
        self,
        scope_type: str,
        scope_id: str,
        actor_id: str,
        days_to_compress: int = 7,
        keep_recent_count: int = 10,
    ) -> dict[str, Any]:
        """
        Compress old conversation context while keeping recent memories intact

        This is useful for long-running agent sessions where old context
        needs to be compressed to reduce token usage.

        Args:
            scope_type: Type of scope
            scope_id: Scope identifier
            actor_id: Actor identifier
            days_to_compress: Compress memories older than this many days
            keep_recent_count: Number of recent memories to keep uncompressed

        Returns:
            Dict with compression results
        """
        try:
            # Calculate cutoff date
            cutoff_date = (
                datetime.utcnow() - timedelta(days=days_to_compress)
            ).isoformat()

            # Get old memories to compress
            old_memories_result = self.read_service.search_memories(
                query="",
                scope_type=scope_type,
                scope_id=scope_id,
                created_before=cutoff_date,
                limit=100,
            )

            old_memories = old_memories_result.get("results", [])

            if len(old_memories) <= keep_recent_count:
                return {
                    "compressed": False,
                    "reason": f"Only {len(old_memories)} old memories found, below keep threshold",
                    "summary_id": None,
                }

            # Summarize old memories
            summary_result = self.summarize_scope_context(
                scope_type=scope_type,
                scope_id=scope_id,
                actor_id=actor_id,
                summary_title=f"Conversation History Summary (up to {days_to_compress} days ago)",
                max_memories=len(old_memories),
                link_to_originals=True,
            )

            return {
                "compressed": True,
                "summary_id": summary_result["summary_id"],
                "compressed_count": summary_result["summarized_count"],
                "compression_date": datetime.utcnow().isoformat(),
                "original_memory_ids": summary_result["original_memory_ids"],
            }

        except Exception as e:
            raise MemoryError(f"Failed to compress conversation history: {e}")
