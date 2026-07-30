--- a/memanto/app/services/memory_read_service.py
+++ b/memanto/app/services/memory_read_service.py
@@ -123,7 +123,7 @@
     def _apply_post_retrieval_filters(
         self, memories: List[MemoryRecord], as_of: datetime
     ) -> List[MemoryRecord]:
-        return [memory for memory in memories if memory.created_at <= as_of]
+        return [memory for memory in memories if memory.created_at <= as_of and memory.status == "active"]
 
     def _rank_memories(self, memories: List[MemoryRecord]) -> List[MemoryRecord]:
         # existing ranking logic remains unchanged
