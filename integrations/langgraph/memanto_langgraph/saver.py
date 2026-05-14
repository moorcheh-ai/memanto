"""
Memanto Checkpointer for LangGraph

Provides persistent checkpointing for LangGraph agents using Memanto's
semantic storage as a backend.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Iterator
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    SerializerProtocol,
)

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)


class MemantoSaver(BaseCheckpointSaver):
    """
    LangGraph checkpoint saver using Memanto.

    Stores LangGraph state as 'artifact' type memories in Memanto,
    allowing for persistent state across threads and sessions.
    """

    client: SdkClient
    agent_id: str

    def __init__(
        self,
        client: SdkClient,
        agent_id: str,
        *,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)
        self.client = client
        self.agent_id = agent_id

        # Ensure agent is active
        try:
            self.client.activate_agent(agent_id)
        except Exception:
            # If activation fails, we assume the caller will handle it or it's already active
            pass

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Get a checkpoint tuple from Memanto."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")

        # Search for the checkpoint in Memanto
        # We use tags to filter by thread_id and checkpoint_id
        tags = [f"thread:{thread_id}"]
        if checkpoint_id:
            tags.append(f"checkpoint:{checkpoint_id}")

        query = f"LangGraph checkpoint for thread {thread_id}"
        if checkpoint_id:
            query += f" and checkpoint {checkpoint_id}"

        try:
            result = self.client.recall(
                agent_id=self.agent_id,
                query=query,
                limit=1,
                tags=tags,
                type=["artifact"],
            )

            memories = result.get("memories", [])
            if not memories:
                return None

            memory = memories[0]
            # Content contains the base64 encoded checkpoint
            checkpoint_data = base64.b64decode(memory["content"])
            checkpoint = self.serde.loads(checkpoint_data)

            # Metadata is stored in the memory tags or we can use another memory
            # For simplicity, we'll assume metadata was serialized with checkpoint or is empty
            metadata = {}  # In a full implementation, we'd store/retrieve metadata too

            return CheckpointTuple(
                config=config,
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=None,  # We don't support branching yet
            )
        except Exception as e:
            logger.error(f"Error retrieving checkpoint from Memanto: {e}")
            return None

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints from Memanto."""
        # This is a bit complex for semantic search, but we can search by thread_id tag
        thread_id = config["configurable"]["thread_id"] if config else "*"
        tags = [f"thread:{thread_id}"]

        try:
            result = self.client.recall(
                agent_id=self.agent_id,
                query=f"LangGraph checkpoints for thread {thread_id}",
                limit=limit or 10,
                tags=tags,
                type=["artifact"],
            )

            for memory in result.get("memories", []):
                checkpoint_data = base64.b64decode(memory["content"])
                checkpoint = self.serde.loads(checkpoint_data)

                yield CheckpointTuple(
                    config={
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_id": memory["id"],
                        }
                    },
                    checkpoint=checkpoint,
                    metadata={},
                    parent_config=None,
                )
        except Exception as e:
            logger.error(f"Error listing checkpoints from Memanto: {e}")

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Any,
    ) -> RunnableConfig:
        """Save a checkpoint to Memanto."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]

        # Serialize checkpoint
        checkpoint_data = self.serde.dumps(checkpoint)
        encoded_data = base64.b64encode(checkpoint_data).decode("utf-8")

        tags = [
            f"thread:{thread_id}",
            f"checkpoint:{checkpoint_id}",
            "langgraph_checkpoint",
        ]

        try:
            self.client.remember(
                agent_id=self.agent_id,
                memory_type="artifact",
                title=f"LangGraph Checkpoint: {thread_id} / {checkpoint_id}",
                content=encoded_data,
                confidence=1.0,
                tags=tags,
                source="langgraph-checkpointer",
            )

            return {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                }
            }
        except Exception as e:
            logger.error(f"Error saving checkpoint to Memanto: {e}")
            raise e
