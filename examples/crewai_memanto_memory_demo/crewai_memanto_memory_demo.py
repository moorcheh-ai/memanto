#!/usr/bin/env python3
"""CrewAI + Memanto durable memory demo.

This example keeps imports lazy so ``--help`` works before optional demo
dependencies are installed. Real Memanto calls are made through this repo's
SDK client and service layer when ``MOORCHEH_API_KEY`` is configured.
"""

from __future__ import annotations

import argparse
import os
import textwrap
from dataclasses import dataclass
from typing import Any


DEFAULT_NAMESPACE = "crewai-memanto-bounty-demo"
DEFAULT_TOPIC = "AI customer support automation"
VALID_PHASES = ("store", "recall", "update", "full-demo")


class DemoSetupError(RuntimeError):
    """Raised when the local environment is not ready to run the demo."""


@dataclass(frozen=True)
class MemoryPayload:
    """A typed memory the demo persists in Memanto."""

    title: str
    content: str
    memory_type: str
    tags: list[str]
    source: str
    confidence: float = 0.9
    provenance: str = "explicit_statement"


class MemantoCrewMemory:
    """Small adapter that uses Memanto as CrewAI's durable memory layer.

    CrewAI's built-in memory is useful inside a Crew run. This adapter shows the
    swap pattern: recall Memanto context before a task, and remember task output
    after a task. It intentionally delegates storage/search to real Memanto code.
    """

    def __init__(self, agent_id: str, api_key: str) -> None:
        self.agent_id = sanitize_agent_id(agent_id)
        self.api_key = api_key
        self.namespace = f"memanto_agent_{self.agent_id}"
        self.client = self._build_client()
        self._ensure_agent_session()

    def remember(self, payload: MemoryPayload) -> dict[str, Any]:
        """Store a normal memory through Memanto's public SDK client method."""
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=payload.memory_type,
            title=payload.title,
            content=payload.content,
            confidence=payload.confidence,
            tags=payload.tags,
            source=payload.source,
            provenance=payload.provenance,
        )

    def remember_with_supersession(
        self,
        payload: MemoryPayload,
        *,
        supersedes_memory_id: str,
        superseded_payload: MemoryPayload,
    ) -> dict[str, Any]:
        """Store a corrected memory and mark the older memory as superseded.

        Memanto exposes temporal/current-only recall and supports supersession
        metadata on ``MemoryRecord``. The high-level ``remember`` command does
        not currently accept supersession fields, so this example uses the repo's
        real lower-level ``MemoryWriteService`` for that metadata and documents
        the limitation in README.md.
        """
        from memanto.app.core import MemoryRecord

        self.client._get_validated_session_for_agent(self.agent_id)
        write_service = self.client._get_write_service()

        corrected = MemoryRecord(
            type=payload.memory_type,
            title=payload.title,
            content=payload.content,
            scope_type="agent",
            scope_id=self.agent_id,
            actor_id=self.agent_id,
            confidence=payload.confidence,
            tags=payload.tags,
            source=payload.source,
            provenance=payload.provenance,
            supersedes=supersedes_memory_id,
        )
        result = write_service.store_memory(corrected)
        new_memory_id = str(result["id"])

        superseded = MemoryRecord(
            id=supersedes_memory_id,
            type=superseded_payload.memory_type,
            title=superseded_payload.title,
            content=superseded_payload.content,
            scope_type="agent",
            scope_id=self.agent_id,
            actor_id=self.agent_id,
            confidence=0.2,
            status="superseded",
            tags=superseded_payload.tags + ["superseded"],
            source=superseded_payload.source,
            provenance="corrected",
            superseded_by=new_memory_id,
            contradiction_detected=True,
        )

        warning = None
        try:
            write_service.delete_memory(supersedes_memory_id, self.namespace)
        except Exception as exc:  # pragma: no cover - depends on remote service
            warning = f"Old memory delete was not confirmed: {exc}"

        write_service.store_memory(superseded)

        return {
            "memory_id": new_memory_id,
            "supersedes": supersedes_memory_id,
            "namespace": self.namespace,
            "warning": warning,
        }

    def recall(
        self,
        query: str,
        *,
        limit: int = 6,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Recall memories through Memanto semantic search."""
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            memory_types=memory_types,
        )
        return list(result.get("memories", []))

    def recall_current(
        self,
        query: str,
        *,
        limit: int = 6,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Recall current, non-superseded memories through Memanto."""
        result = self.client.recall_current(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            memory_types=memory_types,
        )
        return list(result.get("memories", []))

    def _build_client(self) -> Any:
        try:
            from memanto.cli.client.sdk_client import SdkClient
        except ImportError as exc:
            raise DemoSetupError(
                "Memanto dependencies are not installed. From the repo root run:\n"
                "  python -m pip install -e .\n"
                "  python -m pip install -r "
                "examples/crewai_memanto_memory_demo/requirements.txt"
            ) from exc

        os.environ["MOORCHEH_API_KEY"] = self.api_key
        return SdkClient(self.api_key)

    def _ensure_agent_session(self) -> None:
        try:
            self.client.get_agent(self.agent_id)
        except Exception:
            self.client.create_agent(
                self.agent_id,
                pattern="project",
                description="CrewAI + Memanto cross-session bounty demo",
            )

        self.client.activate_agent(self.agent_id, duration_hours=6)


def sanitize_agent_id(raw_agent_id: str) -> str:
    """Keep agent IDs compatible with Memanto namespace constraints."""
    cleaned = []
    for char in raw_agent_id.strip():
        if char.isalnum() or char in {"-", "_"}:
            cleaned.append(char)
        elif char.isspace():
            cleaned.append("-")
    agent_id = "".join(cleaned).strip("-_")
    if not agent_id:
        raise DemoSetupError("Namespace must contain letters or numbers.")
    return agent_id


def load_dotenv_if_present() -> None:
    """Load .env for local demos when python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def build_adapter(namespace: str) -> MemantoCrewMemory:
    api_key = os.environ.get("MOORCHEH_API_KEY", "").strip()
    if not api_key:
        raise DemoSetupError(
            "MOORCHEH_API_KEY is not set.\n"
            "Create a Moorcheh API key, then set it only in your shell:\n"
            "  PowerShell: $env:MOORCHEH_API_KEY=\"your-moorcheh-api-key\"\n"
            "  macOS/Linux: export MOORCHEH_API_KEY=\"your-moorcheh-api-key\"\n"
            "No API key is required for --help."
        )
    return MemantoCrewMemory(namespace, api_key)


def research_memories(topic: str) -> list[MemoryPayload]:
    safe_topic = topic.strip()
    return [
        MemoryPayload(
            title=f"{safe_topic}: automation findings",
            content=(
                f"Research finding for {safe_topic}: support teams should route "
                "refund, onboarding, and billing questions through separate agent "
                "tools. Escalation rules should be explicit before automation."
            ),
            memory_type="fact",
            tags=["crewai-demo", "research", "memory-test"],
            source="research-agent",
            confidence=0.92,
        ),
        MemoryPayload(
            title=f"{safe_topic}: writer preference",
            content=(
                f"User preference for {safe_topic}: write the final brief in a "
                "concise founder-friendly tone with concrete implementation steps."
            ),
            memory_type="preference",
            tags=["crewai-demo", "preference", "writer-brief"],
            source="research-agent",
            confidence=0.95,
        ),
        MemoryPayload(
            title=f"{safe_topic}: task outcome",
            content=(
                f"Task outcome for {safe_topic}: Research Agent completed the "
                "discovery pass and asked Writer Agent to draft a buyer-facing "
                "launch note using recalled Memanto context."
            ),
            memory_type="artifact",
            tags=["crewai-demo", "task-outcome", "handoff"],
            source="research-agent",
            confidence=0.9,
        ),
    ]


def print_banner(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def print_memory(memory: dict[str, Any], index: int) -> None:
    title = memory.get("title") or "Untitled"
    memory_type = memory.get("type") or "unknown"
    memory_id = memory.get("id") or "unknown"
    score = memory.get("score")
    content = compact(memory.get("content") or memory.get("text") or "")
    print(f"  {index}. [{memory_type}] {title}")
    print(f"     id={memory_id}")
    if score is not None:
        print(f"     score={score}")
    print(f"     {content}")


def compact(value: str, width: int = 120) -> str:
    return textwrap.shorten(" ".join(value.split()), width=width, placeholder="...")


def phase_store(args: argparse.Namespace) -> None:
    memory = build_adapter(args.namespace)
    print_banner("[Session 1] Research Agent storing findings in Memanto")
    print("[CrewAI role] Research Agent")
    print(f"[Memanto] agent={memory.agent_id} namespace={memory.namespace}")
    print(f"[Topic] {args.topic}")

    for payload in research_memories(args.topic):
        result = memory.remember(payload)
        print(
            "[Memanto] Stored memory: "
            f"{payload.memory_type} id={result.get('memory_id', 'unknown')}"
        )

    print()
    print("[Session 1] Complete. Start a later run with:")
    print(
        "  python examples/crewai_memanto_memory_demo/"
        "crewai_memanto_memory_demo.py --phase recall"
    )


def phase_recall(args: argparse.Namespace) -> None:
    memory = build_adapter(args.namespace)
    delay_label = "24 hours later" if args.simulate_24h else "later session"
    print_banner(f"[Session 2] Writer Agent recalling Memanto memory ({delay_label})")
    print("[CrewAI role] Writer Agent")
    print("[Boundary] No Session 1 Python variables are used in this phase.")
    print("[Memanto] Running semantic recall for prior research and preferences.")

    query = (
        f"{args.topic} research findings writer preference task outcome "
        "founder-friendly launch note"
    )
    memories = memory.recall(query, limit=args.limit)
    if not memories:
        print("[Memanto] No memories found.")
        print("Run --phase store first with the same --namespace and --topic.")
        return

    print("[Memanto] Retrieved memories from durable storage:")
    for index, item in enumerate(memories, 1):
        print_memory(item, index)

    print()
    current_preferences = memory.recall_current(
        f"{args.topic} writer tone preference",
        limit=3,
        memory_types=["preference"],
    )
    chosen_preference = choose_current_preference(current_preferences or memories)
    print("[Writer Agent] Current preference used:")
    print(f"  {compact(chosen_preference)}")

    writer_brief = build_writer_brief(args.topic, memories, chosen_preference)
    print()
    print("[Writer Agent] Draft based only on recalled Memanto context:")
    print(textwrap.indent(writer_brief, "  "))

    if args.use_real_crewai:
        run_real_crewai_writer(args.topic, memories, chosen_preference)


def phase_update(args: argparse.Namespace) -> None:
    memory = build_adapter(args.namespace)
    print_banner("[Contradiction Test] Updating an old preference in Memanto")
    print("[Memanto] Storing old preference first.")

    old_preference = MemoryPayload(
        title=f"{args.topic}: old tone preference",
        content=(
            f"Preference key demo-tone for {args.topic}: Writer Agent should "
            "use a technical deep-dive tone with detailed implementation notes."
        ),
        memory_type="preference",
        tags=["crewai-demo", "demo-tone", "old-preference"],
        source="research-agent",
        confidence=0.86,
    )
    old_result = memory.remember(old_preference)
    old_memory_id = str(old_result.get("memory_id", "unknown"))
    print(f"[Memanto] Stored old preference id={old_memory_id}")

    print("[Memanto] Storing corrected preference with supersession metadata.")
    new_preference = MemoryPayload(
        title=f"{args.topic}: current tone preference",
        content=(
            f"Preference key demo-tone for {args.topic}: CURRENT preference is "
            "a concise founder-friendly tone with concrete next steps. This "
            f"supersedes memory {old_memory_id}."
        ),
        memory_type="preference",
        tags=["crewai-demo", "demo-tone", "current-preference"],
        source="writer-agent",
        confidence=0.97,
        provenance="corrected",
    )
    new_result = memory.remember_with_supersession(
        new_preference,
        supersedes_memory_id=old_memory_id,
        superseded_payload=old_preference,
    )
    print(
        "[Memanto] Stored corrected preference "
        f"id={new_result.get('memory_id', 'unknown')}"
    )
    if new_result.get("warning"):
        print(f"[Memanto] Warning: {new_result['warning']}")

    print("[Memanto] Recalling current-only preferences.")
    current = memory.recall_current(
        f"{args.topic} demo-tone current preference",
        limit=args.limit,
        memory_types=["preference"],
    )
    if not current:
        print("[Memanto] No current preferences found.")
        return

    print("[Result] Current preferences returned by Memanto:")
    for index, item in enumerate(current, 1):
        print_memory(item, index)

    print()
    print("[Result] Latest preference used:")
    print(f"  {compact(choose_current_preference(current))}")


def phase_full_demo(args: argparse.Namespace) -> None:
    print_banner("[Full Demo] CrewAI + Memanto durable memory")
    phase_store(args)
    print()
    print("[Demo] Re-instantiating adapter to simulate a new run/session.")
    if args.simulate_24h:
        print("[Demo] Simulating the recall step as 24 hours later.")
    phase_recall(args)
    phase_update(args)


def choose_current_preference(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "No preference recalled."

    def rank(memory: dict[str, Any]) -> tuple[int, str]:
        content = str(memory.get("content") or memory.get("text") or "")
        title = str(memory.get("title") or "")
        tags = ",".join(str(tag) for tag in memory.get("tags") or [])
        haystack = f"{title} {content} {tags}".lower()
        current_score = 1 if "current" in haystack else 0
        created = str(memory.get("created_at") or memory.get("updated_at") or "")
        return current_score, created

    selected = sorted(memories, key=rank, reverse=True)[0]
    return str(selected.get("content") or selected.get("text") or selected)


def build_writer_brief(
    topic: str,
    memories: list[dict[str, Any]],
    preference: str,
) -> str:
    bullets = []
    for memory in memories[:3]:
        content = memory.get("content") or memory.get("text") or ""
        if content:
            bullets.append(f"- {compact(str(content), width=100)}")
    if not bullets:
        bullets.append("- No recalled research was available.")

    return "\n".join(
        [
            f"Brief for {topic}:",
            f"Preference: {compact(preference, width=100)}",
            "Use these recalled points:",
            *bullets,
            "Recommendation: ship a scoped agent workflow, persist outcomes in "
            "Memanto, and recall them before Writer Agent drafts follow-ups.",
        ]
    )


def run_real_crewai_writer(
    topic: str,
    memories: list[dict[str, Any]],
    preference: str,
) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise DemoSetupError(
            "--use-real-crewai requires OPENAI_API_KEY or a CrewAI-supported "
            "LLM configuration. Deterministic Memanto recall already ran."
        )

    try:
        from crewai import Agent, Crew, Process, Task
    except ImportError as exc:
        raise DemoSetupError(
            "CrewAI is not installed. Run:\n"
            "  python -m pip install -r "
            "examples/crewai_memanto_memory_demo/requirements.txt"
        ) from exc

    recalled_context = "\n".join(
        f"- {item.get('content') or item.get('text')}" for item in memories[:5]
    )
    writer = Agent(
        role="Writer Agent",
        goal="Write a concise brief from durable Memanto memory.",
        backstory=(
            "You are a careful writer. You only use the recalled Memanto "
            "context passed into the task."
        ),
        verbose=True,
    )
    task = Task(
        description=(
            f"Topic: {topic}\n"
            f"Current preference: {preference}\n"
            f"Memanto recalled context:\n{recalled_context}\n\n"
            "Write a short launch brief grounded in the recalled context."
        ),
        expected_output="A concise launch brief with 3 bullets.",
        agent=writer,
    )
    crew = Crew(
        agents=[writer],
        tasks=[task],
        process=Process.sequential,
        memory=False,
        verbose=True,
    )
    print()
    print("[CrewAI] Running optional LLM-backed Crew kickoff.")
    result = crew.kickoff()
    print("[CrewAI] Result:")
    print(textwrap.indent(str(result), "  "))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CrewAI + Memanto cross-session memory demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase store
              python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase recall --simulate-24h
              python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase update
              python examples/crewai_memanto_memory_demo/crewai_memanto_memory_demo.py --phase full-demo
            """
        ).strip(),
    )
    parser.add_argument(
        "--phase",
        choices=VALID_PHASES,
        default="full-demo",
        help="Which demo phase to run.",
    )
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help="Memanto agent id/namespace suffix for isolating demo memories.",
    )
    parser.add_argument(
        "--topic",
        default=DEFAULT_TOPIC,
        help="Research topic used for stored and recalled memories.",
    )
    parser.add_argument(
        "--simulate-24h",
        action="store_true",
        help="Label recall output as a later 24-hour session.",
    )
    parser.add_argument(
        "--use-real-crewai",
        action="store_true",
        help="After Memanto recall, run an optional LLM-backed CrewAI kickoff.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=6,
        help="Maximum Memanto recall results to display.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv_if_present()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.phase == "store":
            phase_store(args)
        elif args.phase == "recall":
            phase_recall(args)
        elif args.phase == "update":
            phase_update(args)
        elif args.phase == "full-demo":
            phase_full_demo(args)
        else:  # pragma: no cover - argparse prevents this
            parser.error(f"Unknown phase: {args.phase}")
    except DemoSetupError as exc:
        print()
        print("[Setup Required]")
        print(str(exc))
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
