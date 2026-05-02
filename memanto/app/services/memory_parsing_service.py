"""
Memory Parsing Service

Auto-detect memory type before ingestion.
"""

from memanto.app.config import settings
from memanto.app.core import MemoryRecord
from memanto.app.services.memory_export_service import MEMORY_TYPE_ORDER


class MemoryParsingService:
    def parse_memory(self, memory: MemoryRecord) -> MemoryRecord:
        """
        Auto-detect memory type.

        Rules:
        - Skip if disabled
        - Do not override existing type
        - Use rule-based classification
        """

        # 1. Config check
        if not settings.AUTO_PARSE_ENABLED:
            return memory

        # 2. Respect existing type
        if memory.type:
            return memory

        # 3. Rule-based detection
        detected = self._rule_based(memory.content)

        # 4. LLM fallback (only if rule-based fails and enabled)
        if not detected and settings.USE_LLM_FALLBACK:
            detected = self._llm_fallback(memory.content)

        if detected and detected in MEMORY_TYPE_ORDER:
            memory.type = detected

        return memory

    def _rule_based(self, text: str) -> str | None:
        if not text:
            return None
        text = text.lower().strip()

        if any(word in text for word in ["i like", "prefer", "favorite"]):
            return "preference"

        if any(word in text for word in ["must", "should", "always"]):
            return "instruction"

        if any(word in text for word in ["decided", "we chose", "selected"]):
            return "decision"

        if any(word in text for word in ["goal", "aim", "target"]):
            return "goal"

        if any(word in text for word in ["todo", "will do", "need to"]):
            return "commitment"

        if any(word in text for word in ["met", "meeting", "yesterday"]):
            return "event"

        if any(word in text for word in ["learned", "lesson"]):
            return "learning"

        if any(word in text for word in ["error", "failed", "bug"]):
            return "error"

        if any(word in text for word in ["team", "manager", "client"]):
            return "relationship"

        if any(word in text for word in ["context", "status", "currently"]):
            return "context"

        if any(word in text for word in ["noticed", "pattern", "often"]):
            return "observation"

        if any(word in text for word in ["file", "report", "document", "output"]):
            return "artifact"

        if " is " in text or " are " in text:
            return "fact"

        return None

    # LLM fallback (optional, disabled by default for low token usage)
    def _llm_fallback(self, text: str) -> str | None:
        """Fallback using LLM when rule-based fails.
        Placeholder for now. Can integrate Moorcheh/LLM later."""
        return None
