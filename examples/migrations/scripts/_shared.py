"""Shared helpers for migration scripts."""

from __future__ import annotations

import sys
from typing import Any


def parse_markdown(text: str, yaml: Any) -> tuple[str, list, str, str | None]:
    """Parse YAML frontmatter from a markdown string.

    Returns (title, tags, body, created_at).
    """
    title = ""
    tags: list = []
    created_at = None
    body = text

    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm_text = text[3:end].strip()
            rest = text[end + 3:].strip()
            try:
                fm = yaml.safe_load(fm_text) or {}
                title = str(fm.get("title") or fm.get("Title") or "")
                tags = [str(t) for t in (fm.get("tags") or fm.get("Tags") or []) if t]
                raw_created = str(fm.get("created") or fm.get("Created") or "")
                created_at = raw_created or None
            except Exception:
                pass
            body = rest

    return title, tags, body, created_at


def print_summary(summary: Any, dry_run: bool) -> None:
    mode = "Dry run" if dry_run else "Migration"
    print(f"\n{mode} complete")
    print(f"  Source records : {summary.source_count}")
    print(f"  Mapped memories: {summary.mapped_count}  (skipped {summary.skipped})")
    types = ", ".join(f"{k}: {v}" for k, v in summary.type_counts.items()) or "auto"
    print(f"  Type breakdown : {types}")
    if not dry_run:
        print(f"  Imported       : {summary.imported}  Failed: {summary.failed}")


def require_agent(agent: str | None, script: str) -> str | None:
    """Return agent if set and non-empty, otherwise print an error and return None."""
    if agent and agent.strip():
        return agent.strip()
    print(
        f"--agent is required for a live migration. "
        f"Example: python scripts/{script} --agent my-agent-id",
        file=sys.stderr,
    )
    return None
