"""LLM-as-Judge scorer with offline deterministic fallback.

Scoring modes
-------------
1. LLM mode (requires OPENAI_API_KEY or OPENROUTER_API_KEY):
   Uses GPT-4o-mini (cheap, fast) with a strict structured prompt.
   Returns a float 0.0–1.0.

2. Offline mode (default when no key):
   Keyword presence check — deterministic, always reproducible.
   Returns 1.0 if expected_keyword in answer (case-insensitive), else 0.0.
"""
from __future__ import annotations

import os
import re


def score_answer(
    context: str,
    query: str,
    expected_keyword: str,
    explanation: str,
    stale_keyword: str | None = None,
) -> float:
    """Score how well `context` answers `query`.

    Returns 0.0–1.0.
    - Offline: keyword-presence check with optional stale-penalty.
    - LLM mode: GPT-4o-mini structured prompt (set OPENAI_API_KEY).

    Staleness penalty:
      If stale_keyword is provided and present in context while
      expected_keyword is ABSENT, score = 0.25 (wrong answer detected).
      If both are present, score = 0.5 (ambiguous / mixed context).
      This rewards active-memory systems that purge stale facts.
    """
    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    if openai_key:
        try:
            return _llm_score(context, query, expected_keyword, explanation, openai_key)
        except Exception:
            pass
    return _keyword_score(context, expected_keyword, stale_keyword)


def _keyword_score(
    context: str,
    expected_keyword: str,
    stale_keyword: str | None = None,
) -> float:
    """Keyword-presence score with staleness penalty.

    Score table:
      expected present, stale absent  → 1.0  (perfect)
      expected present, stale present → 0.5  (ambiguous, stale leaked)
      expected absent,  stale absent  → 0.0  (miss)
      expected absent,  stale present → 0.0  (wrong answer)
    """
    if not context or not expected_keyword:
        return 0.0
    ctx = context.lower()
    has_expected = expected_keyword.lower() in ctx
    has_stale = bool(stale_keyword) and stale_keyword.lower() in ctx

    if has_expected and not has_stale:
        return 1.0
    if has_expected and has_stale:
        return 0.5   # correct answer found but stale context leaked
    return 0.0


def _llm_score(
    context: str,
    query: str,
    expected_keyword: str,
    explanation: str,
    api_key: str,
) -> float:
    """Use GPT-4o-mini to score whether context correctly answers query."""
    import json
    import urllib.request

    prompt = (
        "You are a strict evaluator for a memory-system benchmark.\n"
        f"Query: {query}\n"
        f"Expected ground truth (keyword): '{expected_keyword}'\n"
        f"Ground truth explanation: {explanation}\n\n"
        f"Memory context retrieved:\n{context}\n\n"
        "Does the memory context contain information that correctly addresses the query "
        "and includes the expected keyword or its synonym?\n"
        "Reply with a JSON object: {\"score\": <0.0 to 1.0>, \"reason\": \"<one sentence>\"}"
    )

    base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    if "openrouter" in (os.getenv("OPENAI_API_BASE") or ""):
        base_url = "https://openrouter.ai/api/v1"
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 100,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    content = data["choices"][0]["message"]["content"]
    match = re.search(r'"score"\s*:\s*([0-9.]+)', content)
    if match:
        return min(1.0, max(0.0, float(match.group(1))))
    return 0.0
