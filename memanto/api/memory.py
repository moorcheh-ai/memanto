from fastapi import APIRouter, HTTPException, status
from memanto.models.memory import Memory, MemoryBatch, MemoryDelete, MemoryDeleteBatch
from memanto.services.session import SessionService
from memanto.utils.logging import logger

router = APIRouter()

@router.post("/memory", response_model=Memory)
async def create_memory(memory: Memory):
    try:
        session_service = SessionService()
        result = session_service.create_memory(memory)
        if not result:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create memory")

        # Best-effort local logging after successful remote commit
        try:
            session_service.log_memory_locally(memory)
        except Exception as e:
            logger.warning(f"Failed to update local session summary: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Error creating memory: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/memory/batch", response_model=MemoryBatch)
async def create_memory_batch(memory_batch: MemoryBatch):
    try:
        session_service = SessionService()
        result = session_service.create_memory_batch(memory_batch)
        if not result:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create memory batch")

        # Best-effort local logging after successful remote commit
        try:
            session_service.log_memory_batch_locally(memory_batch)
        except Exception as e:
            logger.warning(f"Failed to update local session summary for batch: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Error creating memory batch: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete("/memory", response_model=MemoryDelete)
async def delete_memory(memory_delete: MemoryDelete):
    try:
        session_service = SessionService()
        result = session_service.delete_memory(memory_delete)
        if not result:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete memory")

        # Best-effort local logging after successful remote commit
        try:
            session_service.log_memory_deletion_locally(memory_delete)
        except Exception as e:
            logger.warning(f"Failed to update local session summary for deletion: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Error deleting memory: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete("/memory/batch", response_model=MemoryDeleteBatch)
async def delete_memory_batch(memory_delete_batch: MemoryDeleteBatch):
    try:
        session_service = SessionService()
        result = session_service.delete_memory_batch(memory_delete_batch)
        if not result:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete memory batch")

        # Best-effort local logging after successful remote commit
        try:
            session_service.log_memory_batch_deletion_locally(memory_delete_batch)
        except Exception as e:
            logger.warning(f"Failed to update local session summary for batch deletion: {str(e)}")

        return result
    except Exception as e:
        logger.error(f"Error deleting memory batch: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))