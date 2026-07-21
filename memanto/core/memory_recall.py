import logging
from typing import List, Dict, Any, Optional, Union
from moorcheh import Moorcheh
from moorcheh.query import Query
from moorcheh.result import Result
from moorcheh.error import MoorchehError

logger = logging.getLogger(__name__)

class MemoryRecall:
    def __init__(self, moorcheh: Moorcheh):
        self.moorcheh = moorcheh

    def recall_memories(
        self,
        query: str,
        type: Optional[Union[str, List[str]]] = None,
        limit: int = 10,
        confidence: Optional[float] = None,
        ttl: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recall memories from the Moorcheh database.

        Args:
            query: The search query string.
            type: Optional memory type or list of memory types to filter by.
            limit: Maximum number of memories to return.
            confidence: Optional minimum confidence threshold.
            ttl: Optional maximum time-to-live (in seconds) for memories.
            context: Optional additional context for the query.

        Returns:
            List of dictionaries representing the recalled memories.

        Raises:
            MoorchehError: If there's an error during the recall process.
        """
        try:
            # Validate and de-duplicate requested types
            if isinstance(type, list):
                types = list(set(t for t in type if t))  # Remove duplicates and empty strings
                if not types:
                    type = None
            else:
                types = [type] if type else []

            # If no types or single type, use the existing single-query path
            if not types or len(types) == 1:
                moorcheh_query = Query(query)
                if types:
                    moorcheh_query.add_filter(f"#memory_type:{types[0]}")
                if confidence is not None:
                    moorcheh_query.add_filter(f"#confidence:>{confidence}")
                if ttl is not None:
                    moorcheh_query.add_filter(f"#ttl:<{ttl}")
                if context:
                    for key, value in context.items():
                        moorcheh_query.add_filter(f"#{key}:{value}")

                results = self.moorcheh.search(moorcheh_query, limit=limit)
                return self._process_results(results)

            # For multiple types, run one filtered search per type
            all_results = []
            for memory_type in types:
                moorcheh_query = Query(query)
                moorcheh_query.add_filter(f"#memory_type:{memory_type}")
                if confidence is not None:
                    moorcheh_query.add_filter(f"#confidence:>{confidence}")
                if ttl is not None:
                    moorcheh_query.add_filter(f"#ttl:<{ttl}")
                if context:
                    for key, value in context.items():
                        moorcheh_query.add_filter(f"#{key}:{value}")

                results = self.moorcheh.search(moorcheh_query, limit=limit)
                all_results.extend(results)

            # Merge, score-sort, and de-duplicate the union
            return self._process_results(all_results, limit=limit)

        except MoorchehError as e:
            logger.error(f"Error recalling memories: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error recalling memories: {e}")
            raise MoorchehError(f"Unexpected error recalling memories: {e}")

    def _process_results(self, results: List[Result], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Process Moorcheh results into a list of dictionaries.

        Args:
            results: List of Moorcheh Result objects.
            limit: Optional maximum number of results to return.

        Returns:
            List of dictionaries representing the processed results.
        """
        # Convert results to dictionaries and remove duplicates by ID
        unique_results = {}
        for result in results:
            memory_id = result.get("id")
            if memory_id not in unique_results:
                unique_results[memory_id] = {
                    "id": memory_id,
                    "content": result.get("content", ""),
                    "score": result.get("score", 0.0),
                    "metadata": result.get("metadata", {}),
                }

        # Sort by score in descending order
        sorted_results = sorted(
            unique_results.values(),
            key=lambda x: x["score"],
            reverse=True,
        )

        # Apply limit if specified
        if limit is not None:
            sorted_results = sorted_results[:limit]

        return sorted_results