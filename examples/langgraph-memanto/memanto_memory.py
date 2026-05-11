from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass


class MemantoCommandError(RuntimeError):
    pass


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


class MemantoMemory:
    """Tiny CLI adapter used by the LangGraph nodes in this example."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.command = self._resolve_command()

    def ensure_ready(self) -> None:
        if not os.environ.get("MOORCHEH_API_KEY"):
            raise MemantoCommandError(
                "MOORCHEH_API_KEY not set. Copy .env.example to .env and add a key."
            )

        activate = self._run(["agent", "activate", self.agent_id], check=False)
        if activate.returncode == 0:
            return

        self._run(["agent", "create", self.agent_id], check=True)

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        tags: list[str] | None = None,
        confidence: float = 0.8,
        provenance: str = "explicit_statement",
    ) -> str:
        cmd = [
            "remember",
            content,
            "--type",
            memory_type,
            "--confidence",
            str(confidence),
            "--provenance",
            provenance,
            "--source",
            self.agent_id,
        ]
        if tags:
            cmd.extend(["--tags", ",".join(tags)])

        return self._run(cmd, check=True).stdout

    def recall(
        self, query: str, *, limit: int = 5, memory_type: str | None = None
    ) -> str:
        cmd = ["recall", query, "--limit", str(limit)]
        if memory_type:
            cmd.extend(["--type", memory_type])

        result = self._run(cmd, check=True)
        return result.stdout.strip() or "(Memanto returned no matching memories.)"

    def _run(self, args: list[str], *, check: bool) -> CommandResult:
        full_cmd = [*self.command, *args]
        completed = subprocess.run(
            full_cmd,
            capture_output=True,
            check=False,
            text=True,
        )
        result = CommandResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )
        if check and result.returncode != 0:
            rendered = " ".join(shlex.quote(part) for part in full_cmd)
            raise MemantoCommandError(
                f"Memanto command failed: {rendered}\n{result.stderr or result.stdout}"
            )
        return result

    @staticmethod
    def _resolve_command() -> list[str]:
        configured = os.environ.get("MEMANTO_COMMAND")
        if configured:
            return shlex.split(configured)
        if shutil.which("memanto"):
            return ["memanto"]
        return [sys.executable, "-m", "memanto"]


def create_memory_from_env() -> MemantoMemory:
    agent_id = os.environ.get("MEMANTO_AGENT_ID", "langgraph-support-demo")
    memory = MemantoMemory(agent_id)
    memory.ensure_ready()
    return memory
