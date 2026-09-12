"""Convert an Obsidian vault into an importable Open Knowledge Format bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import yaml

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
WIKILINK_RE = re.compile(r"(?P<embed>!)?\[\[(?P<target>[^\]\n]+)\]\]")
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
MEMORY_TYPES = {
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
}


@dataclass
class Report:
    source_files: int = 0
    converted_files: int = 0
    skipped_files: int = 0
    wikilinks_converted: int = 0
    embeds_converted: int = 0
    unresolved_links: list[dict[str, str]] = field(default_factory=list)
    type_counts: dict[str, int] = field(default_factory=dict)
    source_sha256: str = ""


def _normalise_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        values = re.split(r"[,\s]+", value)
    elif isinstance(value, list):
        values = [str(item) for item in value]
    else:
        values = []
    return sorted({item.strip().lstrip("#") for item in values if item.strip()})


def _parse_note(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    return metadata, text[match.end() :]


def _title(metadata: dict[str, Any], body: str, source: Path) -> str:
    candidate = metadata.get("title")
    if candidate:
        return str(candidate).strip()
    heading = HEADING_RE.search(body)
    return heading.group(1).strip() if heading else source.stem


def _memory_type(metadata: dict[str, Any], relative: Path) -> str:
    explicit = str(metadata.get("type", "")).strip().lower()
    if explicit in MEMORY_TYPES:
        return explicit

    # Common Obsidian application schemas carry stronger meaning than folder
    # names. Keep this deterministic: no LLM or private-data upload is needed.
    if metadata.get("codex"):
        return "fact"
    if metadata.get("longform") or metadata.get("inkswell"):
        return "goal"
    if any(part.lower().startswith("draft") for part in relative.parts):
        return "artifact"
    if "plan" in relative.stem.lower():
        return "decision"

    terms = {part.lower() for part in relative.parts}
    terms.update(tag.lower() for tag in _normalise_tags(metadata.get("tags")))
    rules = (
        ("decision", {"decision", "decisions"}),
        ("goal", {"goal", "goals", "project", "projects"}),
        ("preference", {"preference", "preferences"}),
        ("event", {"daily", "journal", "meeting", "meetings"}),
        ("learning", {"learning", "learnings", "lesson", "lessons"}),
        ("error", {"error", "errors", "incident", "incidents"}),
        ("artifact", {"artifact", "artifacts", "reference", "references"}),
    )
    for memory_type, matches in rules:
        if terms & matches:
            return memory_type
    return "context"


def _description(body: str) -> str | None:
    without_code = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    for paragraph in re.split(r"\n\s*\n", without_code):
        cleaned = re.sub(r"^(?:#{1,6}|[-*>])\s*", "", paragraph.strip())
        if cleaned and not cleaned.startswith("!"):
            return re.sub(r"\s+", " ", cleaned)[:280]
    return None


def _timestamp(metadata: dict[str, Any], source: Path) -> str:
    for key in ("timestamp", "date", "created", "created_at", "updated"):
        value = metadata.get(key)
        if value:
            return str(value)
    modified = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
    return modified.isoformat().replace("+00:00", "Z")


def _note_index(files: list[Path], root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for path in files:
        relative = path.relative_to(root)
        keys = {path.stem.casefold(), relative.with_suffix("").as_posix().casefold()}
        for key in keys:
            index.setdefault(key, []).append(relative)
    return index


def _resolve_target(raw_target: str, index: dict[str, list[Path]]) -> Path | None:
    note_part = raw_target.split("#", 1)[0].split("^", 1)[0].strip()
    if not note_part:
        return None
    key = PurePosixPath(note_part.replace("\\", "/")).with_suffix("").as_posix()
    matches = index.get(key.casefold())
    if not matches and "/" not in key:
        matches = index.get(PurePosixPath(key).name.casefold())
    return matches[0] if matches and len(matches) == 1 else None


def _rewrite_links(
    body: str,
    source_relative: Path,
    index: dict[str, list[Path]],
    report: Report,
) -> str:
    output_relative = source_relative.with_suffix(".md")

    def replace(match: re.Match[str]) -> str:
        raw = match.group("target")
        target_and_alias = raw.split("|", 1)
        raw_target = target_and_alias[0].strip()
        alias = target_and_alias[1].strip() if len(target_and_alias) == 2 else ""
        resolved = _resolve_target(raw_target, index)
        if resolved is None:
            report.unresolved_links.append(
                {"source": source_relative.as_posix(), "target": raw_target}
            )
            return match.group(0)

        suffix = ""
        if "#" in raw_target:
            suffix = "#" + raw_target.split("#", 1)[1]
        elif "^" in raw_target:
            suffix = "#^" + raw_target.split("^", 1)[1]
        destination = resolved.with_suffix(".md")
        relative_url = PurePosixPath(
            *([".."] * len(output_relative.parent.parts)), *destination.parts
        ).as_posix()
        if output_relative.parent == Path("."):
            relative_url = destination.as_posix()
        label = alias or PurePosixPath(raw_target.split("#", 1)[0]).name
        report.wikilinks_converted += 1
        if match.group("embed"):
            report.embeds_converted += 1
            return f"![{label}]({quote(relative_url, safe='/#')}{suffix})"
        return f"[{label}]({quote(relative_url, safe='/#')}{suffix})"

    return WIKILINK_RE.sub(replace, body)


def _source_digest(files: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def convert_vault(source: Path, output: Path, *, dry_run: bool = False) -> Report:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise ValueError(f"Vault is not a directory: {source}")
    if output == source or source in output.parents:
        raise ValueError("Output must be outside the source vault")

    files = sorted(
        path
        for path in source.rglob("*.md")
        if ".obsidian" not in path.relative_to(source).parts
        and not any(part.startswith(".") for part in path.relative_to(source).parts)
    )
    report = Report(
        source_files=len(files), source_sha256=_source_digest(files, source)
    )
    index = _note_index(files, source)
    rendered: list[tuple[Path, str]] = []

    for path in files:
        relative = path.relative_to(source)
        metadata, body = _parse_note(path.read_text(encoding="utf-8-sig"))
        if not body.strip() and not metadata:
            report.skipped_files += 1
            continue
        memory_type = _memory_type(metadata, relative)
        report.type_counts[memory_type] = report.type_counts.get(memory_type, 0) + 1
        converted_body = _rewrite_links(body, relative, index, report).strip()
        frontmatter: dict[str, Any] = {
            "type": memory_type,
            "title": _title(metadata, body, path),
            "description": _description(body),
            "tags": _normalise_tags(metadata.get("tags")),
            "timestamp": _timestamp(metadata, path),
            "resource": f"obsidian://open?path={quote(relative.as_posix())}",
            "x_memanto": {
                "type": memory_type,
                "source": "obsidian",
                "provenance": "observed",
            },
            "x_obsidian": {
                "source_path": relative.as_posix(),
                # Preserve the exact parsed source mapping even when a field
                # also has a normalized OKF counterpart.
                "frontmatter": metadata,
            },
        }
        frontmatter = {
            key: value
            for key, value in frontmatter.items()
            if value not in (None, [], {})
        }
        yaml_text = yaml.safe_dump(
            frontmatter, sort_keys=False, allow_unicode=True
        ).strip()
        rendered.append((relative, f"---\n{yaml_text}\n---\n\n{converted_body}\n"))
        report.converted_files += 1

    if not dry_run:
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)
        for relative, text in rendered:
            destination = output / "memories" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text, encoding="utf-8")
        (output / "migration-report.json").write_text(
            json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vault", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = convert_vault(args.vault, args.output, dry_run=args.dry_run)
    print(json.dumps(asdict(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
