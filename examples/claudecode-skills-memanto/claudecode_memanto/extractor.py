"""Extract decisions, preferences, and facts from skill conversation summaries."""

from __future__ import annotations

import re
from typing import Any


class DecisionExtractor:
    """Extracts structured information from skill conversation summaries.

    Uses pattern matching to identify architectural decisions, coding
    preferences, and codebase facts from natural language summaries.
    """

    # Patterns that indicate architectural decisions
    DECISION_PATTERNS = [
        r"(?:decided|chose|picked|selected|went with)\s+(?:to\s+)?(.+?)(?:\.|$)",
        r"(?:will|should|must|need to)\s+(?:use|implement|adopt)\s+(.+?)(?:\.|$)",
        r"(?:architecture|approach|strategy):\s*(.+?)(?:\.|$)",
        r"(?:instead of|rather than)\s+(.+?)(?:,|\.)\s*(?:we|I)\s+(?:will|use|chose)\s+(.+?)(?:\.|$)",
    ]

    # Patterns that indicate coding preferences
    PREFERENCE_PATTERNS = [
        r"(?:prefer|likes?|favor|favour)\s+(.+?)(?:\.|$)",
        r"(?:always|never|avoid)\s+(.+?)(?:\.|$)",
        r"(?:style|convention):\s*(.+?)(?:\.|$)",
        r"(?:use|using)\s+(\w+)\s+(?:instead of|rather than)\s+(\w+)",
    ]

    # Patterns that indicate codebase facts
    FACT_PATTERNS = [
        r"(?:uses?|relies? on|depends? on)\s+(.+?)(?:\.|$)",
        r"(?:is|are)\s+(?:built with|powered by|based on)\s+(.+?)(?:\.|$)",
        r"(?:configured|set up|initialized)\s+(?:with|to)\s+(.+?)(?:\.|$)",
        r"(?:API|endpoint|route)\s+(?:uses?|requires?)\s+(.+?)(?:\.|$)",
    ]

    def extract(self, summary: str) -> dict[str, list[str]]:
        """Extract structured information from a summary.

        Args:
            summary: Natural language summary of a skill session

        Returns:
            Dict with keys: decisions, preferences, facts
        """
        return {
            "decisions": self._extract_patterns(summary, self.DECISION_PATTERNS),
            "preferences": self._extract_patterns(summary, self.PREFERENCE_PATTERNS),
            "facts": self._extract_patterns(summary, self.FACT_PATTERNS),
        }

    def _extract_patterns(self, text: str, patterns: list[str]) -> list[str]:
        """Extract matches for a list of regex patterns."""
        results = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    # Handle patterns with multiple capture groups
                    result = " vs ".join(m.strip() for m in match if m.strip())
                else:
                    result = match.strip()

                # Filter out very short or very long results
                if 10 < len(result) < 200:
                    results.append(result)

        return results

    def extract_from_conversation(self, messages: list[dict[str, str]]) -> dict[str, list[str]]:
        """Extract from a full conversation (list of messages).

        Args:
            messages: List of dicts with 'role' and 'content' keys

        Returns:
            Dict with keys: decisions, preferences, facts
        """
        # Combine all assistant messages (they contain the decisions)
        assistant_text = " ".join(
            msg.get("content", "")
            for msg in messages
            if msg.get("role") == "assistant"
        )

        return self.extract(assistant_text)
