#!/usr/bin/env python3
"""CrewAI + Memanto durable memory example.

Dry-run mode uses a local JSON store so the full memory flow can be checked
without API keys or paid LLM calls. Live mode stores and retrieves memories
through Memanto using MOORCHEH_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STORE = Path("/tmp/crewai_memanto_memory_demo.json")
DEFAULT_AGENT_ID = "crewai-memanto-memory-demo"
DEFAULT_TOPIC = "regional EV charging incentives"


@dataclass
class MemoryItem:
    id: str
    agent_id: str
    memory_type: str
    title: str
    content: str
    confidence: float
    tags: list[str]
    source: str
    provenance: str = "explicit_statement"
    status: str = "active"
    created_at: str = field(default_factory=lambda: now_iso())
    updated_at: str = field(default_factory=lambda: now_iso())
    superseded_by: str | None = None
    supersedes: str | None = None


class MemoryAdapter(ABC):
    """Small adapter surface shared by local dry-run and live Memanto modes."""

    label: str

    @abstractmethod
    def remember(
        self,
        *,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float,
        tags: list[str],
        source: str,
        provenance: str = "explicit_statement",
        supersedes: str | None = None,
    ) -> MemoryItem:
        """Store one memory and optionally supersede an older memory."""

    @abstractmethod
    def recall_current(
        self,
        *,
        agent_id: str,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[MemoryItem]:
        """Return current, non-superseded memories relevant to the query."""


class LocalJsonMemoryAdapter(MemoryAdapter):
    """Deterministic local memory store used only for dry-run proof."""

    label = "dry-run local JSON memory"

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"memories": []})

    def remember(
        self,
        *,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float,
        tags: list[str],
        source: str,
        provenance: str = "explicit_statement",
        supersedes: str | None = None,
    ) -> MemoryItem:
        data = self._read()
        memories = data["memories"]
        memory_id = f"local-{len(memories) + 1:04d}"
        item = MemoryItem(
            id=memory_id,
            agent_id=agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
            source=source,
            provenance=provenance,
            supersedes=supersedes,
        )

        if supersedes:
            for stored in memories:
                if stored["id"] == supersedes and stored["status"] == "active":
                    stored["status"] = "superseded"
                    stored["superseded_by"] = item.id
                    stored["updated_at"] = now_iso()

        memories.append(asdict(item))
        self._write(data)
        return item

    def recall_current(
        self,
        *,
        agent_id: str,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[MemoryItem]:
        query_tokens = tokenize(query)
        tag_filter = set(tags or [])
        results: list[tuple[int, MemoryItem]] = []

        for raw in self._read()["memories"]:
            if raw["agent_id"] != agent_id or raw["status"] != "active":
                continue
            if memory_types and raw["memory_type"] not in memory_types:
                continue
            if tag_filter and not tag_filter.issubset(set(raw["tags"])):
                continue

            searchable = " ".join([raw["title"], raw["content"], *raw["tags"]])
            score = len(query_tokens.intersection(tokenize(searchable)))
            if score > 0 or not query_tokens:
                results.append((score, MemoryItem(**raw)))

        results.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [item for _, item in results[:limit]]

    def _read(self) -> dict[str, Any]:
        with self.path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, data: dict[str, Any]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")


class MemantoLiveAdapter(MemoryAdapter):
    """Live Memanto-backed adapter. Requires MOORCHEH_API_KEY."""

    label = "live Memanto-backed memory"

    def __init__(self, api_key: str, agent_id: str) -> None:
        from memanto.app.core import create_memory_scope
        from memanto.cli.client.direct_client import DirectClient

        self.client = DirectClient(api_key)
        self.namespace = create_memory_scope("agent", agent_id).to_namespace()
        self._ensure_agent(agent_id)

    def remember(
        self,
        *,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float,
        tags: list[str],
        source: str,
        provenance: str = "explicit_statement",
        supersedes: str | None = None,
    ) -> MemoryItem:
        result = self.client.remember(
            agent_id=agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
            source=source,
            provenance=provenance,
        )
        item = MemoryItem(
            id=result["memory_id"],
            agent_id=agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
            source=source,
            provenance=provenance,
            supersedes=supersedes,
        )
        if supersedes:
            self._mark_superseded(supersedes, item.id)
        return item

    def recall_current(
        self,
        *,
        agent_id: str,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[MemoryItem]:
        result = self.client.recall_current(
            agent_id=agent_id,
            query=query,
            limit=limit,
            memory_types=memory_types,
        )
        tag_filter = set(tags or [])
        items = [self._from_memanto(raw, agent_id) for raw in result["memories"]]
        if tag_filter:
            items = [item for item in items if tag_filter.issubset(set(item.tags))]
        return items[:limit]

    def _ensure_agent(self, agent_id: str) -> None:
        try:
            self.client.get_agent(agent_id)
        except Exception:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="tool",
                description="CrewAI Memanto durable memory example",
            )
        self.client.activate_agent(agent_id)

    def _mark_superseded(self, old_id: str, new_id: str) -> None:
        from memanto.app.core import MemoryRecord

        existing = self.client._get_read_service().get_memory(old_id, self.namespace)
        if not existing:
            print(f"  ! Could not find old live memory {old_id} to supersede.")
            return

        old = self._from_memanto(existing, existing.get("scope_id", DEFAULT_AGENT_ID))
        record = MemoryRecord(
            id=old.id,
            type=old.memory_type,
            title=old.title,
            content=old.content,
            scope_type="agent",
            scope_id=old.agent_id,
            actor_id=old.agent_id,
            source=old.source,
            confidence=old.confidence,
            status="superseded",
            tags=old.tags,
            provenance=old.provenance,
            superseded_by=new_id,
        )
        record.created_at = parse_iso(old.created_at)
        record.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        write_service = self.client._get_write_service()
        write_service.delete_memory(old_id, self.namespace)
        write_service.store_memory(record)

    @staticmethod
    def _from_memanto(raw: dict[str, Any], fallback_agent_id: str) -> MemoryItem:
        metadata = raw.get("metadata", raw)
        text = raw.get("text", "")
        title = raw.get("title")
        content = raw.get("content")
        if not title or not content:
            title, content = split_memanto_text(text, raw.get("title", "Memory"))
        raw_tags = metadata.get("tags") or raw.get("tags") or []
        tags = raw_tags.split(",") if isinstance(raw_tags, str) else list(raw_tags)
        return MemoryItem(
            id=raw.get("id") or metadata.get("id", "unknown"),
            agent_id=metadata.get("scope_id", fallback_agent_id),
            memory_type=raw.get("type")
            or raw.get("memory_type")
            or metadata.get("memory_type")
            or metadata.get("type", "fact"),
            title=title,
            content=content,
            confidence=float(metadata.get("confidence", raw.get("confidence", 0.8))),
            tags=[tag for tag in tags if tag],
            source=metadata.get("source", raw.get("source", "agent")),
            provenance=metadata.get("provenance", raw.get("provenance", "imported")),
            status=metadata.get("status", raw.get("status", "active")),
            created_at=metadata.get("created_at", raw.get("created_at", now_iso())),
            updated_at=metadata.get("updated_at", raw.get("updated_at", now_iso())),
            superseded_by=metadata.get("superseded_by", raw.get("superseded_by")),
            supersedes=metadata.get("supersedes", raw.get("supersedes")),
        )


def configure_crewai_agents(enable_llm: bool) -> dict[str, Any] | None:
    """Create CrewAI Agent objects when crewai is installed."""
    try:
        from crewai import Agent, LLM
    except ImportError:
        print("CrewAI package not installed; memory adapter flow still runs.")
        print("Install requirements.txt to instantiate real CrewAI Agent objects.\n")
        return None

    llm = None
    if enable_llm:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
        if not base_url and os.getenv("DEEPSEEK_API_KEY"):
            base_url = "https://api.deepseek.com"
        model = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
        if not api_key:
            raise SystemExit(
                "--enable-crewai-llm requires OPENAI_API_KEY or DEEPSEEK_API_KEY"
            )
        llm = LLM(model=model, api_key=api_key, base_url=base_url)

    kwargs = {"verbose": False}
    if llm is not None:
        kwargs["llm"] = llm

    agents = {
        "researcher": Agent(
            role="Research Agent",
            goal="Find concise research notes and store durable memories.",
            backstory="A careful researcher that records reusable context.",
            **kwargs,
        ),
        "writer": Agent(
            role="Writer Agent",
            goal="Use retrieved durable memory to draft a brief.",
            backstory="A concise writer that adapts to remembered preferences.",
            **kwargs,
        ),
    }
    print("CrewAI agents configured: Research Agent, Writer Agent\n")
    return agents


def run_one(adapter: MemoryAdapter, agent_id: str, topic: str) -> None:
    print("Run 1: Research Agent stores durable context")
    old_pref = adapter.remember(
        agent_id=agent_id,
        memory_type="preference",
        title="Audience format preference",
        content="User prefers long-form narrative reports with extended background.",
        confidence=0.74,
        tags=["demo", "preference", "writing-style"],
        source="research_agent",
    )
    print_memory("stored old preference", old_pref)

    adapter.remember(
        agent_id=agent_id,
        memory_type="fact",
        title=f"Research finding for {topic}",
        content=(
            f"For {topic}, the useful brief should compare eligibility, timing, "
            "and practical action items instead of listing raw links."
        ),
        confidence=0.86,
        tags=["demo", "finding", "research"],
        source="research_agent",
    )

    current_pref = adapter.remember(
        agent_id=agent_id,
        memory_type="preference",
        title="Audience format preference update",
        content="User now prefers a concise bullet brief with a short recommendation.",
        confidence=0.95,
        tags=["demo", "preference", "writing-style"],
        source="research_agent",
        provenance="corrected",
        supersedes=old_pref.id,
    )
    print_memory("stored superseding preference", current_pref)

    adapter.remember(
        agent_id=agent_id,
        memory_type="event",
        title="Research task outcome",
        content=(
            "Research Agent completed run 1 and handed off findings plus the "
            "updated writing preference for a later Writer Agent execution."
        ),
        confidence=0.9,
        tags=["demo", "outcome", "handoff"],
        source="research_agent",
    )
    print("Run 1 complete.\n")


def run_two(
    adapter: MemoryAdapter,
    agent_id: str,
    topic: str,
    writer_agent: Any | None = None,
) -> None:
    print("Run 2: Writer Agent retrieves memories in a separate execution")
    memories = adapter.recall_current(
        agent_id=agent_id,
        query=f"{topic} current writing preference research findings handoff",
        limit=6,
        tags=["demo"],
    )
    if not memories:
        print("No current memories found. Run with --run 1 first, or use --run both.")
        return

    for index, memory in enumerate(memories, start=1):
        print_memory(f"retrieved #{index}", memory)

    preference = first_type(memories, "preference")
    finding = first_type(memories, "fact")
    outcome = first_type(memories, "event")
    if writer_agent:
        brief = run_crewai_writer(writer_agent, topic, memories)
    else:
        brief = draft_writer_output(topic, preference, finding, outcome)

    print("Writer Agent draft using retrieved durable memory:")
    print(indent(brief))
    print()


def run_crewai_writer(writer_agent: Any, topic: str, memories: list[MemoryItem]) -> str:
    memory_context = "\n".join(
        f"- [{memory.memory_type}] {memory.title}: {memory.content}"
        for memory in memories
    )
    prompt = (
        "Use these retrieved durable memories to draft a concise brief.\n\n"
        f"Topic: {topic}\n\n"
        f"Retrieved memory:\n{memory_context}\n\n"
        "Return bullets and honor the current writing preference."
    )
    result = writer_agent.kickoff(prompt)
    return getattr(result, "raw", str(result))


def draft_writer_output(
    topic: str,
    preference: MemoryItem | None,
    finding: MemoryItem | None,
    outcome: MemoryItem | None,
) -> str:
    preference_text = preference.content if preference else "No preference retrieved."
    finding_text = finding.content if finding else "No research finding retrieved."
    outcome_text = outcome.content if outcome else "No handoff outcome retrieved."
    return (
        f"- Topic: {topic}\n"
        f"- Remembered preference: {preference_text}\n"
        f"- Research to apply: {finding_text}\n"
        f"- Handoff state: {outcome_text}\n"
        "- Draft: Use concise bullets, compare eligibility and timing, then close "
        "with one recommendation."
    )


def build_adapter(args: argparse.Namespace) -> MemoryAdapter:
    if args.mode == "dry-run":
        return LocalJsonMemoryAdapter(args.store)

    api_key = (os.getenv("MOORCHEH_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("Live mode requires MOORCHEH_API_KEY in the environment.")
    return MemantoLiveAdapter(api_key, args.agent_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Two-run CrewAI memory demo using Memanto or local JSON dry-run."
    )
    parser.add_argument("--mode", choices=["dry-run", "live"], default="dry-run")
    parser.add_argument("--run", choices=["1", "2", "both"], default="both")
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument(
        "--enable-crewai-llm",
        action="store_true",
        help="Allow CrewAI to call the configured LLM. Off by default.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("CrewAI + Memanto durable memory demo")
    print(f"Mode: {args.mode}")
    print(f"Agent id: {args.agent_id}")
    if args.mode == "dry-run":
        print(f"Local store: {args.store}")
        print("Dry-run proof only: this is not Memanto-backed storage.")
    print()

    agents = configure_crewai_agents(args.enable_crewai_llm)
    adapter = build_adapter(args)
    print(f"Memory adapter: {adapter.label}\n")

    if args.run in {"1", "both"}:
        run_one(adapter, args.agent_id, args.topic)
    if args.run in {"2", "both"}:
        writer_agent = None
        if args.enable_crewai_llm and agents:
            writer_agent = agents["writer"]
        run_two(adapter, args.agent_id, args.topic, writer_agent)


def first_type(memories: list[MemoryItem], memory_type: str) -> MemoryItem | None:
    return next((memory for memory in memories if memory.memory_type == memory_type), None)


def print_memory(label: str, memory: MemoryItem) -> None:
    supersession = ""
    if memory.supersedes:
        supersession = f" supersedes={memory.supersedes}"
    print(
        f"  {label}: [{memory.memory_type}] {memory.title} "
        f"id={memory.id} status={memory.status}{supersession}"
    )
    print(f"    {memory.content}")


def split_memanto_text(text: str, fallback_title: str) -> tuple[str, str]:
    match = re.match(r"^\[[A-Z_]+\]\s*(.*?)\n\n(.*)", text, flags=re.DOTALL)
    if not match:
        return fallback_title, text
    content = match.group(2).split("\n\nTags:", maxsplit=1)[0]
    return match.group(1), content


def tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def indent(value: str) -> str:
    return "\n".join(f"  {line}" for line in value.splitlines())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


if __name__ == "__main__":
    main()
