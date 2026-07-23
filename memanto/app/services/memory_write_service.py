import logging
from typing import List, Dict, Any

from memanto.app.models.memory import Memory
from memanto.app.services.base_service import BaseService

logger = logging.getLogger(__name__)

class MemoryWriteService(BaseService):
    def __init__(self, config):
        super().__init__(config)

    def batch_store_memories(
        self,
        namespace: str,
        memories: List[Memory],
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Store a batch of memories in the database.

        Args:
            namespace: The namespace to store the memories in.
            memories: The list of memories to store.
            batch_size: The number of memories to store in each batch.

        Returns:
            A dictionary containing the status of the batch upload.
        """
        try:
            # Split the memories into batches
            batches = [memories[i:i + batch_size] for i in range(0, len(memories), batch_size)]

            # Store each batch of memories
            results = []
            for batch in batches:
                batch_result = self._db_client.store_memories(namespace, batch)
                results.append(batch_result)

            # Check the results of each batch upload
            upload_status = "success"
            for result in results:
                if result.get("status") != "success":
                    upload_status = "partial_success"
                    break

            # Verify the results of each batch upload
            for result in results:
                if "results" not in result:
                    upload_status = "unconfirmed"
                    break

                for memory_result in result["results"]:
                    if memory_result.get("status") != "success":
                        upload_status = "unconfirmed"
                        break

            return {
                "status": upload_status,
                "results": results,
            }
        except Exception as e:
            logger.error(f"Failed to store memories: {e}")
            raise