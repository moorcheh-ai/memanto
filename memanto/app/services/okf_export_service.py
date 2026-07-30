"""
OKF (Open Knowledge Format) Export Service

Serializes an agent's memories into an OKF v0.1 bundle — a directory of
markdown files with YAML frontmatter, one concept per file, grouped into a
folder per Memanto memory type.

Spec: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf

Layout is controlled by ``split``:
    - ``auto`` (default): a type with <= ``threshold`` memories is written as
      one file per memory (``<type>/<slug>.md``); a larger type is collapsed
      into a single stacked file (``<type>/<type>.md``) to avoid thousands of
      files for high-volume agents.
    - ``file``: always one file per memory.
    - ``type``: always one stacked file per type.

Memanto-only fields (id, confidence, provenance, source, status) are preserved
under a namespaced ``x_memanto`` frontmatter block so that
Memanto -> OKF -> Memanto round-trips keep them. OKF consumers ignore unknown
frontmatter keys.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from memanto.app.services.memory_export_service import MEMORY_TYPE_ORDER
from memanto.app.utils.validation import validate_output_path, validate_safe_id

# Stacked files hold multiple OKF documents. This sentinel separates them so
# the loader can split them back apart without colliding with ``---`` that may
# appear inside a document body (e.g. the migrate ``[Supporting data]`` footer).
ENTRY_DELIMITER = "<!-- okf-entry -->"

# Default: collapse a type into a single stacked file once it exceeds this many
# memories (see the ``auto`` split mode).
DEFAULT_SPLIT_THRESHOLD = 50


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class OkfExportService:
    """Formats and writes an OKF bundle for an agent."""

    def __init__(self, exports_dir: Path | None = None):
        self.exports_dir = exports_dir or (Path.home() / ".memanto" / "exports")

    # Public API
    def write_okf_bundle(
        self,
        agent_id: str,
        memories_by_type: dict[str, list[dict[str, Any]]],
        output_dir: Path | None = None,
        split: str = "auto",
        threshold: int = DEFAULT_SPLIT_THRESHOLD,
        summaries: list[Path] | None = None,
        sessions: list[Path] | None = None,
    ) -> dict[str, Any]:
        """
        Generate and write an OKF bundle to disk.

        The bundle nests memories under ``memories/`` and adds sibling context
        sections when data is available::

            <bundle>/
              index.md
              memories/          # the 13 memory types (from Moorcheh)
              daily-summaries/   # generated daily-summary MD files
              sessions/          # per-session logs (adds/deletes + source)
              metrics/           # aggregate stats & ASCII visualizations

        Args:
            agent_id: Agent identifier.
            memories_by_type: Dict mapping memory type -> list of memory dicts.
            output_dir: Custom bundle directory. Defaults to
                ``~/.memanto/exports/{agent_id}_okf``.
            split: Layout mode — ``auto``, ``file``, or ``type``.
            threshold: Per-type memory count above which ``auto`` collapses to a
                single stacked file.
            summaries: Daily-summary MD file paths to copy in (optional).
            sessions: Session MD file paths to copy in (optional).

        Returns:
            Dict with ``output_path``, ``total_memories``, ``per_type_counts``,
            and ``sections`` (the section folders that were written).
        """
        validate_safe_id(agent_id, "agent_id")
        if split not in ("auto", "file", "type"):
            raise ValueError("split must be one of: auto, file, type")

        if output_dir is None:
            base = self.exports_dir / f"{agent_id}_okf"
        else:
            validated = validate_output_path(
                str(output_dir), base_dir=self.exports_dir.parent
            )
            assert validated is not None
            base = validated
        base.mkdir(parents=True, exist_ok=True)

        # Section order mirrors how an agent would read the bundle.
        sections: dict[str, str] = {}

        type_entries = self._write_memories_section(
            base / "memories", memories_by_type, split, threshold
        )
        per_type_counts = dict(type_entries)
        total = sum(per_type_counts.values())
        if type_entries:
            sections["memories"] = (
                f"{total} memories across {len(type_entries)} type(s)"
            )

        n_summaries = self._write_docs_section(
            base / "daily-summaries", summaries or [], "Daily Summaries"
        )
        if n_summaries:
            sections["daily-summaries"] = f"{n_summaries} daily-summary file(s)"

        n_sessions = self._write_docs_section(
            base / "sessions", sessions or [], "Sessions"
        )
        if n_sessions:
            sections["sessions"] = f"{n_sessions} session log file(s)"

        if self._write_metrics_section(base / "metrics", memories_by_type):
            sections["metrics"] = "aggregate stats & visualizations"

        self._write_root_index(base, agent_id, sections)

        return {
            "output_path": str(base.resolve()),
            "total_memories": total,
            "per_type_counts": per_type_counts,
            "sections": list(sections),
        }

    # Section writers
    def _write_memories_section(
        self,
        memories_dir: Path,
        memories_by_type: dict[str, list[dict[str, Any]]],
        split: str,
        threshold: int,
    ) -> list[tuple[str, int]]:
        """Write the ``memories/`` section (one folder per type). Returns the
        ``(type, count)`` entries that had memories."""
        entries: list[tuple[str, int]] = []
        for mem_type in MEMORY_TYPE_ORDER:
            memories = memories_by_type.get(mem_type) or []
            if not memories:
                continue

            type_dir = memories_dir / mem_type
            type_dir.mkdir(parents=True, exist_ok=True)

            use_stacked = split == "type" or (
                split == "auto" and len(memories) > threshold
            )
            if use_stacked:
                docs = [self._render_okf_doc(m, mem_type) for m in memories]
                stacked = f"\n{ENTRY_DELIMITER}\n".join(docs)
                (type_dir / f"{mem_type}.md").write_text(stacked, encoding="utf-8")
                links = [
                    (m.get("title") or "Untitled", f"{mem_type}.md") for m in memories
                ]
            else:
                used_slugs: set[str] = set()
                links = []
                for mem in memories:
                    slug = self._unique_slug(mem.get("title") or "memory", used_slugs)
                    (type_dir / f"{slug}.md").write_text(
                        self._render_okf_doc(mem, mem_type), encoding="utf-8"
                    )
                    links.append((mem.get("title") or "Untitled", f"{slug}.md"))

            self._write_index(type_dir, mem_type, f"{mem_type} ({len(links)})", links)
            entries.append((mem_type, len(memories)))

        if entries:
            self._write_index(
                memories_dir,
                "memories",
                f"Memories ({sum(count for _, count in entries)})",
                [(mem_type, f"{mem_type}/index.md") for mem_type, _ in entries],
            )
        return entries

    def _write_docs_section(
        self, section_dir: Path, files: list[Path], title: str
    ) -> int:
        """Copy context MD files (daily summaries / session logs) into a section
        folder verbatim and write an index. Returns the count copied.

        These are export-only context — the loader ignores everything outside
        ``memories/`` — so they are copied as-is rather than re-wrapped as OKF
        nodes.
        """
        existing = sorted(f for f in files if f.exists())
        if not existing:
            return 0

        section_dir.mkdir(parents=True, exist_ok=True)
        links: list[tuple[str, str]] = []
        for src in existing:
            shutil.copy2(str(src), str(section_dir / src.name))
            links.append((src.name, src.name))

        self._write_index(section_dir, title, f"{title} ({len(links)})", links)
        return len(links)

    def _write_metrics_section(
        self, metrics_dir: Path, memories_by_type: dict[str, list[dict[str, Any]]]
    ) -> bool:
        """Write a single aggregate metrics overview computed once from the
        gathered memories (no per-day loop, no LLM). Returns False when there
        are no memories to chart."""
        records: list[dict[str, Any]] = []
        for mem_type, memories in memories_by_type.items():
            for mem in memories:
                records.append(
                    {
                        "timestamp": self._parse_ts(mem.get("created_at")),
                        "type": mem_type.upper(),
                        "title": mem.get("title") or "Untitled",
                        "confidence": _as_float(mem.get("confidence"), 0.8),
                    }
                )
        if not records:
            return False

        from memanto.app.services.summary_visualization_service import (
            SummaryVisualizationService,
        )

        viz = SummaryVisualizationService().build_visualization_markdown(records)
        if not viz.strip():
            return False

        metrics_dir.mkdir(parents=True, exist_ok=True)
        body = f"# Metrics — aggregate\n\n> {len(records)} memories\n{viz}\n"
        (metrics_dir / "overview.md").write_text(body, encoding="utf-8")
        self._write_index(
            metrics_dir, "metrics", "Metrics", [("overview", "overview.md")]
        )
        return True

    @staticmethod
    def _parse_ts(value: Any) -> datetime:
        """Best-effort parse of a stored ``created_at`` into a datetime; falls
        back to now so the activity timeline always has an hour bucket."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                return datetime.fromisoformat(text)
            except ValueError:
                pass
        return datetime.now()

    # Rendering helpers
    def _render_okf_doc(self, mem: dict[str, Any], mem_type: str) -> str:
        """Render a single memory dict as one OKF markdown document."""
        content = (mem.get("content") or "").strip()
        title = mem.get("title") or "Untitled"

        frontmatter: dict[str, Any] = {"type": mem_type, "title": title}

        description = self._first_line(content)
        if description:
            frontmatter["description"] = description

        tags = mem.get("tags") or []
        if tags:
            frontmatter["tags"] = list(tags)

        created_at = mem.get("created_at")
        if created_at:
            frontmatter["timestamp"] = str(created_at)

        source_ref = mem.get("source_ref")
        if source_ref:
            frontmatter["resource"] = source_ref

        x_memanto: dict[str, Any] = {}
        for key in ("id", "confidence", "provenance", "source", "status"):
            val = mem.get(key)
            if val not in (None, ""):
                x_memanto[key] = val
        x_memanto["type"] = mem_type
        frontmatter["x_memanto"] = x_memanto

        front = yaml.safe_dump(
            frontmatter,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ).strip()
        return f"---\n{front}\n---\n\n{content}\n"

    def _first_line(self, content: str) -> str:
        """First non-empty line of content (heading marks stripped), for the
        optional OKF ``description`` field."""
        for line in content.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                return stripped[:200]
        return ""

    def _slugify(self, title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        return slug[:60].rstrip("-") or "memory"

    def _unique_slug(self, title: str, used: set[str]) -> str:
        base = self._slugify(title)
        slug = base
        counter = 2
        while slug in used:
            slug = f"{base}-{counter}"
            counter += 1
        used.add(slug)
        return slug

    def _write_index(
        self, directory: Path, title: str, heading: str, links: list[tuple[str, str]]
    ) -> None:
        """Write a navigational ``index.md`` (skipped on import)."""
        now = datetime.now().isoformat(timespec="seconds")
        lines = [
            "---",
            "type: index",
            f"title: {title}",
            f"timestamp: {now}",
            "---",
            "",
            f"# {heading}",
            "",
        ]
        lines += [f"- [{text}]({rel})" for text, rel in links]
        lines.append("")
        (directory / "index.md").write_text("\n".join(lines), encoding="utf-8")

    def _write_root_index(
        self, base: Path, agent_id: str, sections: dict[str, str]
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        lines = [
            "---",
            "type: index",
            f"title: {agent_id} knowledge bundle",
            f"timestamp: {now}",
            "---",
            "",
            f"# {agent_id} — OKF bundle",
            "",
        ]
        if sections:
            lines += [
                f"- [{name}]({name}/index.md) — {desc}"
                for name, desc in sections.items()
            ]
        else:
            lines.append("> Empty bundle — no memories found.")
        lines.append("")
        (base / "index.md").write_text("\n".join(lines), encoding="utf-8")
