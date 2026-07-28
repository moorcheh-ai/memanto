#!/usr/bin/env python3
"""Create a de-identified, real-data sample from an Antigravity brain archive."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

from migrate_antigravity import (
    attachment_manifest,
    discover_artifacts,
    sanitize_artifact,
    source_provenance,
    stable_session_alias,
)

SAMPLE_SENTINEL = ".antigravity-public-sample-v1"


def _prepare_output(output: Path, force: bool) -> None:
    if output.exists():
        sentinel = output / SAMPLE_SENTINEL
        if not force:
            raise FileExistsError(f"Output already exists (use --force): {output}")
        if not sentinel.is_file():
            raise ValueError(
                f"Refusing to replace a directory not created by this tool: {output}"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / SAMPLE_SENTINEL).write_text("1\n", encoding="utf-8")


def prepare_sample(
    source: Path,
    output: Path,
    *,
    conversation: str,
    custom_redactions: dict[str, str] | None = None,
    force: bool = False,
) -> dict[str, object]:
    """Write sanitized canonical artifacts and privacy-safe provenance only."""
    source_root = source.expanduser().resolve()
    artifacts = discover_artifacts(source_root, conversation)
    _prepare_output(output, force)

    counts: Counter[str] = Counter()
    aliases: set[str] = set()
    written = 0
    for artifact in artifacts:
        clean, redactions = sanitize_artifact(artifact, custom_redactions)
        counts.update(redactions)
        aliases.add(clean.session_id)
        destination = output.joinpath(*clean.relative_path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(clean.content)
        written += 1
        if clean.metadata is not None and clean.metadata_name is not None:
            (destination.parent / clean.metadata_name).write_bytes(clean.metadata)
            written += 1

    provenance = source_provenance(source_root, [conversation])
    for row in provenance:
        row["session_id"] = stable_session_alias(str(row["session_id"]))
        row["filename"] = f"{row['session_id']}.pb"
    attachments = attachment_manifest(source_root, [conversation])
    for row in attachments:
        row["session_id"] = stable_session_alias(str(row["session_id"]))

    report: dict[str, object] = {
        "source": "real Google Antigravity desktop brain archive",
        "sessions": len(aliases),
        "canonical_artifacts": len(artifacts),
        "files_written": written,
        "redactions": dict(sorted(counts.items())),
        "raw_conversation_contents_published": False,
        "opaque_conversation_provenance": provenance,
        "attachment_provenance": attachments,
    }
    (output / "source-provenance.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _load_redactions(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError("Redactions file must be a JSON object of string replacements")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to ~/.gemini/antigravity")
    parser.add_argument("output", type=Path)
    parser.add_argument("--conversation", required=True)
    parser.add_argument("--redactions", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = prepare_sample(
        args.source,
        args.output,
        conversation=args.conversation,
        custom_redactions=_load_redactions(args.redactions),
        force=args.force,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
