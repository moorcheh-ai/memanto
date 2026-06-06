import asyncio
from typing import Dict, Any
from benchmarks.evaluators.base import MemoryEvaluator
from memanto import Memanto


class MemantoEvaluator(MemoryEvaluator):
    """Evaluator for Memanto memory framework."""
    
    def __init__(self):
        super().__init__("Memanto")
        self.memanto = None
    
    async def initialize(self) -> None:
        """Initialize Memanto."""
        self.memanto = Memanto()
        # Initialize with default configuration
        await self.memanto.initialize()
    
    async def remember(self, user_id: str, data: str) -> Dict[str, Any]:
        """Store memory data in Memanto."""
        try:
            result = await self.memanto.remember(user_id, data)
            return {
                "success": True,
                "data": result,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }
    
    async def recall(self, user_id: str, query: str) -> Dict[str, Any]:
        """Recall memory data from Memanto."""
        try:
            result = await self.memanto.recall(user_id, query)
            return {
                "success": True,
                "data": result,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }
    
    async def answer(self, user_id: str, query: str) -> Dict[str, Any]:
        """Generate answer from Memanto memory."""
        try:
            result = await self.memanto.answer(user_id, query)
            return {
                "success": True,
                "data": result,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }
    
    async def cleanup(self) -> None:
        """Cleanup Memanto resources."""
        if self.memanto:
            await self.memanto.cleanup()