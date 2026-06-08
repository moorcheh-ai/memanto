"""
LLM-as-a-Judge accuracy evaluation.

Uses Claude Haiku to score whether retrieved memory correctly answers a query
relative to the golden answer. Returns a score from 0-3:
  3 = correct and complete
  2 = partially correct
  1 = retrieved but wrong/stale answer
  0 = no useful information retrieved
"""

from __future__ import annotations

import os

import anthropic

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


_JUDGE_SYSTEM = (
    "You are a strict evaluator of AI memory system retrieval quality. "
    "Score retrieved memory against a golden answer on a 0-3 scale."
)

_JUDGE_TEMPLATE = """You are evaluating memory retrieval for the query: "{query}"

The GOLDEN correct answer is: "{golden}"

The memory system returned the following retrieved text:
---
{retrieved}
---

Score the retrieval on this 0-3 scale:
3 = Retrieved text directly and correctly answers the query, consistent with the golden answer
2 = Retrieved text partially answers the query or is mostly correct with minor gaps
1 = Retrieved text is related but contains stale, wrong, or contradictory information
0 = Retrieved text is irrelevant or empty — cannot answer the query

Respond with ONLY a single digit (0, 1, 2, or 3) followed by a one-sentence explanation.
Format: <score>|<explanation>
Example: 3|The retrieved memory correctly identifies horror as the current preference."""


def judge(query: str, golden: str, retrieved_text: str) -> dict:
    """
    Returns {"score": int, "explanation": str, "input_tokens": int, "output_tokens": int}
    """
    if not retrieved_text or retrieved_text.strip() == "":
        return {"score": 0, "explanation": "No content retrieved", "input_tokens": 0, "output_tokens": 0}

    prompt = _JUDGE_TEMPLATE.format(query=query, golden=golden, retrieved=retrieved_text[:2000])
    client = _get_client()

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=80,
        system=_JUDGE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    try:
        score_str, explanation = raw.split("|", 1)
        score = int(score_str.strip())
    except (ValueError, IndexError):
        score = 0
        explanation = raw

    return {
        "score": max(0, min(3, score)),
        "explanation": explanation.strip(),
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
    }
