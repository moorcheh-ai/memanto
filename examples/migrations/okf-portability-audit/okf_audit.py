"""Deterministic portability audit for two Open Knowledge Format bundles.

The utility intentionally performs no writes to either bundle and needs no API
key.  It uses Memanto's production OKF loader, then compares stable identities
and every portable field so migrations can be checked before deleting a source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memanto.cli.migrate.okf_loader import load_okf_bundle


@dataclass(frozen=True)
class Change:
    """One matched memory whose portable content changed."""

    identity: str
    title: str
    fields: tuple[str, ...]


@dataclass
class AuditReport:
    """Serializable result of comparing two OKF bundles."""

    source_count: int
    target_count: int
    unchanged: int = 0
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    moved: list[str] = field(default_factory=list)
    changed: list[Change] = field(default_factory=list)
    source_duplicates: list[str] = field(default_factory=list)
    target_duplicates: list[str] = field(default_factory=list)
    source_provenance_gaps: list[str] = field(default_factory=list)
    target_provenance_gaps: list[str] = field(default_factory=list)

    @property
    def is_lossless(self) -> bool:
        """True when no source node or portable field was lost or changed."""
        return not (
            self.removed
            or self.changed
            or self.source_duplicates
            or self.target_duplicates
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report including the derived verdict."""
        result = asdict(self)
        result["is_lossless"] = self.is_lossless
        return result


def _text(value: Any) -> str:
    """Return a trimmed text representation for scalar frontmatter fields."""
    return "" if value is None else str(value).strip()


def _normalized_timestamp(value: Any) -> str:
    """Normalize valid timestamps to an aware UTC ISO-8601 representation."""
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _text(value)
        if not text:
            return ""
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _normalized_body(entry: dict[str, Any]) -> str:
    """Remove only the reversible wrapper added by ``map_okf``.

    Description text and administrative source/resource footer lines are
    already represented in frontmatter. Unknown supporting data remains in the
    body and therefore still triggers a fidelity difference.
    """
    raw_body = entry.get("body")
    body = raw_body if isinstance(raw_body, str) else _text(raw_body)
    marker = "\n\n---\n[Supporting data]\n"
    if marker not in body:
        return body

    content, footer = body.rsplit(marker, 1)
    resource = _text(entry.get("resource"))
    source_line = next(
        (line for line in footer.splitlines() if line.startswith("- OKF source:")),
        None,
    )
    resource_line = f"- OKF resource: {resource}" if resource else None
    exporter_wrapper = bool(source_line) and (
        resource_line is None or resource_line in footer.splitlines()
    )
    if not exporter_wrapper:
        return body

    administrative = ("- OKF source:", "- OKF resource:", "- Links:")
    meaningful: list[str] = []
    previous_was_administrative = False
    for line in footer.splitlines():
        if line.startswith(administrative):
            previous_was_administrative = True
            continue
        if line == "..." and previous_was_administrative:
            continue
        previous_was_administrative = False
        meaningful.append(line)
    if meaningful:
        return content.rstrip() + marker + "\n".join(meaningful)
    return content.rstrip()


