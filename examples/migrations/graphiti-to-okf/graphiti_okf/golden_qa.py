"""The golden question set used for round-trip validation.

These are deliberately not "can you find a fact" questions. A flat chat-log
adapter that throws away ``valid_at``/``invalid_at`` can still answer "what
database do you use". It cannot answer "what did you use *before*, and when did
you switch" -- and that is the entire claim this migration makes. So ten of the
twelve questions require both sides of a contradiction plus its transition
date.

``Q09`` and ``Q10`` are controls: facts that were never contradicted. If parity
collapses on those too, the problem is retrieval in general rather than
temporal fidelity in particular, and the results table should say so.

``expected_signals`` is a cheap deterministic tripwire, not the score. The
actual grade comes from the LLM judge in :mod:`graphiti_okf.judge`; the signals
just make it obvious at a glance when an answer has gone badly off the rails.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoldenQuestion:
    id: str
    question: str
    probes: str
    expected_signals: tuple[str, ...] = field(default_factory=tuple)


GOLDEN_QUESTIONS: tuple[GoldenQuestion, ...] = (
    GoldenQuestion(
        id="Q01",
        question=(
            "What is my primary datastore today, and what was it before? "
            "When did it change?"
        ),
        probes="superseded fact + replacement + transition date",
        expected_signals=("clickhouse", "postgres"),
    ),
    GoldenQuestion(
        id="Q02",
        question=(
            "What did I use to prefer for infrastructure as code before I changed "
            "my mind, what do I prefer now, and when did I switch?"
        ),
        probes="reversed preference + transition date",
        expected_signals=("terraform", "pulumi"),
    ),
    GoldenQuestion(
        id="Q03",
        question="Which cloud region do I deploy to now, which one did I use before, and why did I move?",
        probes="superseded fact + stated rationale",
        expected_signals=("us-east-1", "eu-west-1"),
    ),
    GoldenQuestion(
        id="Q04",
        question="How many engineers are on my team now, and how many were there at kickoff?",
        probes="numeric fact that was revised upward",
        expected_signals=("9", "4"),
    ),
    GoldenQuestion(
        id="Q05",
        question="Who is my current employer, who did I work for before, and what are my job titles?",
        probes="superseded employment fact + role change",
        expected_signals=("halcyon", "northwind"),
    ),
    GoldenQuestion(
        id="Q06",
        question=(
            "When was the v1 beta originally supposed to ship, when did it actually "
            "ship, and why did it slip?"
        ),
        probes="revised commitment + causal explanation",
        expected_signals=("q1", "q2"),
    ),
    GoldenQuestion(
        id="Q07",
        question="Is Postgres still part of my stack? If so, in what role?",
        probes="partial supersession — demoted, not removed",
        expected_signals=("auth",),
    ),
    GoldenQuestion(
        id="Q08",
        question="What production incident have I had, and what did I change afterwards?",
        probes="event recall + follow-up action",
        expected_signals=("clickhouse", "disk"),
    ),
    GoldenQuestion(
        id="Q09",
        question="What are my hard rules about how Python code is written and reviewed?",
        probes="control — a stable preference that was never contradicted",
        expected_signals=("type", "400"),
    ),
    GoldenQuestion(
        id="Q10",
        question="What have I committed to delivering by October?",
        probes="control — a current commitment with a deadline",
        expected_signals=("soc 2", "audit"),
    ),
    GoldenQuestion(
        id="Q11",
        question=(
            "List every technology or plan choice I have reversed, with what it was "
            "before, what it is now, and roughly when each reversal happened."
        ),
        probes="full temporal sweep — the hardest question in the set",
        expected_signals=("pulumi", "clickhouse", "us-east-1"),
    ),
    GoldenQuestion(
        id="Q12",
        question="What do I use to manage Python packages, and what did I use before that?",
        probes="superseded tooling fact",
        expected_signals=("uv", "poetry"),
    ),
)


def question_count() -> int:
    return len(GOLDEN_QUESTIONS)


def by_id(question_id: str) -> GoldenQuestion:
    for question in GOLDEN_QUESTIONS:
        if question.id == question_id:
            return question
    raise KeyError(question_id)


def signal_hits(question: GoldenQuestion, answer: str) -> list[str]:
    """Which expected signals actually appear in an answer (case-insensitive)."""
    lowered = (answer or "").lower()
    return [signal for signal in question.expected_signals if signal in lowered]
