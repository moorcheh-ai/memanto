"""
Memory Validation Service

Runs a new memory through ValidationPolicy before it's persisted. This is
the implementation memory_write_service.store_memory() actually calls -
the module of the same name under app/legacy/ references a class that no
longer exists and can't be imported; it's left alone here since nothing
else depends on it.
"""

from typing import Any

from memanto.app.core import MemoryRecord, ValidationPolicy
from memanto.app.utils.errors import ValidationError


class MemoryValidationService:
    def __init__(self, moorcheh_client):
        self.client = moorcheh_client
        self.policy = ValidationPolicy()

    def validate_memory(
        self, memory: MemoryRecord, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Validate memory according to policy"""
        try:
            context = dict(context or {})
            context.setdefault("repetition_count", self._check_repetition(memory))

            validation_result = self.policy.validate_memory(memory, context)

            if validation_result.get("action") == "store_provisional":
                memory = self.policy.make_provisional(memory)
                validation_result["memory"] = memory

            return validation_result

        except Exception as e:
            raise ValidationError(f"Validation failed: {e}")

    def _check_repetition(self, memory: MemoryRecord) -> int:
        """How many times has something like this already been said?"""
        try:
            namespace = memory.namespace()
            search_results = self.client.similarity_search.query(
                query=memory.content, namespaces=[namespace], top_k=10
            )

            similar_count = 0
            for result in search_results.get("results", []):
                if result.get("id") == memory.id:
                    continue
                if result.get("score", 0) > 0.8:
                    similar_count += 1

            return similar_count

        except Exception:
            # If the repetition check itself fails, don't block the write
            # over it - just treat it as unconfirmed.
            return 0
