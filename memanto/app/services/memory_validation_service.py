"""
Memory Validation Service
"""

from typing import Any

from moorcheh_sdk import MoorchehClient

from memanto.app.config import settings
from memanto.app.core import MemoryRecord
from memanto.app.utils.errors import ValidationError


class ValidationPolicy:
    """Memory validation policy to prevent poisoning."""

    @staticmethod
    def validate_memory(
        memory: MemoryRecord, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Validate memory before storage.

        Returns a dict with at least {"valid": bool, "action": str, "reason": str}.
        """
        context = context or {}

        # High-confidence memory types require validation.
        if memory.type in ["fact", "preference"]:
            return ValidationPolicy._validate_critical_memory(memory, context)

        return {"valid": True, "action": "store", "reason": "Non-critical memory type"}

    @staticmethod
    def _validate_critical_memory(
        memory: MemoryRecord, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate critical memory types (fact, preference)."""
        if context.get("user_confirmed"):
            return {"valid": True, "action": "store", "reason": "User confirmed"}

        if context.get("repetition_count", 0) >= 2:
            return {"valid": True, "action": "store", "reason": "Repeated content"}

        if memory.source == "tool" and memory.source_ref:
            return {"valid": True, "action": "store", "reason": "Tool-grounded"}

        if memory.confidence >= 0.9 and memory.source in ["system", "tool"]:
            return {
                "valid": True,
                "action": "store",
                "reason": "High confidence system source",
            }

        return {
            "valid": True,
            "action": "store_provisional",
            "reason": "Requires validation - storing as provisional",
        }

    @staticmethod
    def make_provisional(memory: MemoryRecord) -> MemoryRecord:
        """Convert memory to provisional status with short TTL."""
        memory.status = "provisional"
        memory.confidence = min(memory.confidence, 0.5)
        memory.set_ttl(3600)
        return memory


class MemoryValidationService:
    def __init__(self, moorcheh_client: MoorchehClient):
        self.client = moorcheh_client
        self.policy = ValidationPolicy()

    def validate_memory(
        self, memory: MemoryRecord, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Validate memory according to policy."""
        try:
            context = context or {}
            context.setdefault("repetition_count", 0)

            validation_result = self.policy.validate_memory(memory, context)

            if validation_result.get("action") == "store_provisional":
                memory = self.policy.make_provisional(memory)
                validation_result["memory"] = memory

            return validation_result

        except Exception as e:
            raise ValidationError(f"Validation failed: {e}")

    def _check_repetition(self, memory: MemoryRecord) -> int:
        """Check how many times similar content has been seen."""
        try:
            namespace = memory.get_scope().to_namespace()
            search_results = self.client.similarity_search.query(
                query=memory.content, namespaces=[namespace]
            )

            similar_count = 0
            for result in search_results.get("results", []):
                if result.get("score", 0) > 0.8:
                    similar_count += 1

            return similar_count

        except Exception:
            # If search fails, assume no repetition.
            return 0

    def is_critical_memory_type(self, memory_type: str) -> bool:
        """Check if memory type requires validation."""
        return memory_type in settings.REQUIRE_VALIDATION_FOR

    def get_validation_requirements(self, memory_type: str) -> dict[str, Any]:
        """Get validation requirements for memory type."""
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

        return {"requires_validation": False, "validation_options": []}
