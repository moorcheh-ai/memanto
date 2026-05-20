#!/usr/bin/env python3
"""Read mattpocock/skills-style plugin manifests.

The upstream skills repository exposes skill paths through
``.claude-plugin/plugin.json``. This helper lets reviewers point the example at
a local checkout and list the exact skill names/descriptions that can be used
with ``bridge.py``.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SkillEntry:
    name: str
    description: str
    path: str


def load_skill_entries(repo_root: Path) -> list[SkillEntry]:
    plugin_path = repo_root / ".claude-plugin" / "plugin.json"
    plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    entries: list[SkillEntry] = []
    for raw_path in plugin.get("skills", []):
        skill_dir = (repo_root / raw_path).resolve()
        skill_md = skill_dir / "SKILL.md"
        metadata = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        entries.append(
            SkillEntry(
                name=metadata.get("name", skill_dir.name),
                description=metadata.get("description", ""),
                path=raw_path,
            )
        )
    return entries


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(?P<body>.*?)\n---", text, flags=re.DOTALL)
    if not match:
        return {}
    metadata: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def render_markdown(entries: list[SkillEntry]) -> str:
    lines = [
        "| Skill | Path | Description |",
        "| --- | --- | --- |",
    ]
    for entry in entries:
        lines.append(
            f"| `{entry.name}` | `{entry.path}` | {entry.description or '-'} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List skills from a mattpocock/skills-style plugin manifest."
    )
    parser.add_argument("repo_root", help="Path to the local mattpocock/skills checkout")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    entries = load_skill_entries(Path(args.repo_root))
    if args.format == "json":
        print(json.dumps([entry.__dict__ for entry in entries], indent=2))
    else:
        print(render_markdown(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
