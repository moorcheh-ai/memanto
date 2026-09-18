"""Normalize a Memanto OKF export into a self-contained portable bundle."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, quote, unquote, urlparse

import yaml

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
MARKDOWN_LINK_RE = re.compile(
    r"(?P<prefix>!?)\[(?P<label>[^\]]*)\]\((?P<target>[^)]+)\)"
)


def _source_path(metadata: dict[str, object]) -> PurePosixPath | None:
    resource = metadata.get("resource")
    if not isinstance(resource, str) or not resource.startswith("obsidian://"):
        return None
    value = parse_qs(urlparse(resource).query).get("path", [None])[0]
    return PurePosixPath(unquote(value)) if value else None


def _split_document(text: str) -> tuple[dict[str, object], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    metadata = yaml.safe_load(match.group(1)) or {}
    return metadata, text[match.end() :]


def _dedupe_opening(body: str) -> str:
    paragraphs = re.split(r"(\n\s*\n)", body)
    content_indexes = [i for i, value in enumerate(paragraphs) if value.strip()]
    if len(content_indexes) < 2:
        return body
    first, second = content_indexes[:2]

    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())

    if normalize(paragraphs[first]) != normalize(paragraphs[second]):
        return body
    del paragraphs[first:second]
    return "".join(paragraphs)


def normalize_export(bundle: Path) -> int:
    memories = bundle.resolve() / "memories"
    documents: list[tuple[Path, dict[str, object], str]] = []
    destinations: dict[PurePosixPath, Path] = {}
    for path in sorted(memories.rglob("*.md")):
        if path.name == "index.md":
            continue
        metadata, body = _split_document(path.read_text(encoding="utf-8"))
        documents.append((path, metadata, body))
        source = _source_path(metadata)
        if source is not None:
            destinations[source] = path.relative_to(memories)

    changed = 0
    for path, metadata, body in documents:
        source = _source_path(metadata)
        if source is None:
            continue

        def replace(
            match: re.Match[str], source: PurePosixPath = source, path: Path = path
        ) -> str:
            raw_target = unquote(match.group("target"))
            if raw_target.startswith(("#", "http://", "https://", "obsidian://")):
                return match.group(0)
            path_part, separator, fragment = raw_target.partition("#")
            emitted_target = (path.parent / path_part).resolve()
            if emitted_target.is_relative_to(memories) and emitted_target.exists():
                return match.group(0)
            candidate = PurePosixPath(
                os.path.normpath((source.parent / path_part).as_posix()).replace(
                    "\\", "/"
                )
            )
            destination = destinations.get(candidate)
            if destination is None:
                external = f"obsidian://open?path={quote(candidate.as_posix())}"
                return f"{match.group('prefix')}[{match.group('label')}]({external})"
            relative = os.path.relpath(
                destination, path.relative_to(memories).parent
            ).replace("\\", "/")
            suffix = f"#{fragment}" if separator else ""
            target = quote(f"{relative}{suffix}", safe="/#^")
            return f"{match.group('prefix')}[{match.group('label')}]({target})"

        normalized_body = MARKDOWN_LINK_RE.sub(replace, _dedupe_opening(body))
        if normalized_body == body:
            continue
        match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
        prefix = match.group(0) if match else ""
        path.write_text(f"{prefix}{normalized_body}", encoding="utf-8")
        changed += 1
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    print(f"Normalized {normalize_export(args.bundle)} exported memories")


if __name__ == "__main__":
    main()
