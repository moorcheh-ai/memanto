"""
Memory Validation Service
"""

from typing import Any

from moorcheh_sdk import MoorchehClient

from memanto.app.config import settings
from memanto.app.core import MemoryRecord, ValidationPolicy
from memanto.app.utils.errors import ValidationError


class MemoryValidationService:
    def __init__(self, moorcheh_client: MoorchehClient):
        self.client = moorcheh_client
        self.policy = ValidationPolicy()

    def validate_memory(
        self, memory: MemoryRecord, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Validate memory according to policy"""
        try:
            context = context or {}

            ## Add repetition check
            # if not context.get("repetition_count"):
            #     context["repetition_count"] = self._check_repetition(memory)
            context["repetition_count"] = 0

            # Validate using policy
            validation_result = self.policy.validate_memory(memory, context)

            # Apply provisional conversion if needed
            if validation_result.get("action") == "store_provisional":
                memory = self.policy.make_provisional(memory)
                validation_result["memory"] = memory

            return validation_result

        except Exception as e:
            raise ValidationError(f"Validation failed: {e}")

    def _check_repetition(self, memory: MemoryRecord) -> int:
        """Check how many times similar content has been seen"""
        try:
            # Search for similar content in the same namespace
            namespace = memory.get_scope().to_namespace()

            search_results = self.client.similarity_search.query(
                query=memory.content, namespaces=[namespace]
            )

            # Count high-similarity matches (score > 0.8)
            similar_count = 0
            for result in search_results.get("results", []):
                if result.get("score", 0) > 0.8:
                    similar_count += 1

            return similar_count

        except Exception:
            # If search fails, assume no repetition
            return 0

    def is_critical_memory_type(self, memory_type: str) -> bool:
        """Check if memory type requires validation"""
        return memory_type in settings.REQUIRE_VALIDATION_FOR

    def get_validation_requirements(self, memory_type: str) -> dict[str, Any]:
        """Get validation requirements for memory type"""
        if self.is_critical_memory_type(memory_type):
            return {
                "requires_validation": True,
                "validation_options": [
                    "user_confirmation",
                    "repetition_threshold_2",
                    "tool_grounded_source",
                    "high_confidence_system_source",
                ],
            }
        else:
            return {"requires_validation": False, "validation_options": []}
