"""
Thin Memanto CLI wrapper used by the LangGraph example.

The example keeps memory outside LangGraph state by calling the Memanto CLI
from graph nodes. LangGraph decides when to remember or recall; Memanto owns
the long-term storage and retrieval.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


class MemantoCliError(RuntimeError):
    """Raised when the Memanto CLI cannot complete an operation."""


CLI_TIMEOUT_SECONDS = 30


@dataclass
class MemantoMemory:
    agent_id: str
    source: str = "langgraph-memanto"
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> "MemantoMemory":
        return cls(
            agent_id=os.environ.get("MEMANTO_AGENT_ID", "langgraph-support-memory"),
            dry_run=os.environ.get("MEMANTO_DRY_RUN", "0") == "1",
        )

    def ensure_agent(self) -> None:
        if self.dry_run:
            print(f"[dry-run] would activate or create Memanto agent: {self.agent_id}")
            return

        try:
            activate = subprocess.run(
                ["memanto", "agent", "activate", self.agent_id],
                capture_output=True,
                text=True,
                timeout=CLI_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise MemantoCliError(
                "The `memanto` CLI is not installed. Run `pip install -r requirements.txt`."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise MemantoCliError(
                f"Timed out after {CLI_TIMEOUT_SECONDS}s while activating Memanto agent `{self.agent_id}`."
            ) from exc

        if activate.returncode == 0:
            return

        self._run(["agent", "create", self.agent_id])

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "preference",
        tags: str = "langgraph,cross-session",
        confidence: float = 0.95,
    ) -> str:
        if self.dry_run:
            return f"[dry-run] remembered: {content}"

        return self._run(
            [
                "remember",
                content,
                "--type",
                memory_type,
                "--tags",
                tags,
                "--confidence",
                str(confidence),
                "--provenance",
                "explicit_statement",
                "--source",
                self.source,
            ]
        )

    def recall(self, query: str, *, limit: int = 5) -> str:
        if self.dry_run:
            return (
                "[dry-run memory]\n"
                "- Customer ACME prefers short answers with bullet points.\n"
                "- Customer ACME works in CET and wants deployment alerts before 09:00."
            )

        return self._run(["recall", query, "--limit", str(limit)])

    def _run(self, args: list[str]) -> str:
        try:
            completed = subprocess.run(
                ["memanto", *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=CLI_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise MemantoCliError(
                "The `memanto` CLI is not installed. Run `pip install -r requirements.txt`."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise MemantoCliError(
                f"Timed out after {CLI_TIMEOUT_SECONDS}s while running `memanto {' '.join(args)}`."
            ) from exc
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()
            raise MemantoCliError(details or f"Memanto command failed: {args}") from exc

        return completed.stdout.strip()
