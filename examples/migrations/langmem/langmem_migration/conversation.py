"""Sample LangMem history for one developer, "Alex".

Rather than hand-writing a ``langmem_export.json``, this is a transcript plus
the memory operations an agent would perform over five sessions across three
weeks. ``populate.py`` replays these through LangMem's own ``manage_memory``
tool, so the resulting store has LangMem's real on-disk schema.

Each operation carries a stable ``ref`` so later sessions can ``update`` or
``delete`` an earlier memory without hard-coding LangMem's random UUIDs. The
history covers the cases a migration needs to get right:

    * evolving preferences (Alex changes their mind about the test runner)
    * direct corrections (a fact is revised, not duplicated)
    * stale data cleanup (a completed to-do is deleted, not left behind)
    * a timeline spread across three weeks, so "when did this happen"
      survives the migration
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MemoryOp:
    """One LangMem ``manage_memory`` operation to replay."""

    action: str  # "create" | "update" | "delete"
    ref: str  # stable local handle, resolved to a LangMem UUID at replay time
    content: str | None = None  # None for deletes


@dataclass(frozen=True)
class Session:
    """One working session: a date, the raw user turns, and the memory ops the
    agent committed to LangMem during it."""

    date: str  # ISO date; applied to created_at/updated_at for temporal fidelity
    title: str
    user_turns: list[str] = field(default_factory=list)
    ops: list[MemoryOp] = field(default_factory=list)


# The namespace's dynamic segment -- LangMem stores per-user memories under
# ("memories", USER_ID). Carried into the migration as a scope tag.
USER_ID = "alex"

SESSIONS: list[Session] = [
    Session(
        date="2026-06-02",
        title="Onboarding the assistant",
        user_turns=[
            "Hey -- I'm Alex, a senior backend engineer on the Payments team at "
            "Northwind. I mostly write Go and Python.",
            "For anything new, default to TypeScript on the frontend. I really "
            "dislike untyped JavaScript.",
            "Also: I use dark mode everywhere, and I run pytest for Python tests.",
        ],
        ops=[
            MemoryOp(
                "create",
                "role",
                "Alex is a senior backend engineer on the Payments team at "
                "Northwind, working primarily in Go and Python.",
            ),
            MemoryOp(
                "create",
                "pref_ts",
                "Alex prefers TypeScript for new frontend work and dislikes "
                "untyped JavaScript.",
            ),
            MemoryOp(
                "create",
                "pref_darkmode",
                "Alex uses dark mode in all editors and tools.",
            ),
            MemoryOp(
                "create",
                "pref_testrunner",
                "Alex runs pytest as the test runner for Python projects.",
            ),
        ],
    ),
    Session(
        date="2026-06-06",
        title="Kicking off the ledger service",
        user_turns=[
            "We're starting a new ledger service. The goal is to have a working "
            "double-entry core shipped to staging by end of Q3.",
            "It'll be Go, backed by Postgres. I'm pairing with Priya on it.",
            "Remind me to write an ADR before we lock the schema.",
        ],
        ops=[
            MemoryOp(
                "create",
                "goal_ledger",
                "Alex's goal: ship a working double-entry core for the new "
                "ledger service to staging by end of Q3 2026.",
            ),
            MemoryOp(
                "create",
                "fact_stack",
                "The ledger service is written in Go and backed by Postgres.",
            ),
            MemoryOp(
                "create",
                "rel_priya",
                "Alex is pairing with Priya on the ledger service.",
            ),
            MemoryOp(
                "create",
                "commit_adr",
                "Alex needs to write an ADR before locking the ledger database schema.",
            ),
        ],
    ),
    Session(
        date="2026-06-11",
        title="Changing the test runner",
        user_turns=[
            "I've switched the frontend test setup over to Vitest -- forget "
            "pytest for the TS packages, that was only ever for the Python side.",
            "Actually, going forward assume Vitest for all the TypeScript repos.",
        ],
        ops=[
            # Update in place rather than duplicating -- LangMem keeps the
            # same memory id.
            MemoryOp(
                "update",
                "pref_testrunner",
                "Alex runs pytest for Python projects and Vitest for all "
                "TypeScript repos.",
            ),
        ],
    ),
    Session(
        date="2026-06-16",
        title="A decision and a scheduling rule",
        user_turns=[
            "We decided to use decimal (not float) for all monetary amounts in "
            "the ledger -- money in floats is how you get audited.",
            "Hard rule for me: never deploy on Fridays. I don't care how small "
            "the change is.",
            "The ADR is done and merged, by the way.",
        ],
        ops=[
            MemoryOp(
                "create",
                "decision_decimal",
                "Decision: the ledger service stores all monetary amounts as "
                "decimals, never floats, to avoid rounding errors in audits.",
            ),
            MemoryOp(
                "create",
                "pref_nofriday",
                "Alex never deploys on Fridays, regardless of how small the change is.",
            ),
            # The commitment to write the ADR is now fulfilled -> the stale
            # to-do is deleted (contradiction/obsolescence handling).
            MemoryOp("delete", "commit_adr"),
        ],
    ),
    Session(
        date="2026-06-20",
        title="Reprioritizing",
        user_turns=[
            "Change of plan on the ledger: we're descoping multi-currency for "
            "now. Q3 target is single-currency (USD) double-entry only.",
            "Priya rolled off to the Fraud team, so I'm solo on the ledger now.",
            "Long-term I still want to learn Rust and eventually rewrite the "
            "settlement worker in it.",
        ],
        ops=[
            # Evolving goal: revise the Q3 target in place.
            MemoryOp(
                "update",
                "goal_ledger",
                "Alex's goal: ship a single-currency (USD) double-entry ledger "
                "core to staging by end of Q3 2026; multi-currency is descoped "
                "for now.",
            ),
            # The pairing relationship is no longer true -> revise it.
            MemoryOp(
                "update",
                "rel_priya",
                "Priya moved from the ledger service to the Fraud team; Alex is "
                "now the sole engineer on the ledger.",
            ),
            MemoryOp(
                "create",
                "goal_rust",
                "Alex wants to learn Rust and eventually rewrite the settlement "
                "worker in it.",
            ),
        ],
    ),
]


# --------------------------------------------------------------------------
# Golden Q&A -- the "does memory survive the move" oracle.
#
# Each question probes a fact that the final LangMem state should answer. The
# validation harness asks these before migration (against LangMem) and after
# (against Memanto) and scores recall parity. Answers are graded by keyword
# presence so the harness runs without an LLM judge (an optional LLM-judge mode
# is available when an API key is present).
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldenQA:
    question: str
    # any one of these substrings (case-insensitive) counts as a correct recall
    expect_any: list[str]
    # substrings that MUST NOT appear -- catches stale/contradicted memory
    forbid: list[str] = field(default_factory=list)


GOLDEN_QA: list[GoldenQA] = [
    GoldenQA(
        "What test runner does Alex use for TypeScript repos?",
        expect_any=["vitest"],
    ),
    GoldenQA(
        "What is Alex's rule about deploying on Fridays?",
        expect_any=["never", "no friday", "not on friday"],
    ),
    GoldenQA(
        "Is the ledger multi-currency for the Q3 target?",
        expect_any=["single", "usd", "descoped", "no"],
        forbid=[],
    ),
    GoldenQA(
        "Who works with Alex on the ledger service now?",
        expect_any=["solo", "sole", "alone", "no one", "nobody"],
        forbid=["pairing with priya", "pairing"],
    ),
    GoldenQA(
        "How does the ledger store monetary amounts?",
        expect_any=["decimal"],
    ),
    GoldenQA(
        "What does Alex want to learn long-term?",
        expect_any=["rust"],
    ),
    GoldenQA(
        "What editor theme does Alex prefer?",
        expect_any=["dark"],
    ),
]


def raw_transcript() -> str:
    """The full conversation as plain text -- fed to the optional live-LLM
    extraction path (``create_memory_store_manager``)."""
    blocks: list[str] = []
    for s in SESSIONS:
        blocks.append(f"## Session {s.date} -- {s.title}")
        for turn in s.user_turns:
            blocks.append(f"Alex: {turn}")
        blocks.append("")
    return "\n".join(blocks).strip()
