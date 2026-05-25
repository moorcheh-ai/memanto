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
    """Rule pattern and weight used for memory type classification."""

    pattern: re.Pattern[str]
    score: int


class MemoryParsingService:
    """Classify memories into supported memory types before storage."""

    MIN_RULE_SCORE: ClassVar[int] = 3
    STRONG_FACT_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in [
            r"https?://[^\s<>()\[\]{},;:\"']*[^\s<>()\[\]{},;:\"'.,!?]",
            r"\b(?:endpoint|url|api key|path|email|phone|address)\b",
            r"\b(?:is|are|was|were)\b",
        ]
    ]

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
                (r"\b(?:remind me to|don't forget to|need a reminder)\b", 6),
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
                    r"\b(?:errors?|fail(?:s|ed|ing|ure)?|bugs?|exceptions?|tracebacks?|crash(?:e[ds]|ing)?|outages?|incidents?)\b",
                    5,
                ),
                # CamelCase exception/error class names, e.g. NullPointerException,
                # ValueError. Case-sensitive so it does not match words like "mirror".
                (r"(?-i:[A-Z][A-Za-z0-9]*(?:Exception|Error))\b", 5),
                (
                    r"\b(?:broken|broke|breaks|breaking|regressions?|doesn't work|does not work|not working|timed out|timeouts?)\b",
                    4,
                ),
                (
                    r"\b(?:blocked by|problems?|issues?|wrong|incorrect|misclassified)\b",
                    3,
                ),
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
                    r"(?<![\w./-])[\w.-]+(?:/[\w.-]+)*\.(?:py|md|txt|json|yaml|yml|csv|xlsx|pdf|pptx|png|jpg|jpeg|html|css|js|ts|tsx)(?![\w.-])",
                    5,
                ),
                (
                    r"https?://[^\s<>()\[\]{},;:\"']*[^\s<>()\[\]{},;:\"'.,!?]",
                    4,
                ),
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
        Auto-detect and assign a memory type.

        Rules:
        - Respect an explicit type if one is already set.
        - Skip detection entirely when auto-parsing is disabled.
        - Fall back to ``"fact"`` when classification is inconclusive, so a
          memory is never stored without a type.
        """

        # 1. Respect existing type
        if memory.type:
            return memory

        # 2. Config check
        if not settings.AUTO_PARSE_ENABLED:
            memory.type = cast(MemoryType, "fact")
            return memory

        # 3. Rule-based detection (deterministic)
        detected = self._rule_based(memory.content)

        if detected and detected in MEMORY_TYPE_ORDER:
            memory.type = cast(MemoryType, detected)
        else:
            memory.type = cast(MemoryType, "fact")

        return memory

    def _rule_based(self, text: str) -> str | None:
        """Return the best rule-based type for *text*, or None if not confident.

        Classification favours the single strongest signal (the ``max`` of the
        matched rule scores) over the raw sum, so a decisive intent phrase such
        as "remind me to" outranks several weaker topical keywords. The
        cumulative score and canonical priority act only as tie-breakers.
        """

        if not text:
            return None
        normalized = re.sub(r"\s+", " ", text).strip()
        # Avoid classifying very short / weak inputs
        if len(normalized.split()) < 3:
            return None
        scores = self._score_types(normalized)
        if not scores:
            return None

        # If only "fact" matched with a weak signal, treat as unknown unless a
        # strong factual pattern (URL, endpoint, "is/are" statement) is present.
        if set(scores) == {"fact"}:
            _, fact_max = scores["fact"]
            if fact_max < 4 and not any(
                pattern.search(text) for pattern in self.STRONG_FACT_PATTERNS
            ):
                return None

        ranked = sorted(
            scores.items(),
            key=lambda item: (
                item[1][1],  # strongest single signal
                item[1][0],  # cumulative score
                -self.TYPE_PRIORITY.get(item[0], 999),
            ),
            reverse=True,
        )

        best_type, (best_total, best_max) = ranked[0]

        # Reject low-confidence matches (no sufficiently strong single signal).
        if best_max < self.MIN_RULE_SCORE:
            return None

        # Ambiguity guard: only block when the top two signals are weak and tied.
        if len(ranked) > 1:
            _, (second_total, second_max) = ranked[1]
            if (
                best_max < 4
                and best_max == second_max
                and (best_total - second_total) <= 1
            ):
                return None

        return best_type

    def _score_types(self, text: str) -> dict[str, tuple[int, int]]:
        """Return ``{type: (cumulative_score, strongest_single_score)}`` per match."""

        scores: dict[str, tuple[int, int]] = {}
        for memory_type, rules in self.RULES.items():
            matched = [rule.score for rule in rules if rule.pattern.search(text)]
            if matched:
                scores[memory_type] = (sum(matched), max(matched))
        return scores
