from memanto.models.memory import Memory, MemoryBatch, MemoryDelete, MemoryDeleteBatch
from memanto.services.session import SessionService
from memanto.utils.logging import logger

class DirectClient:
    def __init__(self):
        self.session_service = SessionService()

    def create_memory(self, memory: Memory) -> Memory:
        try:
            result = self.session_service.create_memory(memory)
            if not result:
                raise Exception("Failed to create memory")

            # Best-effort local logging after successful remote commit
            try:
                self.session_service.log_memory_locally(memory)
            except Exception as e:
                logger.warning(f"Failed to update local session summary: {str(e)}")

            return result
        except Exception as e:
            logger.error(f"Error creating memory: {str(e)}")
            raise

    def create_memory_batch(self, memory_batch: MemoryBatch) -> MemoryBatch:
        try:
            result = self.session_service.create_memory_batch(memory_batch)
            if not result:
                raise Exception("Failed to create memory batch")

            # Best-effort local logging after successful remote commit
            try:
                self.session_service.log_memory_batch_locally(memory_batch)
            except Exception as e:
                logger.warning(f"Failed to update local session summary for batch: {str(e)}")

            return result
        except Exception as e:
            logger.error(f"Error creating memory batch: {str(e)}")
            raise

    def delete_memory(self, memory_delete: MemoryDelete) -> MemoryDelete:
        try:
            result = self.session_service.delete_memory(memory_delete)
            if not result:
                raise Exception("Failed to delete memory")

            # Best-effort local logging after successful remote commit
            try:
                self.session_service.log_memory_deletion_locally(memory_delete)
            except Exception as e:
                logger.warning(f"Failed to update local session summary for deletion: {str(e)}")

            return result
        except Exception as e:
            logger.error(f"Error deleting memory: {str(e)}")
            raise

    def delete_memory_batch(self, memory_delete_batch: MemoryDeleteBatch) -> MemoryDeleteBatch:
        try:
            result = self.session_service.delete_memory_batch(memory_delete_batch)
            if not result:
                raise Exception("Failed to delete memory batch")

            # Best-effort local logging after successful remote commit
            try:
                self.session_service.log_memory_batch_deletion_locally(memory_delete_batch)
            except Exception as e:
                logger.warning(f"Failed to update local session summary for batch deletion: {str(e)}")

            return result
        except Exception as e:
            logger.error(f"Error deleting memory batch: {str(e)}")
            raise