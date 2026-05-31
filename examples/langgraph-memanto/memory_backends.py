"""Memory backends for the LangGraph + Memanto demo.

The real backend shells out to the Memanto CLI so the example stays close to
how an agent would use Memanto today. The file backend keeps the demo runnable
for reviewers who do not have a Moorcheh API key configured.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class MemoryRecord:
    """Serializable memory record shared by the demo backends."""

    content: str
    memory_type: str = "fact"
    source: str = "langgraph-support-demo"
    tags: str = "langgraph,memanto,demo"
    created_at: str = ""

    def to_json(self) -> dict[str, str]:
        """Return a JSON-safe representation with a creation timestamp."""

        payload = asdict(self)
        payload["created_at"] = (
            payload["created_at"] or datetime.now(timezone.utc).isoformat()
        )
        return payload


class BaseMemoryBackend:
    """Minimal memory interface used by the LangGraph demo."""

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        tags: str = "langgraph,memanto,demo",
    ) -> None:
        """Persist one memory string for later recall."""

        raise NotImplementedError

    def recall(self, query: str, *, limit: int = 5) -> list[str]:
        """Return memory strings related to a query."""

        raise NotImplementedError


class FileMemoryBackend(BaseMemoryBackend):
    """Small JSON memory backend used only for offline reviewer demos."""

    def __init__(
        self,
        path: Path,
        *,
        source: str = "langgraph-support-demo",
    ) -> None:
        """Create a file-backed memory store at the given path."""

        self.path = path
        self.source = source

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        tags: str = "langgraph,memanto,demo",
    ) -> None:
        """Append a memory record to the JSON demo store."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = self._load()
        records.append(
            MemoryRecord(
                content=content,
                memory_type=memory_type,
                source=self.source,
                tags=tags,
            ).to_json()
        )
        self._write_records_atomic(records)

    def recall(self, query: str, *, limit: int = 5) -> list[str]:
        """Rank stored memories by simple term overlap with the query."""

        query_terms = _terms(query)
        ranked: list[tuple[int, str]] = []
        for record in self._load():
            content = str(record.get("content", ""))
            score = len(query_terms.intersection(_terms(content)))
            if score:
                ranked.append((score, content))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [content for _, content in ranked[:limit]]

    def _load(self) -> list[dict[str, str]]:
        """Read demo records, treating malformed local state as empty memory."""

        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warnings.warn(
                f"Ignoring malformed demo memory file: {self.path}",
                RuntimeWarning,
                stacklevel=2,
            )
            return []
        except OSError as exc:
            warnings.warn(
                f"Could not read demo memory file {self.path}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            return []
        if not _is_record_list(payload):
            warnings.warn(
                f"Ignoring unexpected demo memory shape in {self.path}",
                RuntimeWarning,
                stacklevel=2,
            )
            return []
        return [
            {str(key): str(value) for key, value in record.items()}
            for record in payload
        ]

    def _write_records_atomic(self, records: list[dict[str, str]]) -> None:
        """Rewrite the JSON memory file without leaving partial writes behind."""

        temp_fd, temp_name = tempfile.mkstemp(
            prefix=f"{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as temp_file:
                temp_file.write(json.dumps(records, indent=2) + "\n")
            os.replace(temp_name, self.path)
        except OSError:
            Path(temp_name).unlink(missing_ok=True)
            raise


class MemantoCliBackend(BaseMemoryBackend):
    """Memanto backend that uses the installed `memanto` CLI."""

    def __init__(self, agent_id: str) -> None:
        """Create or activate the Memanto agent used by the demo."""

        self.agent_id = agent_id
        self._ensure_agent()

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        tags: str = "langgraph,memanto,demo",
    ) -> None:
        """Store a memory through the Memanto CLI."""

        cmd = [
            "memanto",
            "remember",
            content,
            "--type",
            memory_type,
            "--source",
            self.agent_id,
            "--tags",
            tags,
        ]
        _run(cmd)

    def recall(self, query: str, *, limit: int = 5) -> list[str]:
        """Recall relevant memories through the Memanto CLI."""

        output = _run(
            ["memanto", "recall", query, "--limit", str(limit)],
            capture=True,
        )
        return [
            line.strip(" -")
            for line in output.splitlines()
            if line.strip() and not line.lstrip().startswith(("MEMANTO", "Agent:"))
        ][:limit]

    def _ensure_agent(self) -> None:
        """Ensure the demo agent exists and is active before CLI calls."""

        try:
            create = subprocess.run(
                ["memanto", "agent", "create", self.agent_id],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise _missing_memanto_error() from exc
        if create.returncode == 0:
            return
        _run(["memanto", "agent", "activate", self.agent_id])


def build_backend(args: argparse.Namespace) -> BaseMemoryBackend:
    """Build either the live Memanto backend or the offline file backend."""

    if args.backend == "memanto":
        return MemantoCliBackend(args.agent_id)
    return FileMemoryBackend(Path(args.memory_file), source=args.agent_id)


def _terms(text: str) -> set[str]:
    """Extract coarse search terms for the offline demo ranking."""

    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def _run(cmd: list[str], *, capture: bool = False) -> str:
    """Run a Memanto CLI command and normalize errors for the demo."""

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError as exc:
        raise _missing_memanto_error() from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "unknown CLI error"
        raise RuntimeError(f"Memanto CLI command failed: {detail}") from exc
    return result.stdout if capture else ""


def _missing_memanto_error() -> RuntimeError:
    """Return the setup hint shown when the Memanto CLI is unavailable."""

    return RuntimeError(
        "The `memanto` CLI was not found. Run `pip install memanto` and "
        "`memanto` to configure your Moorcheh API key, or use "
        "`--backend file` for the offline demo."
    )


def _is_record_list(payload: Any) -> bool:
    """Return whether JSON payload has the expected list-of-records shape."""

    return isinstance(payload, list) and all(
        isinstance(record, dict) for record in payload
    )
