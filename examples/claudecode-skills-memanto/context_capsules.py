#!/usr/bin/env python3
"""Memanto context capsules for Claude Code-style developer skills.

This example keeps the review path credential-free while showing where Memanto
fits in a real skill lifecycle:

1. capture useful decisions from skill transcripts;
2. redact secrets before persistence;
3. retrieve project/file relevant memories before the next skill starts;
4. optionally mirror the same capsules to the active `memanto` CLI session.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

MEMORY_TYPES = {
    "decision": "decision",
    "preference": "preference",
    "constraint": "instruction",
    "gotcha": "observation",
    "bugfix": "learning",
    "context": "context",
}

MARKER_RE = re.compile(
    r"^\s*(decision|preference|constraint|gotcha|bugfix|context)\s*:\s*(.+)$",
    re.IGNORECASE,
)

KEY_VALUE_SECRET_RE = re.compile(
    r"\b([A-Z0-9_.-]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_.-]*)"
    r"\s*[:=]\s*(['\"]?)([A-Za-z0-9_/+=:-]{8,})(['\"]?)([.,;)]?)",
    re.IGNORECASE,
)

SECRET_PATTERNS = [
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_./+=:-]{12,}"), "Bearer <redacted>"),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
            r"-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "<redacted private key>",
    ),
]


@dataclass(frozen=True)
class Capsule:
    """A durable engineering memory distilled from a skill run."""

    kind: str
    content: str
    project: str
    files: list[str]
    source_skill: str
    session_id: str
    tags: list[str]
    confidence: float
    created_at: str
    redactions: int = 0

    def to_memanto_memory(self) -> dict[str, object]:
        """Return the JSON shape accepted by `memanto remember --batch`."""

        title = f"{self.kind}: {self.content[:72]}"
        return {
            "type": MEMORY_TYPES.get(self.kind, "context"),
            "title": title,
            "content": self.content,
            "confidence": self.confidence,
            "tags": self.tags,
            "source": self.source_skill,
            "provenance": "claudecode_skills_context_capsule",
        }


class SecretRedactor:
    """Small deterministic redactor for reviewer-safe local persistence."""

    def redact(self, text: str) -> tuple[str, int]:
        redactions = 0
        output, count = KEY_VALUE_SECRET_RE.subn(
            lambda match: f"{match.group(1)}=<redacted>{match.group(5)}",
            text,
        )
        redactions += count
        for pattern, replacement in SECRET_PATTERNS:
            output, count = pattern.subn(replacement, output)
            redactions += count
        return output, redactions


class CapsuleExtractor:
    """Extract typed capsules from explicit skill transcript markers."""

    def __init__(self, redactor: SecretRedactor | None = None) -> None:
        self.redactor = redactor or SecretRedactor()

    def extract(
        self,
        transcript: str,
        *,
        project: str,
        files: list[str],
        source_skill: str,
        session_id: str,
    ) -> list[Capsule]:
        capsules: list[Capsule] = []
        now = datetime.now(UTC).isoformat(timespec="seconds")

        for raw_line in transcript.splitlines():
            match = MARKER_RE.match(raw_line)
            if not match:
                continue

            kind = match.group(1).lower()
            content, redactions = self.redactor.redact(match.group(2).strip())
            if not content:
                continue

            tags = sorted(
                {
                    "claude-code",
                    "developer-skill",
                    kind,
                    *infer_tags(content),
                    *file_tags(files),
                }
            )
            confidence = 0.9 if kind in {"decision", "constraint"} else 0.82
            capsules.append(
                Capsule(
                    kind=kind,
                    content=content,
                    project=project,
                    files=files,
                    source_skill=source_skill,
                    session_id=session_id,
                    tags=tags,
                    confidence=confidence,
                    created_at=now,
                    redactions=redactions,
                )
            )

        return dedupe_capsules(capsules)


class LocalCapsuleStore:
    """Append-only JSONL store used for deterministic tests and demos."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append_many(self, capsules: Iterable[Capsule]) -> int:
        rows = list(capsules)
        if not rows:
            return 0

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            for capsule in rows:
                file.write(json.dumps(asdict(capsule), ensure_ascii=False) + "\n")
        return len(rows)

    def load(self) -> list[Capsule]:
        if not self.path.exists():
            return []

        capsules: list[Capsule] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            capsules.append(Capsule(**json.loads(line)))
        return capsules

    def recall(
        self,
        *,
        project: str,
        task: str,
        files: list[str],
        limit: int,
    ) -> list[tuple[float, Capsule]]:
        scored = [
            (score_capsule(capsule, project=project, task=task, files=files), capsule)
            for capsule in self.load()
        ]
        return [(score, capsule) for score, capsule in sorted(scored, reverse=True)[:limit] if score > 0]