def _portable(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalize fields that should survive an OKF portability round trip."""
    x_memanto = {
        key: value
        for key, value in (entry.get("x_memanto") or {}).items()
        if key not in {"id", "status", "type"}
    }
    return {
        "type": _text(entry.get("type")),
        "title": _text(entry.get("title")),
        "description": _text(entry.get("description")),
        "resource": _text(entry.get("resource")),
        "links": sorted({_text(link) for link in entry.get("links") or [] if link}),
        "tags": sorted({_text(tag) for tag in entry.get("tags") or [] if tag}),
        "timestamp": _normalized_timestamp(entry.get("timestamp")),
        "body": _normalized_body(entry),
        "x_memanto": x_memanto,
        "extra": entry.get("extra") or {},
    }


def _identity(entry: dict[str, Any]) -> str:
    """Prefer portable origin IDs, then semantics, then runtime IDs."""
    x_memanto = entry.get("x_memanto") or {}
    title = _text(entry.get("title"))
    resource = _text(entry.get("resource"))
    if title:
        semantic_key = {
            "type": _text(entry.get("type")).casefold(),
            "title": title.casefold(),
        }
        encoded = json.dumps(semantic_key, ensure_ascii=False, sort_keys=True).encode(
            "utf-8"
        )
        semantic = hashlib.sha256(encoded).hexdigest()[:16]
        if resource:
            return f"resource:{resource}|semantic:{semantic}"
        return f"semantic:{semantic}"

    if resource:
        return f"resource:{resource}"

    if x_memanto.get("id"):
        return f"id:{x_memanto['id']}"
    return f"path:{_text(entry.get('source_path'))}"


def _index(
    entries: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Index unique entries and report ambiguous duplicate identities."""
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for entry in entries:
        key = _identity(entry)
        if key in indexed:
            duplicates.add(key)
        else:
            indexed[key] = entry
    return indexed, sorted(duplicates)


def _label(entry: dict[str, Any], identity: str) -> str:
    """Build a stable human-readable record label."""
    title = _text(entry.get("title")) or "Untitled"
    return f"{title} ({identity})"


def _provenance_gaps(entries: list[dict[str, Any]]) -> list[str]:
    """Report every entry that lacks both origin and provenance metadata."""
    gaps: list[str] = []
    for entry in entries:
        identity = _identity(entry)
        x_memanto = entry.get("x_memanto") or {}
        has_origin = bool(
            entry.get("resource")
            or x_memanto.get("source")
            or x_memanto.get("provenance")
        )
        if not has_origin:
            gaps.append(_label(entry, identity))
    return sorted(gaps)


def compare_bundles(source: str | Path, target: str | Path) -> AuditReport:
    """Compare two OKF bundle paths without modifying either one."""
    source_entries = load_okf_bundle(source)["memories"]
    target_entries = load_okf_bundle(target)["memories"]
    source_index, source_duplicates = _index(source_entries)
    target_index, target_duplicates = _index(target_entries)

    source_keys = set(source_index)
    target_keys = set(target_index)
    report = AuditReport(
        source_count=len(source_entries),
        target_count=len(target_entries),
        source_duplicates=source_duplicates,
        target_duplicates=target_duplicates,
        source_provenance_gaps=_provenance_gaps(source_entries),
        target_provenance_gaps=_provenance_gaps(target_entries),
    )

    report.removed = [
        _label(source_index[key], key) for key in sorted(source_keys - target_keys)
    ]
    report.added = [
        _label(target_index[key], key) for key in sorted(target_keys - source_keys)
    ]

    for key in sorted(source_keys & target_keys):
        before = source_index[key]
        after = target_index[key]
        before_portable = _portable(before)
        after_portable = _portable(after)
        description = before_portable["description"]
        prefixed_body = f"{description}\n\n{before_portable['body']}"
        if (
            description
            and description not in before_portable["body"]
            and after_portable["body"] == prefixed_body
        ):
            # ``map_okf`` prepends a missing description to memory content.
            # Accept only that exact, source-derived transformation; a native
            # body that already begins with its description stays untouched.
            after_portable["body"] = before_portable["body"]
        fields = tuple(
            name
            for name in before_portable
            if before_portable[name] != after_portable[name]
        )
        if fields:
            report.changed.append(
                Change(
                    identity=key,
                    title=_text(before.get("title")) or "Untitled",
                    fields=fields,
                )
            )
        else:
            report.unchanged += 1

        before_path = _text(before.get("source_path")).replace("\\", "/")
        after_path = _text(after.get("source_path")).replace("\\", "/")
        if before_path != after_path:
            report.moved.append(f"{_label(before, key)}: {before_path} -> {after_path}")

    return report


def render_markdown(report: AuditReport) -> str:
    """Render a stable, human-reviewable Markdown report."""
    verdict = "PASS - portable fields preserved" if report.is_lossless else "FAIL"
    lines = [
        "# OKF portability audit",
        "",
        f"**Verdict:** {verdict}",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Source nodes | {report.source_count} |",
        f"| Target nodes | {report.target_count} |",
        f"| Unchanged | {report.unchanged} |",
        f"| Changed | {len(report.changed)} |",
        f"| Added | {len(report.added)} |",
        f"| Removed | {len(report.removed)} |",
        f"| Moved | {len(report.moved)} |",
        "",
    ]

    sections: list[tuple[str, list[str]]] = [
        (
            "Changed fields",
            [
                f"{change.title} ({change.identity}): " + ", ".join(change.fields)
                for change in report.changed
            ],
        ),
        ("Removed nodes", report.removed),
        ("Added nodes", report.added),
        ("Moved files", report.moved),
        ("Duplicate source identities", report.source_duplicates),
        ("Duplicate target identities", report.target_duplicates),
        ("Source provenance gaps", report.source_provenance_gaps),
        ("Target provenance gaps", report.target_provenance_gaps),
    ]
    for heading, items in sections:
        lines.extend([f"## {heading}", ""])
        lines.extend([f"- {item}" for item in items] or ["- None"])
        lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    """Construct the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Audit fidelity between two OKF bundle directories."
    )
    parser.add_argument("source", type=Path, help="Original OKF bundle")
    parser.add_argument("target", type=Path, help="Migrated OKF bundle")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Report format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the report to this path instead of stdout",
    )
    parser.add_argument(
        "--fail-on-change",
        action="store_true",
        help="Exit 1 when nodes or portable fields were lost or changed",
    )
    return parser


def validate_report_output(source: Path, target: Path, output: Path) -> None:
    """Reject report paths that could modify either audited input bundle."""
    resolved_output = output.resolve()
    for candidate in (source, target):
        resolved_input = candidate.resolve()
        if resolved_output == resolved_input:
            raise ValueError(f"Report output overlaps audited input: {output}")
        if resolved_input.is_dir() and resolved_output.is_relative_to(resolved_input):
            raise ValueError(f"Report output is inside audited bundle: {output}")


def write_report(output: Path, content: str) -> None:
    """Atomically replace the report entry without following an existing hard link."""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, output)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    """Run the audit CLI and return its process exit code."""
    args = _build_parser().parse_args(argv)
    if args.output:
        validate_report_output(args.source, args.target, args.output)
    report = compare_bundles(args.source, args.target)
    if args.format == "json":
        output = json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"
    else:
        output = render_markdown(report)

    if args.output:
        write_report(args.output, output)
    else:
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
        print(output, end="")
    return 1 if args.fail_on_change and not report.is_lossless else 0


if __name__ == "__main__":
    raise SystemExit(main())
