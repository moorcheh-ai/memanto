"""
LLM-as-Judge evaluator.

For each evaluation query, both systems produce an answer (a concatenation
of their retrieved memories). The judge LLM scores each answer on:

  - Accuracy (0–5):  Does it match the golden answer?
  - Staleness (0–5): Does it avoid stale/superseded signals?
  - Precision (0–5): Is it concise and relevant, or polluted with noise?

Total score: 0–15 per query per system.

The judge prompt is identical for both systems — the only variable is
the system's recalled text.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are a strict, impartial evaluator for an AI memory system benchmark.

You will be given:
1. A query asked to a memory system
2. The golden answer (ground truth)
3. Stale signals — phrases that should NOT appear (they represent outdated info)
4. Current signals — phrases that SHOULD appear (they represent current accurate info)
5. The memory system's answer (raw recalled text)

Score the answer on three dimensions, each 0–5:

ACCURACY (0–5):
  5 = Answer is fully correct and complete, matches golden answer
  4 = Mostly correct, minor omissions
  3 = Partially correct, key facts present but incomplete
  2 = Barely correct, major facts missing or wrong
  1 = Almost entirely wrong
  0 = Completely wrong or empty

STALENESS_AVOIDANCE (0–5):
  5 = No stale signals present, answer reflects current state only
  4 = One minor stale signal present but clearly contextualised
  3 = One or two stale signals present without context
  2 = Multiple stale signals, answer is clearly polluted
  1 = Answer is dominated by stale/outdated information
  0 = Answer entirely reflects old state, current state ignored

PRECISION (0–5):
  5 = Answer is concise and directly relevant, no noise
  4 = Minor irrelevant details present
  3 = Some noise but key information still accessible
  2 = Significant noise making answer hard to use
  1 = Mostly noise with little useful signal
  0 = No useful information, pure noise

Respond with ONLY a valid JSON object in this exact format:
{
  "accuracy": <int 0-5>,
  "staleness_avoidance": <int 0-5>,
  "precision": <int 0-5>,
  "reasoning": "<one sentence per dimension, separated by | >"
}
"""

JUDGE_USER_PROMPT = """Query: {query}

Golden answer: {golden_answer}

Stale signals to avoid: {stale_signals}

Current signals that should be present: {current_signals}

Memory system answer:
{recalled_answer}

Score this answer."""


@dataclass
class EvalScore:
    """Scores for a single query against one system."""

    system: str
    query_id: str
    query: str
    accuracy: int
    staleness_avoidance: int
    precision: int
    total: int
    reasoning: str
    recalled_answer: str


class LLMJudge:
    """
    Wraps an LLM to act as a benchmark judge.

    Uses the OpenRouter API (compatible with OpenAI SDK) so any model
    can be used without changing code. Defaults to claude-3-5-haiku
    which is fast and cheap.

    Environment variables:
        OPENROUTER_API_KEY  (required)
        JUDGE_MODEL         (optional, default: anthropic/claude-3-5-haiku)
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        from openai import OpenAI  # type: ignore[import]

        _key = (api_key or os.environ.get("OPENROUTER_API_KEY", "")).strip()
        if not _key:
            raise ValueError("OPENROUTER_API_KEY is required for the LLM judge")

        self.model = model or os.environ.get("JUDGE_MODEL", "openai/gpt-4o-mini")
        self._client = OpenAI(
            api_key=_key,
            base_url="https://openrouter.ai/api/v1",
        )
        logger.debug("Judge model: %s", self.model)

    def score(
        self,
        system_name: str,
        query_id: str,
        query: str,
        golden_answer: str,
        stale_signals: list[str],
        current_signals: list[str],
        recalled_answer: str,
    ) -> EvalScore:
        """Run the LLM judge and return structured scores."""

        user_msg = JUDGE_USER_PROMPT.format(
            query=query,
            golden_answer=golden_answer,
            stale_signals=", ".join(stale_signals),
            current_signals=", ".join(current_signals),
            recalled_answer=recalled_answer[:4000],  # truncate for safety
        )

        for attempt in range(3):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.0,
                    max_tokens=300,
                    seed=42,
                )
                raw = response.choices[0].message.content.strip()
                # Strip markdown code fences if present
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                # Extract just the JSON object — ignore anything after the closing brace
                import re as _re

                json_match = _re.search(r"\{[^{}]*\}", raw, _re.DOTALL)
                if not json_match:
                    raise ValueError(f"No JSON object found in response: {raw[:200]}")
                parsed = json.loads(json_match.group())
                accuracy = max(0, min(5, int(parsed["accuracy"])))
                staleness_avoidance = max(0, min(5, int(parsed["staleness_avoidance"])))
                precision = max(0, min(5, int(parsed["precision"])))
                return EvalScore(
                    system=system_name,
                    query_id=query_id,
                    query=query,
                    accuracy=accuracy,
                    staleness_avoidance=staleness_avoidance,
                    precision=precision,
                    total=accuracy + staleness_avoidance + precision,
                    reasoning=parsed.get("reasoning", ""),
                    recalled_answer=recalled_answer,
                )
            except Exception as exc:
                logger.warning("Judge attempt %d failed: %s", attempt + 1, exc)
                time.sleep(2**attempt)

        # Fallback: return zero scores if all attempts fail
        logger.error(
            "Judge failed for %s / %s — returning zeros", system_name, query_id
        )
        return EvalScore(
            system=system_name,
            query_id=query_id,
            query=query,
            accuracy=0,
            staleness_avoidance=0,
            precision=0,
            total=0,
            reasoning="Judge call failed",
            recalled_answer=recalled_answer,
        )
