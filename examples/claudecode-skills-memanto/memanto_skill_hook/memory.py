"""
Core SkillMemory implementation.

Connects to the Memanto REST API (or directly via Moorcheh SDK) to provide
cross-skill memory for the mattpocock/skills developer workflow.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("memanto_skill_hook")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENV_PREFIX = "MEMANTO_"

# Try loading .env if python-dotenv is available (optional dep)
try:
    from dotenv import load_dotenv

    # Look for .env in cwd, then in the example directory
    _cwd_env = Path.cwd() / ".env"
    _example_env = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_cwd_env)
    load_dotenv(_example_env)
except ImportError:
    pass  # dotenv not installed — user must export vars manually


@dataclass
class SkillMemoryConfig:
    """Runtime configuration resolved from environment / constructor args."""

    api_key: str = ""
    agent_id: str = "claudecode-dev"
    memanto_url: str = ""  # empty → use SDK directly
    context_limit: int = 5
    auto_distill: bool = True  # let Memanto LLM distill memories

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = (
                os.getenv(f"{_ENV_PREFIX}API_KEY")
                or os.getenv("MOORCHEH_API_KEY", "")
            )
        if not self.agent_id or self.agent_id == "claudecode-dev":
            self.agent_id = os.getenv(
                f"{_ENV_PREFIX}AGENT_ID", self.agent_id
            )
        if not self.memanto_url:
            self.memanto_url = os.getenv(f"{_ENV_PREFIX}URL", "")
        limit = os.getenv(f"{_ENV_PREFIX}CONTEXT_LIMIT")
        if limit:
            try:
                self.context_limit = int(limit)
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid MEMANTO_CONTEXT_LIMIT=%r, using default %d",
                    limit, self.context_limit,
                )

    @property
    def has_server(self) -> bool:
        return bool(self.memanto_url)


# ---------------------------------------------------------------------------
# SkillMemory — the public API
# ---------------------------------------------------------------------------


@dataclass
class SkillMemory:
    """Provides persistent cross-skill memory via Memanto.

    Attributes:
        config: Runtime configuration. Auto-populated from env vars.
        _sdk_client: Lazy-initialized MoorchehClient (SDK path).
    """

    config: SkillMemoryConfig = field(default_factory=SkillMemoryConfig)
    _sdk_client: Any = None

    # ------------------------------------------------------------------
    # Public lifecycle hooks
    # ------------------------------------------------------------------

    def on_skill_start(
        self,
        *,
        skill_name: str,
        file_path: str = "",
        task_description: str = "",
    ) -> str:
        """Query Memanto for context relevant to the upcoming skill.

        Returns a plain-text block to prepend to the skill's system prompt.
        """
        query = self._build_recall_query(skill_name, file_path, task_description)
        try:
            results = self._recall(query)
        except Exception as exc:
            logger.warning("recall failed (%s) — continuing without memory", exc)
            return ""

        if not results:
            return ""

        return self._format_context(results, skill_name)

    def on_skill_complete(
        self,
        *,
        skill_name: str,
        summary: str,
        file_path: str = "",
    ) -> bool:
        """Store distilled learnings from a completed skill execution.

        Returns True on success, False on failure.
        """
        content = self._build_memory_content(
            skill_name, summary, file_path
        )
        try:
            self._remember(
                title=f"Skill: {skill_name} — {Path(file_path).name or 'general'}",
                content=content,
                memory_type="decision",
                tags=self._infer_tags(skill_name, file_path),
                source=skill_name.lstrip("/"),
            )
            return True
        except Exception as exc:
            logger.warning("remember failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # SDK / API helpers
    # ------------------------------------------------------------------

    def _get_sdk_client(self) -> Any:
        """Lazy-initialize the Moorcheh SDK client."""
        if self._sdk_client is None:
            from moorcheh_sdk import MoorchehClient

            if not self.config.api_key:
                raise RuntimeError(
                    "MEMANTO_API_KEY (or MOORCHEH_API_KEY) is not set. "
                    "Export it or add it to your .env file."
                )
            self._sdk_client = MoorchehClient(api_key=self.config.api_key)
        return self._sdk_client

    def _recall(self, query: str) -> list[dict]:
        """Semantic search for relevant memories."""
        if self.config.has_server:
            return self._recall_via_server(query)
        return self._recall_via_sdk(query)

    def _recall_via_server(self, query: str) -> list[dict]:
        url = f"{self.config.memanto_url.rstrip('/')}/api/v2/recall"
        resp = requests.post(
            url,
            json={
                "agent_id": self.config.agent_id,
                "query": query,
                "limit": self.config.context_limit,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("memories", [])

    def _recall_via_sdk(self, query: str) -> list[dict]:
        client = self._get_sdk_client()
        result = client.recall(
            agent_id=self.config.agent_id,
            query=query,
            limit=self.config.context_limit,
        )
        return result.get("memories", [])

    def _remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str = "decision",
        tags: list[str] | None = None,
        source: str = "skill-hook",
    ) -> dict:
        """Store a memory."""
        if self.config.has_server:
            return self._remember_via_server(
                title=title,
                content=content,
                memory_type=memory_type,
                tags=tags,
                source=source,
            )
        return self._remember_via_sdk(
            title=title,
            content=content,
            memory_type=memory_type,
            tags=tags,
            source=source,
        )

    def _remember_via_server(self, **kwargs: Any) -> dict:
        url = f"{self.config.memanto_url.rstrip('/')}/api/v2/remember"
        resp = requests.post(
            url,
            json={
                "agent_id": self.config.agent_id,
                **kwargs,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def _remember_via_sdk(self, **kwargs: Any) -> dict:
        client = self._get_sdk_client()
        return client.remember(
            agent_id=self.config.agent_id,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Prompt construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_recall_query(
        skill_name: str, file_path: str, task_description: str
    ) -> str:
        """Build a natural-language recall query from skill metadata."""
        parts: list[str] = []
        if task_description:
            parts.append(task_description)
        if file_path:
            parts.append(f"working in {file_path}")
        # Add skill-specific context keywords
        skill_keywords = {
            "/tdd": "testing strategy test patterns preferences",
            "/grill-with-docs": "documentation standards API design decisions",
            "/handoff": "architecture decisions codebase conventions team patterns",
            "/review": "code review feedback style preferences",
            "/refactor": "refactoring patterns architectural choices",
        }
        if skill_name in skill_keywords:
            parts.append(skill_keywords[skill_name])
        if not parts:
            parts.append(f"developer preferences and past decisions for {skill_name}")
        return " | ".join(parts)

    @staticmethod
    def _build_memory_content(
        skill_name: str, summary: str, file_path: str
    ) -> str:
        """Format a skill summary into a storable memory."""
        sections = [
            f"## Skill: {skill_name}",
            f"### File: {file_path}" if file_path else "",
            "",
            summary,
        ]
        return "\n".join(s for s in sections if s is not None)

    @staticmethod
    def _format_context(memories: list[dict], skill_name: str) -> str:
        """Format recalled memories into a context injection block."""
        if not memories:
            return ""
        lines = [
            f"<memanto-context skill=\"{skill_name}\">",
            "  <engineering-profile>",
            "  The following memories from past sessions are relevant:",
            "",
        ]
        for m in memories:
            mtype = m.get("type", "unknown")
            title = m.get("title", "untitled")
            content = m.get("content", "")
            score = m.get("score", "")
            score_str = f" (relevance: {score:.2f})" if score else ""
            lines.append(f"  [{mtype.upper()}] {title}{score_str}")
            # Truncate very long content
            if len(content) > 500:
                content = content[:497] + "..."
            lines.append(f"    {content}")
            lines.append("")
        lines.append("  </engineering-profile>")
        lines.append("</memanto-context>")
        return "\n".join(lines)

    @staticmethod
    def _infer_tags(skill_name: str, file_path: str) -> list[str]:
        """Infer tags from skill name and file path."""
        tags = ["skill-hook"]
        if skill_name:
            tags.append(skill_name.lstrip("/"))
        if file_path:
            ext = Path(file_path).suffix.lstrip(".")
            if ext:
                tags.append(f"lang:{ext}")
        return tags
