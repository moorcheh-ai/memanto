"""
Memory Parsing Service

Auto-detect memory type before ingestion.
"""

import re
from dataclasses import dataclass
from typing import ClassVar, cast

from memanto.app.config import settings
from memanto.app.constants import MemoryType
from memanto.app.core import MemoryRecord
from memanto.app.services.memory_export_service import MEMORY_TYPE_ORDER


@dataclass(frozen=True)
class MemoryRule:
    pattern: re.Pattern[str]
    score: int


class MemoryParsingService:
    MIN_RULE_SCORE: ClassVar[int] = 3

    # Tie-break toward durable, user-actionable memories when multiple weak
    # signals appear in the same sentence.
    TYPE_PRIORITY: ClassVar[dict[str, int]] = {
        memory_type: index for index, memory_type in enumerate(MEMORY_TYPE_ORDER)
    }

    RULES: ClassVar[dict[str, list[MemoryRule]]] = {
        "preference": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (
                    r"\b(?:i|we|they|he|she|user|client|customer)\s+(?:really\s+)?(?:like|likes|love|loves|prefer|prefers|enjoy|enjoys|favor|favors)\b",
                    4,
                ),
                (r"\b(?:my|our|their|his|her)\s+favou?rite\b", 4),
                (
                    r"\bfavou?rite\s+(?:is|are|tool|language|framework|color|colour|theme)\b",
                    4,
                ),
                (
                    r"\b(?:would rather|rather use|prefer to|prefers to|preference for|likes to)\b",
                    4,
                ),
                (r"\b(?:dislike|dislikes|hate|hates|avoid using|not a fan of)\b", 3),
                (
                    r"\b(?:works best for|feels better with|is more comfortable with)\b",
                    3,
                ),
            ]
        ],
        "instruction": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (
                    r"\bmust\s+(?!say\b)(?:be|do|have|fix|complete|finish|ensure|avoid|follow|use|stop|start|finalize|implement|update|deploy)\b",
                    5,
                ),
                (r"\b(?:always|never)\b", 5),
                (r"\b(?:should|shall|required to|requirement|mandatory)\b", 4),
                (r"\b(?:do not|don't|avoid|make sure to|ensure|remember to)\b", 4),
                (
                    r"\b(?:use|prefer|follow|keep|include|exclude)\s+.+\b(?:by default|going forward|from now on|for future|whenever)\b",
                    5,
                ),
                (r"\b(?:rule|guideline|constraint|policy)\b", 3),
            ]
        ],
        "decision": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (
                    r"\b(?:decided|decision|chose|chosen|selected|settled on|went with|going with)\b",
                    5,
                ),
                (r"\b(?:agreed to|agreed on|approved|rejected|accepted)\b", 4),
                (r"\b(?:we|i|team|client)\s+(?:will use|picked|standardized on)\b", 4),
            ]
        ],
        "goal": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (r"\b(?:goal|aim|objective|target|milestone|north star)\b", 5),
                (
                    r"\b(?:trying to|want to achieve|working toward|focus is to|intends? to)\b",
                    4,
                ),
                (
                    r"\b(?:increase|reduce|improve|ship|launch|finish)\s+.+\b(?:by|before|this quarter|this month|next sprint)\b",
                    4,
                ),
            ]
        ],
        "commitment": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (r"\b(?:todo|to-do|action item|follow up|next step|due)\b", 5),
                (
                    r"\b(?:i|we|they|he|she)\s+(?:will|shall|need to|needs to|have to|has to|promised to|committed to)\b",
                    4,
                ),
                (
                    r"\b(?:assign|assigned|responsible for|owner is|by tomorrow|by eod|by end of day)\b",
                    4,
                ),
                (r"\b(?:remind me to|don't forget to|need a reminder)\b", 5),
            ]
        ],
        "event": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (
                    r"\b(?:met|meeting|call|sync|standup|demo|workshop|interview|conversation)\b",
                    4,
                ),
                (
                    r"\b(?:yesterday|today|last night|last week|this morning|earlier|on \d{4}-\d{2}-\d{2})\b",
                    3,
                ),
                (
                    r"\b(?:happened|occurred|launched|released|deployed|discussed|mentioned|told me|said)\b",
                    3,
                ),
            ]
        ],
        "learning": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (
                    r"\b(?:learned|lesson|takeaway|discovered|realized|found out|understood)\b",
                    5,
                ),
                (
                    r"\b(?:insight|key point|root cause|what worked|what did not work)\b",
                    4,
                ),
                (r"\b(?:next time|in hindsight)\b", 3),
            ]
        ],
        "error": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (
                    r"\b(?:error|failed|failure|bug|exception|traceback|crash|outage|incident)\b",
                    5,
                ),
                (
                    r"\b(?:broken|regression|doesn't work|does not work|not working|timed out|timeout)\b",
                    4,
                ),
                (r"\b(?:blocked by|problem|issue|wrong|incorrect|misclassified)\b", 3),
            ]
        ],
        "relationship": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (
                    r"\b(?:team|manager|client|customer|stakeholder|partner|vendor|coworker|colleague)\b",
                    4,
                ),
                (
                    r"\b(?:reports to|works with|collaborates with|mentor|mentee|lead for|owner of)\b",
                    5,
                ),
                (
                    r"\b(?:(?-i:[A-Z][a-z]+)|user|client|customer|manager|teammate|stakeholder)\s+(?:said|mentioned|asked|prefers|likes|needs)\b",
                    2,
                ),
            ]
        ],
        "context": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (
                    r"\b(?:context|status|currently|right now|now|at the moment|background)\b",
                    4,
                ),
                (
                    r"\b(?:in progress|pending|blocked|waiting on|state is|session summary)\b",
                    4,
                ),
                (r"\b(?:we are on|this project uses|the repo has|environment is)\b", 3),
            ]
        ],
        "observation": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (r"\b(?:noticed|observed|pattern|trend|recurring|repeatedly)\b", 5),
                (
                    r"\b(?:often|usually|tends to|tend to|frequently|sometimes|rarely)\b",
                    5,
                ),
                (r"\b(?:appears to|seems to|looks like|keeps happening)\b", 3),
            ]
        ],
        "artifact": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (
                    r"\b(?:file|report|document|doc|output|artifact|attachment|spreadsheet|slide|deck)\b",
                    4,
                ),
                (
                    r"\b(?:created|generated|exported|uploaded|downloaded|saved)\s+.+\b(?:file|report|document|output|artifact)\b",
                    5,
                ),
                (
                    r"\b[\w./-]+\.(?:py|md|txt|json|yaml|yml|csv|xlsx|pdf|pptx|png|jpg|jpeg|html|css|js|ts|tsx)\b",
                    5,
                ),
                (r"https?://\S+", 4),
            ]
        ],
        "fact": [
            MemoryRule(re.compile(pattern, re.IGNORECASE), score)
            for pattern, score in [
                (
                    r"\b(?:is|are|was|were)\s+(?:called|named|located|based|enabled|disabled|available|unavailable|true|false)\b",
                    4,
                ),
                (r"\b(?:has|have|contains|supports|uses|runs on|depends on)\b", 1),
                (
                    r"\b(?:version|port|api key|endpoint|url|path|email|phone|address)\s+(?:is|=|:)\b",
                    4,
                ),
                (
                    r"\b[A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)?\s+(?:is|are|was|were)\s+[\w .,'/-]+$",
                    3,
                ),
            ]
        ],
    }

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
            memory.type = cast(MemoryType, detected)

        return memory

    def _rule_based(self, text: str) -> str | None:
        if not text:
            return None
        normalized = re.sub(r"\s+", " ", text).strip()
        # Avoid classifying very short / weak inputs
        if len(normalized.split()) < 3:
            return None
        scores = self._score_types(normalized)
        # If only "fact" is detected with weak signal, treat as unknown
        # BUT allow strong factual patterns (like URLs, endpoints, "is/are" statements)
        if set(scores.keys()) == {"fact"}:
            fact_score = scores.get("fact", 0)

            # allow strong fact signals
            strong_fact_patterns = [
                r"https?://\S+",
                r"\b(?:endpoint|url|api key|path|email|phone|address)\b",
                r"\b(?:is|are|was|were)\b",
            ]

            if fact_score < 4 and not any(
                re.search(p, text, re.IGNORECASE) for p in strong_fact_patterns
            ):
                return None
        if not scores:
            return None

        # pick best candidate
        detected, score = max(
            scores.items(),
            key=lambda item: (item[1], -self.TYPE_PRIORITY.get(item[0], 999)),
        )

        # reject low-confidence
        if score < self.MIN_RULE_SCORE:
            return None

        # refined ambiguity guard:
        # only block when signals are weak and very close
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) > 1:
            second_score = sorted_scores[1]
            # allow strong signals (score >= 4) to pass even if tied
            if (score - second_score) <= 1 and score < 4:
                return None

        return detected

    def _score_types(self, text: str) -> dict[str, int]:
        scores: dict[str, int] = {}
        for memory_type, rules in self.RULES.items():
            score = sum(rule.score for rule in rules if rule.pattern.search(text))
            if score:
                scores[memory_type] = score
        return scores

    # LLM fallback (optional, disabled by default for low token usage)
    def _llm_fallback(self, text: str) -> str | None:
        """Fallback using LLM when rule-based fails.
        Placeholder for now. Keep rule parsing deterministic until the LLM
        design supports structured output, multi-label signals, and validation.
        """
        return None
