#!/usr/bin/env python3
"""LangGraph support-agent demo backed by Memanto long-term memory.

The local file backend exists so reviewers can verify the cross-session flow
without credentials. The Memanto backend uses the existing `memanto` CLI and the
same graph nodes.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol, TypedDict

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

DEFAULT_AGENT_ID = "langgraph-support-demo"
DEFAULT_MEMORY_PATH = ".langgraph-memanto-demo.jsonl"


class SupportState(TypedDict):
    """State owned by the current LangGraph run."""

    customer_id: str
    message: str
    recalled_memory: NotRequired[str]
    reply: NotRequired[str]
    writeback: NotRequired[str]


class MemoryBackend(Protocol):
    """Storage interface used by graph nodes."""

    def remember(self, customer_id: str, content: str) -> str:
        """Store a memory and return an identifier."""

    def recall(self, customer_id: str, query: str) -> str:
        """Recall relevant long-term memory for this customer."""


@dataclass
class FileMemoryBackend:
    """Tiny JSONL memory backend for no-credential local demos."""

    path: Path

    def remember(self, customer_id: str, content: str) -> str:
        """Append one customer memory row to the local JSONL store."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = self._read_rows()
        memory_id = f"file-{len(rows) + 1}"
        rows.append(
            {
                "id": memory_id,
                "customer_id": customer_id,
                "content": content,
            }
        )
        with self.path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return memory_id

    def recall(self, customer_id: str, query: str) -> str:
        """Return the best matching local memory for the customer query."""

        query_terms = _expand_query_terms(_tokenize(query))
        candidates = [
            row["content"]
            for row in self._read_rows()
            if row.get("customer_id") == customer_id
        ]
        if not candidates:
            return ""

        def score(content: str) -> float:
            """Rank candidate text by token overlap and string similarity."""

            content_terms = _tokenize(content)
            overlap = len(query_terms & content_terms)
            return overlap + SequenceMatcher(
                None,
                " ".join(sorted(query_terms)),
                " ".join(sorted(content_terms)),
            ).ratio()

        return max(candidates, key=score)

    def _read_rows(self) -> list[dict[str, str]]:
        """Load memory rows from the JSONL store if it exists."""

        if not self.path.exists():
            return []
        rows: list[dict[str, str]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows


@dataclass
class MemantoCliBackend:
    """Memanto CLI-backed storage for the real integration path."""

    agent_id: str = DEFAULT_AGENT_ID
    memanto_bin: str | None = None

    def remember(self, customer_id: str, content: str) -> str:
        """Persist one customer memory through the Memanto CLI."""

        self._ensure_agent()
        output = self._run(
            [
                *self._command(),
                "remember",
                content,
                "--type",
                "preference",
                "--title",
                f"{customer_id}: support preference",
                "--tags",
                f"langgraph-demo,{customer_id}",
                "--source",
                "langgraph-memanto-example",
                "--provenance",
                "observed",
            ]
        )
        return output.strip().splitlines()[-1] if output.strip() else "memanto-memory"

    def recall(self, customer_id: str, query: str) -> str:
        """Recall customer memory through the Memanto CLI."""

        self._ensure_agent()
        output = self._run(
            [
                *self._command(),
                "recall",
                f"Customer {customer_id} support preference relevant to: {query}",
            ]
        )
        return output.strip()

    def _ensure_agent(self) -> None:
        """Activate the demo agent, creating it only when it is missing."""

        try:
            self._run([*self._command(), "agent", "activate", self.agent_id])
        except RuntimeError as error:
            if not _is_missing_agent_error(str(error)):
                raise
            self._run(
                [
                    *self._command(),
                    "agent",
                    "create",
                    self.agent_id,
                    "--pattern",
                    "project",
                    "--description",
                    "LangGraph support demo memory",
                ]
            )
            self._run([*self._command(), "agent", "activate", self.agent_id])

    def _command(self) -> list[str]:
        """Resolve the Memanto command invocation for subprocess calls."""

        if self.memanto_bin:
            return [self.memanto_bin]
        found = shutil.which("memanto")
        if found:
            return [found]
        return [sys.executable, "-m", "memanto"]

    def _run(self, args: Sequence[str]) -> str:
        """Run a Memanto command and return its combined output."""

        completed = subprocess.run(
            list(args),
            text=True,
            capture_output=True,
            check=False,
        )
        output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        if completed.returncode != 0:
            raise RuntimeError(output or f"Command failed: {' '.join(args)}")
        return output


def _tokenize(text: str) -> set[str]:
    """Normalize text into lower-case alphanumeric search terms."""

    return {term.lower() for term in re.findall(r"[A-Za-z0-9]+", text) if len(term) > 2}


def _expand_query_terms(terms: set[str]) -> set[str]:
    """Add simple domain synonyms used by the support export demo."""

    expanded = set(terms)
    if {"format", "export", "exports"} & expanded:
        expanded.update({"csv", "json", "pdf", "xlsx", "export", "exports"})
    return expanded


def _is_missing_agent_error(message: str) -> bool:
    """Identify Memanto CLI errors that mean the requested agent is absent."""

    lowered = message.lower()
    agent_context = "agent" in lowered
    if "404" in lowered and agent_context:
        return True
    if "does not exist" in lowered and agent_context:
        return True
    return any(
        marker in lowered
        for marker in (
            "agent not found",
            "no such agent",
            "unknown agent",
        )
    )


def recall_customer_memory(
    state: SupportState, *, memory_backend: MemoryBackend
) -> dict[str, str]:
    """Graph node: retrieve memory outside the current graph state."""

    recalled = memory_backend.recall(state["customer_id"], state["message"])
    return {"recalled_memory": recalled}


def draft_support_reply(state: SupportState) -> dict[str, str]:
    """Graph node: create a deterministic support reply using recalled memory."""

    memory = state.get("recalled_memory") or "No prior customer preference found."
    if "csv" in memory.lower():
        recommendation = "Use CSV for this export."
    else:
        recommendation = "Ask the customer which export format they prefer."

    return {
        "reply": (
            f"Customer: {state['customer_id']}\n"
            f"Current request: {state['message']}\n"
            f"Recalled memory: {memory}\n"
            f"Recommendation: {recommendation}"
        )
    }


def persist_new_learning(
    state: SupportState, *, memory_backend: MemoryBackend
) -> dict[str, str]:
    """Graph node: write a compact learning after handling the request."""

    writeback = (
        f"Handled support request for {state['customer_id']}: "
        f"{state['message']} | reply used memory: {bool(state.get('recalled_memory'))}"
    )
    memory_id = memory_backend.remember(state["customer_id"], writeback)
    return {"writeback": memory_id}


def build_langgraph_runner(
    memory_backend: MemoryBackend,
) -> Callable[[SupportState], SupportState]:
    """Build a LangGraph runner, falling back to a sequential runner if absent."""

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:

        def fallback_runner(state: SupportState) -> SupportState:
            """Execute the graph nodes sequentially when LangGraph is absent."""

            next_state: SupportState = dict(state)
            next_state.update(
                recall_customer_memory(next_state, memory_backend=memory_backend)
            )
            next_state.update(draft_support_reply(next_state))
            next_state.update(
                persist_new_learning(next_state, memory_backend=memory_backend)
            )
            return next_state

        return fallback_runner

    graph = StateGraph(SupportState)

    def recall_memory_node(state: SupportState) -> dict[str, str]:
        """Run the recall node with the configured memory backend."""

        return recall_customer_memory(state, memory_backend=memory_backend)

    def persist_learning_node(state: SupportState) -> dict[str, str]:
        """Run the persistence node with the configured memory backend."""

        return persist_new_learning(state, memory_backend=memory_backend)

    graph.add_node("recall_memory", recall_memory_node)
    graph.add_node("draft_reply", draft_support_reply)
    graph.add_node("persist_learning", persist_learning_node)
    graph.add_edge(START, "recall_memory")
    graph.add_edge("recall_memory", "draft_reply")
    graph.add_edge("draft_reply", "persist_learning")
    graph.add_edge("persist_learning", END)
    compiled_graph = graph.compile()

    def langgraph_runner(state: SupportState) -> SupportState:
        """Invoke the compiled LangGraph with the provided support state."""

        return compiled_graph.invoke(state)

    return langgraph_runner


def build_backend(args: argparse.Namespace) -> MemoryBackend:
    """Create the configured memory backend from parsed CLI options."""

    if args.backend == "memanto":
        return MemantoCliBackend(agent_id=args.agent_id, memanto_bin=args.memanto_bin)
    return FileMemoryBackend(Path(args.memory_path))


def command_seed(args: argparse.Namespace) -> int:
    """Handle the seed subcommand for adding a customer memory."""

    backend = build_backend(args)
    memory_id = backend.remember(args.customer_id, args.fact)
    print(f"seeded memory {memory_id} for {args.customer_id}")
    return 0


def command_ask(args: argparse.Namespace) -> int:
    """Handle the ask subcommand by running the support graph."""

    backend = build_backend(args)
    runner = build_langgraph_runner(backend)
    final_state = runner(
        {
            "customer_id": args.customer_id,
            "message": args.message,
        }
    )
    print(final_state["reply"])
    print(f"Writeback memory: {final_state.get('writeback', 'not stored')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the demo."""

    parser = argparse.ArgumentParser(
        description="LangGraph support-agent demo with Memanto memory."
    )
    parser.add_argument("--backend", choices=["file", "memanto"], default="file")
    parser.add_argument("--memory-path", default=DEFAULT_MEMORY_PATH)
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    parser.add_argument("--memanto-bin")

    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed", help="Seed a long-term customer memory.")
    seed.add_argument("--customer-id", required=True)
    seed.add_argument("--fact", required=True)
    seed.set_defaults(func=command_seed)

    ask = subparsers.add_parser("ask", help="Ask the support graph a question.")
    ask.add_argument("--customer-id", required=True)
    ask.add_argument("--message", required=True)
    ask.set_defaults(func=command_ask)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI arguments and dispatch to the selected subcommand."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
