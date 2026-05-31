"""Memory backends for the LangGraph + Memanto demo.

The real backend shells out to the Memanto CLI so the example stays close to
how an agent would use Memanto today. The file backend keeps the demo runnable
for reviewers who do not have a Moorcheh API key configured.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class MemoryRecord:
    content: str
    memory_type: str = "fact"
    source: str = "langgraph-support-demo"
    tags: str = "langgraph,memanto,demo"
    created_at: str = ""

    def to_json(self) -> dict[str, str]:
        payload = asdict(self)
        payload["created_at"] = payload["created_at"] or datetime.now(
            timezone.utc
        ).isoformat()
        return payload


class BaseMemoryBackend:
    def remember(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        tags: str = "langgraph,memanto,demo",
    ) -> None:
        raise NotImplementedError

    def recall(self, query: str, *, limit: int = 5) -> list[str]:
        raise NotImplementedError


class FileMemoryBackend(BaseMemoryBackend):
    """Small JSON memory backend used only for offline reviewer demos."""

    def __init__(
        self,
        path: Path,
        *,
        source: str = "langgraph-support-demo",
    ) -> None:
        self.path = path
        self.source = source

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        tags: str = "langgraph,memanto,demo",
    ) -> None:
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
        self.path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    def recall(self, query: str, *, limit: int = 5) -> list[str]:
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
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
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


class MemantoCliBackend(BaseMemoryBackend):
    """Memanto backend that uses the installed `memanto` CLI."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._ensure_agent()

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        tags: str = "langgraph,memanto,demo",
    ) -> None:
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
    if args.backend == "memanto":
        return MemantoCliBackend(args.agent_id)
    return FileMemoryBackend(Path(args.memory_file), source=args.agent_id)


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def _run(cmd: list[str], *, capture: bool = False) -> str:
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
    return RuntimeError(
        "The `memanto` CLI was not found. Run `pip install memanto` and "
        "`memanto` to configure your Moorcheh API key, or use "
        "`--backend file` for the offline demo."
    )
