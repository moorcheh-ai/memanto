"""Fixed benchmark dataset for temporal preference tracking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Turn:
    """One observed memory event inside a synthetic user session."""

    session_id: str
    content: str


@dataclass(frozen=True)
class Question:
    """A retrieval question with golden and stale answer terms."""

    prompt: str
    expected_terms: tuple[str, ...]
    stale_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Session:
    """A chronological group of memory turns."""

    session_id: str
    turns: tuple[Turn, ...]


@dataclass(frozen=True)
class Scenario:
    """Complete benchmark scenario consumed by every backend."""

    name: str
    description: str
    sessions: tuple[Session, ...]
    questions: tuple[Question, ...]

    @property
    def turns(self) -> tuple[Turn, ...]:
        """Return all turns in chronological order."""
        return tuple(turn for session in self.sessions for turn in session.turns)


def load_scenario() -> Scenario:
    """Build the deterministic shifting-persona scenario."""
    sessions = (
        Session(
            session_id="s1-initial-preferences",
            turns=(
                Turn(
                    "s1-initial-preferences",
                    "Morgan prefers concise executive briefs under 5 bullets.",
                ),
                Turn(
                    "s1-initial-preferences",
                    "Use UTC for all launch dates in status updates.",
                ),
                Turn(
                    "s1-initial-preferences",
                    "The billing project uses Stripe webhooks with idempotency keys.",
                ),
            ),
        ),
        Session(
            session_id="s2-preference-change",
            turns=(
                Turn(
                    "s2-preference-change",
                    "Morgan now wants detailed launch-risk memos with evidence tables.",
                ),
                Turn(
                    "s2-preference-change",
                    "Keep UTC only for backend logs; customer-facing dates should use local timezone.",
                ),
            ),
        ),
        Session(
            session_id="s3-architecture-decisions",
            turns=(
                Turn(
                    "s3-architecture-decisions",
                    "Decision: payment retries use advisory locks and outbox events.",
                ),
                Turn(
                    "s3-architecture-decisions",
                    "Morgan dislikes speculative roadmap claims without observed evidence.",
                ),
            ),
        ),
        Session(
            session_id="s4-audience-specific-style",
            turns=(
                Turn(
                    "s4-audience-specific-style",
                    "For investor updates, lead with revenue risk.",
                ),
                Turn(
                    "s4-audience-specific-style",
                    "For engineering tickets, lead with rollback plan.",
                ),
            ),
        ),
    )
    questions = (
        Question(
            prompt="What format should launch-risk updates use now?",
            expected_terms=("detailed launch-risk memos", "evidence tables"),
            stale_terms=("concise executive briefs",),
        ),
        Question(
            prompt="What timezone should customer-facing dates use?",
            expected_terms=("local timezone",),
            stale_terms=("Use UTC for all launch dates",),
        ),
        Question(
            prompt="How should payment retry work be described?",
            expected_terms=("advisory locks", "outbox events"),
        ),
        Question(
            prompt="How should engineering tickets start?",
            expected_terms=("rollback plan",),
            stale_terms=("revenue risk",),
        ),
    )
    return Scenario(
        name="shifting-persona-temporal-tracking",
        description=(
            "A multi-session assistant memory scenario where user preferences "
            "mutate and old facts become stale."
        ),
        sessions=sessions,
        questions=questions,
    )
