"""Memory backends for the Claude Code skills + Memanto demo."""

from __future__ import annotations

import json
import re
import subprocess
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CLI_TIMEOUT_SECONDS = 30


@dataclass
class MemoryRecord:
    content: str
    memory_type: str = "learning"
    source: str = "claudecode-skills-demo"
    tags: str = "claudecode,skills,memanto"
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
        memory_type: str = "learning",
        tags: str = "claudecode,skills,memanto",
    ) -> None:
        raise NotImplementedError

    def recall(self, query: str, *, limit: int = 6) -> list[str]:
        raise NotImplementedError


class FileMemoryBackend(BaseMemoryBackend):
    """Local JSON backend for offline reviewer demos."""

    def __init__(self, path: Path, *, source: str = "claudecode-skills-demo") -> None:
        self.path = path
        self.source = source

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "learning",
        tags: str = "claudecode,skills,memanto",
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

    def recall(self, query: str, *, limit: int = 6) -> list[str]:
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
    """Backend that uses the installed Memanto package and CLI session."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._ensure_agent()

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "learning",
        tags: str = "claudecode,skills,memanto",
    ) -> None:
        self._client().remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=_memory_title(content),
            content=content,
            confidence=0.8,
            tags=_split_tags(tags),
            source=self.agent_id,
            provenance="explicit_statement",
        )

    def recall(self, query: str, *, limit: int = 6) -> list[str]:
        result = self._client().recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            tags=_split_tags("claudecode,skills,memanto"),
        )
        memories = result.get("memories", [])
        recalled: list[str] = []
        for memory in memories:
            content = str(memory.get("content") or memory.get("title") or "").strip()
            if content:
                recalled.append(content)
        return recalled[:limit]

    def _ensure_agent(self) -> None:
        try:
            create = subprocess.run(
                ["memanto", "agent", "create", self.agent_id],
                capture_output=True,
                text=True,
                check=False,
                timeout=CLI_TIMEOUT_SECONDS,
            )
        except OSError as exc:
            raise _missing_memanto_error() from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Memanto CLI agent creation timed out") from exc
        if create.returncode == 0:
            return
        detail = _command_detail(create.stdout, create.stderr)
        if "already exists" not in detail.lower() and "exists" not in detail.lower():
            raise RuntimeError(f"Memanto CLI agent creation failed: {detail}")
        _run(["memanto", "agent", "activate", self.agent_id])

    def _client(self) -> Any:
        try:
            from memanto.cli.client.sdk_client import SdkClient
            from memanto.cli.config.manager import ConfigManager
        except ImportError as exc:
            raise _missing_memanto_error() from exc

        config = ConfigManager()
        api_key = config.get_api_key()
        if not api_key:
            raise RuntimeError(
                "MEMANTO is not configured. Run `memanto` to set an API key."
            )

        active_agent_id, active_session_token = config.get_active_session()
        if active_agent_id != self.agent_id or not active_session_token:
            self._ensure_agent()
            active_agent_id, active_session_token = config.get_active_session()
        if active_agent_id != self.agent_id or not active_session_token:
            raise RuntimeError(f"Memanto agent `{self.agent_id}` is not active.")

        client = SdkClient(api_key)
        client.agent_id = self.agent_id
        client.session_token = active_session_token
        return client


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def _split_tags(tags: str) -> list[str]:
    return [tag.strip() for tag in tags.split(",") if tag.strip()]


def _memory_title(content: str) -> str:
    return content[:47] + "..." if len(content) > 50 else content


def _command_detail(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    for stream in (stderr, stdout):
        if isinstance(stream, bytes):
            stream = stream.decode(errors="replace")
        detail = (stream or "").strip()
        if detail:
            return detail
    return "unknown CLI error"


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=CLI_TIMEOUT_SECONDS,
        )
    except OSError as exc:
        raise _missing_memanto_error() from exc
    except subprocess.TimeoutExpired as exc:
        detail = _command_detail(exc.stdout, exc.stderr)
        raise RuntimeError(f"Memanto CLI command timed out: {detail}") from exc
    except subprocess.CalledProcessError as exc:
        detail = _command_detail(exc.stdout, exc.stderr)
        raise RuntimeError(f"Memanto CLI command failed: {detail}") from exc
    return result.stdout


def _missing_memanto_error() -> RuntimeError:
    return RuntimeError(
        "The `memanto` CLI was not found. Run `pip install memanto` and "
        "`memanto` to configure your Moorcheh API key, or use "
        "`--backend file` for the offline demo."
    )
