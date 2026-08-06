"""LLM-as-judge scoring for before/after recall parity.

The question this answers is narrow: *did migrating cost the agent anything?*
So the judge never grades an answer against a hand-written gold answer -- it
grades the post-migration answer against the pre-migration one, question by
question. That framing matters, because it means a wrong-but-identical answer
scores as parity (the migration preserved behaviour, faithfully) while an
answer that quietly drops a transition date is marked down even if it reads
well.

Grading anything with an LLM invites the obvious objection, so the design
concedes as much ground as possible up front: the rubric is fixed and
verbatim in :data:`RUBRIC`, the raw prompt and raw reply for every pair are
written to disk next to the results, and each verdict carries the judge's own
one-line rationale. A reader who distrusts the score can recompute it.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-5"
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = (2, 5, 12)

# Scores are coarse on purpose. Finer gradations would imply a precision an LLM
# judge does not have, and the headline number is a mean over 12 questions.
RUBRIC = """\
1.00  equivalent — the AFTER answer preserves every substantive claim in the
      BEFORE answer: current value, prior value, and any transition date or
      reason that BEFORE supplied.
0.75  partial — the AFTER answer preserves the current value and the prior
      value, but loses a transition date, a reason, or a secondary detail.
0.50  degraded — the AFTER answer preserves only the current value and drops
      the historical/superseded side of the answer entirely.
0.25  contradicted — the AFTER answer asserts something that conflicts with
      BEFORE, or presents a superseded value as if it were current.
0.00  missing — the AFTER answer is empty, refuses, or contains no relevant
      information.

Grade ONLY on information preservation relative to BEFORE. Do not reward the
AFTER answer for better prose, and do not penalise it for being shorter. If
BEFORE itself failed to answer and AFTER also fails in the same way, that is
1.00 (parity preserved), not 0.00.
"""

_PROMPT = """\
You are auditing a memory-system migration. An agent's memories were moved from
Graphiti (a temporal knowledge graph) into Memanto. The SAME question was asked
before and after the migration.

Score how well the AFTER answer preserves the information in the BEFORE answer.

RUBRIC
{rubric}

QUESTION
{question}

WHAT THIS QUESTION IS PROBING
{probes}

BEFORE (Graphiti, pre-migration)
{before}

AFTER (Memanto, post-migration)
{after}

Reply with a single JSON object and nothing else:
{{"score": <one of 1.0, 0.75, 0.5, 0.25, 0.0>,
  "verdict": "<equivalent|partial|degraded|contradicted|missing>",
  "rationale": "<one sentence, max 30 words>"}}
"""

_VERDICTS = {"equivalent", "partial", "degraded", "contradicted", "missing"}


class JudgeError(RuntimeError):
    """Raised when the judge cannot produce a verdict after retries."""


@dataclass
class JudgeVerdict:
    question_id: str
    question: str
    probes: str
    before: str
    after: str
    score: float
    verdict: str
    rationale: str
    raw_reply: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def judge_model() -> str:
    return os.getenv("JUDGE_MODEL", "").strip() or DEFAULT_JUDGE_MODEL


def build_client() -> Any:
    """Create an Anthropic client, failing loudly if the key is absent."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise JudgeError(
            "ANTHROPIC_API_KEY is not set — the parity score requires a real "
            "judge call. Set it in .env and re-run; the pipeline deliberately "
            "does not fall back to a hard-coded rubric."
        )
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise JudgeError(f"anthropic SDK not installed: {exc}") from exc
    return anthropic.Anthropic(api_key=api_key)


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a reply that may be fenced or padded."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object in judge reply: {text[:200]!r}")
    return json.loads(cleaned[start : end + 1])


def _coerce_verdict(payload: dict[str, Any]) -> tuple[float, str, str]:
    score = float(payload["score"])
    if score not in (0.0, 0.25, 0.5, 0.75, 1.0):
        raise ValueError(f"score {score} is not on the rubric scale")
    verdict = str(payload.get("verdict", "")).strip().lower()
    if verdict not in _VERDICTS:
        raise ValueError(f"verdict {verdict!r} is not a rubric verdict")
    return score, verdict, str(payload.get("rationale", "")).strip()


def judge_pair(client: Any, question: Any, before: str, after: str) -> JudgeVerdict:
    """Score one before/after pair, retrying transient failures with backoff."""
    prompt = _PROMPT.format(
        rubric=RUBRIC,
        question=question.question,
        probes=question.probes,
        before=(before or "").strip() or "(no answer produced)",
        after=(after or "").strip() or "(no answer produced)",
    )

    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.messages.create(
                model=judge_model(),
                max_tokens=400,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            )
            score, verdict, rationale = _coerce_verdict(_extract_json(raw))
            return JudgeVerdict(
                question_id=question.id,
                question=question.question,
                probes=question.probes,
                before=before,
                after=after,
                score=score,
                verdict=verdict,
                rationale=rationale,
                raw_reply=raw,
            )
        except Exception as exc:
            last_error = exc
            if attempt < len(BACKOFF_SECONDS):
                time.sleep(BACKOFF_SECONDS[attempt])

    raise JudgeError(
        f"judge failed for {question.id} after {MAX_ATTEMPTS} attempts: "
        f"{type(last_error).__name__}: {last_error}"
    )


def parity_percentage(verdicts: list[JudgeVerdict]) -> float:
    if not verdicts:
        return 0.0
    return round(100.0 * sum(v.score for v in verdicts) / len(verdicts), 1)


def verdict_counts(verdicts: list[JudgeVerdict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for verdict in verdicts:
        counts[verdict.verdict] = counts.get(verdict.verdict, 0) + 1
    return dict(sorted(counts.items()))


def _cell(text: str, limit: int = 240) -> str:
    """Flatten an answer into something that survives a markdown table cell."""
    flat = " ".join((text or "").split()).replace("|", "\\|")
    return (flat[: limit - 3] + "...") if len(flat) > limit else flat or "_(none)_"


def render_markdown(verdicts: list[JudgeVerdict], *, model: str) -> str:
    """Render the results table that goes straight into the PR description."""
    parity = parity_percentage(verdicts)
    counts = verdict_counts(verdicts)

    lines = [
        "# Round-trip validation — Graphiti vs. Memanto",
        "",
        f"**Recall parity: {parity}%** across {len(verdicts)} golden questions.",
        "",
        f"Judge: `{model}` (Anthropic API), temperature 0. Every question was asked "
        "against the live Graphiti graph before migration and against the Memanto "
        "agent after migration; the judge scored information preservation only.",
        "",
        "| # | Verdict | Score | What it probes | Judge rationale |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for verdict in verdicts:
        lines.append(
            f"| {verdict.question_id} | {verdict.verdict} | {verdict.score:.2f} | "
            f"{verdict.probes} | {_cell(verdict.rationale, 160)} |"
        )

    lines += [
        "",
        "## Verdict distribution",
        "",
        "| Verdict | Count |",
        "| --- | ---: |",
    ]
    lines += [f"| {name} | {count} |" for name, count in counts.items()]

    lines += ["", "## Full before/after transcript", ""]
    for verdict in verdicts:
        lines += [
            f"### {verdict.question_id} — {verdict.question}",
            "",
            f"- **Probes:** {verdict.probes}",
            f"- **Before (Graphiti):** {_cell(verdict.before, 1200)}",
            f"- **After (Memanto):** {_cell(verdict.after, 1200)}",
            f"- **Judge:** {verdict.verdict} ({verdict.score:.2f}) — {verdict.rationale}",
            "",
        ]

    return "\n".join(lines)
