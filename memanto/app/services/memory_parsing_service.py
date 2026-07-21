from typing import Any, cast, List, Optional
from memanto.app.core import MemoryRecord
from memanto.app.services.memory_parsing_service import MemoryParsingService

class MemoryParsingService:
    def __init__(self):
        self.negated_preference_keywords = [
            "do not", "don't", "does not", "doesn't",
            "did not", "didn't", "no longer", "never",
            "can't stand", "prefer not to"
        ]

    def parse_memory(self, memory: MemoryRecord) -> None:
        content = memory.content.lower()
        if memory.type is None:
            if any(keyword in content for keyword in self.negated_preference_keywords):
                memory.type = "preference"
            elif "do not" in content or "don't" in content:
                memory.type = "instruction"
            else:
                memory.type = "fact"