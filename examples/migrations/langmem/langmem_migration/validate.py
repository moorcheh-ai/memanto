"""Round-trip recall-parity check: does memory survive the move?

Uses the Q&A set in ``conversation.py``. Each question is asked twice and the
answers compared:

* **before** -- against the source LangMem store, using LangMem's own semantic
  ``store.search`` to retrieve candidate memories.
* **after** -- against the migrated Memanto memories. Two backends:
    - ``bundle`` (default, offline): retrieve over the generated OKF bundle's
      memory bodies. Checks that the content survived the migration without
      needing a Moorcheh key.
    - ``memanto`` (``--after memanto``): query the live Memanto/Moorcheh agent
      the bundle was imported into (needs ``MOORCHEH_API_KEY`` + an active
      agent). Checks retrieval parity on the real backend.

Grading is deterministic keyword matching (an ``expect_any`` hit with no
``forbid`` hit = correct), so the harness runs with no LLM judge. A wrong
answer on a memory that should have been updated (e.g. still saying "pytest"
after the switch to Vitest, or "pairing with Priya" after she moved teams)
fails the check -- that's exactly the kind of regression this is meant to catch.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .conversation import GOLDEN_QA, USER_ID, GoldenQA


@dataclass
class QAResult:
    question: str
    retrieved: str
    passed: bool
    reason: str


def _grade(qa: GoldenQA, retrieved_text: str) -> tuple[bool, str]:
    text = retrieved_text.lower()
    for bad in qa.forbid:
        if bad.lower() in text:
            return False, f"stale/contradicted term present: {bad!r}"
    for good in qa.expect_any:
        if good.lower() in text:
            return True, f"matched {good!r}"
    return False, "no expected term found"


def _run(qa_set: list[GoldenQA], retriever: Callable[[str], str]) -> list[QAResult]:
    results: list[QAResult] = []
    for qa in qa_set:
        retrieved = retriever(qa.question)
        passed, reason = _grade(qa, retrieved)
        results.append(QAResult(qa.question, retrieved, passed, reason))
    return results


# --------------------------------------------------------------------------
# Retrievers
# --------------------------------------------------------------------------


def _lexical_retrieve(corpus: list[str], question: str, k: int = 3) -> str:
    """Rank memories by query-term overlap and return the top ``k`` joined.

    A dependency-free stand-in for semantic search so the offline harness
    measures both sides (LangMem before, Memanto after) on identical footing:
    did the *content* survive the migration and stay findable?
    """
    q_terms = {w for w in _tokens(question) if len(w) > 2}
    scored = sorted(corpus, key=lambda c: len(q_terms & set(_tokens(c))), reverse=True)
    return "\n".join(scored[:k])


def langmem_retriever(
    store, user_id: str = USER_ID, k: int = 3
) -> Callable[[str], str]:
    """Retrieve over the LangMem store.

    When the store has a semantic index (``--extract live``), use LangMem's own
    ``store.search(query=...)``. Otherwise fall back to the shared lexical
    ranker over the stored contents, so the offline "before" number is a fair
    peer of the offline "after" number.
    """
    namespace = ("memories", user_id)
    indexed = getattr(store, "index_config", None) is not None

    def retrieve(question: str) -> str:
        if indexed:
            try:
                hits = store.search(namespace, query=question, limit=k)
                return "\n".join((h.value or {}).get("content", "") for h in hits)
            except (TypeError, ValueError):
                pass
        corpus = [(h.value or {}).get("content", "") for h in store.search(namespace)]
        return _lexical_retrieve(corpus, question, k)

    return retrieve


def bundle_retriever(export: dict[str, Any]) -> Callable[[str], str]:
    """Retrieve over the migrated memory *content* (offline parity check)."""
    corpus = [
        str((m.get("value") or {}).get("content") or "")
        for m in export.get("memories", []) or []
    ]

    def retrieve(question: str) -> str:
        return _lexical_retrieve(corpus, question, k=3)

    return retrieve


def memanto_retriever(agent_id: str, k: int = 5) -> Callable[[str], str]:
    """Retrieve from a live Memanto agent (needs MOORCHEH_API_KEY)."""
    from memanto.cli.client.sdk_client import SdkClient  # imported lazily

    client = SdkClient(api_key=os.environ["MOORCHEH_API_KEY"])

    def retrieve(question: str) -> str:
        result = client.recall(agent_id=agent_id, query=question, limit=k)
        memories = (result or {}).get("memories", []) or []
        return "\n".join(
            str(m.get("content") or m.get("title") or "") for m in memories
        )

    return retrieve


def _tokens(text: str) -> list[str]:
    return "".join(c.lower() if c.isalnum() else " " for c in text).split()


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def parity_report(before: list[QAResult], after: list[QAResult]) -> dict[str, Any]:
    b_pass = sum(r.passed for r in before)
    a_pass = sum(r.passed for r in after)
    n = len(before)
    rows = []
    for b, a in zip(before, after, strict=False):
        rows.append(
            {
                "question": b.question,
                "before": b.passed,
                "after": a.passed,
                "parity": b.passed == a.passed,
                "after_reason": a.reason,
            }
        )
    return {
        "n": n,
        "before_pass": b_pass,
        "after_pass": a_pass,
        "before_pct": round(100 * b_pass / n, 1) if n else 0.0,
        "after_pct": round(100 * a_pass / n, 1) if n else 0.0,
        "parity_pct": round(100 * sum(r["parity"] for r in rows) / n, 1) if n else 0.0,
        "rows": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Round-trip recall parity",
        "",
        f"- Questions: **{report['n']}**",
        f"- Recall before migration (LangMem): **{report['before_pass']}/{report['n']}** "
        f"({report['before_pct']}%)",
        f"- Recall after migration (Memanto): **{report['after_pass']}/{report['n']}** "
        f"({report['after_pct']}%)",
        f"- Before/after parity: **{report['parity_pct']}%**",
        "",
        "| Question | Before | After | Parity |",
        "| --- | :---: | :---: | :---: |",
    ]
    for row in report["rows"]:
        b = "PASS" if row["before"] else "FAIL"
        a = "PASS" if row["after"] else "FAIL"
        p = "OK" if row["parity"] else "DRIFT"
        lines.append(f"| {row['question']} | {b} | {a} | {p} |")
    lines.append("")
    return "\n".join(lines)


def validate(
    store,
    export: dict[str, Any],
    after: str = "bundle",
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Run before/after parity and return the report dict."""
    before = _run(GOLDEN_QA, langmem_retriever(store))

    if after == "memanto":
        aid = agent_id or os.environ.get("MEMANTO_AGENT_ID") or "langmem-import"
        after_results = _run(GOLDEN_QA, memanto_retriever(aid))
    else:
        after_results = _run(GOLDEN_QA, bundle_retriever(export))

    return parity_report(before, after_results)