class MemantoCliMirror:
    """Optional live adapter that reuses the contributor's active Memanto CLI."""

    def sync(self, capsules: list[Capsule]) -> None:
        if not capsules:
            return

        payload = [capsule.to_memanto_memory() for capsule in capsules]
        temp_path = Path(".memanto-capsules-batch.json")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            subprocess.run(
                ["memanto", "remember", "--batch", str(temp_path)],
                check=True,
                text=True,
            )
        finally:
            temp_path.unlink(missing_ok=True)


def infer_tags(text: str) -> set[str]:
    lowered = text.lower()
    tags: set[str] = set()
    for token in [
        "auth",
        "billing",
        "cache",
        "database",
        "migration",
        "stripe",
        "test",
        "webhook",
    ]:
        if token in lowered:
            tags.add(token)
    return tags


def file_tags(files: list[str]) -> set[str]:
    tags: set[str] = set()
    for file in files:
        suffix = Path(file).suffix.lower().lstrip(".")
        if suffix:
            tags.add(suffix)
        if "test" in Path(file).name.lower():
            tags.add("test")
    return tags


def dedupe_capsules(capsules: list[Capsule]) -> list[Capsule]:
    seen: set[tuple[str, str]] = set()
    unique: list[Capsule] = []
    for capsule in capsules:
        key = (capsule.kind, capsule.content.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(capsule)
    return unique


def tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]{3,}", text.lower())}


def score_capsule(
    capsule: Capsule,
    *,
    project: str,
    task: str,
    files: list[str],
) -> float:
    score = 0.0
    if capsule.project == project:
        score += 2.0

    requested_files = {normalize_path(file) for file in files}
    capsule_files = {normalize_path(file) for file in capsule.files}
    if requested_files & capsule_files:
        score += 4.0

    query_terms = tokenize(task + " " + " ".join(files))
    capsule_terms = tokenize(
        capsule.content + " " + " ".join(capsule.tags) + " " + " ".join(capsule.files)
    )
    score += min(len(query_terms & capsule_terms), 8) * 0.75

    if capsule.kind in {"decision", "constraint"}:
        score += 0.5

    return score


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().lower()


def parse_files(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def format_context_block(matches: list[tuple[float, Capsule]]) -> str:
    if not matches:
        return "MEMANTO_CONTEXT: no relevant prior engineering memories found."

    lines = ["MEMANTO_CONTEXT:"]
    for score, capsule in matches:
        files = ", ".join(capsule.files) if capsule.files else "project-wide"
        lines.append(
            f"- [{capsule.kind} score={score:.2f} files={files}] {capsule.content}"
        )
    return "\n".join(lines)


def cmd_capture(args: argparse.Namespace) -> int:
    transcript = args.summary
    if args.transcript_file:
        transcript += "\n" + Path(args.transcript_file).read_text(encoding="utf-8")

    files = parse_files(args.files)
    capsules = CapsuleExtractor().extract(
        transcript,
        project=args.project,
        files=files,
        source_skill=args.skill,
        session_id=args.session,
    )
    count = LocalCapsuleStore(Path(args.store)).append_many(capsules)
    if args.sync_memanto:
        MemantoCliMirror().sync(capsules)

    print(f"stored {count} context capsule(s)")
    for capsule in capsules:
        redacted = " redacted" if capsule.redactions else ""
        print(f"- {capsule.kind}:{redacted} {capsule.content}")
    return 0


def cmd_recall(args: argparse.Namespace) -> int:
    matches = LocalCapsuleStore(Path(args.store)).recall(
        project=args.project,
        task=args.task,
        files=parse_files(args.files),
        limit=args.limit,
    )
    print(format_context_block(matches))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture and recall Memanto context capsules for developer skills."
    )
    parser.set_defaults(func=lambda _: parser.print_help())
    subparsers = parser.add_subparsers()

    capture = subparsers.add_parser("capture", help="store capsules from a skill run")
    capture.add_argument("--skill", required=True)
    capture.add_argument("--project", required=True)
    capture.add_argument("--session", default="local-demo")
    capture.add_argument("--files", default="")
    capture.add_argument("--summary", default="")
    capture.add_argument("--transcript-file")
    capture.add_argument("--store", default=".memanto/context-capsules.jsonl")
    capture.add_argument("--sync-memanto", action="store_true")
    capture.set_defaults(func=cmd_capture)

    recall = subparsers.add_parser("recall", help="emit context for a new skill run")
    recall.add_argument("--project", required=True)
    recall.add_argument("--task", required=True)
    recall.add_argument("--files", default="")
    recall.add_argument("--limit", type=int, default=5)
    recall.add_argument("--store", default=".memanto/context-capsules.jsonl")
    recall.set_defaults(func=cmd_recall)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = args.func(args)
    return 0 if result is None else result


if __name__ == "__main__":
    sys.exit(main())
