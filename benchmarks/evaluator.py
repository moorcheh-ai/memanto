"""
LLM-as-a-Judge evaluator for retrieval accuracy.
"""

import os
from openai import OpenAI


JUDGE_SYSTEM_PROMPT = """You are an expert evaluator for AI memory systems.
You will be given:
1. A QUERY that was used to search a memory system
2. A GOLDEN ANSWER (the ideal/correct response)
3. A set of RETRIEVED MEMORIES from the system

Score the retrieval quality on a scale from 0.0 to 1.0:
- 1.0: Retrieved memories fully contain the golden answer information
- 0.7-0.9: Retrieved memories mostly contain relevant info, minor gaps
- 0.4-0.6: Partial match, some relevant info but significant gaps
- 0.1-0.3: Poor match, mostly irrelevant
- 0.0: Completely irrelevant or no useful information

Respond with ONLY a JSON object: {"score": <float>, "reasoning": "<brief explanation>"}"""


class LLMEvaluator:
    """Evaluates retrieval quality using LLM-as-a-judge with keyword fallback."""
    """Evaluates retrieval accuracy using an LLM judge."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or os.environ.get("JUDGE_MODEL", "gpt-4o")
        self.client = OpenAI(api_key=key) if key else None

    def score_retrieval(
        self,
        query: str,
        golden_answer: str,
        retrieved_memories: list[str],
    ) -> tuple[float, str]:
        """Score a retrieval against a golden answer. Returns (score, reasoning)."""
        if not self.client:
            # Fallback: simple keyword overlap scoring
            return self._keyword_score(golden_answer, retrieved_memories)

        memories_text = "\n---\n".join(
            f"Memory {i+1}: {m}" for i, m in enumerate(retrieved_memories)
        )
        user_prompt = f"""QUERY: {query}

GOLDEN ANSWER: {golden_answer}

RETRIEVED MEMORIES:
{memories_text}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            import json
            content = response.choices[0].message.content
            parsed = json.loads(content)
            return float(parsed.get("score", 0.0)), parsed.get("reasoning", "")
        except Exception as e:
            return self._keyword_score(golden_answer, retrieved_memories)

    @staticmethod
    def _keyword_score(
        golden: str, memories: list[str]
    ) -> tuple[float, str]:
        """Fallback keyword-overlap scoring when no LLM judge is available."""
        golden_words = set(golden.lower().split())
        if not golden_words:
            return 0.0, "Empty golden answer"

        all_memory_text = " ".join(memories).lower()
        memory_words = set(all_memory_text.split())
        overlap = golden_words & memory_words
        score = len(overlap) / len(golden_words) if golden_words else 0.0
        return min(score, 1.0), f"Keyword overlap: {len(overlap)}/{len(golden_words)}"
