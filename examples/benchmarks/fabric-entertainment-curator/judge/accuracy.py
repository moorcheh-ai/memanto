"""LLM-as-judge accuracy scorer.

When ``OPENAI_API_KEY`` is available, uses GPT-4o-mini (temperature=0,
seed=42) to score whether retrieved memories correctly represent the
user's CURRENT state/preferences.

Falls back to a keyword-overlap heuristic when the key is not set — this
allows the benchmark to run in fully offline/CI mode without any API cost.

Scoring rubric (LLM judge):
    1.0  All retrieved information is accurate and current.
    0.5  Mix of current and outdated information.
    0.0  Information is stale, incorrect, or missing the current preference.
"""

from __future__ import annotations

import json
import os
import re

_JUDGE_SYSTEM = """\
You are an expert evaluator for AI agent memory retrieval systems.

Your task: score whether the RETRIEVED MEMORIES correctly represent the
user's CURRENT preferences (not past/stale ones).

Rules:
- Score 1.0 if retrieved memories are accurate and reflect the CURRENT state.
- Score 0.5 if memories are a mix of current and outdated information.
- Score 0.0 if memories are stale, incorrect, or missing key current facts.

Respond with only valid JSON: {"score": 0.0} or {"score": 0.5} or {"score": 1.0}
Then add a one-sentence explanation on the same line after the JSON.
"""


def _keyword_judge(retrieved: list[str], ground_truth: str) -> float:
    """Keyword-overlap fallback judge (no API key required).

    Computes the fraction of content words from *ground_truth* that appear
    anywhere in the joined *retrieved* text.
    """
    _STOP = {
        "and", "the", "for", "not", "but", "with", "that", "this",
        "from", "have", "been", "they", "their", "also", "some",
    }

    def _content(t: str) -> set[str]:
        return {
            w for w in re.sub(r"[^\w\s]", "", t.lower()).split()
            if len(w) > 3 and w not in _STOP
        }

    gt_words = _content(ground_truth)
    if not gt_words or not retrieved:
        return 0.0
    combined = " ".join(retrieved).lower()
    hits = sum(1 for w in gt_words if w in combined)
    return min(1.0, hits / len(gt_words))


def judge_accuracy(
    query: str,
    retrieved: list[str],
    ground_truth: str,
    client=None,
) -> float:
    """Score retrieval accuracy.

    Args:
        query:        The recall query issued to the backend.
        retrieved:    Memory strings returned by the backend.
        ground_truth: What a perfect memory system should surface.
        client:       An ``openai.OpenAI`` client instance, or ``None`` to
                      use the keyword fallback.

    Returns:
        Float in ``[0.0, 1.0]``.
    """
    if not retrieved:
        return 0.0

    if client is None or not os.environ.get("OPENAI_API_KEY"):
        return _keyword_judge(retrieved, ground_truth)

    prompt = (
        f"Query: {query}\n\n"
        f"Ground truth (current state): {ground_truth}\n\n"
        "Retrieved memories:\n"
        + "\n".join(f"  - {m}" for m in retrieved)
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        seed=42,
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        max_tokens=80,
    )

    text = resp.choices[0].message.content or ""
    m = re.search(r'"score"\s*:\s*([0-9.]+)', text)
    return float(m.group(1)) if m else 0.5
