"""
Memanto-style Active Memory Backend (offline simulation).

Models Memanto's core architectural difference from Mem0:
- Instead of storing raw conversation turns, it extracts TYPED FACTS via LLM
- Each fact has a fixed topic key; newer facts for the same topic replace older ones
- On recall, only relevant facts are returned (not entire history)

This is a faithful offline simulation based on Memanto's actual extraction
pipeline (see memanto/app/services/conversation_memory_extraction_service.py).

Requires: ANTHROPIC_API_KEY environment variable.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict

import anthropic

from .base import BackendStats, count_tokens

_ALLOWED_TOPICS = frozenset({
    "programming_language", "editor_theme", "diet", "city",
    "job_title", "team_size", "communication_preference", "company_stack",
})

# Fixed topic vocabulary — consistent keys ensure reliable conflict resolution.
# Each topic maps to exactly one current fact; later sessions overwrite earlier ones.
_EXTRACT_PROMPT = """Extract durable personal facts from this conversation.
Return a JSON array. Each object must have:
  "topic": EXACTLY one of these fixed keys (choose the best match):
    programming_language | editor_theme | diet | city | job_title |
    team_size | communication_preference | company_stack
  "content": the current stated value, 1 sentence max

Rules:
- Use ONLY the exact topic keys listed above, no variations.
- If a fact updates or contradicts something from before, still emit it — the latest wins.
- Only extract facts a personal assistant would remember across sessions.
- Skip greetings, questions, filler, and assistant responses.
Return ONLY the JSON array, nothing else.

Conversation:
{conversation}"""

# Topic-to-query keyword mapping for relevance scoring
_TOPIC_QUERY_HINTS = {
    "programming_language": ["language", "programming", "code", "backend", "python", "go", "typescript"],
    "editor_theme": ["dark", "light", "mode", "theme", "editor"],
    "diet": ["diet", "eat", "food", "vegetarian", "vegan", "pescatarian", "fish"],
    "city": ["live", "city", "location", "where", "move", "berlin", "london"],
    "job_title": ["role", "title", "job", "position", "engineer", "lead", "manager"],
    "team_size": ["team", "size", "people", "manage", "report"],
    "communication_preference": ["communicate", "async", "slack", "voice", "call", "message"],
    "company_stack": ["company", "stack", "tech", "standardize"],
}


class MemantoBackend:
    name = "Memanto (simulation)"

    def __init__(self) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=api_key)
        # user_id → {topic: content} — latest fact per topic wins
        self._store: dict[str, dict[str, str]] = defaultdict(dict)
        self.stats = BackendStats()

    def add(self, messages: list[dict], user_id: str) -> None:
        """Extract typed facts and store them; newer entries overwrite stale ones."""
        conversation = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in messages
        )
        tokens_in = count_tokens(conversation)

        t0 = time.perf_counter()
        response = self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            temperature=0,
            messages=[{"role": "user", "content": _EXTRACT_PROMPT.format(conversation=conversation)}],
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        raw = response.content[0].text.strip()
        facts = self._parse_facts(raw)

        for fact in facts:
            if not isinstance(fact, dict):
                continue
            topic = fact.get("topic", "").strip().lower().replace(" ", "_")
            content = fact.get("content", "").strip()
            if topic in _ALLOWED_TOPICS and content:
                self._store[user_id][topic] = content

        self.stats.record_ingest(tokens_in, elapsed_ms)

    def search(self, query: str, user_id: str) -> str:
        """Return the top-3 most relevant facts from the active digest."""
        t0 = time.perf_counter()
        user_facts = self._store.get(user_id, {})
        if not user_facts:
            self.stats.record_retrieve(0, (time.perf_counter() - t0) * 1000)
            return ""

        query_words = set(re.sub(r"[^\w\s]", "", query.lower()).split())

        def relevance(item: tuple[str, str]) -> int:
            topic, content = item
            # Score against fixed hint words for this topic
            hint_words = set(_TOPIC_QUERY_HINTS.get(topic, []))
            content_words = set(content.lower().split())
            topic_words = set(topic.replace("_", " ").split())
            return len(query_words & (hint_words | content_words | topic_words))

        ranked = sorted(user_facts.items(), key=relevance, reverse=True)
        top = ranked[:3]
        result = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in top)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.stats.record_retrieve(count_tokens(result), elapsed_ms)
        return result

    def reset(self, user_id: str) -> None:
        self._store.pop(user_id, None)

    @staticmethod
    def _parse_facts(raw: str) -> list[dict]:
        text = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        try:
            result = json.loads(text)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            start, end = text.find("["), text.rfind("]")
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return []
